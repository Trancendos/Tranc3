"""Tests for auth enforcement on the six previously-unauthenticated in-repo
routers flagged by the Security Matrix (docs/compliance/SECURITY-MATRIX.md,
MC-015): src/artifactory, src/library, src/studio, src/imind, src/vrar3d,
src/resonate (covered separately in tests/test_resonate_escalation.py).

These five manage shared/global resources (artifacts, articles, jobs,
sensitivity assessments, scenes) with no per-user ownership concept, so each
route now requires only an authenticated caller (Depends(get_current_user))
rather than the ownership-scoped `_require_self_or_admin` pattern used for
per-user resources like Tranquility/tAimra. vrar3d's /sessions route is the
one exception here — it carries a user_id in its request body, so it reuses
the ownership-check pattern.

Guards against regressing to the previous behaviour where every route in
these five routers (including two unauthenticated DELETE endpoints) was
reachable by anyone with no authentication at all.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.artifactory.routes import router as artifactory_router
from src.imind.routes import router as imind_router
from src.library.routes import router as library_router
from src.studio.routes import router as studio_router
from src.vrar3d.routes import router as vrar3d_router

app = FastAPI()
app.include_router(artifactory_router)
app.include_router(library_router)
app.include_router(studio_router)
app.include_router(imind_router)
app.include_router(vrar3d_router)
client = TestClient(app)


def _override(user_id: str = "u1", role: str = "user"):
    def _dep():
        return {"sub": user_id, "tier": 0, "role": role}

    return _dep


def _clear_override():
    app.dependency_overrides.pop(get_current_user, None)


# ── Public status endpoints stay public ─────────────────────────────────


def test_artifactory_status_is_public():
    assert client.get("/artifactory/status").status_code == 200


def test_library_stats_is_public():
    assert client.get("/library/stats").status_code == 200


def test_studio_status_and_capabilities_are_public():
    assert client.get("/studio/status").status_code == 200
    assert client.get("/studio/capabilities").status_code == 200


def test_imind_status_is_public():
    assert client.get("/imind/status").status_code == 200


def test_vrar3d_status_is_public():
    assert client.get("/vrar3d/status").status_code == 200


# ── Everything else requires authentication ──────────────────────────────


def test_artifactory_list_requires_auth():
    _clear_override()
    resp = client.get("/artifactory/artifacts")
    assert resp.status_code in (401, 403)


def test_artifactory_delete_requires_auth():
    _clear_override()
    resp = client.delete("/artifactory/artifacts/does-not-exist")
    assert resp.status_code in (401, 403)


def test_library_list_requires_auth():
    _clear_override()
    resp = client.get("/library/articles")
    assert resp.status_code in (401, 403)


def test_library_delete_requires_auth():
    _clear_override()
    resp = client.delete("/library/articles/does-not-exist")
    assert resp.status_code in (401, 403)


def test_studio_submit_job_requires_auth():
    _clear_override()
    resp = client.post("/studio/jobs", json={"service": "imaginarium"})
    assert resp.status_code in (401, 403)


def test_imind_assess_requires_auth():
    _clear_override()
    resp = client.post("/imind/assess", json={"text": "hello"})
    assert resp.status_code in (401, 403)


def test_vrar3d_scenes_requires_auth():
    _clear_override()
    resp = client.get("/vrar3d/scenes")
    assert resp.status_code in (401, 403)


# ── Authenticated callers can use the shared-resource routes ─────────────


def test_artifactory_create_list_and_delete_with_auth():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        created = client.post("/artifactory/artifacts", json={"name": "widget"})
        assert created.status_code == 200
        artifact_id = created.json()["id"]

        assert client.get("/artifactory/artifacts").status_code == 200
        assert client.get(f"/artifactory/artifacts/{artifact_id}").status_code == 200

        deleted = client.delete(f"/artifactory/artifacts/{artifact_id}")
        assert deleted.status_code == 200
    finally:
        _clear_override()


def test_library_create_and_delete_with_auth():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        created = client.post(
            "/library/articles",
            json={"title": "Test", "body": "Body text", "tags": ["t"]},
        )
        assert created.status_code == 200
        article_id = created.json()["id"]

        assert client.get(f"/library/articles/{article_id}").status_code == 200

        deleted = client.delete(f"/library/articles/{article_id}")
        assert deleted.status_code == 200
    finally:
        _clear_override()


def test_studio_submit_job_with_auth():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/studio/jobs", json={"service": "imaginarium", "payload": {}})
        assert resp.status_code == 200
    finally:
        _clear_override()


def test_imind_assess_with_auth():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/imind/assess", json={"text": "hello"})
        assert resp.status_code == 200
    finally:
        _clear_override()


def test_vrar3d_scenes_with_auth():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.get("/vrar3d/scenes")
        assert resp.status_code == 200
    finally:
        _clear_override()


# ── vrar3d /sessions carries user_id in the body, so it keeps an ownership
#    check (mirrors src/tranquility/routes.py's path-param pattern, adapted
#    for a body field instead of a path param) ─────────────────────────────


def test_vrar3d_start_session_requires_auth():
    _clear_override()
    resp = client.post("/vrar3d/sessions", json={"user_id": "u1", "scene_id": "x"})
    assert resp.status_code in (401, 403)


def test_vrar3d_user_can_start_own_session():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        scenes = client.get("/vrar3d/scenes").json()
        assert scenes, "expected at least one seeded scene"
        scene_id = scenes[0]["id"]
        resp = client.post("/vrar3d/sessions", json={"user_id": "u1", "scene_id": scene_id})
        assert resp.status_code == 200
    finally:
        _clear_override()


def test_vrar3d_user_cannot_start_session_for_another_user():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        scenes = client.get("/vrar3d/scenes").json()
        scene_id = scenes[0]["id"]
        resp = client.post("/vrar3d/sessions", json={"user_id": "u2", "scene_id": scene_id})
        assert resp.status_code == 403
    finally:
        _clear_override()


def test_vrar3d_admin_can_start_session_for_any_user():
    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        scenes = client.get("/vrar3d/scenes").json()
        scene_id = scenes[0]["id"]
        resp = client.post(
            "/vrar3d/sessions", json={"user_id": "some-other-user", "scene_id": scene_id}
        )
        assert resp.status_code == 200
    finally:
        _clear_override()
