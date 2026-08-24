# tests/test_zero_trust_asgi_enforcement.py
# Regression test for a second bug cubic-dev-ai found in the MFA header-spoofing fix:
# resolve_mfa_verified_header() correctly stopped trusting the client's X-MFA-Verified
# header, which makes an unauthenticated request to an MFA-gated route resolve to
# AccessPolicy.MFA_REQUIRED — but ZeroTrustASGIMiddleware.dispatch() only ever rejected
# on AccessPolicy.DENY, so MFA_REQUIRED fell through to call_next() same as ALLOW. The
# route was never actually protected, before or after the header fix. This verifies
# MFA_REQUIRED is now rejected (401) and a verified session still passes (200).

from __future__ import annotations

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import create_token
from src.security.middleware import ZeroTrustASGIMiddleware


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("ZERO_TRUST_ENABLED", "true")
    monkeypatch.setenv("ZERO_TRUST_MFA_ROUTES", "/admin")

    app = FastAPI()
    app.add_middleware(ZeroTrustASGIMiddleware)

    @app.get("/admin")
    async def admin():
        return {"ok": True}

    @app.post("/auth/register")
    async def register():
        return {"ok": True}

    @app.post("/auth/token")
    async def token():
        return {"ok": True}

    with TestClient(app) as c:
        yield c


class TestMfaRouteActuallyEnforced:
    def test_no_token_is_rejected_not_allowed_through(self, client):
        resp = client.get("/admin")
        assert resp.status_code == 401
        assert "MFA" in resp.json()["error"]

    def test_spoofed_header_without_token_is_rejected(self, client):
        resp = client.get("/admin", headers={"X-MFA-Verified": "true"})
        assert resp.status_code == 401

    def test_token_without_mfa_claim_is_rejected(self, client):
        token = create_token(user_id="u1", username="alice")
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401

    def test_token_with_real_mfa_claim_is_allowed(self, client):
        token = create_token(user_id="u1", username="alice", extra={"mfa_verified": True})
        resp = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}


class TestOrdinaryRoutesNotMfaGated:
    """
    Regression for a second bug cubic-dev-ai found in the MFA enforcement fix (P1,
    confidence 10): rejecting on AccessPolicy.MFA_REQUIRED without first resetting the
    Zero Trust decision meant *every* unauthenticated request — not just configured
    mfa_routes — inherited ZeroTrustMiddleware.extract_context()'s tentative default of
    MFA_REQUIRED (see src/auth/zero_trust.py's _determine_policy()), including bootstrap
    endpoints like /auth/register and /auth/token that have no business being MFA-gated.
    """

    def test_register_route_not_blocked_without_mfa(self, client):
        resp = client.post("/auth/register")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_token_route_not_blocked_without_mfa(self, client):
        resp = client.post("/auth/token")
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_admin_route_still_requires_mfa(self, client):
        """The fix for the false-positive must not regress the real MFA gate."""
        resp = client.get("/admin")
        assert resp.status_code == 401
