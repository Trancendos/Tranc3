"""
Infinity Auth — FastAPI Router
================================
All HTTP routes for the infinity-auth worker, mounted via APIRouter.
"""

from __future__ import annotations

import json
import logging
import os
import secrets
import time
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from models import (
    RefreshRequest,
    TokenRequest,
    TokenResponse,
    TOTPSetupResponse,
    UserLogin,
    UserProfile,
    UserRegister,
)
from service import (
    RateLimiter,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    generate_backup_codes,
    generate_totp_provisioning_uri,
    generate_totp_secret,
    get_infinity_role_for_role,
    get_tier_for_role,
    hash_backup_code,
    hash_password,
    verify_password,
    verify_totp,
)

from config import AUTH_BASE_URL, AUTH_ISSUER, JWT_EXPIRY_MINUTES, REFRESH_EXPIRY_DAYS
from database import AuthDatabase

# Phase 22.6: Smart Adaptive Intelligence
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger("tranc3.workers.infinity-auth")

router = APIRouter()
security = HTTPBearer()

# Module-level singletons (initialised by main.py via init_router)
_db: AuthDatabase | None = None
_rate_limiter: RateLimiter | None = None
# worker_kit is accessed via the module imported in main.py
_worker_kit: Any = None


def init_router(db: AuthDatabase, rate_limiter: RateLimiter, worker_kit: Any) -> None:
    """Inject shared singletons into the router module."""
    global _db, _rate_limiter, _worker_kit
    _db = db
    _rate_limiter = rate_limiter
    _worker_kit = worker_kit


def _get_db() -> AuthDatabase:
    assert _db is not None, "Router not initialised — call init_router() first"
    return _db


@contextmanager
def _db_ctx():
    """Context manager returning the module-level AuthDatabase singleton."""
    yield _get_db()


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
    assert _rate_limiter is not None
    client_ip = request.client.host if request.client else "unknown"
    if not _rate_limiter.is_allowed(f"auth:{client_ip}"):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


# ── Health ──────────────────────────────────────────────────────────────────────


@router.get("/health")
async def health():
    """Health check endpoint."""
    assert _worker_kit is not None
    health_summary_obj = _worker_kit.health.get_health_summary()
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
        "defense_blocked_ips": len(_worker_kit.defense.get_blocked_ips()),
    }


# ── Auth Endpoints ───────────────────────────────────────────────────────────────


@router.post("/auth/register", response_model=TokenResponse)
async def register(user: UserRegister, _=Depends(rate_limit_check)):
    """Register a new user account.

    Phase 22.5: Includes role in JWT claims for Infinity Gate routing.
    """
    db = _get_db()

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
    tier = get_tier_for_role(role)
    infinity_role = get_infinity_role_for_role(role)
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


@router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin, _=Depends(rate_limit_check)):
    """Authenticate a user and issue tokens.

    Phase 22.5: Includes role/tier/infinity_role in JWT claims.
    """
    db = _get_db()

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
            if not verify_totp(totp_secret, code):
                raise HTTPException(status_code=403, detail="Invalid MFA code")
        else:
            # Backup code recovery path — compare HMAC hashes, constant-time, one-time use
            stored_hashes: list[str] = json.loads(row["backup_codes"] or "[]")
            import hmac as _hmac

            incoming_hash = hash_backup_code(code)
            matched_idx = next(
                (i for i, h in enumerate(stored_hashes) if _hmac.compare_digest(h, incoming_hash)),
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
    tier = get_tier_for_role(role)
    infinity_role = get_infinity_role_for_role(role)

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


@router.post("/auth/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, _=Depends(rate_limit_check)):
    """Refresh an access token using a valid refresh token."""
    db = _get_db()

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
    tier = get_tier_for_role(role)
    infinity_role = get_infinity_role_for_role(role)

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


@router.post("/auth/logout")
async def logout(user: dict = Depends(get_current_user)):
    """Revoke all sessions for the current user."""
    db = _get_db()
    db.execute("UPDATE sessions SET is_revoked = 1 WHERE user_id = ?", (user["sub"],))
    db.commit()
    return {"message": "Logged out successfully"}


@router.get("/auth/me", response_model=UserProfile)
async def get_profile(user: dict = Depends(get_current_user)):
    """Get the current user's profile with tier information."""
    db = _get_db()
    row = db.execute(
        "SELECT user_id, username, email, display_name, mfa_enabled, created_at, last_login, role FROM users WHERE user_id = ?",
        (user["sub"],),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="User not found")

    role = row["role"] if "role" in row.keys() else "user"
    tier = get_tier_for_role(role)
    infinity_role = get_infinity_role_for_role(role)

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


@router.post("/auth/mfa/setup", response_model=TOTPSetupResponse)
async def setup_mfa(user: dict = Depends(get_current_user)):
    """Set up TOTP multi-factor authentication."""
    db = _get_db()

    # Generate TOTP secret (Base32 so any RFC 6238 authenticator can import it)
    totp_secret = generate_totp_secret()
    plaintext_codes, hashed_codes = generate_backup_codes(10)

    # Store TOTP secret and hashed backup codes
    db.execute(
        "UPDATE users SET totp_secret = ?, backup_codes = ? WHERE user_id = ?",
        (totp_secret, json.dumps(hashed_codes), user["sub"]),
    )
    db.commit()

    # Build a standards-compliant otpauth:// provisioning URI
    username = user.get("username", "user")
    qr_url = generate_totp_provisioning_uri(totp_secret, username)

    return TOTPSetupResponse(
        secret=totp_secret,
        qr_code_url=qr_url,
        backup_codes=plaintext_codes,  # plaintext shown once; DB holds hashes
    )


@router.post("/auth/mfa/enable")
async def enable_mfa(user: dict = Depends(get_current_user)):
    """Enable MFA after setup is confirmed."""
    db = _get_db()
    db.execute("UPDATE users SET mfa_enabled = 1 WHERE user_id = ?", (user["sub"],))
    db.commit()
    return {"message": "MFA enabled successfully"}


@router.post("/auth/mfa/disable")
async def disable_mfa(user: dict = Depends(get_current_user)):
    """Disable MFA for the current user."""
    db = _get_db()
    db.execute(
        "UPDATE users SET mfa_enabled = 0, totp_secret = NULL WHERE user_id = ?", (user["sub"],)
    )
    db.commit()
    return {"message": "MFA disabled"}


@router.get("/auth/verify")
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


@router.put("/auth/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    role: str = Query(..., description="New role for the user"),
    current_user: dict = Depends(get_current_user),
):
    """Update a user's role (admin-only).

    This affects the tier and infinity_role in their JWT claims,
    which changes how the Infinity Gate routes them.
    """
    db = _get_db()

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

    tier = get_tier_for_role(role)
    infinity_role = get_infinity_role_for_role(role)

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


# ── OIDC Discovery (RFC 8414 / OpenID Connect Discovery 1.0) ────────────────


@router.get("/.well-known/openid-configuration", tags=["oidc"])
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


@router.get("/.well-known/jwks.json", tags=["oidc"])
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
                        }
                    ]
                }
        except Exception as exc:
            logger.debug("JWKS generation failed: %s", exc)
    return {"keys": []}


@router.get("/auth/authorize", tags=["oidc"])
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
    db = _get_db()
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

    params = {"code": auth_code, "state": state}
    return {
        "redirect_to": f"{redirect_uri}?{urllib.parse.urlencode(params)}",
        "code": auth_code,
        "state": state,
    }


@router.post("/auth/token", tags=["oidc"])
async def token_endpoint(req: TokenRequest):
    """OAuth2 token endpoint — authorization_code + refresh_token grant."""
    if req.grant_type == "refresh_token":
        if not req.refresh_token:
            raise HTTPException(status_code=400, detail="refresh_token required")
        return await _refresh_via_token(req.refresh_token)

    if req.grant_type != "authorization_code":
        raise HTTPException(status_code=400, detail=f"Unsupported grant_type: {req.grant_type}")

    db = _get_db()
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
    from config import JWT_ALGORITHM, JWT_SECRET  # noqa: PLC0415

    db = _get_db()
    row = db.execute(
        "SELECT * FROM refresh_tokens WHERE token = ? AND expires_at > ?",
        (refresh_token, int(time.time())),
    ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
    user = db.execute("SELECT * FROM users WHERE user_id = ?", (row["user_id"],)).fetchone()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    from jose import jwt as _jwt  # noqa: PLC0415

    claims = {
        "sub": user["user_id"],
        "username": user["username"],
        "role": user["role"],
        "iss": AUTH_ISSUER,
        "iat": int(time.time()),
        "exp": int(time.time()) + JWT_EXPIRY_MINUTES * 60,
    }
    return {
        "access_token": _jwt.encode(claims, JWT_SECRET, algorithm=JWT_ALGORITHM),
        "token_type": "Bearer",
        "expires_in": JWT_EXPIRY_MINUTES * 60,
    }
