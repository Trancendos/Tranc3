"""
Infinity Auth — OAuth2/SSO Authentication Worker
===================================================
Self-hosted replacement for Cloudflare infinity-auth-api worker.
Provides OAuth2 authentication, JWT tokens, and session management.

Phase 22.5: Updated with Infinity Portal integration:
- Tier-aware JWT claims (role, tier, infinity_role)
- Role-based user classification for Infinity Gate routing
- Extended TokenResponse with role and tier information
- Sentinel Station event publishing for auth events
- Dimensional Service integration for infinity_auth

Features:
- OAuth2 authorization code flow
- JWT token issuance and validation with tier/role claims
- Refresh token rotation
- Session management
- TOTP multi-factor authentication
- User registration and login
- Password hashing (argon2)
- Rate limiting on auth endpoints

Zero-cost: FastAPI + SQLite + python-jose. No CF Workers or KV.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid

import bcrypt  # type: ignore[import-untyped]
from src.database.encrypted_sqlite import connect as sqlite3_connect, encrypt_field
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pyotp
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

# Phase 22.5: Infinity Ecosystem nomenclature
from shared_core.infinity.nomenclature import InfinityRole, Tier

# Phase 22.6: Smart Adaptive Intelligence
from shared_core.infinity.worker_integration import InfinityWorkerKit
from shared_core.sanitize import sanitize_for_log
from src.entities.health_metadata import health_entity_block

logger = logging.getLogger("tranc3.workers.infinity-auth")

# ── Configuration ──────────────────────────────────────────────────────────────

_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. Infinity (auth service) cannot start without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"',
    )
JWT_SECRET: str = _jwt_secret_raw
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "60"))
REFRESH_EXPIRY_DAYS = int(os.environ.get("REFRESH_EXPIRY_DAYS", "30"))
DATABASE_PATH = os.environ.get("AUTH_DATABASE_PATH", "/data/auth.db")
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))
AUTH_ISSUER = os.environ.get("AUTH_ISSUER", "https://auth.trancendos.com")
AUTH_BASE_URL = os.environ.get("AUTH_BASE_URL", "http://localhost:8005")

# ── Models ─────────────────────────────────────────────────────────────────────


class UserRegister(BaseModel):
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")  # Phase 22.5: role for Infinity Gate routing


class UserLogin(BaseModel):
    username: str
    password: str
    totp_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    username: str
    # Phase 22.5: Tier-aware claims
    role: str = "user"
    tier: int = 0
    infinity_role: str = "user"


class RefreshRequest(BaseModel):
    refresh_token: str


class TOTPSetupResponse(BaseModel):
    secret: str
    qr_code_url: str
    backup_codes: list[str]


class UserProfile(BaseModel):
    user_id: str
    username: str
    email: str
    display_name: str
    mfa_enabled: bool
    created_at: str
    last_login: str | None = None
    # Phase 22.5: Extended profile
    role: str = "user"
    tier: int = 0
    infinity_role: str = "user"


# ── Role/Tier Mapping ──────────────────────────────────────────────────────────
# Maps user roles to Tier and InfinityRole for JWT claims.
# This aligns with the Infinity Gate routing in the Portal service.

ROLE_TIER_MAP: dict[str, Tier] = {
    "admin": Tier.HUMAN,
    "user": Tier.HUMAN,
    "developer": Tier.HUMAN,
    "devops": Tier.HUMAN,
    "prime": Tier.PRIME,
    "ai": Tier.AI,
    "agent": Tier.AGENT,
    "bot": Tier.BOT,
    "service": Tier.BOT,
}

ROLE_INFINITY_ROLE_MAP: dict[str, InfinityRole] = {
    "admin": InfinityRole.ADMIN,
    "user": InfinityRole.USER,
    "developer": InfinityRole.USER,
    "devops": InfinityRole.USER,
    "prime": InfinityRole.PRIME,
    "ai": InfinityRole.AI,
    "agent": InfinityRole.AGENT,
    "bot": InfinityRole.BOT,
    "service": InfinityRole.SERVICE,
}


def _get_tier_for_role(role: str) -> Tier:
    """Get the Tier for a given role string."""
    return ROLE_TIER_MAP.get(role.lower().strip(), Tier.HUMAN)


def _get_infinity_role_for_role(role: str) -> InfinityRole:
    """Get the InfinityRole for a given role string."""
    return ROLE_INFINITY_ROLE_MAP.get(role.lower().strip(), InfinityRole.USER)


# ── Database ────────────────────────────────────────────────────────────────────


class AuthDatabase:
    """SQLite database for auth persistence. Replaces CF D1."""

    def __init__(self, db_path: str = DATABASE_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3_connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                mfa_enabled INTEGER DEFAULT 0,
                totp_secret TEXT,
                backup_codes TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER DEFAULT 1,
                role TEXT DEFAULT 'user'
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                refresh_token TEXT NOT NULL,
                refresh_token_hash TEXT UNIQUE NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_revoked INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                window_start TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS token_revocations (
                jti TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                revoked_at TEXT NOT NULL,
                expires_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_refresh ON sessions(refresh_token_hash);
            CREATE INDEX IF NOT EXISTS idx_revocations_user ON token_revocations(user_id);
        """)
        # Migration: add refresh_token_hash if upgrading from older schema
        try:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN refresh_token_hash TEXT UNIQUE DEFAULT ''")
        except Exception:
            pass  # column already exists
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()

    def token_hash(self, token: str) -> str:
        """HMAC-SHA256 of a token for deterministic indexed lookup."""
        from src.database.encrypted_sqlite import _derive_key
        key = _derive_key(self.db_path)
        return hmac.new(key, token.encode(), hashlib.sha256).hexdigest()


# ── Password Hashing ───────────────────────────────────────────────────────────

try:
    _BCRYPT_ROUNDS = int(os.environ.get("BCRYPT_ROUNDS", "12"))
except ValueError:
    _BCRYPT_ROUNDS = 12
_BCRYPT_ROUNDS = max(12, _BCRYPT_ROUNDS)  # never allow rounds < 12


def _is_bcrypt_hash(stored_hash: str) -> bool:
    """Return True if *stored_hash* is a bcrypt hash (``$2a/b/x/y$`` prefix)."""
    return stored_hash.startswith("$2") and len(stored_hash) > 30


def hash_password(password: str) -> str:
    """Hash a password using bcrypt (work factor controlled by BCRYPT_ROUNDS env var)."""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)).decode()


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against a stored hash.

    Supports both bcrypt hashes (new) and legacy PBKDF2-SHA256 hashes
    (format ``salt:hexdigest``) so existing accounts keep working until
    their next login triggers a transparent rehash.
    """
    try:
        if _is_bcrypt_hash(stored_hash):
            return bcrypt.checkpw(password.encode(), stored_hash.encode())
        # Legacy PBKDF2-SHA256: "salt:hexdigest"
        salt, hash_val = stored_hash.split(":", 1)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        return hmac.compare_digest(hash_val, computed)
    except (ValueError, AttributeError):
        return False


def hash_backup_code(code: str) -> str:
    """Hash a backup code with HMAC-SHA256 using the site key.

    HMAC-SHA256 is site-specific so leaked hashes cannot be reversed via rainbow
    tables, yet fast enough for one-time-use codes where bcrypt is overkill.
    """
    return hmac.new(JWT_SECRET.encode(), code.upper().encode(), hashlib.sha256).hexdigest()


# ── JWT Token Management ───────────────────────────────────────────────────────


def create_access_token(
    user_id: str,
    username: str,
    role: str = "user",
    extra_claims: dict | None = None,
) -> str:
    """Create a JWT access token with tier-aware claims.

    Phase 22.5: Includes role, tier, and infinity_role in the JWT payload
    so that downstream services (Infinity Portal, Infinity Gate) can make
    routing and access decisions without additional lookups.
    """
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)

    claims = {
        "sub": user_id,
        "username": username,
        "role": role,
        "tier": tier.value,
        "infinity_role": infinity_role.value,
        "exp": int(time.time()) + JWT_EXPIRY_MINUTES * 60,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        **(extra_claims or {}),
    }

    try:
        from jose import jwt

        return jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM)
    except ImportError:
        # Fallback: simple base64-encoded token (for development)
        import base64

        return base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()


def create_refresh_token() -> str:
    """Create a cryptographically secure refresh token."""
    return secrets.token_urlsafe(64)


def decode_access_token(token: str) -> dict[str, Any] | None:
    """Decode and validate a JWT access token."""
    try:
        from jose import JWTError, jwt

        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            return payload
        except JWTError:
            return None
    except ImportError:
        # Fallback: decode base64 token
        try:
            import base64

            payload = json.loads(base64.urlsafe_b64decode(token + "=="))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            return None


# ── Rate Limiting ──────────────────────────────────────────────────────────────


class RateLimiter:
    """In-memory rate limiter. Replaces CF KV rate limiting."""

    def __init__(self, max_requests: int = RATE_LIMIT_PER_MINUTE, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """Check if a request is allowed within the rate limit."""
        now = time.monotonic()
        window_start = now - self.window_seconds

        # Clean old entries
        if key in self._requests:
            self._requests[key] = [t for t in self._requests[key] if t > window_start]
        else:
            self._requests[key] = []

        if len(self._requests[key]) >= self.max_requests:
            return False

        self._requests[key].append(now)
        return True


# ── FastAPI Application ────────────────────────────────────────────────────────


@asynccontextmanager
async def _lifespan(app: FastAPI):
    await worker_kit.startup(app)
    worker_kit.health.register_daemon("auth_health_reporter", baseline_interval=60.0)
    logger.info("Infinity-Auth smart adaptive layer started")

    async def _bg_loop():
        while True:
            try:
                await asyncio.sleep(30)
                if worker_kit.health.should_fire("auth_health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    if hasattr(summary, "to_dict"):
                        summary = summary.to_dict()
                    worker_kit.health.update_health(summary.get("health_score", 1.0))
                    worker_kit.health.record_fire("auth_health_reporter")
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("auth background health reporter error")

    async def _revocation_cleanup_loop():
        """Purge expired revocation records hourly to keep the table lean."""
        while True:
            try:
                await asyncio.sleep(3600)
                deleted = db.execute(
                    "DELETE FROM token_revocations WHERE expires_at < ?",
                    (datetime.now(timezone.utc).isoformat(),),
                ).rowcount
                db.commit()
                if deleted:
                    logger.info("Revocation cleanup: purged %d expired entries", deleted)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("revocation cleanup error")

    task = asyncio.create_task(_bg_loop())
    cleanup_task = asyncio.create_task(_revocation_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        cleanup_task.cancel()
        for t in (task, cleanup_task):
            try:
                await t
            except asyncio.CancelledError:
                pass
        await worker_kit.shutdown()
        logger.info("Infinity-Auth smart adaptive layer stopped")


app = FastAPI(
    title="Infinity Auth — OAuth2/SSO API",
    description="Self-hosted authentication for Trancendos with tier-aware JWT claims",
    version="2.0.0",
    lifespan=_lifespan,
)

_cors_origins_raw = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]
# Wildcard origin is incompatible with allow_credentials=True (Starlette raises ValueError)
_cors_allow_credentials = "*" not in _cors_origins_raw
_cors_origins = _cors_origins_raw if _cors_allow_credentials else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=_cors_allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = AuthDatabase()
rate_limiter = RateLimiter()
security = HTTPBearer()


@contextmanager
def _get_db():
    """Context manager returning the module-level AuthDatabase singleton."""
    yield db


# Phase 22.6: Smart adaptive worker kit for auth service
worker_kit = InfinityWorkerKit(
    "infinity-auth",
    defense_threshold=5,  # Strict: auth service is high-value target
    defense_window_seconds=120,  # 2-minute violation window
    defense_block_seconds=3600,  # 1-hour block for auth violations
)


# ── Dependencies ────────────────────────────────────────────────────────────────


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict[str, Any]:
    """Validate JWT token and return user payload.

    Checks the token_revocations table so that logged-out tokens are
    immediately rejected even before their exp claim elapses.
    """
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    jti = payload.get("jti")
    if jti:
        revoked = db.execute(
            "SELECT 1 FROM token_revocations WHERE jti = ?", (jti,)
        ).fetchone()
        if revoked:
            raise HTTPException(status_code=401, detail="Token has been revoked")
    return payload


async def rate_limit_check(request: Request) -> None:
    """Rate limit middleware for auth endpoints."""
    client_ip = request.client.host if request.client else "unknown"
    if not rate_limiter.is_allowed(f"auth:{client_ip}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


# ── Endpoints ───────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    """Health check endpoint."""
    health_summary_obj = worker_kit.health.get_health_summary()
    health_summary = (
        health_summary_obj.to_dict()
        if hasattr(health_summary_obj, "to_dict")
        else health_summary_obj
    )
    return {
        "status": "healthy",
        "service": "infinity-auth",
        "version": "2.0.0",
        "health_score": health_summary.get("health_score", 1.0),
        "health_tier": health_summary.get("tier", "EXCELLENT"),
        "smart_adaptive": True,
        "defense_blocked_ips": len(worker_kit.defense.get_blocked_ips()),
        "entity": health_entity_block(8005, "infinity-auth"),
    }


@app.post("/auth/register", response_model=TokenResponse)
async def register(user: UserRegister, _=Depends(rate_limit_check)):
    """Register a new user account.

    Phase 22.5: Includes role in JWT claims for Infinity Gate routing.
    """
    # Check if username exists
    existing = db.execute(
        "SELECT user_id FROM users WHERE username = ?",
        (user.username,),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Username already exists")

    # Check if email exists
    existing = db.execute("SELECT user_id FROM users WHERE email = ?", (user.email,)).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")

    # Create user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(user.password)
    now = datetime.now(timezone.utc).isoformat()

    role = user.role.lower().strip()

    db.execute(
        "INSERT INTO users (user_id, username, email, password_hash, display_name, created_at, role) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, user.username, user.email, password_hash,
         encrypt_field(db.db_path, user.display_name), now, role),
    )
    db.commit()

    # Create tokens with tier-aware claims
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)
    access_token = create_access_token(user_id, user.username, role=role)
    refresh_token = create_refresh_token()

    # Store session (refresh token encrypted at rest)
    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)).isoformat()
    db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, refresh_token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, encrypt_field(db.db_path, refresh_token), db.token_hash(refresh_token), now, expires_at),
    )
    db.commit()

    logger.info(
        "user_registered: username=%s role=%s",
        sanitize_for_log(user.username),
        role,
    )  # codeql[py/cleartext-logging]

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=JWT_EXPIRY_MINUTES * 60,
        user_id=user_id,
        username=user.username,
        role=role,
        tier=tier.value,
        infinity_role=infinity_role.value,
    )


@app.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, _=Depends(rate_limit_check)):
    """Authenticate a user and issue tokens.

    Phase 22.5: Includes role/tier/infinity_role in JWT claims.
    """
    # Find user
    row = db.execute(
        "SELECT user_id, username, password_hash, mfa_enabled, totp_secret, backup_codes, role"
        " FROM users WHERE username = ? AND is_active = 1",
        (credentials.username,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    if not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Transparently rehash legacy PBKDF2 hashes to bcrypt on successful login
    if not _is_bcrypt_hash(row["password_hash"]):
        try:
            new_hash = hash_password(credentials.password)
            db.execute(
                "UPDATE users SET password_hash = ? WHERE user_id = ?",
                (new_hash, row["user_id"]),
            )
            db.commit()
        except Exception:
            logger.exception("Password rehash failed for user=%s", row["user_id"])

    # Check MFA
    if row["mfa_enabled"]:
        if not credentials.totp_code:
            raise HTTPException(status_code=403, detail="MFA code required")
        totp_secret = row["totp_secret"]
        if not totp_secret:
            raise HTTPException(status_code=500, detail="MFA misconfigured — contact support")
        code = credentials.totp_code.strip()
        if code.isdigit() and len(code) == 6:
            # Standard TOTP path — ±30s clock drift tolerance
            try:
                valid = pyotp.TOTP(totp_secret).verify(code, valid_window=1)
            except Exception:
                raise HTTPException(status_code=403, detail="Invalid MFA code") from None
            if not valid:
                raise HTTPException(status_code=403, detail="Invalid MFA code")
        else:
            # Backup code recovery path — compare HMAC hashes, constant-time, one-time use
            stored_hashes: list[str] = json.loads(row["backup_codes"] or "[]")
            incoming_hash = hash_backup_code(code)
            matched_idx = next(
                (i for i, h in enumerate(stored_hashes) if hmac.compare_digest(h, incoming_hash)),
                None,
            )
            if matched_idx is None:
                raise HTTPException(status_code=403, detail="Invalid MFA code")
            # Consume the hash so the code cannot be reused
            remaining = stored_hashes[:matched_idx] + stored_hashes[matched_idx + 1 :]
            db.execute(
                "UPDATE users SET backup_codes = ? WHERE user_id = ?",
                (json.dumps(remaining), row["user_id"]),
            )
            db.commit()

    # Get role for JWT claims
    user_id = row["user_id"]
    username = row["username"]
    role = row["role"] if "role" in row.keys() else "user"
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)

    # Create tokens with tier-aware claims
    access_token = create_access_token(user_id, username, role=role)
    refresh_token = create_refresh_token()

    # Store session (refresh token encrypted at rest)
    now = datetime.now(timezone.utc).isoformat()
    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)).isoformat()
    db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, refresh_token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (session_id, user_id, encrypt_field(db.db_path, refresh_token), db.token_hash(refresh_token), now, expires_at),
    )

    # Update last login
    db.execute("UPDATE users SET last_login = ? WHERE user_id = ?", (now, user_id))
    db.commit()

    logger.info(
        "user_login: username=%s role=%s",
        sanitize_for_log(credentials.username),
        role,
    )  # codeql[py/cleartext-logging]

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=JWT_EXPIRY_MINUTES * 60,
        user_id=user_id,
        username=username,
        role=role,
        tier=tier.value,
        infinity_role=infinity_role.value,
    )


@app.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, _=Depends(rate_limit_check)):
    """Refresh an access token using a valid refresh token."""
    # Find session
    row = db.execute(
        "SELECT session_id, user_id, expires_at, is_revoked FROM sessions WHERE refresh_token_hash = ?",
        (db.token_hash(request.refresh_token),),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if row["is_revoked"]:
        raise HTTPException(status_code=401, detail="Refresh token revoked")

    # Check expiry
    expires_at = datetime.fromisoformat(row["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        raise HTTPException(status_code=401, detail="Refresh token expired")

    # Get user with role
    user = db.execute(
        "SELECT username, role FROM users WHERE user_id = ?",
        (row["user_id"],),
    ).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    # Get role for JWT claims
    role = user["role"] if "role" in user.keys() else "user"
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)

    # Rotate refresh token (invalidate old, issue new)
    new_refresh_token = create_refresh_token()
    now = datetime.now(timezone.utc).isoformat()
    new_expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)).isoformat()

    # Revoke old session
    db.execute("UPDATE sessions SET is_revoked = 1 WHERE session_id = ?", (row["session_id"],))

    # Create new session
    new_session_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, refresh_token_hash, created_at, expires_at) VALUES (?, ?, ?, ?, ?, ?)",
        (new_session_id, row["user_id"], encrypt_field(db.db_path, new_refresh_token), db.token_hash(new_refresh_token), now, new_expires_at),
    )
    db.commit()

    # Issue new access token with tier-aware claims
    access_token = create_access_token(row["user_id"], user["username"], role=role)

    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        expires_in=JWT_EXPIRY_MINUTES * 60,
        user_id=row["user_id"],
        username=user["username"],
        role=role,
        tier=tier.value,
        infinity_role=infinity_role.value,
    )


@app.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Revoke all sessions and the current JWT for the user."""
    user_id = user["sub"]
    db.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (user_id,))
    jti = user.get("jti")
    if jti:
        exp = user.get("exp", int(time.time()) + JWT_EXPIRY_MINUTES * 60)
        db.execute(
            "INSERT OR IGNORE INTO token_revocations (jti, user_id, revoked_at, expires_at) VALUES (?, ?, ?, ?)",
            (
                jti,
                user_id,
                datetime.now(timezone.utc).isoformat(),
                datetime.fromtimestamp(exp, tz=timezone.utc).isoformat(),
            ),
        )
    db.commit()
    return {"message": "Logged out successfully"}


@app.get("/auth/me", response_model=UserProfile)
async def get_profile(user: dict = Depends(get_current_user)):
    """Get the current user's profile with tier information."""
    row = db.execute(
        "SELECT user_id, username, email, display_name, mfa_enabled, created_at, last_login, role FROM users WHERE user_id = ?",
        (user["sub"],),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    role = row["role"] if "role" in row.keys() else "user"
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)

    return UserProfile(
        user_id=row["user_id"],
        username=row["username"],
        email=row["email"],
        display_name=row["display_name"],
        mfa_enabled=bool(row["mfa_enabled"]),
        created_at=row["created_at"],
        last_login=row["last_login"],
        role=role,
        tier=tier.value,
        infinity_role=infinity_role.value,
    )


@app.post("/auth/mfa/setup", response_model=TOTPSetupResponse)
async def setup_mfa(user: dict = Depends(get_current_user)):
    """Set up TOTP multi-factor authentication."""
    # Generate TOTP secret (Base32 so any RFC 6238 authenticator can import it)
    totp_secret = pyotp.random_base32()
    plaintext_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    # Hash before storage — HMAC-SHA256 with site key; plaintext only shown to user once
    hashed_codes = [hash_backup_code(c) for c in plaintext_codes]

    # Store TOTP secret and hashed backup codes
    db.execute(
        "UPDATE users SET totp_secret = ?, backup_codes = ? WHERE user_id = ?",
        (totp_secret, json.dumps(hashed_codes), user["sub"]),
    )
    db.commit()

    # Build a standards-compliant otpauth:// provisioning URI
    username = user.get("username", "user")
    qr_url = pyotp.TOTP(totp_secret).provisioning_uri(name=username, issuer_name="Trancendos")

    return TOTPSetupResponse(
        secret=totp_secret,
        qr_code_url=qr_url,
        backup_codes=plaintext_codes,  # plaintext shown once; DB holds hashes
    )


@app.post("/auth/mfa/enable")
async def enable_mfa(user: dict = Depends(get_current_user)):
    """Enable MFA after setup is confirmed."""
    db.execute("UPDATE users SET mfa_enabled = 1 WHERE user_id = ?", (user["sub"],))
    db.commit()
    return {"message": "MFA enabled successfully"}


@app.post("/auth/mfa/disable")
async def disable_mfa(user: dict = Depends(get_current_user)):
    """Disable MFA for the current user."""
    db.execute(
        "UPDATE users SET mfa_enabled = 0, totp_secret = NULL WHERE user_id = ?",
        (user["sub"],),
    )
    db.commit()
    return {"message": "MFA disabled"}


@app.get("/auth/verify")
async def verify_token_endpoint(user: dict = Depends(get_current_user)):
    """Verify a token is valid (for other services to check).

    Phase 22.5: Returns role, tier, and infinity_role from JWT claims.
    """
    return {
        "valid": True,
        "user_id": user.get("sub"),
        "username": user.get("username"),
        "role": user.get("role", "user"),
        "tier": user.get("tier", 0),
        "infinity_role": user.get("infinity_role", "user"),
    }


# ── Role Management Endpoints (Phase 22.5) ─────────────────────────────────────


@app.put("/auth/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: str = Query(..., description="New role for the user"),
    current_user: dict = Depends(get_current_user),
):
    """Update a user's role (admin-only).

    This affects the tier and infinity_role in their JWT claims,
    which changes how the Infinity Gate routes them.
    """
    # Only admins can change roles
    current_role = current_user.get("role", "user")
    if current_role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can change user roles")

    # Verify target user exists
    target = db.execute(
        "SELECT user_id, username FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not target:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate role
    valid_roles = {"admin", "user", "developer", "devops", "prime", "ai", "agent", "bot", "service"}
    role = role.lower().strip()
    if role not in valid_roles:
        raise HTTPException(status_code=400, detail=f"Invalid role. Must be one of: {valid_roles}")

    # Update role
    db.execute(
        "UPDATE users SET role = ? WHERE user_id = ?",
        (role, user_id),
    )
    db.commit()

    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)

    logger.info(
        "role_updated: user_id=%s new_role=%s by=%s",
        user_id,
        role,
        sanitize_for_log(current_user.get("username", "unknown")),
    )

    return {
        "message": "Role updated",
        "user_id": user_id,
        "username": target["username"],
        "role": role,
        "tier": tier.value,
        "infinity_role": infinity_role.value,
    }


# ── Admin: revoke all tokens for a user ──────────────────────────────────────


@app.post("/auth/admin/revoke-user-tokens/{user_id}", tags=["admin"])
async def admin_revoke_user_tokens(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Immediately revoke all active tokens for a user (admin only)."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")

    # Verify target user exists
    user_row = db.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,)).fetchone()
    if not user_row:
        raise HTTPException(status_code=404, detail="User not found")

    # Revoke all active sessions — marks sessions table + purges via token_revocations
    sessions = db.execute(
        "SELECT session_id, expires_at FROM sessions WHERE user_id = ? AND is_revoked = 0",
        (user_id,),
    ).fetchall()

    now = datetime.now(timezone.utc).isoformat()
    # Also revoke any JTIs in the revocation table that belong to this user
    db.execute(
        "INSERT OR IGNORE INTO token_revocations (jti, user_id, revoked_at, expires_at) "
        "SELECT 'session:' || session_id, ?, ?, expires_at FROM sessions WHERE user_id = ? AND is_revoked = 0",
        (user_id, now, user_id),
    )
    db.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (user_id,))
    db.commit()

    logger.warning(
        "Admin revoked all tokens for user_id=%s by admin_user_id=%s",
        sanitize_for_log(user_id),
        sanitize_for_log(current_user.get("user_id", "unknown")),
    )
    return {"revoked": len(sessions), "user_id": user_id}


# ── OIDC Discovery (RFC 8414 / OpenID Connect Discovery 1.0) ────────────────


@app.get("/.well-known/openid-configuration", tags=["oidc"])
async def oidc_discovery():
    """OpenID Connect Discovery document — RFC 8414."""
    return {
        "issuer": AUTH_ISSUER,
        "authorization_endpoint": f"{AUTH_BASE_URL}/auth/authorize",
        "token_endpoint": f"{AUTH_BASE_URL}/auth/token",
        "userinfo_endpoint": f"{AUTH_BASE_URL}/auth/me",
        "jwks_uri": f"{AUTH_BASE_URL}/.well-known/jwks.json",
        "registration_endpoint": f"{AUTH_BASE_URL}/auth/register",
        "scopes_supported": ["openid", "profile", "email", "offline_access"],
        "response_types_supported": ["code", "token", "id_token"],
        "grant_types_supported": ["authorization_code", "refresh_token", "client_credentials"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["HS256", "RS256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post", "client_secret_basic"],
        "claims_supported": ["sub", "iss", "aud", "exp", "iat", "email", "username", "role"],
        "code_challenge_methods_supported": ["S256"],
    }


@app.get("/.well-known/jwks.json", tags=["oidc"])
async def jwks():
    """JSON Web Key Set — public keys for token verification."""
    # HS256: symmetric — expose a placeholder JWKS (no public key to share)
    # RS256: expose the public key JWK when JWT_PUBLIC_KEY is configured
    public_key_pem = os.environ.get("JWT_PUBLIC_KEY", "")
    if public_key_pem:
        try:
            import base64  # noqa: PLC0415

            from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey  # noqa: PLC0415
            from cryptography.hazmat.primitives.serialization import (
                load_pem_public_key,  # noqa: PLC0415
            )

            pub = load_pem_public_key(public_key_pem.encode())
            if isinstance(pub, RSAPublicKey):
                pub_numbers = (
                    pub.public_key().public_numbers()
                    if hasattr(pub, "public_key")
                    else pub.public_numbers()
                )

                def _b64url(n: int, length: int) -> str:
                    return base64.urlsafe_b64encode(n.to_bytes(length, "big")).rstrip(b"=").decode()

                return {
                    "keys": [
                        {
                            "kty": "RSA",
                            "use": "sig",
                            "alg": "RS256",
                            "n": _b64url(pub_numbers.n, 256),
                            "e": _b64url(pub_numbers.e, 3),
                        },
                    ],
                }
        except Exception as exc:
            logger.debug("JWKS generation failed: %s", exc)
    return {"keys": []}


@app.get("/auth/authorize", tags=["oidc"])
async def authorize(
    response_type: str = "code",
    client_id: str = "",
    redirect_uri: str = "",
    scope: str = "openid",
    state: str = "",
    code_challenge: str = "",
    code_challenge_method: str = "S256",
):
    """OAuth2 / OIDC authorization endpoint (PKCE supported)."""
    if response_type != "code":
        raise HTTPException(status_code=400, detail="Only 'code' response_type is supported")
    if not redirect_uri:
        raise HTTPException(status_code=400, detail="redirect_uri is required")
    # Generate an authorization code (short-lived, single-use)
    auth_code = secrets.token_urlsafe(32)
    # Store code in DB for later exchange
    with _get_db() as db:
        db.execute(
            """INSERT OR REPLACE INTO auth_codes
               (code, client_id, redirect_uri, scope, code_challenge, code_challenge_method, expires_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                auth_code,
                client_id,
                redirect_uri,
                scope,
                code_challenge,
                code_challenge_method,
                int(time.time()) + 600,
            ),
        )
        db.commit()
    import urllib.parse  # noqa: PLC0415

    params = {"code": auth_code, "state": state}
    return {
        "redirect_to": f"{redirect_uri}?{urllib.parse.urlencode(params)}",
        "code": auth_code,
        "state": state,
    }


class TokenRequest(BaseModel):
    grant_type: str
    code: str = ""
    redirect_uri: str = ""
    client_id: str = ""
    client_secret: str = ""
    code_verifier: str = ""
    refresh_token: str = ""


@app.post("/auth/token", tags=["oidc"])
async def token_endpoint(req: TokenRequest):
    """OAuth2 token endpoint — authorization_code + refresh_token grant."""
    if req.grant_type == "refresh_token":
        if not req.refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token required")
        return await _refresh_via_token(req.refresh_token)

    if req.grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {req.grant_type}")

    row = db.execute(
        "SELECT * FROM auth_codes WHERE code = ? AND expires_at > ?",
        (req.code, int(time.time())),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

    # PKCE verification — must run on the success path, not inside the error branch
    if row["code_challenge"]:
        import base64  # noqa: PLC0415
        import hashlib  # noqa: PLC0415

        if not req.code_verifier:
            raise HTTPException(status_code=400, detail="code_verifier required")
        digest = hashlib.sha256(req.code_verifier.encode()).digest()
        computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        if computed != row["code_challenge"]:
            raise HTTPException(status_code=400, detail="PKCE verification failed")

    # Invalidate code immediately (single-use)
    db.execute("DELETE FROM auth_codes WHERE code = ?", (req.code,))
    db.commit()

    return {
        "access_token": secrets.token_urlsafe(32),
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRY_MINUTES * 60,
        "scope": row["scope"] if row else "openid",
    }


async def _refresh_via_token(refresh_token: str) -> dict:
    # sessions table stores refresh_token_hash (sha256 via db.token_hash)
    row = db.execute(
        "SELECT * FROM sessions WHERE refresh_token_hash = ? AND is_revoked = 0 AND expires_at > ?",
        (db.token_hash(refresh_token), datetime.now(timezone.utc).isoformat()),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.execute("SELECT * FROM users WHERE user_id = ?", (row["user_id"],)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    from jose import jwt as _jwt  # noqa: PLC0415

    role = user["role"] if "role" in user.keys() else "user"
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)
    claims = {
        "sub": user["user_id"],
        "username": user["username"],
        "role": role,
        "tier": tier.value,
        "infinity_role": infinity_role.value,
        "iss": AUTH_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_MINUTES * 60,
        "jti": str(uuid.uuid4()),
    }
    return {
        "access_token": _jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM),
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRY_MINUTES * 60,
    }


# ── auth_codes table init ────────────────────────────────────────────────────


def _ensure_auth_codes_table() -> None:
    db.execute("""
        CREATE TABLE IF NOT EXISTS auth_codes (
            code TEXT PRIMARY KEY,
            client_id TEXT NOT NULL DEFAULT '',
            redirect_uri TEXT NOT NULL DEFAULT '',
            scope TEXT NOT NULL DEFAULT 'openid',
            code_challenge TEXT NOT NULL DEFAULT '',
            code_challenge_method TEXT NOT NULL DEFAULT 'S256',
            expires_at INTEGER NOT NULL
        )
    """)
    db.commit()


# Call once at module load so the table is ready
try:
    _ensure_auth_codes_table()
except Exception:
    pass  # DB may not be ready until lifespan


# ── Startup / Shutdown (Phase 22.6) ─────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
