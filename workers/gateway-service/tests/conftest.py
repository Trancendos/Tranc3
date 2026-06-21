"""
conftest.py — Shared fixtures for gateway-service tests.
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# Ensure the service directory is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ---------------------------------------------------------------------------
# Environment stubs (must be set before any service imports)
# ---------------------------------------------------------------------------

os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32x")
os.environ.setdefault("GATEWAY_DB_PATH", ":memory:")
os.environ.setdefault("GATEWAY_CACHE_TTL", "5")


# ---------------------------------------------------------------------------
# Dimensional stubs — mock the entire Dimensional package
# ---------------------------------------------------------------------------


def _make_dimensional_mocks():
    """Return a dict of mock objects for all Dimensional imports."""
    sentinel_mock = MagicMock()
    sentinel_mock.is_running = False
    sentinel_mock.is_redis_connected = False
    sentinel_mock.circuit_breaker_state.value = "closed"
    sentinel_mock.get_stats.return_value = {}
    sentinel_mock.health_check = AsyncMock(return_value={"ok": True})
    sentinel_mock.start = AsyncMock()
    sentinel_mock.stop = AsyncMock()
    sentinel_mock.publish = AsyncMock(return_value=None)

    sse_gen_mock = MagicMock()
    sse_gen_mock.start = AsyncMock()

    dimensional_bus_mock = MagicMock()
    dimensional_bus_mock.is_running = False
    dimensional_bus_mock.get_stats.return_value = {}
    dimensional_bus_mock.start = AsyncMock()
    dimensional_bus_mock.stop = AsyncMock()

    registry_mock = MagicMock()
    registry_mock.list_all.return_value = []
    registry_mock.get_pillar_summary.return_value = {}
    registry_mock.get_stats.return_value = {}
    registry_mock.heartbeat = MagicMock()
    registry_mock.get.return_value = None

    underverse_mock = MagicMock()
    underverse_mock.list_all.return_value = []
    underverse_mock.get_pillar_summary.return_value = {}
    underverse_mock.get_capabilities_index.return_value = {}
    underverse_mock.get_stats.return_value = {}
    underverse_mock.heartbeat = MagicMock()
    underverse_mock.get_by_dimensional.return_value = []
    underverse_mock.get_by_capability.return_value = []

    rbac_mock = MagicMock()
    rbac_mock.check_access.return_value = True
    rbac_mock.get_audit_context.return_value = {}

    abac_mock = MagicMock()
    abac_mock.evaluate.return_value = True
    abac_mock.threat_level.value = "low"
    abac_mock._policies = []

    ws_auth_mock = MagicMock()
    ws_auth_mock.connection_count = 0
    ws_auth_mock.connections = []
    ws_auth_mock.get_connection_stats.return_value = {}
    ws_auth_mock.authenticate_ws_upgrade.return_value = None
    ws_auth_mock.register_connection.return_value = True
    ws_auth_mock.unregister_connection = MagicMock()
    ws_auth_mock.update_activity = MagicMock()
    ws_auth_mock.get_stale_connections.return_value = []

    worker_kit_mock = MagicMock()
    worker_kit_mock.startup = AsyncMock()
    worker_kit_mock.shutdown = AsyncMock()
    worker_kit_mock.health.should_fire.return_value = False
    worker_kit_mock.health.register_daemon = MagicMock()

    return {
        "sentinel": sentinel_mock,
        "sse_gen": sse_gen_mock,
        "dimensional_bus": dimensional_bus_mock,
        "dimensional_registry": registry_mock,
        "underverse_registry": underverse_mock,
        "rbac": rbac_mock,
        "abac": abac_mock,
        "ws_auth": ws_auth_mock,
        "worker_kit": worker_kit_mock,
    }


@pytest.fixture(scope="session")
def mocks():
    return _make_dimensional_mocks()


@pytest.fixture(scope="session")
def client(mocks):
    """Return a TestClient backed by the gateway FastAPI app with all Dimensional deps mocked."""
    patches = [
        patch("Dimensional.dimensionals.get_dimensional_registry", return_value=mocks["dimensional_registry"]),
        patch("Dimensional.dimensionals.get_dimensional_bus", return_value=mocks["dimensional_bus"]),
        patch("Dimensional.dimensionals.get_underverse_registry", return_value=mocks["underverse_registry"]),
        patch("Dimensional.infinity.abac.ABACEngine", return_value=mocks["abac"]),
        patch("Dimensional.infinity.abac.get_default_policies", return_value=[]),
        patch("Dimensional.infinity.auth_gateway.AuthGatewayMiddleware", MagicMock(return_value=MagicMock())),
        patch("Dimensional.infinity.auth_gateway.WebSocketAuthManager", return_value=mocks["ws_auth"]),
        patch("Dimensional.infinity.owasp_hardening.OWASPHardeningMiddleware", MagicMock(return_value=MagicMock())),
        patch("Dimensional.infinity.rbac.RBACEngine", return_value=mocks["rbac"]),
        patch("Dimensional.infinity.sentinel_station.get_sentinel_station", return_value=mocks["sentinel"]),
        patch("Dimensional.infinity.sentinel_station.SharedSSEGenerator", return_value=mocks["sse_gen"]),
        patch("Dimensional.infinity.worker_integration.InfinityWorkerKit", return_value=mocks["worker_kit"]),
    ]
    [p.start() for p in patches]
    try:
        from main import create_app
        app = create_app()
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c
    finally:
        for p in patches:
            p.stop()
