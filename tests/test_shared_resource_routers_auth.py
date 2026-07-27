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


def test_studio_status_is_public():
    assert client.get("/studio/status").status_code == 200


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


def test_artifactory_push_version_requires_auth():
    _clear_override()
    resp = client.post("/artifactory/artifacts/does-not-exist/versions", json={"version": "1.0"})
    assert resp.status_code in (401, 403)


def test_artifactory_apply_retention_requires_auth():
    _clear_override()
    resp = client.post("/artifactory/retention/apply")
    assert resp.status_code in (401, 403)


def test_library_list_requires_auth():
    _clear_override()
    resp = client.get("/library/articles")
    assert resp.status_code in (401, 403)


def test_library_search_requires_auth():
    _clear_override()
    resp = client.get("/library/articles/search", params={"q": "test"})
    assert resp.status_code in (401, 403)


def test_library_get_requires_auth():
    _clear_override()
    resp = client.get("/library/articles/does-not-exist")
    assert resp.status_code in (401, 403)


def test_library_delete_requires_auth():
    _clear_override()
    resp = client.delete("/library/articles/does-not-exist")
    assert resp.status_code in (401, 403)


def test_library_apply_retention_requires_auth():
    _clear_override()
    resp = client.post("/library/retention/apply")
    assert resp.status_code in (401, 403)


def test_studio_capabilities_requires_auth():
    _clear_override()
    resp = client.get("/studio/capabilities")
    assert resp.status_code in (401, 403)


def test_studio_submit_job_requires_auth():
    _clear_override()
    resp = client.post("/studio/jobs", json={"service": "imaginarium"})
    assert resp.status_code in (401, 403)


def test_studio_list_jobs_requires_auth():
    _clear_override()
    resp = client.get("/studio/jobs")
    assert resp.status_code in (401, 403)


def test_studio_get_job_requires_auth():
    _clear_override()
    resp = client.get("/studio/jobs/does-not-exist")
    assert resp.status_code in (401, 403)


def test_imind_assess_requires_auth():
    _clear_override()
    resp = client.post("/imind/assess", json={"text": "hello"})
    assert resp.status_code in (401, 403)


def test_vrar3d_scenes_requires_auth():
    _clear_override()
    resp = client.get("/vrar3d/scenes")
    assert resp.status_code in (401, 403)


def test_vrar3d_get_scene_requires_auth():
    _clear_override()
    resp = client.get("/vrar3d/scenes/does-not-exist")
    assert resp.status_code in (401, 403)


def test_vrar3d_recommend_requires_auth():
    _clear_override()
    resp = client.get("/vrar3d/recommend")
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

        pushed = client.post(
            f"/artifactory/artifacts/{artifact_id}/versions", json={"version": "1.0"}
        )
        assert pushed.status_code == 200

        assert client.post("/artifactory/retention/apply").status_code == 200

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
        assert client.get("/library/articles/search", params={"q": "Test"}).status_code == 200
        assert client.post("/library/retention/apply").status_code == 200

        deleted = client.delete(f"/library/articles/{article_id}")
        assert deleted.status_code == 200
    finally:
        _clear_override()


def test_library_create_rejects_unknown_classification():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post(
            "/library/articles",
            json={"title": "Bad", "body": "Body", "classification": "not-a-real-level"},
        )
        assert resp.status_code == 400
    finally:
        _clear_override()


# ── Classification gates read access, not just write access ─────────────


def test_library_restricted_article_hidden_from_other_users():
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        created = client.post(
            "/library/articles",
            json={"title": "Secret", "body": "Body", "classification": "restricted"},
        )
        article_id = created.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("someone-else")
    try:
        resp = client.get(f"/library/articles/{article_id}")
        assert resp.status_code == 403

        listed = client.get("/library/articles", params={"limit": 200}).json()
        assert all(a["id"] != article_id for a in listed)
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        client.delete(f"/library/articles/{article_id}")
    finally:
        _clear_override()


def test_library_restricted_article_cannot_be_deleted_by_other_users():
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        created = client.post(
            "/library/articles",
            json={"title": "Secret", "body": "Body", "classification": "restricted"},
        )
        article_id = created.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("someone-else")
    try:
        resp = client.delete(f"/library/articles/{article_id}")
        assert resp.status_code == 403
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        resp = client.get(f"/library/articles/{article_id}")
        assert resp.status_code == 200
        assert client.delete(f"/library/articles/{article_id}").status_code == 200
    finally:
        _clear_override()


def test_library_restricted_article_visible_to_author():
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        created = client.post(
            "/library/articles",
            json={
                "title": "Secret",
                "body": "Body",
                "author": "owner",
                "classification": "top_secret",
            },
        )
        article_id = created.json()["id"]
        resp = client.get(f"/library/articles/{article_id}")
        assert resp.status_code == 200
    finally:
        client.delete(f"/library/articles/{article_id}")
        _clear_override()


def test_library_restricted_article_visible_to_admin():
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        created = client.post(
            "/library/articles",
            json={"title": "Secret", "body": "Body", "classification": "restricted"},
        )
        article_id = created.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        resp = client.get(f"/library/articles/{article_id}")
        assert resp.status_code == 200
        client.delete(f"/library/articles/{article_id}")
    finally:
        _clear_override()


def test_library_create_ignores_client_supplied_author_for_non_admin():
    """A non-admin caller cannot forge an arbitrary `author` to grant read
    access to a restricted article to some other principal — the server
    always attributes authorship to the caller's own identity instead."""
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        created = client.post(
            "/library/articles",
            json={
                "title": "Secret",
                "body": "Body",
                "author": "someone-else",
                "classification": "restricted",
            },
        )
        assert created.json()["author"] == "owner"
        article_id = created.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("someone-else")
    try:
        resp = client.get(f"/library/articles/{article_id}")
        assert resp.status_code == 403
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        client.delete(f"/library/articles/{article_id}")
    finally:
        _clear_override()


def test_library_create_honors_explicit_author_for_admin():
    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        created = client.post(
            "/library/articles",
            json={
                "title": "Assigned",
                "body": "Body",
                "author": "designated-owner",
                "classification": "restricted",
            },
        )
        assert created.json()["author"] == "designated-owner"
        article_id = created.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("designated-owner")
    try:
        resp = client.get(f"/library/articles/{article_id}")
        assert resp.status_code == 200
    finally:
        client.delete(f"/library/articles/{article_id}")
        _clear_override()


def test_library_list_does_not_let_restricted_articles_crowd_out_visible_ones():
    """Restricted articles filling the recency window ahead of a caller's own
    visible article must not push it out of a small `limit` — the route must
    filter by visibility before truncating, not after."""
    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        created = client.post("/library/articles", json={"title": "Visible", "body": "Body"})
        article_id = created.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("someone-else")
    noise_ids = []
    try:
        for i in range(5):
            resp = client.post(
                "/library/articles",
                json={"title": f"Noise {i}", "body": "Body", "classification": "restricted"},
            )
            noise_ids.append(resp.json()["id"])
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("owner")
    try:
        listed = client.get("/library/articles", params={"limit": 1}).json()
        assert any(a["id"] == article_id for a in listed)
    finally:
        client.delete(f"/library/articles/{article_id}")
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("someone-else")
    try:
        for nid in noise_ids:
            client.delete(f"/library/articles/{nid}")
    finally:
        _clear_override()


def test_studio_submit_job_with_auth():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        assert client.get("/studio/capabilities").status_code == 200

        resp = client.post("/studio/jobs", json={"service": "imaginarium", "payload": {}})
        assert resp.status_code == 200
        job_id = resp.json()["id"]

        assert client.get("/studio/jobs").status_code == 200
        assert client.get(f"/studio/jobs/{job_id}").status_code == 200
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
        scene_id = resp.json()[0]["id"]

        assert client.get(f"/vrar3d/scenes/{scene_id}").status_code == 200
        assert client.get("/vrar3d/recommend").status_code in (200, 404)
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


# ── /sessions/{id}/end resolves the session first and authorizes against its
#    owner, not just "any authenticated caller" — a user must not be able to
#    end (and overwrite mood_after on) another user's session just by
#    guessing/knowing its session_id ───────────────────────────────────────


def test_vrar3d_user_can_end_own_session():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        scenes = client.get("/vrar3d/scenes").json()
        scene_id = scenes[0]["id"]
        started = client.post("/vrar3d/sessions", json={"user_id": "u1", "scene_id": scene_id})
        session_id = started.json()["id"]

        resp = client.post(f"/vrar3d/sessions/{session_id}/end", json={"mood_after": 4})
        assert resp.status_code == 200

        # Already-ended session: get_session() still finds it, but
        # end_session() itself refuses a second end — the 404 in that
        # second, inner check.
        resp2 = client.post(f"/vrar3d/sessions/{session_id}/end", json={"mood_after": 3})
        assert resp2.status_code == 404
    finally:
        _clear_override()


def test_vrar3d_end_session_not_found():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        resp = client.post("/vrar3d/sessions/does-not-exist/end", json={"mood_after": 4})
        assert resp.status_code == 404
    finally:
        _clear_override()


def test_vrar3d_user_cannot_end_another_users_session():
    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        scenes = client.get("/vrar3d/scenes").json()
        scene_id = scenes[0]["id"]
        started = client.post(
            "/vrar3d/sessions", json={"user_id": "victim-user", "scene_id": scene_id}
        )
        session_id = started.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("attacker-user")
    try:
        resp = client.post(f"/vrar3d/sessions/{session_id}/end", json={"mood_after": 1})
        assert resp.status_code == 403
    finally:
        _clear_override()


def test_vrar3d_admin_can_end_any_users_session():
    app.dependency_overrides[get_current_user] = _override("u1")
    try:
        scenes = client.get("/vrar3d/scenes").json()
        scene_id = scenes[0]["id"]
        started = client.post("/vrar3d/sessions", json={"user_id": "u1", "scene_id": scene_id})
        session_id = started.json()["id"]
    finally:
        _clear_override()

    app.dependency_overrides[get_current_user] = _override("admin-user", role="admin")
    try:
        resp = client.post(f"/vrar3d/sessions/{session_id}/end", json={"mood_after": 3})
        assert resp.status_code == 200
    finally:
        _clear_override()
