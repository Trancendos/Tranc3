"""
rust_crypto — Thin Python shim over the tranc3_crypto Rust extension.

Provides a graceful fallback to the Python cryptography library when the
Rust extension is not installed (e.g. during development without maturin).

Usage:
    from src.security.rust_crypto import encrypt, decrypt, hmac_sha256, constant_time_eq

Build:
    cd rust_extensions/tranc3_crypto && maturin build --release
    pip install target/wheels/tranc3_crypto-*.whl
"""

from __future__ import annotations

import logging

logger = logging.getLogger("tranc3.rust_crypto")

try:
    import tranc3_crypto as _rust

    _USING_RUST = True
    logger.debug("tranc3_crypto: using Rust AES-256-GCM extension")
except ImportError:
    _rust = None  # type: ignore[assignment]
    _USING_RUST = False
    logger.info(
        "tranc3_crypto Rust extension not installed — falling back to Python cryptography. "
        "Build with: cd rust_extensions/tranc3_crypto && maturin build --release"
    )


def is_rust_available() -> bool:
    """Return True if the Rust extension is loaded."""
    return _USING_RUST


# ---------------------------------------------------------------------------
# Core API — delegates to Rust when available, Python crypto otherwise
# ---------------------------------------------------------------------------


def encrypt(plaintext: bytes, key_seed: str) -> bytes:
    """AES-256-GCM encrypt. Returns SALT(32) ++ NONCE(12) ++ CT+TAG."""
    if _USING_RUST:
        return _rust.encrypt(plaintext, key_seed)  # type: ignore[union-attr]
    return _python_encrypt(plaintext, key_seed)


def decrypt(ciphertext: bytes, key_seed: str) -> bytes:
    """AES-256-GCM decrypt. Raises ValueError on auth failure."""
    if _USING_RUST:
        return _rust.decrypt(ciphertext, key_seed)  # type: ignore[union-attr]
    return _python_decrypt(ciphertext, key_seed)


def hmac_sha256(key: bytes, data: bytes) -> bytes:
    """HMAC-SHA256. Returns 32-byte tag."""
    if _USING_RUST:
        return _rust.hmac_sha256(key, data)  # type: ignore[union-attr]
    return _python_hmac(key, data)


def constant_time_eq(a: bytes, b: bytes) -> bool:
    """Constant-time byte comparison."""
    if _USING_RUST:
        return _rust.constant_time_eq(a, b)  # type: ignore[union-attr]
    import hmac as _hmac

    return _hmac.compare_digest(a, b)


def derive_key_hkdf(seed: bytes, salt: bytes, info: bytes) -> bytes:
    """HKDF-SHA256 — returns 32-byte key."""
    if _USING_RUST:
        return _rust.derive_key_hkdf(seed, salt, info)  # type: ignore[union-attr]
    return _python_hkdf(seed, salt, info)


def derive_key_pbkdf2(seed: str, salt: bytes) -> bytes:
    """PBKDF2-HMAC-SHA256 (100k iters) — returns 32-byte key."""
    if _USING_RUST:
        return _rust.derive_key_pbkdf2(seed, salt)  # type: ignore[union-attr]
    return _python_pbkdf2(seed, salt)


# ---------------------------------------------------------------------------
# Python fallback implementations (identical wire format)
# ---------------------------------------------------------------------------

_SALT_LEN = 32
_NONCE_LEN = 12


def _python_encrypt(plaintext: bytes, key_seed: str) -> bytes:
    import os

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = os.urandom(_SALT_LEN)
    nonce = os.urandom(_NONCE_LEN)
    key = _python_pbkdf2(key_seed, salt)
    ct = AESGCM(key).encrypt(nonce, plaintext, None)
    return salt + nonce + ct


def _python_decrypt(ciphertext: bytes, key_seed: str) -> bytes:
    if len(ciphertext) < _SALT_LEN + _NONCE_LEN + 16:
        raise ValueError("ciphertext too short")
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = ciphertext[:_SALT_LEN]
    nonce = ciphertext[_SALT_LEN : _SALT_LEN + _NONCE_LEN]
    ct = ciphertext[_SALT_LEN + _NONCE_LEN :]
    key = _python_pbkdf2(key_seed, salt)
    return AESGCM(key).decrypt(nonce, ct, None)


def _python_pbkdf2(seed: str, salt: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=100_000)
    return kdf.derive(seed.encode())


def _python_hkdf(seed: bytes, salt: bytes, info: bytes) -> bytes:
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF

    return HKDF(algorithm=hashes.SHA256(), length=32, salt=salt, info=info).derive(seed)


def _python_hmac(key: bytes, data: bytes) -> bytes:
    import hashlib
    import hmac as _hmac

    return _hmac.new(key, data, hashlib.sha256).digest()
