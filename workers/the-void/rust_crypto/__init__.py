"""
vault_crypto — AES-256-GCM encryption for The Void.

Tries to import the compiled Rust extension (vault_crypto.so / vault_crypto.pyd).
If it is not available (e.g. the Rust toolchain has not been run yet), falls back
to a pure-Python implementation backed by the `cryptography` package.

Public API (identical between both implementations):
    encrypt(plaintext: str, master_key_hex: str) -> str
    decrypt(ciphertext_hex: str, master_key_hex: str) -> str
    derive_key(password: str, salt_hex: str) -> str

Output format for encrypt():
    hex(salt[32] || iv[12] || tag[16] || ciphertext)
"""

from __future__ import annotations

import os

try:
    # Compiled Rust extension built with `maturin develop` or `maturin build`
    from .vault_crypto import decrypt, derive_key, encrypt  # type: ignore[import]

    _BACKEND = "rust"

except ImportError:
    # ── Pure-Python fallback ─────────────────────────────────────────────────
    import hashlib

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as _ce:
        raise ImportError(
            "vault_crypto: neither the Rust extension nor the `cryptography` "
            "package is available. Install it with: pip install cryptography"
        ) from _ce

    _SALT_LEN = 32
    _IV_LEN = 12
    _TAG_LEN = 16
    _KEY_LEN = 32
    _ITERATIONS = 100_000

    def _derive_key_bytes(password: bytes, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password, salt, _ITERATIONS, dklen=_KEY_LEN)

    def encrypt(plaintext: str, master_key_hex: str) -> str:
        """Encrypt *plaintext* with AES-256-GCM.

        Returns hex(salt[32] || iv[12] || tag[16] || ciphertext).
        """
        master_key = bytes.fromhex(master_key_hex)
        salt = os.urandom(_SALT_LEN)
        iv = os.urandom(_IV_LEN)
        key = _derive_key_bytes(master_key, salt)

        aes = AESGCM(key)
        # AESGCM.encrypt() returns ciphertext || tag (tag is last 16 bytes)
        ct_with_tag = aes.encrypt(iv, plaintext.encode(), None)
        ct = ct_with_tag[:-_TAG_LEN]
        tag = ct_with_tag[-_TAG_LEN:]

        blob = salt + iv + tag + ct
        return blob.hex()

    def decrypt(ciphertext_hex: str, master_key_hex: str) -> str:
        """Decrypt output produced by *encrypt*.

        Returns the original plaintext string.
        """
        master_key = bytes.fromhex(master_key_hex)
        blob = bytes.fromhex(ciphertext_hex)

        min_len = _SALT_LEN + _IV_LEN + _TAG_LEN
        if len(blob) < min_len:
            raise ValueError(
                f"ciphertext too short: expected at least {min_len} bytes, got {len(blob)}"
            )

        salt = blob[:_SALT_LEN]
        iv = blob[_SALT_LEN : _SALT_LEN + _IV_LEN]
        tag = blob[_SALT_LEN + _IV_LEN : _SALT_LEN + _IV_LEN + _TAG_LEN]
        ct = blob[_SALT_LEN + _IV_LEN + _TAG_LEN :]

        key = _derive_key_bytes(master_key, salt)
        aes = AESGCM(key)
        # AESGCM.decrypt() expects ciphertext || tag
        plaintext_bytes = aes.decrypt(iv, ct + tag, None)
        return plaintext_bytes.decode()

    def derive_key(password: str, salt_hex: str) -> str:
        """Standalone PBKDF2-HMAC-SHA256 key derivation.

        Returns a hex-encoded 32-byte derived key.
        """
        salt = bytes.fromhex(salt_hex)
        key = _derive_key_bytes(password.encode(), salt)
        return key.hex()

    _BACKEND = "python"


__all__ = ["encrypt", "decrypt", "derive_key", "_BACKEND"]
