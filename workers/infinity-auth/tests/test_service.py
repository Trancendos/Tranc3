"""
Infinity Auth — Service layer unit tests
=========================================
Tests for password hashing, JWT creation/validation,
TOTP helpers, rate limiting, and role/tier mapping.
"""

from __future__ import annotations

# ── Password hashing ───────────────────────────────────────────────────────────


def test_hash_and_verify_password():
    from service import hash_password, verify_password

    pw = "correct-horse-battery-staple"
    h = hash_password(pw)
    assert verify_password(pw, h)
    assert not verify_password("wrong", h)


def test_verify_pbkdf2_hash():
    """PBKDF2 fallback format must round-trip correctly."""
    import hashlib  # noqa: E401
    import os

    salt = os.urandom(32)
    dk = hashlib.pbkdf2_hmac("sha256", b"mypassword", salt, 260000)
    stored = f"pbkdf2:{salt.hex()}:{dk.hex()}"
    from service import verify_password

    assert verify_password("mypassword", stored)
    assert not verify_password("wrong", stored)


def test_hash_backup_code_deterministic():
    """Same code must always produce the same hash."""
    from service import hash_backup_code

    assert hash_backup_code("ABCD1234") == hash_backup_code("ABCD1234")
    assert hash_backup_code("ABCD1234") == hash_backup_code("abcd1234")  # upper-cased


# ── JWT ───────────────────────────────────────────────────────────────────────


def test_create_and_decode_access_token():
    from service import create_access_token, decode_access_token

    token = create_access_token("uid-1", "alice", role="user")
    payload = decode_access_token(token)
    assert payload is not None
    assert payload["sub"] == "uid-1"
    assert payload["username"] == "alice"
    assert payload["role"] == "user"


def test_decode_invalid_token_returns_none():
    from service import decode_access_token

    assert decode_access_token("not.a.valid.token") is None


def test_create_refresh_token_is_unique():
    from service import create_refresh_token

    tokens = {create_refresh_token() for _ in range(20)}
    assert len(tokens) == 20  # all unique


# ── Role/tier mapping ─────────────────────────────────────────────────────────


def test_get_tier_for_known_roles():
    from service import get_tier_for_role

    # These just need to not raise and return a Tier object
    for role in ("admin", "user", "developer", "prime", "ai", "agent", "bot", "service"):
        t = get_tier_for_role(role)
        assert t is not None


def test_get_infinity_role_for_known_roles():
    from service import get_infinity_role_for_role

    for role in ("admin", "user", "prime", "ai", "agent", "bot", "service"):
        ir = get_infinity_role_for_role(role)
        assert ir is not None


def test_unknown_role_falls_back_to_human():
    from service import get_tier_for_role

    from shared_core.infinity.nomenclature import Tier

    assert get_tier_for_role("unknown-role") == Tier.HUMAN


# ── Rate limiter ──────────────────────────────────────────────────────────────


def test_rate_limiter_allows_up_to_limit():
    from service import RateLimiter

    rl = RateLimiter(max_requests=3, window_seconds=60)
    assert rl.is_allowed("ip1")
    assert rl.is_allowed("ip1")
    assert rl.is_allowed("ip1")
    assert not rl.is_allowed("ip1")  # 4th request in window → denied


def test_rate_limiter_different_keys_independent():
    from service import RateLimiter

    rl = RateLimiter(max_requests=1, window_seconds=60)
    assert rl.is_allowed("ip1")
    assert not rl.is_allowed("ip1")
    assert rl.is_allowed("ip2")  # different key — unaffected


# ── TOTP helpers ──────────────────────────────────────────────────────────────


def test_generate_totp_secret_is_base32():
    import re

    from service import generate_totp_secret

    secret = generate_totp_secret()
    assert re.match(r"^[A-Z2-7]+=*$", secret), f"Not base32: {secret}"


def test_verify_totp_with_current_code():
    import pyotp
    from service import generate_totp_secret, verify_totp

    secret = generate_totp_secret()
    valid_code = pyotp.TOTP(secret).now()
    assert verify_totp(secret, valid_code)


def test_generate_backup_codes_count_and_hash():
    from service import generate_backup_codes, hash_backup_code

    plain, hashed = generate_backup_codes(5)
    assert len(plain) == 5
    assert len(hashed) == 5
    for p, h in zip(plain, hashed, strict=False):
        assert hash_backup_code(p) == h


def test_generate_totp_provisioning_uri():
    from service import generate_totp_provisioning_uri, generate_totp_secret

    secret = generate_totp_secret()
    uri = generate_totp_provisioning_uri(secret, "alice")
    assert uri.startswith("otpauth://totp/")
    assert "alice" in uri
    assert "Trancendos" in uri
