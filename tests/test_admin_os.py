"""Infinity Admin OS API tests."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SECRET_KEY", "test-secret-not-for-prod")
os.environ.setdefault("JWT_SECRET", "test-jwt-not-for-prod")
os.environ.setdefault("ADMIN_OS_WORKSPACE_ROOT", "data/test_admin_os_workspace")


@pytest.fixture(autouse=True)
def _clean_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("ADMIN_OS_WORKSPACE_ROOT", str(ws))
    monkeypatch.setenv("ADMIN_OS_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.setenv("ENTITY_OVERRIDES_DB", str(tmp_path / "test_admin.db"))


def test_files_crud():
    from src.admin_os import files_manager

    files_manager.write_file("docs/readme.md", "hello admin os", create=True)
    listed = files_manager.list_dir("")
    assert any(e["name"] == "docs" for e in listed["entries"])
    content = files_manager.read_file("docs/readme.md")
    assert content["content"] == "hello admin os"
    files_manager.delete_path("docs/readme.md")


def test_domain_model_list():
    from src.admin_os import domain_model

    entities = domain_model.list_entities()
    assert len(entities) >= 40
    summary = domain_model.domain_model_summary()
    assert summary["entity_count"] == len(entities)


def test_backup_run():
    from src.admin_os import backups, files_manager

    files_manager.write_file("seed.txt", "backup me")
    result = backups.run_backup(trigger="test")
    assert result["size_bytes"] > 0
    assert backups.list_backups()


@pytest.mark.asyncio
async def test_admin_os_routes():
    from fastapi.testclient import TestClient

    import api
    from auth import get_current_user

    api.app.dependency_overrides[get_current_user] = lambda: {"sub": "admin1", "role": "admin"}
    try:
        client = TestClient(api.app)
        r = client.get("/admin-os/status")
        assert r.status_code == 200
        assert "domain-model" in r.json()["features"]

        r2 = client.get("/admin-os/domain-model")
        assert r2.status_code == 200
        assert len(r2.json()["entities"]) > 0

        r3 = client.get("/admin-os/system")
        assert r3.status_code == 200
        assert "infrastructure" in r3.json()

        r4 = client.get("/admin-os/events?limit=5")
        assert r4.status_code == 200
        assert r4.json()["source"] == "The Observatory"
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)


def test_admin_os_requires_admin():
    from fastapi.testclient import TestClient

    import api
    from auth import get_current_user

    api.app.dependency_overrides[get_current_user] = lambda: {"sub": "u1", "role": "user"}
    try:
        client = TestClient(api.app)
        r = client.get("/admin-os/status")
        assert r.status_code == 403
    finally:
        api.app.dependency_overrides.pop(get_current_user, None)
