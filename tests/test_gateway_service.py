"""Phase 21 — Gateway Aggregation Service test suite.

Covers the unified gateway (port 8040) that aggregates all P4 worker data:
  - Health and stats endpoints
  - /api/overview, /api/agents, /api/models, /api/workflows, /api/security, /api/audit
  - WebSocket /ws for real-time push
  - SSE /events stream
  - Event persistence (POST /events, GET /events/history)
  - Topology mode switching (PUT /api/topology/mode)
  - Cache layer with 5s TTL
  - Circuit breaker per upstream worker
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """Create a TestClient for the gateway service with an isolated temp database."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_path = tmp.name
    tmp.close()

    os.environ["GATEWAY_DB_PATH"] = tmp_path
    os.environ["GATEWAY_PORT"] = "8040"

    import importlib

    mod = importlib.import_module("workers.gateway-service.worker")
    mod._init_db()

    with TestClient(mod.app) as c:
        yield c

    os.unlink(tmp_path)


# ── Health & Stats ──────────────────────────────────────────────────────────


class TestGatewayHealth:
    def test_health_endpoint(self, client):
        res = client.get("/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "ok"
        assert data["service"] == "gateway-service"
        assert data["upstream_workers"] == 8

    def test_stats_endpoint(self, client):
        res = client.get("/stats")
        assert res.status_code == 200
        data = res.json()
        assert data["upstream_workers"] == 8
        assert "reachable" in data
        assert "unreachable" in data
        assert "cache_entries" in data
        assert "circuit_breakers" in data


# ── Aggregated API Endpoints ────────────────────────────────────────────────


class TestGatewayOverview:
    def test_overview_returns_structure(self, client):
        res = client.get("/api/overview")
        assert res.status_code == 200
        data = res.json()
        # Top-level keys: platform, services, ai, security, infrastructure, workers
        assert "platform" in data
        assert "services" in data
        assert "ai" in data
        assert "security" in data
        assert "infrastructure" in data
        assert "workers" in data

    def test_overview_platform_info(self, client):
        res = client.get("/api/overview")
        data = res.json()
        platform = data["platform"]
        assert platform["name"] == "Tranc3"
        assert platform["version"] == "0.6.0"
        assert platform["status"] in ("operational", "degraded", "critical")

    def test_overview_services_structure(self, client):
        res = client.get("/api/overview")
        data = res.json()
        services = data["services"]
        assert isinstance(services, dict)
        assert services["total"] == 8


class TestGatewayAgents:
    def test_agents_endpoint(self, client):
        res = client.get("/api/agents")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        assert "agents" in data
        assert "skills" in data
        assert "tasks" in data
        assert "total_agents" in data

    def test_agents_create_rejects_bad_schema(self, client):
        """AgentCreate requires 'name' field; missing it should 422."""
        res = client.post("/api/agents", json={"prompt": "test agent"})
        assert res.status_code == 422


class TestGatewayModels:
    def test_models_endpoint(self, client):
        res = client.get("/api/models")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        assert "models" in data
        assert "total_models" in data


class TestGatewayWorkflows:
    def test_workflows_endpoint(self, client):
        res = client.get("/api/workflows")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        assert "workflows" in data
        assert "total_workflows" in data


class TestGatewaySecurity:
    def test_security_endpoint(self, client):
        res = client.get("/api/security")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        assert "vault" in data
        assert "ledger" in data
        assert "topology" in data


class TestGatewayAudit:
    def test_audit_endpoint(self, client):
        res = client.get("/api/audit")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, dict)
        assert "ledger" in data
        assert "vault_audit" in data
        assert "total_ledger" in data
        assert "total_vault_audit" in data


# ── Topology Mode Switching ─────────────────────────────────────────────────


class TestGatewayTopology:
    def test_topology_mode_switch_hybrid(self, client):
        """PUT /api/topology/mode forwards to topology service (may 503 if down)."""
        res = client.put("/api/topology/mode", json={"mode": "HYBRID"})
        # Upstream is down in test, so expect 503; but schema is valid
        assert res.status_code in (200, 503)

    def test_topology_mode_switch_nas(self, client):
        res = client.put("/api/topology/mode", json={"mode": "TRUE_NAS"})
        assert res.status_code in (200, 503)

    def test_topology_mode_switch_cloud(self, client):
        res = client.put("/api/topology/mode", json={"mode": "CLOUD_ONLY"})
        assert res.status_code in (200, 503)

    def test_topology_mode_missing_field(self, client):
        """Missing 'mode' field should 422."""
        res = client.put("/api/topology/mode", json={})
        assert res.status_code == 422


# ── Event Persistence ───────────────────────────────────────────────────────


class TestGatewayEvents:
    def test_post_event(self, client):
        res = client.post(
            "/events",
            json={
                "source": "test",
                "event_type": "test_event",
                "payload": {"key": "value"},
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["event_type"] == "test_event"
        assert data["source"] == "test"
        assert "id" in data
        assert "created_at" in data

    def test_get_events_history(self, client):
        # Post an event first
        client.post(
            "/events",
            json={
                "source": "test",
                "event_type": "history_test",
                "payload": {},
            },
        )
        res = client.get("/events/history")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_events_history_with_limit(self, client):
        # Post multiple events
        for i in range(5):
            client.post(
                "/events",
                json={
                    "source": "test",
                    "event_type": f"limit_test_{i}",
                    "payload": {"i": i},
                },
            )
        res = client.get("/events/history?limit=3")
        assert res.status_code == 200
        data = res.json()
        assert len(data) <= 3

    def test_post_event_minimal(self, client):
        """Payload is optional (defaults to empty dict)."""
        res = client.post(
            "/events",
            json={
                "source": "test",
                "event_type": "minimal",
            },
        )
        assert res.status_code == 200


# ── WebSocket ───────────────────────────────────────────────────────────────


class TestGatewayWebSocket:
    def test_ws_connect_and_ping(self, client):
        with client.websocket_connect("/ws") as ws:
            # First message should be initial_state
            init_msg = ws.receive_json()
            assert init_msg["type"] == "initial_state"
            assert "data" in init_msg

            # Send ping
            ws.send_text('{"type": "ping"}')
            msg = ws.receive_json()
            assert msg["type"] == "pong"

    def test_ws_get_overview(self, client):
        with client.websocket_connect("/ws") as ws:
            # Consume initial state push
            ws.receive_json()

            ws.send_text('{"type": "get_overview"}')
            msg = ws.receive_json()
            assert msg["type"] == "overview"
            assert "data" in msg

    def test_ws_subscribe(self, client):
        with client.websocket_connect("/ws") as ws:
            # Consume initial state push
            ws.receive_json()

            ws.send_text('{"type": "subscribe", "channels": ["agents", "workflows"]}')
            msg = ws.receive_json()
            assert msg["type"] == "subscribed"
            assert "channels" in msg

    def test_ws_invalid_json(self, client):
        with client.websocket_connect("/ws") as ws:
            # Consume initial state push
            ws.receive_json()

            ws.send_text("not json")
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "message" in msg


# ── SSE ─────────────────────────────────────────────────────────────────────


class TestGatewaySSE:
    @pytest.mark.skip(reason="SSE EventSourceResponse hangs in TestClient; verified manually")
    def test_sse_events_endpoint_exists(self, client):
        """SSE endpoint should exist and return proper content type.

        TestClient doesn't stream SSE well, but we can verify the route exists
        by checking that it doesn't 404.
        """
        res = client.get("/events")
        # 200 = SSE stream started; other codes are also acceptable
        assert res.status_code != 404


# ── Cache Layer ─────────────────────────────────────────────────────────────


class TestGatewayCache:
    def test_cache_ttl_config(self, client):
        """Verify cache TTL is configurable via env var."""
        import importlib

        mod = importlib.import_module("workers.gateway-service.worker")
        assert hasattr(mod, "CACHE_TTL")
        assert isinstance(mod.CACHE_TTL, int)
        assert mod.CACHE_TTL >= 1

    def test_cache_in_memory_structure(self, client):
        """Verify the in-memory cache dict exists."""
        import importlib

        mod = importlib.import_module("workers.gateway-service.worker")
        assert hasattr(mod, "_cache")
        assert isinstance(mod._cache, dict)


# ── Circuit Breaker ─────────────────────────────────────────────────────────


class TestGatewayCircuitBreaker:
    def test_circuit_breaker_initialized(self, client):
        """Verify circuit breakers are initialized for all upstream workers."""
        import importlib

        mod = importlib.import_module("workers.gateway-service.worker")
        assert hasattr(mod, "_circuit_breaker")
        cb = mod._circuit_breaker
        # Should have entries for all 8 workers
        assert len(cb) == 8
        for name, state in cb.items():
            assert state["state"] == "closed"
            assert state["failures"] == 0

    def test_upstream_workers_config(self, client):
        """Verify all 8 upstream workers are configured."""
        import importlib

        mod = importlib.import_module("workers.gateway-service.worker")
        uw = mod.UPSTREAM_WORKERS
        assert len(uw) == 8
        expected = {
            "vault",
            "topology",
            "ledger",
            "model_router",
            "workflow",
            "benchmark",
            "langchain",
            "deepagents",
        }
        assert set(uw.keys()) == expected
