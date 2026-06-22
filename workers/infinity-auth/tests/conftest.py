"""
Infinity Auth — Test fixtures
==============================
Shared pytest fixtures for test_router.py and test_service.py.
"""

from __future__ import annotations

import os
import sys
from unittest.mock import MagicMock

import pytest

# Ensure the worker package root is on sys.path so absolute imports work
_WORKER_DIR = os.path.dirname(os.path.dirname(__file__))
if _WORKER_DIR not in sys.path:
    sys.path.insert(0, _WORKER_DIR)

# Set required env vars before any worker module is imported
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-pytest-only-do-not-use-in-prod")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:3000")


@pytest.fixture()
def tmp_db(tmp_path):
    """Provide a temporary AuthDatabase backed by a temp file."""
    from database import AuthDatabase

    db_path = str(tmp_path / "auth_test.db")
    return AuthDatabase(db_path=db_path)


@pytest.fixture()
def mock_worker_kit():
    """A minimal mock of InfinityWorkerKit for health/defense checks."""
    kit = MagicMock()
    kit.health.get_health_summary.return_value = {"health_score": 1.0, "tier": "EXCELLENT"}
    kit.defense.get_blocked_ips.return_value = []
    kit.startup = MagicMock(return_value=None)
    kit.shutdown = MagicMock(return_value=None)
    return kit


@pytest.fixture()
def test_client(tmp_db, mock_worker_kit):
    """
    Return a TestClient for the FastAPI app with mocked DB, rate limiter,
    and worker kit.
    """
    import router as auth_router
    from fastapi.testclient import TestClient
    from service import RateLimiter

    rl = RateLimiter(max_requests=1000)  # effectively unlimited in tests
    auth_router.init_router(tmp_db, rl, mock_worker_kit)

    from main import create_app

    app = create_app()
    # Override lifespan so tests don't need a real worker_kit.startup coroutine
    app.router.lifespan_context = None  # type: ignore[assignment]

    with TestClient(app, raise_server_exceptions=True) as client:
        yield client


@pytest.fixture()
def valid_access_token(tmp_db):
    """Return a valid JWT access token for a freshly registered test user."""
    from service import create_access_token

    return create_access_token("test-user-id", "testuser", role="user")
