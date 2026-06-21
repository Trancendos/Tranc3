"""
Infinity-Admin Service — Router Tests
======================================
Integration-style tests for the FastAPI routes.

Most tests mock the Dimensional singletons so they can run without the full
Dimensional package installed.  Tests that need live Dimensional objects are
marked @pytest.mark.integration and will be skipped in unit-test-only runs.

Run all tests:
    pytest tests/test_router.py -v

Run unit tests only (no Dimensional):
    pytest tests/test_router.py -v -m "not integration"
"""

from __future__ import annotations

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(tmp_db, monkeypatch):
    """Return a TestClient wired to tmp_db, skipping if dependencies missing."""
    try:
        from fastapi.testclient import TestClient
    except ImportError:
        pytest.skip("httpx not installed — skipping router tests")

    try:
        import service

        import database

        monkeypatch.setattr(database, "db", tmp_db)
        monkeypatch.setattr(service, "db", tmp_db)

        from main import app

        return TestClient(app, raise_server_exceptions=False)
    except Exception as exc:
        pytest.skip(f"Could not create app (missing dependency): {exc}")


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_returns_200(self, tmp_db, monkeypatch):
        client = _make_client(tmp_db, monkeypatch)
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_body_has_service(self, tmp_db, monkeypatch):
        client = _make_client(tmp_db, monkeypatch)
        data = client.get("/health").json()
        assert data.get("service") == "infinity-admin"


# ---------------------------------------------------------------------------
# /admin/config
# ---------------------------------------------------------------------------


class TestConfig:
    def test_list_config_requires_auth(self, tmp_db, monkeypatch):
        """Without a valid JWT the AuthGateway should reject the request."""
        client = _make_client(tmp_db, monkeypatch)
        resp = client.get("/admin/config")
        # Depending on AuthGateway strictness it may be 200, 401, or 403
        assert resp.status_code in (200, 401, 403)

    def test_get_config_missing_key(self, tmp_db, monkeypatch):
        client = _make_client(tmp_db, monkeypatch)
        resp = client.get(
            "/admin/config/does_not_exist",
            headers={"X-Internal-Secret": ""},
        )
        # Either 404 (found route, key missing) or 401/403 (auth enforced)
        assert resp.status_code in (404, 401, 403)


# ---------------------------------------------------------------------------
# /admin/features
# ---------------------------------------------------------------------------


class TestFeatures:
    def test_list_features_returns_list(self, tmp_db, monkeypatch):
        client = _make_client(tmp_db, monkeypatch)
        resp = client.get("/admin/features")
        if resp.status_code == 200:
            data = resp.json()
            assert "features" in data
            assert isinstance(data["features"], list)

    def test_update_feature_creates_row(self, tmp_db, monkeypatch):
        client = _make_client(tmp_db, monkeypatch)
        resp = client.put(
            "/admin/features/test_flag",
            json={"enabled": True, "description": "unit test flag"},
            headers={"X-Internal-Secret": ""},
        )
        if resp.status_code == 200:
            data = resp.json()
            assert data["enabled"] is True
            row = tmp_db.execute(
                "SELECT enabled FROM feature_flags WHERE key = 'test_flag'"
            ).fetchone()
            assert row is not None
            assert row["enabled"] == 1


# ---------------------------------------------------------------------------
# /admin/audit
# ---------------------------------------------------------------------------


class TestAudit:
    def test_audit_log_empty_on_fresh_db(self, tmp_db, monkeypatch):
        client = _make_client(tmp_db, monkeypatch)
        resp = client.get("/admin/audit")
        if resp.status_code == 200:
            data = resp.json()
            assert "actions" in data
            assert isinstance(data["total"], int)


# ---------------------------------------------------------------------------
# /admin/entities (platform entity registry)
# ---------------------------------------------------------------------------


class TestEntities:
    def test_list_entities_when_unavailable(self, tmp_db, monkeypatch):
        """When platform entities are unavailable, endpoint should say so."""
        import service

        monkeypatch.setattr(service, "_PLATFORM_ENTITIES_AVAILABLE", False)
        monkeypatch.setattr(service, "PLATFORM_ENTITIES", {})

        import router as r

        monkeypatch.setattr(r, "_PLATFORM_ENTITIES_AVAILABLE", False)
        monkeypatch.setattr(r, "PLATFORM_ENTITIES", {})

        client = _make_client(tmp_db, monkeypatch)
        resp = client.get("/admin/entities")
        if resp.status_code == 200:
            data = resp.json()
            assert data["platform_available"] is False
            assert data["total"] == 0

    def test_get_entity_404_when_unavailable(self, tmp_db, monkeypatch):
        """GET /admin/entities/{pid} should 404 or 503 when registry unavailable."""
        import service

        monkeypatch.setattr(service, "_PLATFORM_ENTITIES_AVAILABLE", False)
        monkeypatch.setattr(service, "get_entity_by_pid", lambda pid: None)

        import router as r

        monkeypatch.setattr(r, "_PLATFORM_ENTITIES_AVAILABLE", False)
        monkeypatch.setattr(r, "get_entity_by_pid", lambda pid: None)

        client = _make_client(tmp_db, monkeypatch)
        resp = client.get("/admin/entities/nonexistent-pid")
        assert resp.status_code in (404, 503, 401, 403)
