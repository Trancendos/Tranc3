"""
Infinity Auth — Service Layer
==============================
Business logic: password hashing, JWT creation/validation,
TOTP, rate limiting, role/tier mapping.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid
from typing import Any

try:
    from argon2 import PasswordHasher as _ArgonPH
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    _ph = _ArgonPH(time_cost=2, memory_cost=65536, parallelism=2)
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False

import pyotp

from config import (
    JWT_ALGORITHM,
    JWT_EXPIRY_MINUTES,
    JWT_SECRET,
    RATE_LIMIT_PER_MINUTE,
)

# Phase 22.5: Infinity Ecosystem nomenclature
from shared_core.infinity.nomenclature import InfinityRole, Tier

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


def get_tier_for_role(role: str) -> Tier:
    """Get the Tier for a given role string."""
    return ROLE_TIER_MAP.get(role.lower().strip(), Tier.HUMAN)


def get_infinity_role_for_role(role: str) -> InfinityRole:
    """Get the InfinityRole for a given role string."""
    return ROLE_INFINITY_ROLE_MAP.get(role.lower().strip(), InfinityRole.USER)


# ── Password Hashing ───────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using argon2id (preferred) or PBKDF2-HMAC-SHA256 fallback."""
    if _ARGON2_AVAILABLE:
        return _ph.hash(password)
    # fallback: PBKDF2-HMAC-SHA256 (better than plain SHA-256)
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
    return f"pbkdf2:{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against stored hash (supports argon2, pbkdf2, and legacy formats)."""
    if not stored_hash:
        return False
    if stored_hash.startswith("$argon2") and _ARGON2_AVAILABLE:
        try:
            return _ph.verify(stored_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    elif stored_hash.startswith("pbkdf2:"):
        try:
            _, salt_hex, dk_hex = stored_hash.split(":", 2)
            salt = bytes.fromhex(salt_hex)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260000)
            return hmac.compare_digest(dk.hex(), dk_hex)
        except (ValueError, AttributeError):
            return False
    else:
        # legacy salt:hash format (PBKDF2-SHA256 with string salt, 100k iterations)
        try:
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
    tier = get_tier_for_role(role)
    infinity_role = get_infinity_role_for_role(role)

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


# ── TOTP ───────────────────────────────────────────────────────────────────────


def generate_totp_secret() -> str:
    """Generate a new TOTP secret (Base32)."""
    return pyotp.random_base32()


def generate_totp_provisioning_uri(secret: str, username: str) -> str:
    """Build a standards-compliant otpauth:// provisioning URI."""
    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name="Trancendos")


def verify_totp(secret: str, code: str) -> bool:
    """Verify a TOTP code with ±30s clock drift tolerance."""
    try:
        return pyotp.TOTP(secret).verify(code, valid_window=1)
    except Exception:
        return False


def generate_backup_codes(count: int = 10) -> tuple[list[str], list[str]]:
    """Generate backup codes. Returns (plaintext_codes, hashed_codes)."""
    plaintext = [secrets.token_hex(4).upper() for _ in range(count)]
    hashed = [hash_backup_code(c) for c in plaintext]
    return plaintext, hashed


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
