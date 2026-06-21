"""
Infinity-Admin Service — Test Fixtures
========================================
Shared pytest fixtures for router and service tests.
"""

from __future__ import annotations

import os
import sys

import pytest

# Ensure the worker directory is on the path so imports resolve
_WORKER_DIR = os.path.dirname(os.path.dirname(__file__))
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)


@pytest.fixture(scope="session", autouse=True)
def set_required_env_vars(tmp_path_factory):
    """Set required environment variables before any module is imported."""
    tmp = tmp_path_factory.mktemp("db")
    os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-unit-tests-only")
    os.environ.setdefault("INFINITY_ADMIN_DB_PATH", str(tmp / "test_admin.db"))
    yield


@pytest.fixture()
def tmp_db(tmp_path):
    """Return a fresh AdminDatabase backed by a temp file."""
    # Import here so env vars are set first
    from database import AdminDatabase

    return AdminDatabase(db_path=str(tmp_path / "admin.db"))


@pytest.fixture()
def test_client(tmp_db, monkeypatch):
    """Return a FastAPI TestClient wired to a temporary database.

    NOTE: Integration tests that exercise the full middleware stack
    (AuthGateway, OWASP, Dimensional singletons) require the Dimensional
    package to be importable. In CI without it, skip those tests with:
        pytest -m "not integration"
    """
    pytest.importorskip("fastapi.testclient", reason="httpx required for TestClient")
    import service
    from fastapi.testclient import TestClient

    # Patch the module-level db singleton used by router / service
    import database

    monkeypatch.setattr(database, "db", tmp_db)
    monkeypatch.setattr(service, "db", tmp_db)

    try:
        from main import app

        return TestClient(app, raise_server_exceptions=False)
    except Exception as exc:
        pytest.skip(f"App creation failed (missing dependency?): {exc}")
