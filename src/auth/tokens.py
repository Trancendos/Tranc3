"""
src/auth/tokens.py — Canonical JWT token management for Trancendos.

Provides create/decode/refresh token helpers with tier-aware claims
(role, tier, infinity_role) for Infinity Gate routing.
Imported by workers/infinity-auth/worker.py so JWT logic lives here once.
"""

from __future__ import annotations

import secrets
import time
import uuid
from typing import Any

__all__ = [
    "create_access_token",
    "decode_access_token",
    "create_refresh_token",
]


def create_access_token(
    user_id: str,
    username: str,
    jwt_secret: str,
    algorithm: str = "HS256",
    expiry_minutes: int = 60,
    role: str = "user",
    tier_value: int = 0,
    infinity_role_value: str = "user",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """Create a JWT access token with tier-aware claims.

    Tier and InfinityRole values are passed in pre-resolved so this module
    stays independent of the Infinity nomenclature enums.
    """
    claims: dict[str, Any] = {
        "sub": user_id,
        # Several call sites across the codebase (api.py's /chat, /feedback,
        # /usage, GDPR erasure, plus src/{taimra,tranquility,access,devocity}
        # routes) index the authenticated user dict as current_user["id"],
        # not ["sub"] — mirror the same value under both keys so tokens
        # issued here satisfy that existing convention.
        "id": user_id,
        "username": username,
        "role": role,
        "tier": tier_value,
        "infinity_role": infinity_role_value,
        "exp": int(time.time()) + expiry_minutes * 60,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        **(extra_claims or {}),
    }

    from jose import jwt  # type: ignore

    return jwt.encode(claims, jwt_secret, algorithm=algorithm)


def decode_access_token(
    token: str, jwt_secret: str, algorithm: str = "HS256"
) -> dict[str, Any] | None:
    """Decode and validate a JWT access token. Returns None if invalid/expired."""
    from jose import JWTError, jwt  # type: ignore

    try:
        return jwt.decode(token, jwt_secret, algorithms=[algorithm])
    except JWTError:
        return None


def create_refresh_token() -> str:
    """Create a cryptographically secure refresh token."""
    return secrets.token_urlsafe(64)
