"""
conftest.py — Infinity Portal Service tests
============================================
Shared fixtures for router and service tests.

Import path note: workers run as standalone scripts, so sys.path must
include the service directory before importing local modules.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure the service directory is on sys.path so local imports resolve
SERVICE_DIR = Path(__file__).parent.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


# ---------------------------------------------------------------------------
# Stubs for Dimensional / InfinityWorkerKit (not available in test env)
# ---------------------------------------------------------------------------


def _make_dimensional_stubs():
    """Patch all Dimensional imports with lightweight stubs."""

    # Stub InfinityLocation enum values used in routing
    from unittest.mock import MagicMock

    location_stub = MagicMock()
    location_stub.ARCADIA = MagicMock(value="arcadia")
    location_stub.ADMIN = MagicMock(value="infinity_admin")
    location_stub.CITADEL = MagicMock(value="the_citadel")
    location_stub.CENTRAL = MagicMock(value="infinity")
    location_stub.PORTAL = MagicMock(value="infinity_portal")
    location_stub.GATE = MagicMock(value="infinity_gate")
    location_stub.ONE = MagicMock(value="infinity_one")
    location_stub.BRIDGE = MagicMock(value="infinity_bridge")
    location_stub.SENTINEL = MagicMock(value="sentinel_station")

    return location_stub


@pytest.fixture(autouse=True)
def stub_dimensional(monkeypatch):
    """Auto-used fixture — stubs out Dimensional imports for all tests."""
    # Provide enough of a stub that module-level imports don't fail.
    # Individual tests that need specific behaviour can override.
    sentinel_mock = MagicMock()
    sentinel_mock.is_running = True
    sentinel_mock.publish = AsyncMock()
    sentinel_mock.start = AsyncMock()
    sentinel_mock.stop = AsyncMock()
    sentinel_mock.get_stats = MagicMock(return_value={})

    dim_bus_mock = MagicMock()
    dim_bus_mock.is_running = True
    dim_bus_mock.start = AsyncMock()
    dim_bus_mock.stop = AsyncMock()
    dim_bus_mock.get_stats = MagicMock(return_value={})

    dim_registry_mock = MagicMock()
    underverse_mock = MagicMock()

    worker_kit_mock = MagicMock()
    worker_kit_mock.health = MagicMock()
    worker_kit_mock.defense = MagicMock()
    worker_kit_mock.defense.evaluate_request = AsyncMock(
        return_value=MagicMock(allowed=True, reason="")
    )
    worker_kit_mock.gateway = MagicMock()
    worker_kit_mock.gateway.route = AsyncMock(return_value=MagicMock(target_location="arcadia"))
    worker_kit_mock.gateway.record_route_success = MagicMock()
    worker_kit_mock.get_kit_stats = MagicMock(return_value={"subsystems": {}})
    worker_kit_mock.startup = AsyncMock()
    worker_kit_mock.shutdown = AsyncMock()

    health_summary_mock = MagicMock()
    health_summary_mock.to_dict = MagicMock(
        return_value={"health_score": 1.0, "health_tier": "EXCELLENT"}
    )
    worker_kit_mock.health.get_health_summary = MagicMock(return_value=health_summary_mock)
    worker_kit_mock.health.record_request = MagicMock()
    worker_kit_mock.health.record_metric = MagicMock()
    worker_kit_mock.health.should_fire = MagicMock(return_value=False)
    worker_kit_mock.health.record_fire = MagicMock()
    worker_kit_mock.health.update_health = MagicMock()
    worker_kit_mock.health.register_daemon = MagicMock()

    patches = [
        patch("Dimensional.dimensionals.get_dimensional_bus", return_value=dim_bus_mock),
        patch("Dimensional.dimensionals.get_dimensional_registry", return_value=dim_registry_mock),
        patch("Dimensional.dimensionals.get_underverse_registry", return_value=underverse_mock),
        patch(
            "Dimensional.infinity.sentinel_station.get_sentinel_station",
            return_value=sentinel_mock,
        ),
        patch(
            "Dimensional.infinity.worker_integration.InfinityWorkerKit",
            return_value=worker_kit_mock,
        ),
        patch("Dimensional.infinity.auth_gateway.AuthGatewayMiddleware", MagicMock()),
        patch("Dimensional.infinity.owasp_hardening.OWASPHardeningMiddleware", MagicMock()),
        patch("Dimensional.infinity.rbac.RBACEngine", MagicMock()),
    ]
    [p.start() for p in patches]
    yield {
        "sentinel": sentinel_mock,
        "dim_bus": dim_bus_mock,
        "worker_kit": worker_kit_mock,
    }
    for p in patches:
        p.stop()


@pytest.fixture()
def in_memory_db(tmp_path, monkeypatch):
    """Provide an isolated PortalDatabase backed by a temp file."""
    # Must be imported AFTER sys.path is set
    import database as db_module

    tmp_db = str(tmp_path / "test_portal.db")
    monkeypatch.setattr(db_module, "DB_PATH", tmp_db)
    test_db = db_module.PortalDatabase(db_path=tmp_db)
    monkeypatch.setattr(db_module, "db", test_db)
    return test_db
