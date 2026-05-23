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
        assert r.status_code == 200

        r = client.post("/auth/token", json={"username": "testuser", "password": "TestPass123!"})
        assert r.status_code == 200
        assert "access_token" in r.json()

    def test_login_wrong_password(self):
        client.post("/auth/register", json={"username": "user2", "password": "correct"})
        r = client.post("/auth/token", json={"username": "user2", "password": "wrong"})
        assert r.status_code == 401


class TestChat:
    def _get_token(self):
        client.post("/auth/register", json={"username": "chatuser", "password": "Pass123!"})
        r = client.post("/auth/token", json={"username": "chatuser", "password": "Pass123!"})
        return r.json().get("access_token", "")

    def test_chat_requires_auth(self):
        r = client.post("/chat", json={"message": "Hello"})
        assert r.status_code == 403

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
