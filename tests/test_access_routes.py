# tests/test_access_routes.py
# HTTP-level tests for src/access/routes.py (the /access API) and the
# reusable require_location_subscription dependency.

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.access import registry as registry_module
from src.access.registry import CURRENT_TERMS_VERSION, AccessRegistry
from src.access.routes import require_location_subscription
from src.access.routes import router as access_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_registry = AccessRegistry(db_path=tmp_path / "access_routes_test.db")
    monkeypatch.setattr(registry_module, "_registry", test_registry)

    app = FastAPI()
    app.include_router(access_router)

    @app.get("/gated/the-lab")
    def gated_endpoint(current_user: dict = Depends(require_location_subscription("The Lab"))):
        return {"ok": True}

    with TestClient(app) as c:
        yield c
    test_registry.close()


def _override(user_id: str, role: str = "user"):
    def _dep():
        return {"sub": user_id, "role": role}

    return _dep


class TestSelfServiceSubscribe:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.post(
            "/access/The Lab/subscribe",
            json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
        )
        assert resp.status_code in (401, 403)

    def test_any_authenticated_user_can_subscribe_for_self(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["user_id"] == "u1"
            assert body["status"] == "active"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_subscribe_without_accepting_terms_422s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": False, "terms_version": CURRENT_TERMS_VERSION},
            )
            assert resp.status_code == 422
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_subscribe_with_stale_terms_version_422s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": "0.1"},
            )
            assert resp.status_code == 422
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_subscribe_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.post(
                "/access/Nonexistent Place/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_unsubscribe(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            resp = client.request("DELETE", "/access/The Lab/subscribe")
            assert resp.status_code == 200
            assert resp.json()["status"] == "revoked"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestReadOwnStatus:
    def test_get_my_subscription_when_none_exists(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.get("/access/The Lab")
            assert resp.status_code == 200
            assert resp.json()["status"] == "none"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_list_my_subscriptions(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            resp = client.get("/access/me")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["location"] == "The Lab"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_slash_location_status(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.get("/access/ChronosSphere / ArcStream")
            assert resp.status_code == 200
            assert resp.json()["location"] == "ChronosSphere / ArcStream"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_listing_exposes_stale_terms_status(self, client, monkeypatch):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            fresh = client.get("/access/me").json()
            assert fresh[0]["grants_access"] is True
            assert fresh[0]["terms_current"] is True
            # Bump the policy version: the row is now stale — still status
            # 'active' but no longer granting access.
            monkeypatch.setattr("src.access.registry.CURRENT_TERMS_VERSION", "2.0")
            monkeypatch.setattr("src.access.routes.CURRENT_TERMS_VERSION", "2.0")
            stale = client.get("/access/me").json()
            assert stale[0]["status"] == "active"
            assert stale[0]["terms_current"] is False
            assert stale[0]["grants_access"] is False
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_get_my_subscription_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.get("/access/Nonexistent Place")
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_history_route_returns_events(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            client.request("DELETE", "/access/The Lab/subscribe")
            resp = client.get("/access/The Lab/history")
            assert resp.status_code == 200
            actions = [e["action"] for e in resp.json()]
            assert actions == ["revoke", "subscribe"]  # newest first
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_history_route_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1")
        try:
            resp = client.get("/access/Nonexistent Place/history")
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestAdminRevokeRoute:
    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.request("DELETE", "/access/The Lab/subscribers/u2")
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_revoke_another_users_subscription(self, client):
        # u1 subscribes to a gated location.
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            assert client.get("/gated/the-lab").status_code == 200
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        # An admin revokes u1's subscription on their behalf.
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.request("DELETE", "/access/The Lab/subscribers/u1")
            assert resp.status_code == 200
            assert resp.json()["status"] == "revoked"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        # u1 is now blocked by the gate again.
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            assert client.get("/gated/the-lab").status_code == 402
            # And the admin is recorded as the revoking actor in u1's history.
            history = client.get("/access/The Lab/history").json()
            revoke = next(e for e in history if e["action"] == "revoke")
            assert revoke["actor"] == "admin1"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_revoke_unknown_location_404s(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.request("DELETE", "/access/Nonexistent Place/subscribers/u1")
            assert resp.status_code == 404
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestSubscribersRoute:
    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.get("/access/The Lab/subscribers")
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_list_subscribers(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.get("/access/The Lab/subscribers")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["user_id"] == "u1"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestRequireLocationSubscriptionDependency:
    def test_unsubscribed_user_gets_402(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.get("/gated/the-lab")
            assert resp.status_code == 402
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_subscribed_user_gets_through(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            resp = client.get("/gated/the-lab")
            assert resp.status_code == 200
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_bypasses_subscription_requirement(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.get("/gated/the-lab")
            assert resp.status_code == 200
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_revoked_subscription_blocks_again(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            client.post(
                "/access/The Lab/subscribe",
                json={"accepted_terms": True, "terms_version": CURRENT_TERMS_VERSION},
            )
            assert client.get("/gated/the-lab").status_code == 200
            client.request("DELETE", "/access/The Lab/subscribe")
            assert client.get("/gated/the-lab").status_code == 402
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)
