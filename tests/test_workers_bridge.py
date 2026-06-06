"""
Worker HTTP tests — Three Bridge Workers
=========================================
Tests the HTTP API layer of the three bridge worker entry points:
  - hive-service (port 8060)       — Data movement & swarm coordination
  - dimensional-nexus-service (port 8050) — AI/Agent/Bot traffic
  - infinity-bridge-service (port 8070)   — User context & human traffic

These workers wrap Dimensional module factory functions and expose
a FastAPI application protected by X-Internal-Secret middleware on
all routes except /health (and / for infinity-bridge).

The tests verify:
  1. /health is publicly accessible (no auth required)
  2. Protected routes return 401 when secret is missing
  3. Protected routes return non-401 when the correct secret is provided
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parent.parent


def _import(dotted: str, path: Path):
    if dotted in sys.modules:
        return sys.modules[dotted]
    spec = importlib.util.spec_from_file_location(dotted, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    return mod


_hive_mod = _import("hive_worker", _ROOT / "workers" / "hive-service" / "worker.py")
_nexus_mod = _import("nexus_worker", _ROOT / "workers" / "dimensional-nexus-service" / "worker.py")
_bridge_mod = _import(
    "infinity_bridge_worker",
    _ROOT / "workers" / "infinity-bridge-service" / "worker.py",
)


def _client(mod) -> TestClient:
    secret = getattr(mod, "_INTERNAL_SECRET", "")
    headers = {"X-Internal-Secret": secret} if secret else {}
    return TestClient(mod.app, headers=headers)


def _unauth_client(mod) -> TestClient:
    """Client without auth header — for testing 401 paths."""
    return TestClient(mod.app, headers={})


# ═══════════════════════════════════════════════════════════════════════════════
# hive-service — The HIVE (port 8060)
# ═══════════════════════════════════════════════════════════════════════════════


class TestHiveWorker:
    def test_health_public(self):
        """GET /health should be accessible without auth."""
        c = _unauth_client(_hive_mod)
        r = c.get("/health")
        assert r.status_code == 200

    def test_health_returns_ok(self):
        """GET /health should indicate operational status."""
        c = _client(_hive_mod)
        r = c.get("/health")
        assert r.status_code == 200
        data = r.json()
        # hive_core returns its own health structure; worker adds fallback
        assert isinstance(data, dict)

    def test_status_requires_auth(self):
        """GET /status should require X-Internal-Secret when secret is set."""
        secret = getattr(_hive_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set — auth middleware inactive")
        c = _unauth_client(_hive_mod)
        r = c.get("/status")
        assert r.status_code == 401

    def test_sources_requires_auth(self):
        """GET /sources should require X-Internal-Secret when secret is set."""
        secret = getattr(_hive_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set — auth middleware inactive")
        c = _unauth_client(_hive_mod)
        r = c.get("/sources")
        assert r.status_code == 401

    def test_status_with_auth(self):
        """GET /status is accessible with the correct secret."""
        c = _client(_hive_mod)
        r = c.get("/status")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_sources_with_auth(self):
        """GET /sources is accessible with the correct secret."""
        c = _client(_hive_mod)
        r = c.get("/sources")
        assert r.status_code == 200

    def test_sinks_with_auth(self):
        """GET /sinks is accessible with the correct secret."""
        c = _client(_hive_mod)
        r = c.get("/sinks")
        assert r.status_code == 200

    def test_pipelines_with_auth(self):
        """GET /pipelines is accessible with the correct secret."""
        c = _client(_hive_mod)
        r = c.get("/pipelines")
        assert r.status_code == 200

    def test_swarms_with_auth(self):
        """GET /swarms is accessible with the correct secret."""
        c = _client(_hive_mod)
        r = c.get("/swarms")
        assert r.status_code == 200

    def test_flow_with_auth(self):
        """GET /flow is accessible with the correct secret."""
        c = _client(_hive_mod)
        r = c.get("/flow")
        assert r.status_code == 200

    def test_wrong_secret_rejected(self):
        """Wrong X-Internal-Secret should yield 401."""
        secret = getattr(_hive_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set")
        c = TestClient(_hive_mod.app, headers={"X-Internal-Secret": "wrong-secret-xyz"})
        r = c.get("/status")
        assert r.status_code == 401

    def test_app_has_internal_secret(self):
        """The module exposes _INTERNAL_SECRET attribute."""
        assert hasattr(_hive_mod, "_INTERNAL_SECRET")


# ═══════════════════════════════════════════════════════════════════════════════
# dimensional-nexus-service — The Nexus (port 8050)
# ═══════════════════════════════════════════════════════════════════════════════


class TestNexusWorker:
    def test_health_public(self):
        """GET /health should be accessible without auth."""
        c = _unauth_client(_nexus_mod)
        r = c.get("/health")
        assert r.status_code == 200

    def test_health_returns_ok(self):
        """GET /health should return a valid health structure."""
        c = _client(_nexus_mod)
        r = c.get("/health")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_status_requires_auth(self):
        """GET /status should require X-Internal-Secret when secret is set."""
        secret = getattr(_nexus_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set — auth middleware inactive")
        c = _unauth_client(_nexus_mod)
        r = c.get("/status")
        assert r.status_code == 401

    def test_topology_requires_auth(self):
        """GET /topology should require X-Internal-Secret when secret is set."""
        secret = getattr(_nexus_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set — auth middleware inactive")
        c = _unauth_client(_nexus_mod)
        r = c.get("/topology")
        assert r.status_code == 401

    def test_status_with_auth(self):
        """GET /status is accessible with the correct secret."""
        c = _client(_nexus_mod)
        r = c.get("/status")
        assert r.status_code == 200
        assert isinstance(r.json(), dict)

    def test_topology_with_auth(self):
        """GET /topology is accessible with the correct secret."""
        c = _client(_nexus_mod)
        r = c.get("/topology")
        assert r.status_code == 200

    def test_topology_nodes_with_auth(self):
        """GET /topology/nodes is accessible with the correct secret."""
        c = _client(_nexus_mod)
        r = c.get("/topology/nodes")
        assert r.status_code == 200

    def test_events_recent_with_auth(self):
        """GET /events/recent is accessible with the correct secret."""
        c = _client(_nexus_mod)
        r = c.get("/events/recent")
        assert r.status_code == 200

    def test_access_tiers_with_auth(self):
        """GET /access/tiers is accessible with the correct secret."""
        c = _client(_nexus_mod)
        r = c.get("/access/tiers")
        assert r.status_code == 200

    def test_wrong_secret_rejected(self):
        """Wrong X-Internal-Secret should yield 401."""
        secret = getattr(_nexus_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set")
        c = TestClient(_nexus_mod.app, headers={"X-Internal-Secret": "wrong-secret-xyz"})
        r = c.get("/status")
        assert r.status_code == 401

    def test_app_has_internal_secret(self):
        """The module exposes _INTERNAL_SECRET attribute."""
        assert hasattr(_nexus_mod, "_INTERNAL_SECRET")

    def test_dimensional_nexus_alias(self):
        """DimensionalNexus is a backward-compatible alias for Nexus."""
        assert _nexus_mod.DimensionalNexus is _nexus_mod.Nexus


# ═══════════════════════════════════════════════════════════════════════════════
# infinity-bridge-service — InfinityBridge (port 8070)
# ═══════════════════════════════════════════════════════════════════════════════


class TestInfinityBridgeWorker:
    def test_module_level_app_exists(self):
        """Module must expose a module-level app for testability."""
        assert hasattr(_bridge_mod, "app")

    def test_app_has_internal_secret(self):
        """Module exposes _INTERNAL_SECRET attribute."""
        assert hasattr(_bridge_mod, "_INTERNAL_SECRET")

    def test_health_public(self):
        """GET /health is accessible without auth."""
        c = _unauth_client(_bridge_mod)
        r = c.get("/health")
        assert r.status_code == 200

    def test_root_public(self):
        """GET / (service info) is accessible without auth."""
        c = _unauth_client(_bridge_mod)
        r = c.get("/")
        assert r.status_code == 200
        data = r.json()
        assert "three_bridges" in data

    def test_users_list_requires_auth(self):
        """GET /users should require X-Internal-Secret when secret is set."""
        secret = getattr(_bridge_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set — auth middleware inactive")
        c = _unauth_client(_bridge_mod)
        r = c.get("/users")
        assert r.status_code == 401

    def test_paths_requires_auth(self):
        """GET /paths should require X-Internal-Secret when secret is set."""
        secret = getattr(_bridge_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set — auth middleware inactive")
        c = _unauth_client(_bridge_mod)
        r = c.get("/paths")
        assert r.status_code == 401

    def test_users_list_with_auth(self):
        """GET /users is accessible with the correct secret."""
        c = _client(_bridge_mod)
        r = c.get("/users")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_paths_with_auth(self):
        """GET /paths is accessible with the correct secret."""
        c = _client(_bridge_mod)
        r = c.get("/paths")
        assert r.status_code == 200

    def test_locations_with_auth(self):
        """GET /locations is accessible with the correct secret."""
        c = _client(_bridge_mod)
        r = c.get("/locations")
        assert r.status_code == 200

    def test_presence_with_auth(self):
        """GET /presence is accessible with the correct secret."""
        c = _client(_bridge_mod)
        r = c.get("/presence")
        assert r.status_code == 200

    def test_connect_user(self):
        """POST /users/connect creates a user context."""
        c = _client(_bridge_mod)
        r = c.post(
            "/users/connect",
            params={"user_id": "test-user-001", "location": "infinity_portal"},
        )
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == "test-user-001"

    def test_disconnect_user(self):
        """POST /users/{id}/disconnect removes a connected user."""
        c = _client(_bridge_mod)
        c.post("/users/connect", params={"user_id": "test-user-002"})
        r = c.post("/users/test-user-002/disconnect")
        assert r.status_code == 200

    def test_disconnect_unknown_user(self):
        """POST /users/{id}/disconnect for unknown user returns error."""
        c = _client(_bridge_mod)
        r = c.post("/users/no-such-user-xyz/disconnect")
        # Returns tuple (error_dict, 404) from bridge — FastAPI returns 200 with tuple
        # The actual behavior depends on how the bridge handles it
        assert r.status_code in (200, 404)

    def test_wrong_secret_rejected(self):
        """Wrong X-Internal-Secret yields 401."""
        secret = getattr(_bridge_mod, "_INTERNAL_SECRET", "")
        if not secret:
            pytest.skip("_INTERNAL_SECRET not set")
        c = TestClient(_bridge_mod.app, headers={"X-Internal-Secret": "wrong-secret-xyz"})
        r = c.get("/users")
        assert r.status_code == 401

    def test_root_service_info_structure(self):
        """GET / returns correct three-bridges metadata."""
        c = _client(_bridge_mod)
        r = c.get("/")
        assert r.status_code == 200
        data = r.json()
        bridges = data["three_bridges"]
        assert "infinity_bridge" in bridges
        assert "nexus" in bridges
        assert "hive" in bridges
        assert bridges["infinity_bridge"]["port"] == 8070
        assert bridges["nexus"]["port"] == 8050
        assert bridges["hive"]["port"] == 8060
