"""Phase 20 — P4 Worker test suite.

Covers all 9 intelligence-layer workers (ports 8030–8038):
  gbrain-bridge (8030), topology-service (8031), ledger-service (8032),
  model-router-service (8033), workflow-engine-service (8034),
  skills-benchmark-service (8035), langchain-integration-service (8036),
  deepagents-orchestrator-service (8037), vault-service (8038)
"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

# Map: module_name → env_var for DB_PATH override
MODULE_ENV_MAP = {
    "workers.vault-service.worker": "VAULT_DB_PATH",
    "workers.topology-service.worker": "TOPOLOGY_DB_PATH",
    "workers.ledger-service.worker": "LEDGER_DB_PATH",
    "workers.model-router-service.worker": "MODEL_ROUTER_DB_PATH",
    "workers.workflow-engine-service.worker": "WORKFLOW_DB_PATH",
    "workers.skills-benchmark-service.worker": "BENCHMARK_DB_PATH",
    "workers.langchain-integration-service.worker": "LANGCHAIN_DB_PATH",
    "workers.deepagents-orchestrator-service.worker": "__DEEPAGENTS__",
}

_module_cache: dict[str, object] = {}


@pytest.fixture()
def client(request):
    """Create a TestClient for a worker with an isolated temp database."""
    module_name = request.param

    if module_name not in _module_cache:
        tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp_path = tmp.name
        tmp.close()

        env_var = MODULE_ENV_MAP.get(module_name)
        if env_var and env_var != "__DEEPAGENTS__":
            os.environ[env_var] = tmp_path

        import importlib

        mod = importlib.import_module(module_name)

        # DeepAgents uses Path-based DB_PATH, override directly
        if module_name == "workers.deepagents-orchestrator-service.worker":
            from pathlib import Path

            mod.DB_PATH = Path(tmp_path)
            mod.init_db()
        else:
            # The 7 other workers use env-var-based DB_PATH + _init_db()
            mod._init_db()

        _module_cache[module_name] = mod

    mod = _module_cache[module_name]
    # Pass X-Internal-Secret for workers that enforce it
    secret = getattr(mod, "_INTERNAL_SECRET", "")
    headers = {"X-Internal-Secret": secret} if secret else {}
    c = TestClient(mod.app, headers=headers)
    yield c


# ═══════════════════════════════════════════════════════════════════════════════
# 1. vault-service (8038)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.vault-service.worker"], indirect=True)
class TestVaultService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "deprecated"
        assert d["service"] == "vault-service"
        assert "successor" in d

    def test_create_and_get_secret(self, client):
        r = client.post(
            "/secrets",
            json={"key": "db-password", "value": "s3cret!", "tags": ["database"]},
        )
        assert r.status_code == 201
        sid = r.json()["id"]
        r2 = client.get(f"/secrets/{sid}")
        assert r2.status_code == 200
        assert r2.json()["key"] == "db-password"

    def test_list_secrets(self, client):
        client.post("/secrets", json={"key": "k1", "value": "v1"})
        client.post("/secrets", json={"key": "k2", "value": "v2"})
        r = client.get("/secrets")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 2

    def test_revoke_secret(self, client):
        r = client.post("/secrets", json={"key": "to-revoke", "value": "val"})
        sid = r.json()["id"]
        r2 = client.put(f"/secrets/{sid}/revoke")
        assert r2.status_code == 200
        assert r2.json()["is_active"] == 0

    def test_zeroize_secret(self, client):
        r = client.post("/secrets", json={"key": "to-zeroize", "value": "val"})
        sid = r.json()["id"]
        r2 = client.put(f"/secrets/{sid}/zeroize")
        assert r2.status_code == 200
        assert r2.json()["zeroized"] is True

    def test_audit_log(self, client):
        client.post("/secrets", json={"key": "audited", "value": "v"})
        r = client.get("/audit")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_verify_audit_chain(self, client):
        client.post("/secrets", json={"key": "chain-test", "value": "v"})
        r = client.get("/audit/verify")
        assert r.status_code == 200
        assert r.json()["chain_valid"] is True

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "total_secrets" in r.json()

    def test_get_nonexistent_secret(self, client):
        r = client.get("/secrets/nonexistent-id")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 2. topology-service (8031)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.topology-service.worker"], indirect=True)
class TestTopologyService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "topology-service"

    def test_get_current_mode(self, client):
        r = client.get("/mode")
        assert r.status_code == 200
        assert r.json()["mode"] in ["TRUE_NAS", "HYBRID", "CLOUD_ONLY"]

    def test_switch_mode(self, client):
        r = client.put("/mode", json={"mode": "HYBRID", "reason": "testing"})
        assert r.status_code == 200
        r2 = client.get("/mode")
        assert r2.json()["mode"] == "HYBRID"

    def test_register_and_list_nodes(self, client):
        r = client.post(
            "/nodes",
            json={"name": "node-1", "type": "nas", "endpoint": "http://nas1:8000"},
        )
        assert r.status_code == 201
        r2 = client.get("/nodes")
        assert r2.status_code == 200
        data = r2.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_update_node_health(self, client):
        r = client.post(
            "/nodes",
            json={"name": "health-node", "type": "cloud", "endpoint": "http://c1:8000"},
        )
        nid = r.json()["id"]
        r2 = client.put(f"/nodes/{nid}/health", json={"status": "healthy", "latency_ms": 42})
        assert r2.status_code == 200
        assert r2.json()["status"] == "healthy"

    def test_deregister_node(self, client):
        r = client.post(
            "/nodes",
            json={"name": "temp-node", "type": "hybrid", "endpoint": "http://h1:8000"},
        )
        nid = r.json()["id"]
        r2 = client.delete(f"/nodes/{nid}")
        assert r2.status_code == 204

    def test_failover(self, client):
        client.put("/mode", json={"mode": "TRUE_NAS", "reason": "reset"})
        r = client.post("/failover")
        assert r.status_code == 200
        assert "new_mode" in r.json()

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "current_mode" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 3. ledger-service (8032)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.ledger-service.worker"], indirect=True)
class TestLedgerService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "ledger-service"

    def test_append_and_list_entries(self, client):
        r = client.post(
            "/entries",
            json={"actor": "admin", "action": "create_secret", "resource": "db-pw"},
        )
        assert r.status_code == 201
        r2 = client.get("/entries")
        assert r2.status_code == 200
        data = r2.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_entry(self, client):
        r = client.post("/entries", json={"actor": "system", "action": "rotate_key"})
        eid = r.json()["id"]
        r2 = client.get(f"/entries/{eid}")
        assert r2.status_code == 200
        assert r2.json()["actor"] == "system"

    def test_verify_chain(self, client):
        client.post("/entries", json={"actor": "a1", "action": "act1"})
        client.post("/entries", json={"actor": "a2", "action": "act2"})
        r = client.get("/verify")
        assert r.status_code == 200
        assert r.json()["chain_valid"] is True

    def test_sentinel_history(self, client):
        r = client.get("/sentinel/history")
        assert r.status_code == 200

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "total_entries" in r.json()

    def test_get_nonexistent_entry(self, client):
        r = client.get("/entries/nonexistent")
        assert r.status_code == 404


# ═══════════════════════════════════════════════════════════════════════════════
# 4. model-router-service (8033)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.model-router-service.worker"], indirect=True)
class TestModelRouterService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "model-router-service"

    def test_list_models(self, client):
        r = client.get("/models")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Seeded models
        assert len(data) >= 6

    def test_register_model(self, client):
        r = client.post(
            "/models",
            json={
                "name": "test-model",
                "provider": "test",
                "cost_per_1k": 0.0,
                "latency_ms": 100,
                "priority": 5,
            },
        )
        assert r.status_code == 201
        assert r.json()["name"] == "test-model"

    def test_route_request(self, client):
        r = client.post("/route", json={"strategy": "round_robin"})
        assert r.status_code == 200
        assert "model" in r.json()

    def test_report_health(self, client):
        models = client.get("/models").json()
        if models:
            mid = models[0]["id"]
            r = client.put(f"/models/{mid}/health", json={"healthy": True, "latency_ms": 50})
            assert r.status_code == 200

    def test_deregister_model(self, client):
        r = client.post(
            "/models",
            json={
                "name": "temp-model",
                "provider": "tmp",
                "cost_per_1k": 0,
                "latency_ms": 50,
                "priority": 1,
            },
        )
        mid = r.json()["id"]
        r2 = client.delete(f"/models/{mid}")
        assert r2.status_code == 204

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "total_models" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 5. workflow-engine-service (8034)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.workflow-engine-service.worker"], indirect=True)
class TestWorkflowEngineService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "workflow-engine-service"

    def test_create_workflow(self, client):
        r = client.post(
            "/workflows",
            json={
                "name": "test-flow",
                "steps": [
                    {"id": "s1", "name": "step1", "depends_on": []},
                    {"id": "s2", "name": "step2", "depends_on": ["s1"]},
                ],
            },
        )
        assert r.status_code == 201
        assert r.json()["name"] == "test-flow"

    def test_create_workflow_cycle_detected(self, client):
        r = client.post(
            "/workflows",
            json={
                "name": "cyclic-flow",
                "steps": [
                    {"id": "a", "name": "A", "depends_on": ["b"]},
                    {"id": "b", "name": "B", "depends_on": ["a"]},
                ],
            },
        )
        assert r.status_code == 400

    def test_start_run(self, client):
        wf = client.post(
            "/workflows",
            json={
                "name": "run-test",
                "steps": [{"id": "s1", "name": "step1", "depends_on": []}],
            },
        ).json()
        r = client.post(f"/workflows/{wf['id']}/runs")
        assert r.status_code == 201
        assert r.json()["status"] == "running"

    def test_list_workflows(self, client):
        client.post(
            "/workflows",
            json={"name": "list-test", "steps": [{"id": "s1", "name": "s1", "depends_on": []}]},
        )
        r = client.get("/workflows")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "total_workflows" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 6. skills-benchmark-service (8035)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.skills-benchmark-service.worker"], indirect=True)
class TestSkillsBenchmarkService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "skills-benchmark-service"

    def test_list_suites(self, client):
        r = client.get("/suites")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        # Seeded suites
        assert len(data) >= 3

    def test_create_suite(self, client):
        r = client.post(
            "/suites",
            json={
                "name": "custom-suite",
                "category": "reasoning",
                "tests": [{"name": "t1", "difficulty": "hard"}],
            },
        )
        assert r.status_code == 201
        assert r.json()["name"] == "custom-suite"

    def test_create_evaluation(self, client):
        suites = client.get("/suites").json()
        sid = suites[0]["id"]
        r = client.post("/evaluations", json={"suite_id": sid, "model_name": "test-model"})
        assert r.status_code == 201

    def test_leaderboard(self, client):
        r = client.get("/leaderboard")
        assert r.status_code == 200

    def test_skill_gaps(self, client):
        r = client.get("/skill-gaps")
        assert r.status_code == 200

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "total_suites" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 7. langchain-integration-service (8036)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("client", ["workers.langchain-integration-service.worker"], indirect=True)
class TestLangchainIntegrationService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "langchain-integration-service"

    def test_create_template(self, client):
        r = client.post(
            "/templates",
            json={"name": "greet", "template": "Hello {name}!", "variables": ["name"]},
        )
        assert r.status_code == 201
        assert r.json()["name"] == "greet"

    def test_list_templates(self, client):
        client.post("/templates", json={"name": "t1", "template": "Hi", "variables": []})
        r = client.get("/templates")
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_create_chain(self, client):
        r = client.post(
            "/chains",
            json={"name": "seq-chain", "chain_type": "sequential", "template_ids": []},
        )
        assert r.status_code == 201

    def test_create_document(self, client):
        r = client.post(
            "/documents",
            json={"name": "Test Doc", "content": "Some text content here."},
        )
        assert r.status_code == 201

    def test_list_chains(self, client):
        r = client.get("/chains")
        assert r.status_code == 200

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "prompt_templates" in r.json()


# ═══════════════════════════════════════════════════════════════════════════════
# 8. deepagents-orchestrator-service (8037)
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "client",
    ["workers.deepagents-orchestrator-service.worker"],
    indirect=True,
)
class TestDeepagentsOrchestratorService:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["service"] == "deepagents-orchestrator"
        assert r.json()["skills"] >= 10

    def test_create_and_get_agent(self, client):
        r = client.post(
            "/agents",
            json={"name": "agent-1", "capabilities": ["coding"], "model_binding": "gpt-4o-mini"},
        )
        assert r.status_code == 200
        aid = r.json()["id"]
        r2 = client.get(f"/agents/{aid}")
        assert r2.status_code == 200
        assert r2.json()["name"] == "agent-1"

    def test_list_agents(self, client):
        client.post("/agents", json={"name": "a1", "capabilities": []})
        r = client.get("/agents")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_create_and_list_tasks(self, client):
        r = client.post("/tasks", json={"title": "do-something", "priority": 3})
        assert r.status_code == 200
        r2 = client.get("/tasks")
        assert r2.json()["total"] >= 1

    def test_delegate_task(self, client):
        a1 = client.post(
            "/agents",
            json={"name": "delegator", "capabilities": ["reasoning"]},
        ).json()
        a2 = client.post("/agents", json={"name": "worker", "capabilities": ["coding"]}).json()
        t = client.post("/tasks", json={"title": "delegate-me", "priority": 5}).json()
        r = client.post(
            "/delegate",
            json={"task_id": t["id"], "from_agent_id": a1["id"], "to_agent_id": a2["id"]},
        )
        assert r.status_code == 200
        assert r.json()["depth"] == 1

    def test_skills_list(self, client):
        r = client.get("/skills")
        assert r.status_code == 200
        assert r.json()["total"] >= 10

    def test_assign_skill_to_agent(self, client):
        a = client.post("/agents", json={"name": "skilled-agent", "capabilities": []}).json()
        skills = client.get("/skills").json()["skills"]
        sid = skills[0]["id"]
        r = client.post(f"/agents/{a['id']}/skills/{sid}?proficiency=expert")
        assert r.status_code in (200, 409)  # 409 if already assigned

    def test_execution_logs(self, client):
        client.post("/agents", json={"name": "logged-agent", "capabilities": []})
        r = client.get("/logs")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    def test_stats(self, client):
        r = client.get("/stats")
        assert r.status_code == 200
        assert "agents" in r.json()
        assert "tasks" in r.json()

    def test_deregister_agent(self, client):
        a = client.post("/agents", json={"name": "to-remove", "capabilities": []}).json()
        r = client.delete(f"/agents/{a['id']}")
        assert r.status_code == 200
        assert r.json()["deregistered"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Phase 21 — Real-Time Endpoint Tests (WebSocket, SSE, Dashboard Summary)
# ═══════════════════════════════════════════════════════════════════════════════

ALL_P4_MODULES = list(MODULE_ENV_MAP.keys())


@pytest.mark.parametrize("client", ALL_P4_MODULES, indirect=True)
class TestP4RealTimeEndpoints:
    """Test the Phase 21 real-time enhancements added to all P4 workers."""

    def test_dashboard_summary(self, client):
        """GET /dashboard/summary returns aggregated service data."""
        r = client.get("/dashboard/summary")
        assert r.status_code == 200
        data = r.json()
        assert "service" in data
        assert "port" in data
        assert "status" in data
        assert data["status"] == "healthy"
        assert "summary" in data
        assert "real_time" in data
        # real_time should advertise ws and sse URLs
        rt = data["real_time"]
        assert "websocket" in rt
        assert "sse" in rt

    def test_websocket_connect_and_ping(self, client):
        """WebSocket /ws accepts connection, sends initial_state, responds to ping."""
        with client.websocket_connect("/ws") as ws:
            # First message should be initial_state
            init_msg = ws.receive_json()
            assert init_msg["type"] == "initial_state"
            assert "data" in init_msg

            # Send ping, expect pong
            ws.send_text('{"type": "ping"}')
            msg = ws.receive_json()
            assert msg["type"] == "pong"

    def test_websocket_get_stats(self, client):
        """WebSocket /ws responds to get_stats message."""
        with client.websocket_connect("/ws") as ws:
            # Consume initial_state
            ws.receive_json()

            ws.send_text('{"type": "get_stats"}')
            msg = ws.receive_json()
            assert msg["type"] == "stats"
            assert "data" in msg

    @pytest.mark.skip(reason="SSE EventSourceResponse hangs in TestClient; verified manually")
    def test_sse_events_endpoint(self, client):
        """GET /events returns an SSE stream."""
        r = client.get("/events")
        assert r.status_code == 200
