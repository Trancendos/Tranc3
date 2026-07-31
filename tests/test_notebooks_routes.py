# tests/test_notebooks_routes.py
# HTTP-level tests for src/notebooks/routes.py (the /notebooks API).

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import get_current_user
from src.notebooks import registry as registry_module
from src.notebooks.registry import NotebookRegistry
from src.notebooks.routes import router as notebooks_router


@pytest.fixture
def client(tmp_path, monkeypatch):
    test_registry = NotebookRegistry(db_path=tmp_path / "routes_test.db")
    monkeypatch.setattr(registry_module, "_registry", test_registry)

    app = FastAPI()
    app.include_router(notebooks_router)
    with TestClient(app) as c:
        yield c
    test_registry.close()


def _override(user_id: str, role: str = "user"):
    def _dep():
        return {"sub": user_id, "role": role}

    return _dep


class TestCreateRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.post("/notebooks", json={"owner": "The Nexus", "content": "Note"})
        assert resp.status_code in (401, 403)

    def test_non_admin_forbidden(self, client):
        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.post("/notebooks", json={"owner": "The Nexus", "content": "Note"})
            assert resp.status_code == 403
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_create(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post("/notebooks", json={"owner": "The Nexus", "content": "Note"})
            assert resp.status_code == 200
            body = resp.json()
            assert body["owner"] == "The Nexus"
            assert body["content"] == "Note"
            assert body["visibility"] == "ai_private"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_admin_can_create_with_explicit_visibility_and_links(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/notebooks",
                json={
                    "owner": "The Nexus",
                    "content": "Note",
                    "visibility": "public",
                    "linked_card_id": "card-1",
                    "linked_location": "The Nexus",
                },
            )
            assert resp.status_code == 200
            body = resp.json()
            assert body["visibility"] == "public"
            assert body["linked_card_id"] == "card-1"
            assert body["linked_location"] == "The Nexus"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_blank_content_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post("/notebooks", json={"owner": "The Nexus", "content": "   "})
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_unsafe_content_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "<script>alert(1)</script>"},
            )
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_invalid_visibility_rejected(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Note", "visibility": "private"},
            )
            assert resp.status_code == 400
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestListForOwnerRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.get("/notebooks/The Nexus")
        assert resp.status_code in (401, 403)

    def test_admin_sees_all_visibilities(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Private", "visibility": "ai_private"},
            )
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Operator", "visibility": "operator"},
            )
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Public", "visibility": "public"},
            )
            resp = client.get("/notebooks/The Nexus")
            assert resp.status_code == 200
            contents = {e["content"] for e in resp.json()}
            assert contents == {"Private", "Operator", "Public"}
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_non_admin_never_sees_ai_private(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Private", "visibility": "ai_private"},
            )
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Operator", "visibility": "operator"},
            )
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Public", "visibility": "public"},
            )
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.get("/notebooks/The Nexus")
            assert resp.status_code == 200
            contents = {e["content"] for e in resp.json()}
            assert contents == {"Operator", "Public"}
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_empty_for_unknown_owner(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.get("/notebooks/Nobody")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)


class TestListForCardRoute:
    def test_requires_auth(self, client):
        client.app.dependency_overrides.pop(get_current_user, None)
        resp = client.get("/notebooks/card/card-1")
        assert resp.status_code in (401, 403)

    def test_admin_sees_linked_entries(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post(
                "/notebooks",
                json={"owner": "The Nexus", "content": "Linked", "linked_card_id": "card-1"},
            )
            client.post("/notebooks", json={"owner": "The Nexus", "content": "Unlinked"})
            resp = client.get("/notebooks/card/card-1")
            assert resp.status_code == 200
            body = resp.json()
            assert len(body) == 1
            assert body[0]["content"] == "Linked"
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_non_admin_filters_ai_private_linked_entries(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            client.post(
                "/notebooks",
                json={
                    "owner": "The Nexus",
                    "content": "Private linked",
                    "visibility": "ai_private",
                    "linked_card_id": "card-1",
                },
            )
            client.post(
                "/notebooks",
                json={
                    "owner": "The Nexus",
                    "content": "Public linked",
                    "visibility": "public",
                    "linked_card_id": "card-1",
                },
            )
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

        client.app.dependency_overrides[get_current_user] = _override("u1", role="user")
        try:
            resp = client.get("/notebooks/card/card-1")
            assert resp.status_code == 200
            contents = {e["content"] for e in resp.json()}
            assert contents == {"Public linked"}
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)

    def test_empty_for_unknown_card(self, client):
        client.app.dependency_overrides[get_current_user] = _override("admin1", role="admin")
        try:
            resp = client.get("/notebooks/card/nonexistent-card")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            client.app.dependency_overrides.pop(get_current_user, None)
