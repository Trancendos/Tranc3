"""
src/auth/facade.py — Unified auth facade for the Trancendos platform.

Merges the two JWT implementations:
  • auth.py       — root-level, uses PyJWT (`import jwt`), bcrypt
  • src/auth/tokens.py — uses python-jose, tier-aware claims

This facade is the single import point going forward. Both underlying
libraries are supported; jose takes priority when available.

Workers and API routes should import from here:
    from src.auth.facade import (
        AuthFacade, get_current_user_dep,
        create_token, verify_token, hash_password, verify_password,
    )
"""

from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.auth.passwords import hash_password, verify_password  # noqa: F401
from src.auth.tokens import (  # noqa: F401
    create_access_token as _tokens_create,
)
from src.auth.tokens import (
    create_refresh_token,
)
from src.auth.tokens import (
    decode_access_token as _tokens_decode,
)

logger = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_DEFAULT_EXPIRY_MINUTES = 60
_bearer = HTTPBearer(auto_error=False)


def _jwt_secret() -> str:
    """Single source for the JWT signing secret."""
    secret = os.getenv("JWT_SECRET")
    if secret:
        return secret
    if os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError(
            "JWT_SECRET is not set. "
            'Generate: python -c "import secrets; print(secrets.token_hex(32))"'
        )
    gen = os.environ.setdefault("JWT_SECRET", secrets.token_hex(32))
    logger.warning("JWT_SECRET not set — ephemeral secret generated (tokens won't survive restart)")
    return gen


def create_token(
    user_id: str,
    username: str,
    *,
    expiry_minutes: int = _DEFAULT_EXPIRY_MINUTES,
    role: str = "user",
    tier: int = 0,
    infinity_role: str = "user",
    extra: dict[str, Any] | None = None,
) -> str:
    """Create a signed JWT access token (tier-aware, unified)."""
    return _tokens_create(
        user_id=user_id,
        username=username,
        jwt_secret=_jwt_secret(),
        algorithm=_ALGORITHM,
        expiry_minutes=expiry_minutes,
        role=role,
        tier_value=tier,
        infinity_role_value=infinity_role,
        extra_claims=extra,
    )


def verify_token(token: str) -> dict[str, Any] | None:
    """Decode and verify a JWT. Returns payload dict or None."""
    return _tokens_decode(token, _jwt_secret(), _ALGORITHM)


class AuthFacade:
    """
    Single auth entry point for all 38 workers.

    Usage:
        auth = AuthFacade()
        token = auth.login(username, password, db_lookup_fn)
        user  = auth.authenticate_bearer(token)
    """

    def login(
        self,
        username: str,
        password: str,
        lookup_fn,  # Callable[[str], Optional[dict]] — returns user dict with "hashed_password"
        *,
        role: str = "user",
        tier: int = 0,
    ) -> dict[str, str]:
        """Authenticate and return access + refresh tokens."""
        user = lookup_fn(username)
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not verify_password(password, user.get("hashed_password", "")):
            raise HTTPException(status_code=401, detail="Invalid credentials")
        if not user.get("is_active", True):
            raise HTTPException(status_code=403, detail="Account disabled")

        access = create_token(
            user_id=str(user.get("id", user.get("user_id", ""))),
            username=username,
            role=user.get("role", role),
            tier=user.get("tier_value", tier),
        )
        refresh = create_refresh_token()
        return {"access_token": access, "refresh_token": refresh, "token_type": "bearer"}

    def authenticate_bearer(self, token: str) -> dict[str, Any]:
        """Verify a bearer token. Raises 401 on failure."""
        payload = verify_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return payload

    def require_role(self, payload: dict[str, Any], *roles: str) -> None:
        """Raise 403 if the token role is not in the allowed set."""
        if payload.get("role") not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")

    def require_tier(self, payload: dict[str, Any], min_tier: int) -> None:
        """Raise 403 if the token tier is below minimum."""
        if int(payload.get("tier", 0)) < min_tier:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient tier")


# ---------------------------------------------------------------------------
# FastAPI dependency — drop-in for both auth.get_current_user and
# src.auth.dependencies.get_current_user
# ---------------------------------------------------------------------------

_facade = AuthFacade()


async def get_current_user_dep(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> dict[str, Any]:
    """
    FastAPI dependency.  Returns user payload dict.
    REQUIRE_AUTH=false → returns anonymous user (dev/test mode).
    """
    if os.getenv("REQUIRE_AUTH", "true").lower() == "false":
        if not credentials:
            return {
                "sub": "anonymous",
                "id": "anonymous",
                "username": "anonymous",
                "role": "user",
                "tier": 0,
            }

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return _facade.authenticate_bearer(credentials.credentials)


# Alias matching old dependency name in auth.py and src/auth/dependencies.py
get_current_user = get_current_user_dep
