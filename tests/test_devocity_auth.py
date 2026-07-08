"""Tests for auth enforcement on DevOcity routes (src/devocity/routes.py).

Guards against regressing to the previous behaviour where account creation,
API key issuance (including admin/full scopes), key revocation, and webhook
registration were reachable by anyone who knew or guessed an account_id.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.devocity.portal import get_devocity
from src.devocity.routes import router as devocity_router

app = FastAPI()
app.include_router(devocity_router)
client = TestClient(app)


def _override(user_id: str, tier: str = "free"):
    def _dep():
        return {"id": user_id, "tier": tier}

    return _dep


def test_status_is_public():
    resp = client.get("/devocity/status")
    assert resp.status_code == 200


def test_create_account_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.post("/devocity/accounts", json={"user_id": "u1"})
    assert resp.status_code in (401, 403)


def test_user_can_create_own_account():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/devocity/accounts", json={"user_id": "u1"})
        assert resp.status_code == 200
        assert resp.json()["user_id"] == "u1"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_user_cannot_create_account_for_others():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/devocity/accounts", json={"user_id": "u2"})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_user_cannot_access_others_account():
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        account_id = client.post("/devocity/accounts", json={"user_id": "owner"}).json()["id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    app.dependency_overrides[get_current_user] = _override("intruder")
    try:
        resp = client.get(f"/devocity/accounts/{account_id}")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_user_cannot_issue_admin_key_on_others_account():
    app.dependency_overrides[get_current_user] = _override("owner2")
    try:
        account_id = client.post("/devocity/accounts", json={"user_id": "owner2"}).json()["id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    app.dependency_overrides[get_current_user] = _override("intruder2")
    try:
        resp = client.post(
            f"/devocity/accounts/{account_id}/keys",
            json={"name": "stolen", "scopes": ["admin", "full"]},
        )
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_owner_can_issue_key_on_own_account():
    app.dependency_overrides[get_current_user] = _override("owner3")
    try:
        account_id = client.post("/devocity/accounts", json={"user_id": "owner3"}).json()["id"]
        resp = client.post(
            f"/devocity/accounts/{account_id}/keys",
            json={"name": "mine", "scopes": ["read"]},
        )
        assert resp.status_code == 200
        assert "key" in resp.json()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_enterprise_can_access_any_account():
    app.dependency_overrides[get_current_user] = _override("owner4")
    try:
        account_id = client.post("/devocity/accounts", json={"user_id": "owner4"}).json()["id"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    app.dependency_overrides[get_current_user] = _override("admin", tier="enterprise")
    try:
        resp = client.get(f"/devocity/accounts/{account_id}")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_devocity_singleton_isolated():
    assert get_devocity() is get_devocity()
