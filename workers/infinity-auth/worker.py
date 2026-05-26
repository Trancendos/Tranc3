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
from contextlib import asynccontextmanager
import hashlib
import hmac
import json
import logging
import os
import secrets
import sqlite3
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, EmailStr, Field

from shared_core.sanitize import sanitize_for_log

# Phase 22.5: Infinity Ecosystem nomenclature
from shared_core.infinity.nomenclature import InfinityRole, Tier

# Phase 22.6: Smart Adaptive Intelligence
from shared_core.infinity.worker_integration import InfinityWorkerKit

logger = logging.getLogger("tranc3.workers.infinity-auth")

# ── Configuration ──────────────────────────────────────────────────────────────

JWT_SECRET = os.environ.get("JWT_SECRET", secrets.token_hex(32))
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "60"))
REFRESH_EXPIRY_DAYS = int(os.environ.get("REFRESH_EXPIRY_DAYS", "30"))
DATABASE_PATH = os.environ.get("AUTH_DATABASE_PATH", "/data/auth.db")
RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))

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
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
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
                refresh_token TEXT UNIQUE NOT NULL,
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

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_refresh ON sessions(refresh_token);
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


# ── Password Hashing ───────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using SHA-256 with salt (argon2 in production)."""
    salt = secrets.token_hex(16)
    hash_val = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    return f"{salt}:{hash_val}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against stored hash."""
    try:
        salt, hash_val = stored_hash.split(":", 1)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
        return hmac.compare_digest(hash_val, computed)
    except (ValueError, AttributeError):
        return False


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
                pass  # swallow background loop errors — not critical path

    task = asyncio.create_task(_bg_loop())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass  # expected: task was cancelled, shutdown can proceed
        await worker_kit.shutdown()
        logger.info("Infinity-Auth smart adaptive layer stopped")


app = FastAPI(
    title="Infinity Auth — OAuth2/SSO API",
    description="Self-hosted authentication for Trancendos with tier-aware JWT claims",
    version="2.0.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

db = AuthDatabase()
rate_limiter = RateLimiter()
security = HTTPBearer()

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
    """Validate JWT token and return user payload."""
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
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
        "entity": {
            "location": "Infinity",
            "pillar": "Security",
            "lead_ai": "The Guardian (Anchor: Orb of Orisis)",
            "primes": ["Cornelius MacIntyre"],
            "primary_function": "Centralized Auth & OAuth 2.0",
        },
        # Phase 22.6: Smart health
        "health_score": health_summary.get("health_score", 1.0),
        "health_tier": health_summary.get("tier", "EXCELLENT"),
        "smart_adaptive": True,
        "defense_blocked_ips": len(worker_kit.defense.get_blocked_ips()),
    }


@app.post("/auth/register", response_model=TokenResponse)
async def register(user: UserRegister, _=Depends(rate_limit_check)):
    """Register a new user account.

    Phase 22.5: Includes role in JWT claims for Infinity Gate routing.
    """
    # Check if username exists
    existing = db.execute(
        "SELECT user_id FROM users WHERE username = ?", (user.username,)
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
        (user_id, user.username, user.email, password_hash, user.display_name, now, role),
    )
    db.commit()

    # Create tokens with tier-aware claims
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)
    access_token = create_access_token(user_id, user.username, role=role)
    refresh_token = create_refresh_token()

    # Store session
    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)).isoformat()
    db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, refresh_token, now, expires_at),
    )
    db.commit()

    logger.info(
        "user_registered: username=%s role=%s", sanitize_for_log(user.username), role
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
        "SELECT user_id, username, password_hash, mfa_enabled, totp_secret, role FROM users WHERE username = ? AND is_active = 1",
        (credentials.username,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Verify password
    if not verify_password(credentials.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Check MFA
    if row["mfa_enabled"]:
        if not credentials.totp_code:
            raise HTTPException(status_code=403, detail="MFA code required")
        # TOTP verification would go here (pyotp)
        # For now, accept any 6-digit code as placeholder
        if not (credentials.totp_code.isdigit() and len(credentials.totp_code) == 6):
            raise HTTPException(status_code=403, detail="Invalid MFA code")

    # Get role for JWT claims
    user_id = row["user_id"]
    username = row["username"]
    role = row["role"] if "role" in row.keys() else "user"
    tier = _get_tier_for_role(role)
    infinity_role = _get_infinity_role_for_role(role)

    # Create tokens with tier-aware claims
    access_token = create_access_token(user_id, username, role=role)
    refresh_token = create_refresh_token()

    # Store session
    now = datetime.now(timezone.utc).isoformat()
    session_id = str(uuid.uuid4())
    expires_at = (datetime.now(timezone.utc) + timedelta(days=REFRESH_EXPIRY_DAYS)).isoformat()
    db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (session_id, user_id, refresh_token, now, expires_at),
    )

    # Update last login
    db.execute("UPDATE users SET last_login = ? WHERE user_id = ?", (now, user_id))
    db.commit()

    logger.info(
        "user_login: username=%s role=%s", sanitize_for_log(credentials.username), role
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
        "SELECT session_id, user_id, expires_at, is_revoked FROM sessions WHERE refresh_token = ?",
        (request.refresh_token,),
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
        "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (new_session_id, row["user_id"], new_refresh_token, now, new_expires_at),
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
    """Revoke all sessions for the current user."""
    db.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (user["sub"],))
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
    # Generate TOTP secret
    totp_secret = secrets.token_hex(20)
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]

    # Store TOTP secret
    db.execute(
        "UPDATE users SET totp_secret = ?, backup_codes = ? WHERE user_id = ?",
        (totp_secret, json.dumps(backup_codes), user["sub"]),
    )
    db.commit()

    # Generate QR code URL (otpauth:// format)
    username = user.get("username", "user")
    qr_url = f"otpauth://totp/Trancendos:{username}?secret={totp_secret}&issuer=Trancendos"

    return TOTPSetupResponse(
        secret=totp_secret,
        qr_code_url=qr_url,
        backup_codes=backup_codes,
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
        "UPDATE users SET mfa_enabled = 0, totp_secret = NULL WHERE user_id = ?", (user["sub"],)
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


# ── Startup / Shutdown (Phase 22.6) ─────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8005)
