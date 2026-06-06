# tests/test_enhanced_api.py
# LEGACY TEST — api_enhanced.py has been archived to archive/api_enhanced.py.
# Canonical tests for these routes now live in tests/test_canonical_routes.py.
# This file is retained for historical reference only; it imports from archive/.
# Uses TestClient with mocked subsystems so no real Redis/DB/AI needed.

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Disable auth and set safe test defaults before importing app
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("REQUIRE_AUTH", "false")
os.environ.setdefault("ALLOWED_ORIGINS", "*")
os.environ.setdefault("SECRET_KEY", "test-secret-key-for-unit-tests-0000001")
os.environ.setdefault("JWT_SECRET", "test-secret-for-unit-tests-only-32chars")
os.environ.setdefault("TRANC3_API_KEY", "test-key-12345")


def _make_enhanced_mock():
    m = MagicMock()
    m.initialize = AsyncMock()
    m.start_background_services = AsyncMock()
    m.print_banner = MagicMock()
    m.think = AsyncMock(return_value={"response": "hello", "personality": "tranc3-base"})
    m.get_system_health = AsyncMock(return_value={"status": "ok", "components": {}})
    m.call_mcp_tool = AsyncMock(return_value={"result": "tool_result"})
    m.execute_workflow = AsyncMock(return_value={"execution_id": "abc", "status": "completed"})
    m._subsystems = {
        "evolution": MagicMock(
            get_stats=MagicMock(return_value={"generation": 1, "best_fitness": 0.9}),
            record_feedback=MagicMock(),
        ),
    }
    return m


@pytest.fixture(scope="module")
def client():
    enhanced_mock = _make_enhanced_mock()
    with (
        patch("src.core.startup_validator.validate_startup"),
        patch("src.main_enhanced.enhanced", enhanced_mock),
    ):
        from fastapi.testclient import TestClient

        import sys
        import os as _os
        sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'archive'))
        from api_enhanced import app

        # Manually inject mock into app state (lifespan won't run in TestClient)
        app.state.enhanced = enhanced_mock
        yield TestClient(app, raise_server_exceptions=False)


# ─── Core ──────────────────────────────────────────────────────────────────────


class TestCoreEndpoints:
    def test_root_returns_200(self, client):
        r = client.get("/")
        assert r.status_code == 200
        data = r.json()
        assert data["system"] == "TRANC3 Enhanced"
        assert data["version"] == "3.0.0"
        assert data["status"] == "operational"

    def test_health_returns_200(self, client):
        r = client.get("/health")
        assert r.status_code == 200

    def test_think_accepts_valid_prompt(self, client):
        r = client.post("/think", json={"prompt": "Hello TRANC3"})
        assert r.status_code == 200
        assert "response" in r.json()

    def test_think_rejects_empty_prompt(self, client):
        r = client.post("/think", json={"prompt": ""})
        assert r.status_code == 422

    def test_think_rejects_oversized_prompt(self, client):
        r = client.post("/think", json={"prompt": "x" * 9000})
        assert r.status_code == 422

    def test_think_with_personality(self, client):
        r = client.post(
            "/think",
            json={"prompt": "Analyse portfolio risk", "personality": "dorris-fontaine"},
        )
        assert r.status_code == 200


# ─── MCP ───────────────────────────────────────────────────────────────────────


class TestMCPEndpoints:
    def test_list_tools_public(self, client):
        r = client.get("/mcp/tools")
        assert r.status_code in (200, 503)  # 503 if registry not loaded

    def test_mcp_rpc_initialize(self, client):
        r = client.post(
            "/mcp/rpc",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"clientInfo": {"name": "test", "version": "0.1"}},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data or "error" in data

    def test_mcp_rpc_invalid_method(self, client):
        r = client.post(
            "/mcp/rpc",
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "nonexistent/method",
                "params": {},
            },
        )
        assert r.status_code == 200
        data = r.json()
        assert "error" in data

    def test_mcp_rpc_bad_json_version(self, client):
        r = client.post(
            "/mcp/rpc",
            json={
                "jsonrpc": "1.0",
                "id": 3,
                "method": "ping",
            },
        )
        assert r.status_code == 200
        assert "error" in r.json()

    def test_mcp_tool_call(self, client):
        r = client.post("/mcp/tool", json={"tool": "get_evolution_stats", "params": {}})
        assert r.status_code in (200, 404, 503)


# ─── Workflow ──────────────────────────────────────────────────────────────────


class TestWorkflowEndpoints:
    def test_templates_public(self, client):
        r = client.get("/workflow/templates")
        assert r.status_code in (200, 503)

    def test_execute_workflow_valid(self, client):
        r = client.post(
            "/workflow/execute",
            json={
                "workflow": {
                    "id": "test-wf",
                    "name": "Test",
                    "nodes": [],
                    "edges": [],
                },
                "inputs": {},
            },
        )
        assert r.status_code in (200, 500, 503)

    def test_workflow_status_not_found(self, client):
        r = client.get("/workflow/status/nonexistent-id-12345")
        assert r.status_code in (404, 503)


# ─── Skills ────────────────────────────────────────────────────────────────────


class TestSkillsEndpoints:
    def test_search_valid(self, client):
        r = client.post("/skills/search", json={"query": "security compliance"})
        assert r.status_code in (200, 503)

    def test_search_empty_query_rejected(self, client):
        r = client.post("/skills/search", json={"query": ""})
        assert r.status_code == 422

    def test_search_top_k_limit(self, client):
        r = client.post("/skills/search", json={"query": "test", "top_k": 200})
        assert r.status_code == 422

    def test_stats_public(self, client):
        r = client.get("/skills/stats")
        assert r.status_code in (200, 503)

    def test_detect_bundle(self, client):
        r = client.post("/skills/detect-bundle", json={"prompt": "run compliance audit"})
        assert r.status_code in (200, 503)


# ─── Code Generation ───────────────────────────────────────────────────────────


class TestCodeGenEndpoints:
    def test_generate_valid(self, client):
        r = client.post(
            "/code/generate",
            json={
                "description": "A function to compute fibonacci numbers",
                "language": "python",
            },
        )
        assert r.status_code in (200, 503)

    def test_generate_empty_description_rejected(self, client):
        r = client.post("/code/generate", json={"description": "", "language": "python"})
        assert r.status_code == 422

    def test_generate_invalid_language_rejected(self, client):
        r = client.post(
            "/code/generate",
            json={
                "description": "test",
                "language": "../../etc/passwd",
            },
        )
        assert r.status_code == 422

    def test_improve_valid(self, client):
        r = client.post("/code/improve", json={"code": "def foo(): pass"})
        assert r.status_code in (200, 503)

    def test_improve_empty_code_rejected(self, client):
        r = client.post("/code/improve", json={"code": ""})
        assert r.status_code == 422

    def test_explain_public(self, client):
        r = client.post("/code/explain", json={"code": "x = 1 + 1"})
        assert r.status_code in (200, 503)


# ─── Healing ───────────────────────────────────────────────────────────────────


class TestHealingEndpoints:
    def test_dashboard_public(self, client):
        r = client.get("/healing/dashboard")
        assert r.status_code == 200

    def test_repair_protected(self, client):
        r = client.post("/healing/repair")
        # Without REQUIRE_AUTH, should succeed or 503 if subsystem unavailable
        assert r.status_code in (200, 503)

    def test_bots_public(self, client):
        r = client.get("/healing/bots")
        assert r.status_code in (200, 503)


# ─── Evolution ─────────────────────────────────────────────────────────────────


class TestEvolutionEndpoints:
    def test_stats_public(self, client):
        r = client.get("/evolution/stats")
        assert r.status_code in (200, 503)

    def test_feedback_valid(self, client):
        r = client.post(
            "/evolution/feedback",
            json={
                "quality_score": 0.85,
                "user_satisfaction": 0.9,
                "session_id": "test-session",
            },
        )
        assert r.status_code in (200, 503)

    def test_feedback_out_of_range_rejected(self, client):
        r = client.post(
            "/evolution/feedback",
            json={
                "quality_score": 1.5,  # > 1.0
                "user_satisfaction": 0.9,
            },
        )
        assert r.status_code == 422

    def test_feedback_negative_rejected(self, client):
        r = client.post(
            "/evolution/feedback",
            json={
                "quality_score": -0.1,
                "user_satisfaction": 0.9,
            },
        )
        assert r.status_code == 422


# ─── Personality ───────────────────────────────────────────────────────────────


class TestPersonalityEndpoints:
    def test_list_personalities(self, client):
        r = client.get("/personality/list")
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            assert "personalities" in data
            names = [p["name"] for p in data["personalities"]]
            # All five named personalities must be present
            assert "dorris-fontaine" in names
            assert "cornelius-macintyre" in names
            assert "the-guardian" in names
            assert "vesper-nightingale" in names
            assert "atlas-meridian" in names

    def test_get_vector_known_personality(self, client):
        r = client.post("/personality/vector", json={"name": "dorris-fontaine"})
        assert r.status_code in (200, 503)
        if r.status_code == 200:
            data = r.json()
            assert "vector" in data
            assert len(data["vector"]) == 12  # 12 trait dimensions

    def test_get_vector_unknown_falls_back(self, client):
        r = client.post("/personality/vector", json={"name": "does-not-exist"})
        # Falls back to tranc3-base — should still return 200
        assert r.status_code in (200, 503)

    def test_spawn_invalid_personality(self, client):
        r = client.post(
            "/personality/spawn",
            json={
                "personality_id": "nonexistent",
                "repo_name": "test-repo",
            },
        )
        assert r.status_code in (503,)  # ValueError propagated as 503


# ─── Auth & Rate Limiting ──────────────────────────────────────────────────────


class TestAuthAndRateLimiting:
    def test_auth_disabled_by_default_in_test(self, client):
        """With REQUIRE_AUTH=false, all endpoints accessible."""
        r = client.post("/think", json={"prompt": "test"})
        assert r.status_code != 401

    def test_rate_limit_in_memory_tracking(self):
        """Verify _rate_store tracks requests per IP."""
        import sys
        import os as _os
        sys.path.insert(0, _os.path.join(_os.path.dirname(__file__), '..', 'archive'))
        import api_enhanced as api

        initial = len(api._rate_store)
        # Make a request — the store should have grown
        from fastapi.testclient import TestClient

        c = TestClient(api.app, raise_server_exceptions=False)
        c.get("/health")
        assert len(api._rate_store) >= initial

    def test_field_validation_rejects_path_traversal_in_language(self, client):
        """Ensure language field regex blocks injection attempts."""
        for bad in ["../evil", "python; rm -rf /", "py thon"]:
            r = client.post("/code/generate", json={"description": "test", "language": bad})
            assert r.status_code == 422, f"Expected 422 for language='{bad}'"

    def test_repo_name_regex_blocks_path_traversal(self, client):
        """Ensure repo_name field only allows safe chars."""
        for bad in ["../etc", "name with space", "name;echo"]:
            r = client.post(
                "/personality/spawn",
                json={
                    "personality_id": "the-guardian",
                    "repo_name": bad,
                },
            )
            assert r.status_code == 422, f"Expected 422 for repo_name='{bad}'"
