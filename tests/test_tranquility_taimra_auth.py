"""Tests for auth enforcement on Tranquility and tAimra routes.

Guards against regressing to the previous behaviour where every route taking
a user_id path parameter (mood logs, digital-twin export/delete, etc.) was
reachable by anyone with no authentication at all.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.taimra.routes import router as taimra_router
from src.tranquility.routes import router as tranquility_router

app = FastAPI()
app.include_router(tranquility_router)
app.include_router(taimra_router)
client = TestClient(app)


def _override(user_id: str, role: str = "user"):
    """Real JWT payloads (src/auth/tokens.py) carry the caller's identity under
    "sub", not "id", and "tier" as a numeric int, never the string
    "enterprise" — override with the real shape so these tests exercise what
    callers actually get, not a shape that happens to match the code under
    test."""

    def _dep():
        return {"sub": user_id, "tier": 0, "role": role}

    return _dep


def test_tranquility_status_is_public():
    resp = client.get("/tranquility/status")
    assert resp.status_code == 200


def test_taimra_status_is_public():
    resp = client.get("/taimra/status")
    assert resp.status_code == 200


def test_tranquility_mood_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.post("/tranquility/mood/u1", json={"mood": 3})
    assert resp.status_code in (401, 403)


def test_taimra_twin_requires_auth():
    app.dependency_overrides.pop(get_current_user, None)
    resp = client.get("/taimra/twin/u1")
    assert resp.status_code in (401, 403)


def test_tranquility_user_can_access_own_mood():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/tranquility/mood/u1", json={"mood": 3})
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_tranquility_user_cannot_access_others_mood():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/tranquility/mood/u2", json={"mood": 3})
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_tranquility_admin_can_access_any_user():
    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        resp = client.get("/tranquility/export/some-other-user")
        assert resp.status_code in (200, 404)
        assert resp.status_code != 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_taimra_user_can_activate_own_twin():
    app.dependency_overrides[get_current_user] = _override("u3")
    try:
        resp = client.post("/taimra/activate/u3")
        assert resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_taimra_user_cannot_activate_others_twin():
    app.dependency_overrides[get_current_user] = _override("u3")
    try:
        resp = client.post("/taimra/activate/u4")
        assert resp.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_taimra_admin_can_delete_any_twin():
    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        resp = client.delete("/taimra/twin/some-other-user")
        assert resp.status_code in (200, 404)
        assert resp.status_code != 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)
