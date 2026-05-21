# shared_core/security.py
# Shared security utilities — JWT, password hashing, input validation

import hashlib
import logging
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Lazy imports for heavy crypto dependencies
_jose = None
_passlib = None


def _get_jose():
    global _jose
    if _jose is None:
        from jose import JWTError, jwt
        _jose = jwt
    return _jose


def _get_passlib():
    global _passlib
    if _passlib is None:
        from passlib.context import CryptContext
        _passlib = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return _passlib


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
    to_encode.update({
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=expires_minutes),
    })
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
        logger.warning(f"JWT verification failed: {e}")
        raise


# ── Password hashing ────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    """Hash a password using bcrypt"""
    ctx = _get_passlib()
    return ctx.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a password against a hash"""
    ctx = _get_passlib()
    return ctx.verify(plain, hashed)


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