"""
src/auth/tokens.py — Canonical JWT token management for Trancendos.

Provides create/decode/refresh token helpers with tier-aware claims
(role, tier, infinity_role) for Infinity Gate routing.
Imported by workers/infinity-auth/worker.py so JWT logic lives here once.
"""

from __future__ import annotations

import json
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
        "username": username,
        "role": role,
        "tier": tier_value,
        "infinity_role": infinity_role_value,
        "exp": int(time.time()) + expiry_minutes * 60,
        "iat": int(time.time()),
        "jti": str(uuid.uuid4()),
        **(extra_claims or {}),
    }

    try:
        from jose import jwt  # type: ignore

        return jwt.encode(claims, jwt_secret, algorithm=algorithm)
    except ImportError:
        import base64

        return base64.urlsafe_b64encode(json.dumps(claims).encode()).decode()


def decode_access_token(
    token: str, jwt_secret: str, algorithm: str = "HS256"
) -> dict[str, Any] | None:
    """Decode and validate a JWT access token. Returns None if invalid/expired."""
    try:
        from jose import JWTError, jwt  # type: ignore

        try:
            return jwt.decode(token, jwt_secret, algorithms=[algorithm])
        except JWTError:
            return None
    except ImportError:
        try:
            import base64

            payload = json.loads(base64.urlsafe_b64decode(token + "=="))
            if payload.get("exp", 0) < time.time():
                return None
            return payload
        except Exception:
            return None


def create_refresh_token() -> str:
    """Create a cryptographically secure refresh token."""
    return secrets.token_urlsafe(64)
