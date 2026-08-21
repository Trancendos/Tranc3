# tests/test_zero_trust_mfa_header.py
# Regression test for the MFA header-spoofing fix in src/security/middleware.py.
#
# ZeroTrustASGIMiddleware used to build its ZeroTrustContext straight from
# dict(request.headers) — including X-MFA-Verified, which Traefik never
# strips or validates (infra/traefik/dynamic/mtls.yml only CORS-allowlists
# it). Any caller could set X-MFA-Verified: true on their own request and
# satisfy MFA-gated routes with no real TOTP/backup-code check ever having
# happened. resolve_mfa_verified_header() closes that: X-MFA-Verified is now
# always derived from the signed JWT's mfa_verified claim (set server-side by
# workers/infinity-auth/router.py's login/refresh only after a real MFA
# check), never from the raw client header.

from __future__ import annotations

import secrets

import pytest

from auth import create_token
from src.security.middleware import resolve_mfa_verified_header


@pytest.fixture(autouse=True)
def _jwt_secret(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))


class TestResolveMfaVerifiedHeader:
    def test_spoofed_header_without_token_is_stripped(self):
        """The core regression: a bare client header must not survive."""
        headers = resolve_mfa_verified_header({"X-MFA-Verified": "true"}, authorization="")
        assert headers.get("X-MFA-Verified") != "true"
        assert "x-mfa-verified" not in {k.lower() for k in headers}

    def test_spoofed_header_with_unrelated_token_is_stripped(self):
        """A valid token that never verified MFA must not let the header through."""
        token = create_token(user_id="u1", username="alice")  # no mfa_verified claim
        headers = resolve_mfa_verified_header(
            {"X-MFA-Verified": "true"}, authorization=f"Bearer {token}"
        )
        assert headers.get("X-MFA-Verified") != "true"

    def test_real_mfa_claim_sets_header(self):
        """A token whose mfa_verified claim is True is the only way in."""
        token = create_token(user_id="u1", username="alice", extra={"mfa_verified": True})
        headers = resolve_mfa_verified_header({}, authorization=f"Bearer {token}")
        assert headers.get("X-MFA-Verified") == "true"

    def test_false_mfa_claim_does_not_set_header(self):
        token = create_token(user_id="u1", username="alice", extra={"mfa_verified": False})
        headers = resolve_mfa_verified_header(
            {"X-MFA-Verified": "true"}, authorization=f"Bearer {token}"
        )
        assert headers.get("X-MFA-Verified") != "true"

    def test_malformed_token_fails_safe(self):
        headers = resolve_mfa_verified_header(
            {"X-MFA-Verified": "true"}, authorization="Bearer not-a-real-token"
        )
        assert headers.get("X-MFA-Verified") != "true"

    def test_other_headers_pass_through_unchanged(self):
        headers = resolve_mfa_verified_header(
            {"X-Device-Posture": "healthy", "X-Client-Country": "US"}, authorization=""
        )
        assert headers["X-Device-Posture"] == "healthy"
        assert headers["X-Client-Country"] == "US"
