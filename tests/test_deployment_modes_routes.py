# tests/test_deployment_modes_routes.py
# HTTP-level tests for src/deployment_modes/routes.py (the /deployment-modes API).

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.deployment_modes import registry as registry_module
from src.deployment_modes.registry import DeploymentModeRegistry
from src.deployment_modes.routes import router as deployment_modes_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_registry = DeploymentModeRegistry(db_path=tmp_path / "routes_test.db")
    monkeypatch.setattr(registry_module, "_registry", test_registry)

    app = FastAPI()
    app.include_router(deployment_modes_router)
    with TestClient(app) as c:
        yield c
    test_registry.close()


def _override(user_id: str, role: str = "user"):
    def _dep():
        return {"sub": user_id, "role": role}

    return _dep


class TestReadRoutes:
    def test_list_modes_is_public(self, client):
        resp = client.get("/deployment-modes/")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body) == 43

    def test_get_known_mode_defaults_cloud_only(self, client):
        resp = client.get("/deployment-modes/Royal Bank of Arcadia")
        assert resp.status_code == 200
        assert resp.json()["mode"] == "cloud_only"

    def test_get_mode_with_slash_in_location_name(self, client):
        """ChronosSphere / ArcStream is the one canonical location whose name
        contains a literal '/' — the {location:path} route converter must
        resolve it instead of 404ing or matching the wrong route."""
        resp = client.get("/deployment-modes/ChronosSphere / ArcStream")
        assert resp.status_code == 200
        assert resp.json()["location"] == "ChronosSphere / ArcStream"

    def test_history_for_slash_location_does_not_shadow_get(self, client):
        resp = client.get("/deployment-modes/ChronosSphere / ArcStream/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_unknown_mode_404s(self, client):
        resp = client.get("/deployment-modes/Nonexistent Place")
        assert resp.status_code == 404

    def test_history_empty_for_untouched_location(self, client):
        resp = client.get("/deployment-modes/Luminous/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_history_unknown_location_404s(self, client):
        resp = client.get("/deployment-modes/Nonexistent Place/history")
        assert resp.status_code == 404

    def test_list_environments_returns_all_three(self, client):
        resp = client.get("/deployment-modes/The Nexus/environments")
        assert resp.status_code == 200
        body = resp.json()
        assert {e["environment"] for e in body} == {"dev", "uat", "prod"}

    def test_prod_environment_provisioned_by_default(self, client):
        resp = client.get("/deployment-modes/The Nexus/environments")
        prod = next(e for e in resp.json() if e["environment"] == "prod")
        assert prod["provisioned"] is True

    def test_dev_environment_not_provisioned_by_default(self, client):
        resp = client.get("/deployment-modes/The Nexus/environments")
        dev = next(e for e in resp.json() if e["environment"] == "dev")
        assert dev["provisioned"] is False

    def test_environment_history_route_not_shadowed_by_mode_history(self, client):
        """mode_history's bare `{location:path}/history` pattern is greedy
        enough to swallow "<location>/environments/<env>/history" whole if
        registered ahead of environment_history — regression guard for that
        route-ordering bug."""
        resp = client.get("/deployment-modes/The Nexus/environments/dev/history")
        assert resp.status_code == 200
        assert resp.json() == []


class TestSetModeRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.put("/deployment-modes/The Nexus", json={"mode": "hybrid"})
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.put("/deployment-modes/The Nexus", json={"mode": "hybrid"})
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_set_mode(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.put(
                "/deployment-modes/The Nexus",
                json={"mode": "hybrid", "reason": "pilot"},
            )
            assert resp.status_code == 200
            assert resp.json()["mode"] == "hybrid"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_invalid_mode_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.put("/deployment-modes/The Nexus", json={"mode": "not-a-real-mode"})
            assert resp.status_code == 422
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_set_mode_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.put("/deployment-modes/Nonexistent Place", json={"mode": "hybrid"})
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_set_mode_records_history(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.put("/deployment-modes/The HIVE", json={"mode": "local"})
            history = client.get("/deployment-modes/The HIVE/history").json()
            assert len(history) == 1
            assert history[0]["new_mode"] == "local"
            assert history[0]["previous_mode"] == "cloud_only"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestProvisionEnvironmentRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.post(
            "/deployment-modes/The Nexus/environments/dev/provision",
            json={"scoped_by": "rfc-1"},
        )
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.post(
                "/deployment-modes/The Nexus/environments/dev/provision",
                json={"scoped_by": "rfc-1"},
            )
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_provision(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/deployment-modes/The Nexus/environments/dev/provision",
                json={"scoped_by": "think-tank:rfc-042", "reason": "spike"},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["provisioned"] is True
            assert body["scoped_by"] == "think-tank:rfc-042"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_cannot_provision_prod(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/deployment-modes/The Nexus/environments/prod/provision",
                json={"scoped_by": "rfc-1"},
            )
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_missing_scoped_by_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/deployment-modes/The Nexus/environments/dev/provision",
                json={"scoped_by": ""},
            )
            assert resp.status_code == 422
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_provision_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/deployment-modes/Nonexistent Place/environments/dev/provision",
                json={"scoped_by": "rfc-1"},
            )
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestDeprovisionEnvironmentRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.request("DELETE", "/deployment-modes/The Nexus/environments/dev")
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.request("DELETE", "/deployment-modes/The Nexus/environments/dev")
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_deprovision(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post(
                "/deployment-modes/The Nexus/environments/dev/provision",
                json={"scoped_by": "rfc-1"},
            )
            resp = client.request("DELETE", "/deployment-modes/The Nexus/environments/dev")
            assert resp.status_code == 200
            assert resp.json()["provisioned"] is False
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_cannot_deprovision_prod(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.request("DELETE", "/deployment-modes/The Nexus/environments/prod")
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_deprovision_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.request("DELETE", "/deployment-modes/Nonexistent Place/environments/dev")
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)
