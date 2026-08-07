# tests/test_zero_trust_asgi_enforcement.py
# Regression test for a second bug cubic-dev-ai found in the MFA header-spoofing fix:
# resolve_mfa_verified_header() correctly stopped trusting the client's X-MFA-Verified
# header, which makes an unauthenticated request to an MFA-gated route resolve to
# AccessPolicy.MFA_REQUIRED — but ZeroTrustASGIMiddleware.dispatch() only ever rejected
# on AccessPolicy.DENY, so MFA_REQUIRED fell through to call_next() same as ALLOW. The
# route was never actually protected, before or after the header fix. This verifies
# MFA_REQUIRED is now rejected (401) and a verified session still passes (200).

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import create_token
from src.security.middleware import ZeroTrustASGIMiddleware


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-unit-tests-00003")
    monkeypatch.setenv("ZERO_TRUST_ENABLED", "true")
    monkeypatch.setenv("ZERO_TRUST_MFA_ROUTES", "/admin")

    app = FastAPI()
    app.add_middleware(ZeroTrustASGIMiddleware)

    @app.get("/admin")
    async def admin():
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
