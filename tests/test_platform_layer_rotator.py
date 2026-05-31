"""Platform layer rotator — config, env overrides, rotation API."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("JWT_SECRET", "test-jwt-not-for-prod")


@pytest.fixture(autouse=True)
def _clear_layer_env(monkeypatch):
    for key in (
        "PLATFORM_DB_URLS",
        "PLATFORM_BLOB_BACKENDS",
        "PLATFORM_KNOWLEDGE_BACKENDS",
        "PLATFORM_API_UPSTREAMS",
        "PLATFORM_FRONTEND_ORIGINS",
        "DATABASE_URL",
        "SQLITE_FALLBACK_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("PLATFORM_LAYER_ROTATION_ENABLED", "true")


def test_layer_rotator_loads_all_layers():
    import src.platform.layer_rotator as lr

    lr._layer_rotator = None
    rotator = lr.get_layer_rotator()
    st = rotator.status()
    assert st["enabled"] is True
    assert "database" in st["layers"]
    assert "hosting" in st["layers"]
    assert "knowledge" in st["layers"]


def test_database_backends_from_env(monkeypatch):
    monkeypatch.setenv(
        "PLATFORM_DB_URLS",
        "primary=sqlite:///./test_primary.db,replica=sqlite:///./test_replica.db",
    )
    import src.platform.layer_rotator as lr

    lr._layer_rotator = None
    rotator = lr.get_layer_rotator()
    db = rotator._states["database"]
    assert "primary" in db.backends
    assert "replica" in db.backends


def test_force_rotate_advances_index():
    import src.platform.layer_rotator as lr

    lr._layer_rotator = None
    rotator = lr.get_layer_rotator()
    state = rotator._states["blob"]
    if len(state.backends) < 2:
        pytest.skip("need multiple blob backends")
    idx_before = state.index
    rotator.force_rotate("blob")
    assert state.index != idx_before or len(state.backends) == 1


def test_layer_rotation_enabled_flag(monkeypatch):
    monkeypatch.setenv("PLATFORM_LAYER_ROTATION_ENABLED", "false")
    from src.platform.layer_rotator import layer_rotation_enabled

    assert layer_rotation_enabled() is False


@pytest.mark.asyncio
async def test_adaptive_layers_route():
    from fastapi.testclient import TestClient

    import api

    client = TestClient(api.app)
    r = client.get("/adaptive/layers")
    assert r.status_code == 200
    body = r.json()
    assert "layers" in body
    assert "database" in body["layers"]
