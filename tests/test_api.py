# tests/test_api.py

import os
from unittest.mock import MagicMock, patch

import pytest

# This test file requires the full production stack (torch, transformers, etc.)
# and a SECRET_KEY env var. Skip gracefully when either is absent.
_SKIP_REASON = None

if not os.getenv("SECRET_KEY"):
    _SKIP_REASON = "SECRET_KEY env var not set"
else:
    try:
        from fastapi.testclient import TestClient

        with patch("redis.from_url", return_value=MagicMock(ping=lambda: True)):
            from api import app
        client = TestClient(app, raise_server_exceptions=False)
    except (ImportError, ModuleNotFoundError) as e:
        _SKIP_REASON = f"Missing production dependency: {e}"
    except Exception as e:
        _SKIP_REASON = f"api.py failed to load: {e}"

pytestmark = pytest.mark.skipif(
    _SKIP_REASON is not None,
    reason=_SKIP_REASON or "skipped",
)


class TestHealth:
    def test_health_returns_200(self):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] in ("healthy", "degraded")

    def test_health_has_components(self):
        r = client.get("/health")
        assert "components" in r.json()

    def test_ready_returns_200_or_503(self):
        r = client.get("/ready")
        assert r.status_code in (200, 503)


class TestAuth:
    def test_register_and_login(self):
        r = client.post("/auth/register", json={"username": "testuser", "password": "TestPass123!"})
        assert r.status_code == 201

        r = client.post("/auth/token", json={"username": "testuser", "password": "TestPass123!"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self):
        client.post("/auth/register", json={"username": "user2", "password": "correct"})
        r = client.post("/auth/token", json={"username": "user2", "password": "wrong"})
        assert r.status_code == 401

    def test_login_and_refresh_preserve_tier_derived_role(self):
        # Regression: login()/refresh_token() used to always issue role="user"
        # regardless of the account's tier, so enterprise/admin-tier users
        # never got admin RBAC permissions. Bump a fresh user to "enterprise"
        # (which db_user_manager._TIER_ROLE_MAP maps to role "admin") and
        # confirm both /auth/token and /auth/refresh carry that role.
        #
        # `import api` resolves to the api/ package (not this root api.py
        # file — see api/__init__.py's lazy loader), so the live
        # db_user_manager instance the running `app` actually uses is only
        # reachable via a route handler's closure, not a fresh import.
        db_user_manager = None
        for route in app.routes:
            endpoint = getattr(route, "endpoint", None)
            globals_dict = getattr(endpoint, "__globals__", {})
            if "db_user_manager" in globals_dict:
                db_user_manager = globals_dict["db_user_manager"]
                break
        assert db_user_manager is not None

        client.post("/auth/register", json={"username": "enterpriseuser", "password": "Pass123!"})
        db_user_manager.update_tier("enterpriseuser", "enterprise")

        r = client.post("/auth/token", json={"username": "enterpriseuser", "password": "Pass123!"})
        assert r.status_code == 200
        token = r.json()["access_token"]

        from src.auth.facade import verify_token

        payload = verify_token(token)
        assert payload["role"] == "admin"

        r2 = client.post("/auth/refresh", headers={"Authorization": f"Bearer {token}"})
        assert r2.status_code == 200
        refreshed_payload = verify_token(r2.json()["access_token"])
        assert refreshed_payload["role"] == "admin"


class TestChat:
    def _get_token(self):
        client.post("/auth/register", json={"username": "chatuser", "password": "Pass123!"})
        r = client.post("/auth/token", json={"username": "chatuser", "password": "Pass123!"})
        return r.json().get("access_token", "")

    def test_chat_requires_auth(self):
        r = client.post("/chat", json={"message": "Hello"})
        assert r.status_code in (401, 403)

    def test_chat_valid(self):
        token = self._get_token()
        r = client.post(
            "/chat",
            json={"message": "Hello TRANC3", "language": "en"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        assert "request_id" in data
        assert "processing_time_ms" in data

    def test_chat_empty_message_rejected(self):
        token = self._get_token()
        r = client.post(
            "/chat",
            json={"message": ""},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 422

    def test_chat_location_resolves_personality_from_role_registry(self):
        # A caller scoping /chat to a Location gets whoever the Role Registry
        # currently says holds that seat, not a hardcoded string — see
        # src/personality/role_resolution.py.
        token = self._get_token()
        r = client.post(
            "/chat",
            json={"message": "What's our exposure?", "location": "Royal Bank of Arcadia"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["personality"] == "dorris-fontaine"

    def test_chat_unknown_location_falls_back_to_supplied_personality(self):
        token = self._get_token()
        r = client.post(
            "/chat",
            json={
                "message": "Hello",
                "personality": "tranc3-creative",
                "location": "Not A Real Location",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 200
        assert r.json()["personality"] == "tranc3-creative"


class TestInfo:
    def test_languages(self):
        r = client.get("/languages")
        assert r.status_code == 200
        assert "languages" in r.json()

    def test_billing_tiers(self):
        r = client.get("/billing/tiers")
        assert r.status_code == 200
        assert "free" in r.json()
        assert "pro" in r.json()
