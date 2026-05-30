# Dimensional/security.py
# Shared security utilities — JWT, password hashing, input validation

import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# Lazy imports for heavy crypto dependencies
_jose = None


def _get_jose():  # type: ignore[return]
    """Lazily import and cache python-jose's jwt module."""
    global _jose
    if _jose is None:
        from jose import jwt

        _jose = jwt
    return _jose


class _BcryptContext:
    """Minimal bcrypt wrapper replacing passlib.CryptContext — avoids crypt DeprecationWarning."""

    def hash(self, password: str) -> str:
        import bcrypt

        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify(self, plain: str, hashed: str) -> bool:
        import bcrypt

        try:
            return bcrypt.checkpw(plain.encode(), hashed.encode())
        except Exception:
            return False


_bcrypt_ctx = _BcryptContext()


# ── JWT ──────────────────────────────────────────────────────────────────────


def generate_jwt(
    payload: Dict[str, Any],
    secret_key: Optional[str] = None,
    algorithm: str = "HS256",
    expires_minutes: int = 60,
) -> str:
    """Generate a JWT token with expiry"""
    jwt = _get_jose()

    key = secret_key or os.getenv("JWT_SECRET")
    if not key:
        raise RuntimeError("JWT_SECRET is not set")

    to_encode = payload.copy()
    to_encode.update(
        {
            "iat": datetime.utcnow(),
            "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
        }
    )
    return jwt.encode(to_encode, key, algorithm=algorithm)


def verify_jwt(
    token: str,
    secret_key: Optional[str] = None,
    algorithm: str = "HS256",
) -> Dict[str, Any]:
    """Verify and decode a JWT token. Raises on invalid/expired."""
    jwt = _get_jose()

    key = secret_key or os.getenv("JWT_SECRET")
    if not key:
        raise RuntimeError("JWT_SECRET is not set")

    try:
        return jwt.decode(token, key, algorithms=[algorithm])
    except Exception as e:
        logger.warning(
            "JWT verification failed: %s", sanitize_for_log(e)
        )  # codeql[py/cleartext-logging]
        raise
    return None


# ── Password hashing ────────────────────────────────────────────────────────


def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    return _bcrypt_ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a hash"""
    return _bcrypt_ctx.verify(plain, hashed)


# ── Input sanitization ──────────────────────────────────────────────────────


def sanitize_input(text: str, max_length: int = 4096) -> str:
    """Basic input sanitization — strip control chars, limit length"""
    if len(text) > max_length:
        raise ValueError(f"Input exceeds max length ({max_length})")
    # Remove null bytes and control characters (keep newlines)
    return "".join(c for c in text if c == "\n" or (ord(c) >= 32 and ord(c) != 127))


def generate_token_hex(length: int = 32) -> str:
    """Generate a random hex token"""
    return secrets.token_hex(length)


def constant_time_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks"""
    return secrets.compare_digest(a.encode(), b.encode())
