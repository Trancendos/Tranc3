"""
src/auth/passwords.py — Canonical password hashing for Trancendos.

Provides argon2id (preferred) with PBKDF2-HMAC-SHA256 fallback and
a legacy salt:hash format for reading pre-existing hashes.
Imported by workers/infinity-auth/worker.py so logic lives here once.
"""

from __future__ import annotations

import hashlib
import hmac
import os

try:
    from argon2 import PasswordHasher as _ArgonPH
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    _ph = _ArgonPH(time_cost=2, memory_cost=65536, parallelism=2)
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False

__all__ = ["hash_password", "verify_password", "hash_backup_code"]


def hash_password(password: str) -> str:
    """Hash a password using argon2id (preferred) or PBKDF2-HMAC-SHA256 fallback."""
    if _ARGON2_AVAILABLE:
        return _ph.hash(password)  # type: ignore[union-attr]
    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 260_000)
    return f"pbkdf2:{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a password against stored hash (supports argon2, pbkdf2, legacy formats)."""
    if stored_hash.startswith("$argon2") and _ARGON2_AVAILABLE:
        try:
            return _ph.verify(stored_hash, password)  # type: ignore[union-attr]
        except (VerifyMismatchError, VerificationError, InvalidHashError):  # type: ignore[possibly-undefined]
            return False
    if stored_hash.startswith("pbkdf2:"):
        try:
            _, salt_hex, dk_hex = stored_hash.split(":", 2)
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), 260_000)
            return hmac.compare_digest(dk.hex(), dk_hex)
        except (ValueError, AttributeError):
            return False
    # Legacy salt:hash format (PBKDF2-SHA256, 100k iterations)
    try:
        salt, hash_val = stored_hash.split(":", 1)
        computed = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100_000).hex()
        return hmac.compare_digest(hash_val, computed)
    except (ValueError, AttributeError):
        return False


def hash_backup_code(code: str, site_key: str) -> str:
    """HMAC-SHA256 hash of a backup code, keyed by the site secret.

    Site-specific keying prevents rainbow-table reversal of leaked hashes.
    Fast enough for one-time-use codes where argon2 overhead is unnecessary.
    """
    return hmac.new(site_key.encode(), code.upper().encode(), hashlib.sha256).hexdigest()
