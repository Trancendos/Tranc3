# tests/test_trusted_proxy.py
# Regression tests for the residual Zero Trust gap: X-Device-Posture and
# X-Client-Country were client-supplied headers Traefik never strips, so a
# peer already inside tranc3-net (e.g. a compromised sibling container) could
# call a worker directly and set X-Device-Posture: healthy /
# X-Client-Country: <allowed> to escalate trust — the same class of bug the
# MFA header fix closed, but with no JWT claim to substitute. See
# src/security/trusted_proxy.py's module docstring for the full design.

from __future__ import annotations

import secrets

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.security.middleware import ZeroTrustASGIMiddleware
from src.security.trusted_proxy import (
    is_trusted_proxy_peer,
    sanitize_zero_trust_client_headers,
)


class TestIsTrustedProxyPeer:
    def test_missing_peer_is_not_trusted(self):
        assert is_trusted_proxy_peer(None) is False
        assert is_trusted_proxy_peer("") is False

    def test_unparsable_peer_is_not_trusted(self):
        assert is_trusted_proxy_peer("testclient") is False

    def test_configured_cidr_is_trusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.28.0.0/16")
        assert is_trusted_proxy_peer("172.28.5.7") is True

    def test_address_outside_configured_cidr_is_not_trusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.28.0.0/16")
        assert is_trusted_proxy_peer("10.0.0.5") is False

    def test_invalid_cidr_entry_is_ignored_not_fatal(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "not-a-cidr, 172.28.0.0/16")
        assert is_trusted_proxy_peer("172.28.5.7") is True

    def test_unresolvable_hostname_is_not_trusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOSTNAMES", "no-such-host-in-this-test.invalid")
        monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
        assert is_trusted_proxy_peer("172.28.5.7") is False

    def test_hostname_resolving_to_peer_is_trusted(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_HOSTNAMES", "localhost")
        monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
        assert is_trusted_proxy_peer("127.0.0.1") is True


class TestSanitizeZeroTrustClientHeaders:
    def test_untrusted_peer_has_headers_stripped(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
        monkeypatch.setenv("TRUSTED_PROXY_HOSTNAMES", "no-such-host-in-this-test.invalid")
        headers = sanitize_zero_trust_client_headers(
            {"X-Device-Posture": "healthy", "X-Client-Country": "US"},
            peer_ip="172.28.9.9",
        )
        assert "X-Device-Posture" not in headers
        assert "X-Client-Country" not in headers

    def test_trusted_peer_headers_pass_through(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXY_CIDRS", "172.28.0.0/16")
        headers = sanitize_zero_trust_client_headers(
            {"X-Device-Posture": "healthy", "X-Client-Country": "US"},
            peer_ip="172.28.9.9",
        )
        assert headers["X-Device-Posture"] == "healthy"
        assert headers["X-Client-Country"] == "US"

    def test_unrelated_headers_always_pass_through(self, monkeypatch):
        monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
        monkeypatch.setenv("TRUSTED_PROXY_HOSTNAMES", "no-such-host-in-this-test.invalid")
        headers = sanitize_zero_trust_client_headers(
            {"Authorization": "Bearer x", "X-Device-Posture": "healthy"},
            peer_ip="172.28.9.9",
        )
        assert headers["Authorization"] == "Bearer x"
        assert "X-Device-Posture" not in headers


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
    monkeypatch.setenv("ZERO_TRUST_ENABLED", "true")
    monkeypatch.setenv("ZERO_TRUST_MFA_ROUTES", "/admin")
    # TestClient's peer is never a real Docker address, so with no CIDR/hostname
    # override these requests are always "untrusted peer" — exactly the
    # compromised-sibling-container scenario this fix defends against.
    monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
    monkeypatch.setenv("TRUSTED_PROXY_HOSTNAMES", "no-such-host-in-this-test.invalid")

    app = FastAPI()
    app.add_middleware(ZeroTrustASGIMiddleware)

    @app.get("/admin")
    async def admin():
        return {"ok": True}

    with TestClient(app) as c:
        yield c


class TestAsgiIntegration:
    def test_spoofed_healthy_posture_from_untrusted_peer_no_longer_bypasses_mfa(self, client):
        """The core regression: before this fix, ZeroTrustASGIMiddleware built
        its context straight from request headers, so any caller — including
        one reaching the worker directly over tranc3-net rather than through
        Traefik — could set X-Device-Posture: healthy and use
        mfa_bypass_for_healthy to skip MFA on a gated route entirely."""
        resp = client.get("/admin", headers={"X-Device-Posture": "healthy"})
        assert resp.status_code == 401

    def test_country_header_is_gone_by_evaluation_time_for_untrusted_peer(self, monkeypatch):
        """End-to-end confirmation that X-Client-Country from an untrusted
        peer never reaches ZeroTrustMiddleware.evaluate(): configuring
        ZERO_TRUST_BLOCKED_COUNTRIES=US and then claiming X-Client-Country: US
        must NOT get denied on that basis, because the header was stripped
        before extract_context() ever saw it — proving the sanitize step is
        wired into the real ASGI request path, not just unit-tested in
        isolation."""
        monkeypatch.setenv("JWT_SECRET", secrets.token_hex(32))
        monkeypatch.setenv("ZERO_TRUST_ENABLED", "true")
        monkeypatch.setenv("ZERO_TRUST_MFA_ROUTES", "")
        monkeypatch.setenv("ZERO_TRUST_BLOCKED_COUNTRIES", "US")
        monkeypatch.delenv("TRUSTED_PROXY_CIDRS", raising=False)
        monkeypatch.setenv("TRUSTED_PROXY_HOSTNAMES", "no-such-host-in-this-test.invalid")

        app = FastAPI()
        app.add_middleware(ZeroTrustASGIMiddleware)

        @app.get("/open")
        async def open_route():
            return {"ok": True}

        with TestClient(app) as c:
            resp = c.get("/open", headers={"X-Client-Country": "US"})
            assert resp.status_code == 200
