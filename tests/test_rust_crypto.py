"""
Tests for the tranc3_crypto Rust extension and its Python fallback shim.

Covers both paths: Rust extension (when available) and Python cryptography fallback.
Wire format: SALT(32) ++ NONCE(12) ++ CT+TAG(≥16)
"""

from __future__ import annotations

import hashlib
import hmac as _hmac

import pytest


# ---------------------------------------------------------------------------
# Import the shim under test
# ---------------------------------------------------------------------------

from src.security.rust_crypto import (
    constant_time_eq,
    decrypt,
    derive_key_hkdf,
    derive_key_pbkdf2,
    encrypt,
    hmac_sha256,
    is_rust_available,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SALT_LEN = 32
NONCE_LEN = 12
TAG_LEN = 16
MIN_CT_LEN = SALT_LEN + NONCE_LEN + TAG_LEN  # 60


# ---------------------------------------------------------------------------
# Availability
# ---------------------------------------------------------------------------

def test_is_rust_available_returns_bool():
    result = is_rust_available()
    assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Encrypt / Decrypt roundtrip
# ---------------------------------------------------------------------------

def test_encrypt_returns_bytes():
    ct = encrypt(b"hello", "myseed")
    assert isinstance(ct, bytes)


def test_encrypt_output_length():
    plaintext = b"hello secure world"
    ct = encrypt(plaintext, "myseed")
    # SALT(32) + NONCE(12) + CT(len(plaintext)) + TAG(16)
    assert len(ct) >= MIN_CT_LEN
    assert len(ct) == SALT_LEN + NONCE_LEN + len(plaintext) + TAG_LEN


def test_encrypt_decrypt_roundtrip():
    plaintext = b"hello secure world"
    key = "test-key-seed"
    ct = encrypt(plaintext, key)
    recovered = decrypt(ct, key)
    assert recovered == plaintext


def test_encrypt_decrypt_empty_plaintext():
    ct = encrypt(b"", "seed")
    assert decrypt(ct, "seed") == b""


def test_encrypt_produces_different_ciphertext_each_call():
    pt = b"same plaintext"
    key = "same-key"
    ct1 = encrypt(pt, key)
    ct2 = encrypt(pt, key)
    # Different random salt/nonce each time
    assert ct1 != ct2
    # But both decrypt correctly
    assert decrypt(ct1, key) == pt
    assert decrypt(ct2, key) == pt


def test_decrypt_wrong_key_raises():
    ct = encrypt(b"secret", "correct-key")
    with pytest.raises((ValueError, Exception)):
        decrypt(ct, "wrong-key")


def test_decrypt_truncated_ciphertext_raises():
    with pytest.raises((ValueError, Exception)):
        decrypt(b"\x00" * 10, "key")


def test_decrypt_exactly_min_length_but_corrupt():
    with pytest.raises((ValueError, Exception)):
        decrypt(b"\x00" * MIN_CT_LEN, "key")


def test_encrypt_binary_payload():
    payload = bytes(range(256))
    key = "binary-key"
    ct = encrypt(payload, key)
    assert decrypt(ct, key) == payload


def test_encrypt_unicode_key():
    pt = b"data"
    key = "unicode-key-éàü"
    ct = encrypt(pt, key)
    assert decrypt(ct, key) == pt


# ---------------------------------------------------------------------------
# HMAC-SHA256
# ---------------------------------------------------------------------------

def test_hmac_sha256_returns_32_bytes():
    tag = hmac_sha256(b"key", b"data")
    assert isinstance(tag, bytes)
    assert len(tag) == 32


def test_hmac_sha256_correct_value():
    key = b"test-key"
    data = b"test-data"
    expected = _hmac.new(key, data, hashlib.sha256).digest()
    result = hmac_sha256(key, data)
    assert result == expected


def test_hmac_sha256_empty_inputs():
    tag = hmac_sha256(b"", b"")
    assert len(tag) == 32


def test_hmac_sha256_deterministic():
    assert hmac_sha256(b"k", b"d") == hmac_sha256(b"k", b"d")


# ---------------------------------------------------------------------------
# Constant-time equality
# ---------------------------------------------------------------------------

def test_constant_time_eq_equal():
    assert constant_time_eq(b"hello", b"hello") is True


def test_constant_time_eq_not_equal():
    assert constant_time_eq(b"hello", b"world") is False


def test_constant_time_eq_different_lengths():
    assert constant_time_eq(b"hello", b"hell") is False


def test_constant_time_eq_empty():
    assert constant_time_eq(b"", b"") is True
    assert constant_time_eq(b"", b"x") is False


# ---------------------------------------------------------------------------
# HKDF-SHA256
# ---------------------------------------------------------------------------

def test_derive_key_hkdf_returns_32_bytes():
    key = derive_key_hkdf(b"seed", b"salt", b"info")
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_derive_key_hkdf_deterministic():
    k1 = derive_key_hkdf(b"seed", b"salt", b"info")
    k2 = derive_key_hkdf(b"seed", b"salt", b"info")
    assert k1 == k2


def test_derive_key_hkdf_different_info():
    k1 = derive_key_hkdf(b"seed", b"salt", b"context-a")
    k2 = derive_key_hkdf(b"seed", b"salt", b"context-b")
    assert k1 != k2


def test_derive_key_hkdf_different_salt():
    k1 = derive_key_hkdf(b"seed", b"salt1", b"info")
    k2 = derive_key_hkdf(b"seed", b"salt2", b"info")
    assert k1 != k2


# ---------------------------------------------------------------------------
# PBKDF2-HMAC-SHA256
# ---------------------------------------------------------------------------

def test_derive_key_pbkdf2_returns_32_bytes():
    key = derive_key_pbkdf2("passphrase", b"saltsalt")
    assert isinstance(key, bytes)
    assert len(key) == 32


def test_derive_key_pbkdf2_deterministic():
    k1 = derive_key_pbkdf2("pass", b"salt")
    k2 = derive_key_pbkdf2("pass", b"salt")
    assert k1 == k2


def test_derive_key_pbkdf2_different_password():
    k1 = derive_key_pbkdf2("pass1", b"salt")
    k2 = derive_key_pbkdf2("pass2", b"salt")
    assert k1 != k2


def test_derive_key_pbkdf2_correct_value():
    """Cross-check against stdlib hashlib for wire-format compatibility."""
    import hashlib as _hashlib

    seed = "test-seed"
    salt = b"test-salt-bytes!"
    expected = _hashlib.pbkdf2_hmac("sha256", seed.encode(), salt, 100_000, dklen=32)
    result = derive_key_pbkdf2(seed, salt)
    assert result == expected


# ---------------------------------------------------------------------------
# Python fallback path
# ---------------------------------------------------------------------------

def test_python_fallback_encrypt_decrypt(monkeypatch):
    """Force the Python fallback path by monkeypatching _USING_RUST to False."""
    import src.security.rust_crypto as rc

    original = rc._USING_RUST
    try:
        rc._USING_RUST = False
        ct = rc.encrypt(b"fallback test", "seed")
        pt = rc.decrypt(ct, "seed")
        assert pt == b"fallback test"
    finally:
        rc._USING_RUST = original


def test_python_fallback_hmac(monkeypatch):
    import src.security.rust_crypto as rc

    original = rc._USING_RUST
    try:
        rc._USING_RUST = False
        tag = rc.hmac_sha256(b"key", b"data")
        assert len(tag) == 32
    finally:
        rc._USING_RUST = original


def test_rust_and_python_produce_interoperable_ciphertext():
    """Rust-encrypted data must be decryptable by the Python path and vice versa."""
    import src.security.rust_crypto as rc

    if not rc._USING_RUST:
        pytest.skip("Rust extension not available — can only test one path")

    key = "interop-key"
    plaintext = b"cross-path message"

    # Encrypt with Rust, decrypt with Python
    rc._USING_RUST = True
    ct_rust = rc.encrypt(plaintext, key)
    rc._USING_RUST = False
    try:
        pt_from_rust = rc.decrypt(ct_rust, key)
        assert pt_from_rust == plaintext

        # Encrypt with Python, decrypt with Rust
        ct_python = rc.encrypt(plaintext, key)
    finally:
        rc._USING_RUST = True
    pt_from_python = rc.decrypt(ct_python, key)
    assert pt_from_python == plaintext
