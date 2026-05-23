"""
All Workers Health Check Test
================================
Verifies that all workers can be imported and respond to /health endpoint.

This test ensures:
1. All worker modules can be imported
2. All workers have a FastAPI app
3. All workers have a /health endpoint
4. All /health endpoints return valid responses
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_TRANC3_ROOT = Path(__file__).resolve().parent.parent


def _import_worker(module_dotted: str, file_path: Path):
    """Import a worker module with hyphenated path using importlib."""
    spec = importlib.util.spec_from_file_location(module_dotted, str(file_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_dotted] = mod
    spec.loader.exec_module(mod)
    return mod


# Workers that have SQLite databases that need temporary paths for testing
DB_WORKERS = {
    "infinity_auth": "AuthDatabase",
    "users_service": "UsersDatabase",
    "monitoring": "MonitoringDatabase",
    "notifications": "NotificationsDatabase",
    "infinity_ai": "AIDatabase",
    "the_grid": "GridDatabase",
    "products_service": "ProductsDatabase",
    "orders_service": "OrdersDatabase",
    "payments_service": "PaymentsDatabase",
    "files_service": "FilesDatabase",
    "identity_service": "IdentitiesDatabase",
}

# Workers that have an 'engine' attribute that also needs patching
ENGINE_WORKERS = {
    "the_grid": "WorkflowEngine",
}

# Workers that need special initialization (startup events that create tables)
STARTUP_WORKERS = {"infinity_void"}

# Workers that use module-level DB_PATH + init_db() + lifespan pattern.
# These workers create their SQLite tables inside a lifespan context manager,
# so we must patch DB_PATH to a temp dir and call init_db() before testing.
LIFESPAN_DB_WORKERS = {
    "analytics_service",
    "audit_service",
    "cdn_service",
    "config_service",
    "cron_service",
    "email_service",
    "geo_service",
    "queue_service",
    "search_service",
    "sms_service",
    "storage_service",
}

# All workers: (module_name, file_path)
ALL_WORKERS = [
    ("infinity_ws", _TRANC3_ROOT / "workers" / "infinity-ws" / "worker.py"),
    ("infinity_auth", _TRANC3_ROOT / "workers" / "infinity-auth" / "worker.py"),
    ("users_service", _TRANC3_ROOT / "workers" / "users-service" / "worker.py"),
    ("monitoring", _TRANC3_ROOT / "workers" / "monitoring" / "worker.py"),
    ("notifications", _TRANC3_ROOT / "workers" / "notifications" / "worker.py"),
    ("infinity_ai", _TRANC3_ROOT / "workers" / "infinity-ai" / "worker.py"),
    ("the_grid", _TRANC3_ROOT / "workers" / "the-grid" / "worker.py"),
    ("products_service", _TRANC3_ROOT / "workers" / "products-service" / "worker.py"),
    ("orders_service", _TRANC3_ROOT / "workers" / "orders-service" / "worker.py"),
    ("payments_service", _TRANC3_ROOT / "workers" / "payments-service" / "worker.py"),
    ("files_service", _TRANC3_ROOT / "workers" / "files-service" / "worker.py"),
    ("identity_service", _TRANC3_ROOT / "workers" / "identity-service" / "worker.py"),
    ("analytics_service", _TRANC3_ROOT / "workers" / "analytics-service" / "worker.py"),
    ("api_gateway", _TRANC3_ROOT / "workers" / "api-gateway" / "worker.py"),
    ("audit_service", _TRANC3_ROOT / "workers" / "audit-service" / "worker.py"),
    ("cache_service", _TRANC3_ROOT / "workers" / "cache-service" / "worker.py"),
    ("cdn_service", _TRANC3_ROOT / "workers" / "cdn-service" / "worker.py"),
    ("config_service", _TRANC3_ROOT / "workers" / "config-service" / "worker.py"),
    ("cron_service", _TRANC3_ROOT / "workers" / "cron-service" / "worker.py"),
    ("email_service", _TRANC3_ROOT / "workers" / "email-service" / "worker.py"),
    ("geo_service", _TRANC3_ROOT / "workers" / "geo-service" / "worker.py"),
    ("health_aggregator", _TRANC3_ROOT / "workers" / "health-aggregator" / "worker.py"),
    ("infinity_void", _TRANC3_ROOT / "workers" / "infinity-void" / "worker.py"),
    ("queue_service", _TRANC3_ROOT / "workers" / "queue-service" / "worker.py"),
    ("rate_limit_service", _TRANC3_ROOT / "workers" / "rate-limit-service" / "worker.py"),
    ("search_service", _TRANC3_ROOT / "workers" / "search-service" / "worker.py"),
    ("sms_service", _TRANC3_ROOT / "workers" / "sms-service" / "worker.py"),
    ("storage_service", _TRANC3_ROOT / "workers" / "storage-service" / "worker.py"),
    ("tranc3_ai", _TRANC3_ROOT / "workers" / "tranc3-ai" / "worker.py"),
]


def _check_worker_health(module_name: str, file_path: Path, tmp_path: Path):
    """Import a worker and verify its /health endpoint."""
    mod = _import_worker(f"{module_name}_worker", file_path)
    assert hasattr(mod, "app"), f"Worker {module_name} missing 'app' attribute"

    # Check /health route exists
    routes = [route.path for route in mod.app.routes]
    assert "/health" in routes, f"Worker {module_name} missing /health endpoint"

    # Set up test client with patched database if needed
    patches = []
    test_db = None
    test_engine = None

    if module_name in DB_WORKERS:
        db_class = getattr(mod, DB_WORKERS[module_name])
        db_path = tmp_path / f"test_{module_name}.db"
        test_db = db_class(db_path=db_path)
        from unittest.mock import patch

        patches.append(patch.object(mod, "db", test_db))

        if module_name in ENGINE_WORKERS:
            engine_class = getattr(mod, ENGINE_WORKERS[module_name])
            test_engine = engine_class(test_db)
            patches.append(patch.object(mod, "engine", test_engine))

    # Special handling for workers that need startup initialization
    if module_name in STARTUP_WORKERS:
        from unittest.mock import patch as _patch

        # infinity-void: patch DB_PATH to temp dir, then init schema before testing
        if module_name == "infinity_void":
            test_void_dir = tmp_path / "void-data"
            test_void_dir.mkdir(parents=True, exist_ok=True)
            test_db_path = test_void_dir / "void.db"
            with (
                _patch.object(mod, "DB_PATH", test_db_path),
                _patch.object(mod, "DATA_DIR", test_void_dir),
                _patch.object(mod, "R2_DIR", test_void_dir / "secrets"),
            ):
                mod.init_schema()
                client = TestClient(mod.app)
                response = client.get("/health")
                assert response.status_code == 200, (
                    f"Worker {module_name} /health returned {response.status_code}"
                )
                data = response.json()
                assert "status" in data, f"Worker {module_name} /health missing 'status' field"
            return

    # Workers that use module-level DB_PATH + init_db() + lifespan pattern.
    # Patch DB_PATH to a temp directory and call init_db() before testing.
    if module_name in LIFESPAN_DB_WORKERS:
        from unittest.mock import patch as _patch

        test_data_dir = tmp_path / f"{module_name}_data"
        test_data_dir.mkdir(parents=True, exist_ok=True)
        test_db_path = test_data_dir / f"{module_name}.db"
        with _patch.object(mod, "DB_PATH", test_db_path):
            mod.init_db()
            client = TestClient(mod.app)
            response = client.get("/health")
            assert response.status_code == 200, (
                f"Worker {module_name} /health returned {response.status_code}"
            )
            data = response.json()
            assert "status" in data, f"Worker {module_name} /health missing 'status' field"
        return

    import contextlib

    with contextlib.ExitStack() as stack:
        for p in patches:
            stack.enter_context(p)

        client = TestClient(mod.app)
        response = client.get("/health")
        assert response.status_code == 200, (
            f"Worker {module_name} /health returned {response.status_code}"
        )

        data = response.json()
        assert "status" in data, f"Worker {module_name} /health missing 'status' field"

    # Cleanup database connection
    if test_db:
        if hasattr(test_db, "_conn"):
            try:
                test_db._conn.close()
            except Exception:
                pass  # nosec B110 — graceful degradation
        if hasattr(test_db, "_local") and hasattr(test_db._local, "conn") and test_db._local.conn:
            try:
                test_db._local.conn.close()
            except Exception:
                pass  # nosec B110 — graceful degradation


class TestAllWorkersHealth:
    """Test health endpoints for all workers."""

    @pytest.mark.parametrize("module_name,file_path", ALL_WORKERS)
    def test_worker_health(self, module_name, file_path, tmp_path):
        """Verify worker can be imported and /health endpoint responds."""
        _check_worker_health(module_name, file_path, tmp_path)


class TestWorkerCounts:
    """Verify the expected number of workers and test coverage."""

    def test_total_worker_count(self):
        """Verify we have 29 workers total."""
        assert len(ALL_WORKERS) == 29

    def test_db_worker_count(self):
        """Verify we have 11 database-backed workers."""
        assert len(DB_WORKERS) == 11

    def test_p0_worker_count(self):
        """Verify P0 workers (infinity-ws, infinity-auth)."""
        p0_workers = [w for w in ALL_WORKERS if w[0] in ("infinity_ws", "infinity_auth")]
        assert len(p0_workers) == 2

    def test_p1_worker_count(self):
        """Verify P1 workers (users-service, monitoring, notifications, infinity-ai)."""
        p1_workers = [
            w
            for w in ALL_WORKERS
            if w[0] in ("users_service", "monitoring", "notifications", "infinity_ai")
        ]
        assert len(p1_workers) == 4

    def test_p2_worker_count(self):
        """Verify P2 workers (the-grid, products, orders, payments, files, identity)."""
        p2_workers = [
            w
            for w in ALL_WORKERS
            if w[0]
            in (
                "the_grid",
                "products_service",
                "orders_service",
                "payments_service",
                "files_service",
                "identity_service",
            )
        ]
        assert len(p2_workers) == 6
