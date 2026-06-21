"""
test_router.py — Integration-style tests for router.py
========================================================
Uses FastAPI TestClient against a minimal app built from the router.

NOTE: Full integration tests require Dimensional stubs (provided by conftest).
The tests here focus on route registration, response shapes, and error codes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

SERVICE_DIR = Path(__file__).parent.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


# ---------------------------------------------------------------------------
# Minimal test app fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def test_app(stub_dimensional, in_memory_db):
    """Build a minimal FastAPI test app with just the portal router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import router as router_module

    # Inject stubs into the router module
    router_module._sentinel = stub_dimensional["sentinel"]
    router_module._worker_kit = stub_dimensional["worker_kit"]

    app = FastAPI()
    app.include_router(router_module.router)

    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# /portal/status
# ---------------------------------------------------------------------------


class TestPortalStatus:
    def test_returns_200(self, test_app):
        response = test_app.get("/portal/status")
        assert response.status_code == 200

    def test_response_has_expected_fields(self, test_app):
        data = test_app.get("/portal/status").json()
        assert "status" in data
        assert "portal_name" in data
        assert "active_sessions" in data
        assert data["portal_name"] == "Infinity Portal"


# ---------------------------------------------------------------------------
# /portal/locations
# ---------------------------------------------------------------------------


class TestPortalLocations:
    def test_returns_200(self, test_app):
        response = test_app.get("/portal/locations")
        assert response.status_code == 200

    def test_response_has_locations_list(self, test_app):
        data = test_app.get("/portal/locations").json()
        assert "locations" in data
        assert "total" in data


# ---------------------------------------------------------------------------
# /portal/gate-info
# ---------------------------------------------------------------------------


class TestGateInfo:
    def test_returns_200(self, test_app):
        response = test_app.get("/portal/gate-info")
        assert response.status_code == 200

    def test_response_has_routing_rules(self, test_app):
        data = test_app.get("/portal/gate-info").json()
        assert "routing_rules" in data
        assert "gate_name" in data
        assert data["gate_name"] == "Infinity Gate"


# ---------------------------------------------------------------------------
# /portal/sessions (no auth enforced in test app)
# ---------------------------------------------------------------------------


class TestPortalSessions:
    def test_returns_200(self, test_app):
        response = test_app.get("/portal/sessions")
        assert response.status_code == 200

    def test_response_shape(self, test_app):
        data = test_app.get("/portal/sessions").json()
        assert "sessions" in data
        assert isinstance(data["sessions"], list)


# ---------------------------------------------------------------------------
# /portal/events
# ---------------------------------------------------------------------------


class TestPortalEvents:
    def test_returns_200(self, test_app):
        response = test_app.get("/portal/events")
        assert response.status_code == 200

    def test_response_shape(self, test_app):
        data = test_app.get("/portal/events").json()
        assert "events" in data


# ---------------------------------------------------------------------------
# /portal/routing-history
# ---------------------------------------------------------------------------


class TestRoutingHistory:
    def test_returns_200(self, test_app):
        response = test_app.get("/portal/routing-history")
        assert response.status_code == 200

    def test_response_shape(self, test_app):
        data = test_app.get("/portal/routing-history").json()
        assert "routing_history" in data


# ---------------------------------------------------------------------------
# /portal/login — happy path with mocked auth service
# ---------------------------------------------------------------------------


class TestPortalLogin:
    def test_login_delegates_to_auth_service(self, test_app, stub_dimensional):
        fake_auth_result = {
            "user_id": "u1",
            "username": "testuser",
            "role": "user",
            "access_token": "access_tok",
            "refresh_token": "refresh_tok",
            "expires_in": 3600,
        }
        with patch("service.call_auth_service", new=AsyncMock(return_value=fake_auth_result)):
            response = test_app.post(
                "/portal/login",
                json={"username": "testuser", "password": "secret"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["access_token"] == "access_tok"
        assert "session_id" in data
        assert "routed_to" in data

    def test_login_blocked_by_defense_layer(self, test_app, stub_dimensional):
        stub_dimensional["worker_kit"].defense.evaluate_request = AsyncMock(
            return_value=MagicMock(allowed=False, reason="IP blocked")
        )
        response = test_app.post(
            "/portal/login",
            json={"username": "bad", "password": "actor"},
        )
        assert response.status_code == 429


# ---------------------------------------------------------------------------
# /portal/register — happy path
# ---------------------------------------------------------------------------


class TestPortalRegister:
    def test_register_returns_session(self, test_app, stub_dimensional):
        fake_auth_result = {
            "user_id": "u2",
            "username": "newuser",
            "role": "user",
            "access_token": "access_tok2",
            "refresh_token": "refresh_tok2",
            "expires_in": 3600,
        }
        with patch("service.call_auth_service", new=AsyncMock(return_value=fake_auth_result)):
            response = test_app.post(
                "/portal/register",
                json={
                    "username": "newuser",
                    "email": "new@example.com",
                    "password": "password123",
                },
            )
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "newuser"
        assert "session_id" in data


# ---------------------------------------------------------------------------
# /portal/logout
# ---------------------------------------------------------------------------


class TestPortalLogout:
    def test_logout_returns_redirect(self, test_app):
        response = test_app.post("/portal/logout")
        assert response.status_code == 200
        data = response.json()
        assert "redirect" in data
        assert data["redirect"] == "/portal/login"
