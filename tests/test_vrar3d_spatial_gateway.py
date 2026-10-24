"""Regression tests for the user-authenticated VRAR3D gateway."""

from __future__ import annotations

import asyncio

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.auth.facade import get_current_user_dep
from src.vrar3d import spatial_gateway as gw

_ONE = "11111111-1111-4111-8111-111111111111"


@pytest.fixture
def app(monkeypatch):
    api = FastAPI()
    api.include_router(gw.router)
    monkeypatch.setenv("INTERNAL_SECRET", "a" * 64)
    monkeypatch.setenv("VRAR3D_WORKER_URL", "http://vrar3d:8060")
    api.dependency_overrides[get_current_user_dep] = lambda: {"sub": "alice", "role": "user"}
    return api


def _scene(owner: str, scene_id: str = _ONE):
    return {
        "scene_id": scene_id,
        "name": "Scene",
        "scene_type": "3d",
        "metadata": {"owner_id": owner},
    }


def test_list_returns_only_owned_scenes(app, monkeypatch):
    async def fake_request(method, path, *, payload=None, params=None):
        assert method == "GET"
        return [
            _scene("alice"),
            _scene("bob", "22222222-2222-4222-8222-222222222222"),
            {"scene_id": "legacy", "metadata": {}},
        ]

    monkeypatch.setattr(gw, "_worker_request", fake_request)
    response = TestClient(app).get("/spatial/scenes")
    assert response.status_code == 200
    assert [scene["scene_id"] for scene in response.json()] == [_ONE]


def test_create_overrides_owner_and_rejects_spoofed_metadata(app, monkeypatch):
    seen = []

    async def fake_request(method, path, *, payload=None, params=None):
        seen.append((method, path, payload))
        return {"scene_id": _ONE, **payload}

    monkeypatch.setattr(gw, "_worker_request", fake_request)
    client = TestClient(app)
    response = client.post(
        "/spatial/scenes",
        json={
            "name": "Mine",
            "scene_type": "3d",
            "metadata": {"owner_id": "bob"},
        },
    )
    assert response.status_code == 422

    response = client.post(
        "/spatial/scenes",
        json={"name": "Mine", "scene_type": "3d"},
    )
    assert response.status_code == 201
    assert seen[-1][2]["metadata"]["owner_id"] == "alice"
    assert "dev-secret" not in response.text


def test_get_other_user_scene_is_hidden(app, monkeypatch):
    async def fake_request(method, path, *, payload=None, params=None):
        return _scene("bob")

    monkeypatch.setattr(gw, "_worker_request", fake_request)
    response = TestClient(app).get(f"/spatial/scenes/{_ONE}")
    assert response.status_code == 404


def test_delete_rechecks_ownership(app, monkeypatch):
    requests = []

    async def fake_request(method, path, *, payload=None, params=None):
        requests.append(method)
        return _scene("bob")

    monkeypatch.setattr(gw, "_worker_request", fake_request)
    response = TestClient(app).delete(f"/spatial/scenes/{_ONE}")
    assert response.status_code == 404
    assert requests == ["GET"]


def test_anonymous_identity_is_denied(app):
    app.dependency_overrides[get_current_user_dep] = lambda: {
        "sub": "anonymous",
        "role": "user",
    }
    response = TestClient(app).get("/spatial/scenes")
    assert response.status_code == 401


def test_worker_secret_required(monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "")
    with pytest.raises(Exception) as exc:
        asyncio.run(gw._worker_request("GET", "/vrar3d/scenes"))
    assert getattr(exc.value, "status_code", None) == 503


def test_worker_url_requires_private_service_target(monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "a" * 64)
    monkeypatch.setenv("VRAR3D_WORKER_URL", "http://169.254.169.254:8060")
    with pytest.raises(ValueError):
        gw._worker_settings()
    monkeypatch.setenv("VRAR3D_WORKER_URL", "https://example.com")
    with pytest.raises(ValueError):
        gw._worker_settings()


def test_worker_secret_sent_only_server_to_server(monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "s" * 64)
    monkeypatch.setenv("VRAR3D_WORKER_URL", "http://vrar3d:8060")
    seen = []
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        def reply(request):
            seen.append(request)
            return httpx.Response(200, json={"ok": True})

        kwargs["transport"] = httpx.MockTransport(reply)
        return original(*args, **kwargs)

    monkeypatch.setattr(gw.httpx, "AsyncClient", factory)
    result = asyncio.run(gw._worker_request("GET", "/vrar3d/scenes"))
    assert result == {"ok": True}
    assert len(seen) == 1
    assert seen[0].url.host == "vrar3d"
    assert seen[0].headers["x-internal-secret"] == "s" * 64
    assert seen[0].headers.get("authorization") is None


def test_worker_refuses_redirects(monkeypatch):
    monkeypatch.setenv("INTERNAL_SECRET", "s" * 64)
    monkeypatch.setenv("VRAR3D_WORKER_URL", "http://vrar3d:8060")
    original = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(gw.httpx, "AsyncClient", factory)
    with pytest.raises(Exception) as exc:
        asyncio.run(gw._worker_request("GET", "/vrar3d/scenes"))
    assert getattr(exc.value, "status_code", None) == 502


def test_invalid_scene_id_never_contacts_worker(app, monkeypatch):
    async def no_network(*args, **kwargs):
        raise AssertionError("Invalid ID must not contact worker")

    monkeypatch.setattr(gw, "_worker_request", no_network)
    response = TestClient(app).get("/spatial/scenes/not-a-uuid")
    assert response.status_code == 404
