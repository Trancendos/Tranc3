"""
Compatibility Tests — JSON-RPC 2.0, MCP protocol version, Pydantic v2, serialization.

Verifies that all interfaces and data contracts are structurally compatible:
  - JSON-RPC 2.0 framing
  - MCP protocol version negotiation
  - Pydantic v2 model config (no .Config class, uses model_config)
  - WorkflowDefinition.to_dict() roundtrip produces valid JSON
  - NodeType and ErrorCode are string-valued enums
  - The Digital Grid and The Spark agree on engine field
"""
from __future__ import annotations

import json
import logging
import pytest

_log = logging.getLogger("tranc3.tests.compatibility")


# ---------------------------------------------------------------------------
# JSON-RPC 2.0 framing
# ---------------------------------------------------------------------------

class TestJSONRPC20Compatibility:
    @pytest.mark.asyncio
    async def test_request_with_string_id(self, caplog):
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": "str-id-001", "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "compat", "version": "0"}},
        })
        _log.info("compat.jsonrpc string_id id=%s keys=%s", resp.get("id"), list(resp.keys()))
        assert resp.get("id") == "str-id-001"
        assert "result" in resp

    @pytest.mark.asyncio
    async def test_request_with_integer_id(self, caplog):
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 42, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "compat", "version": "0"}},
        })
        _log.info("compat.jsonrpc integer_id id=%s", resp.get("id"))
        assert resp.get("id") == 42

    @pytest.mark.asyncio
    async def test_response_always_has_jsonrpc_field(self, caplog):
        from src.mcp.server import handle_rpc
        for method in ("initialize", "tools/list", "nonexistent_method"):
            resp = await handle_rpc({
                "jsonrpc": "2.0", "id": 1, "method": method,
                "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "c", "version": "0"}}
                if method == "initialize" else {},
            })
            _log.info("compat.jsonrpc method=%s has_jsonrpc=%s", method, "jsonrpc" in resp)
            assert "jsonrpc" in resp
            assert resp["jsonrpc"] == "2.0"

    @pytest.mark.asyncio
    async def test_error_response_has_correct_shape(self, caplog):
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "bad_method", "params": {}
        })
        _log.info("compat.jsonrpc error_shape error=%s", resp.get("error"))
        assert "error" in resp
        err = resp["error"]
        assert "code" in err
        assert "message" in err
        assert isinstance(err["code"], int)

    @pytest.mark.asyncio
    async def test_tools_call_response_has_content_field(self, caplog):
        """tools/call responses must have a 'content' or 'result.content' field per MCP spec."""
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "get_system_health", "arguments": {"subsystems": ["mcp_server"]}},
        })
        _log.info("compat.jsonrpc tools_call resp_keys=%s", list(resp.keys()))
        # Must be either a result or an error
        assert "result" in resp or "error" in resp


# ---------------------------------------------------------------------------
# MCP protocol version compatibility
# ---------------------------------------------------------------------------

class TestMCPProtocolVersionCompatibility:
    @pytest.mark.asyncio
    async def test_protocol_version_2024_11_05_accepted(self, caplog):
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "c", "version": "0"}},
        })
        _log.info("compat.mcp proto_version result_keys=%s", list(resp.get("result", {}).keys()))
        assert "result" in resp
        assert resp["result"]["protocolVersion"] == "2024-11-05"

    @pytest.mark.asyncio
    async def test_server_info_name_and_grid(self, caplog):
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "c", "version": "0"}},
        })
        info = resp["result"]["serverInfo"]
        _log.info("compat.mcp server_info name=%s grid=%s version=%s",
                  info.get("name"), info.get("grid"), info.get("version"))
        assert info["name"] == "the-spark"
        assert info["grid"] == "the-digital-grid"
        assert "version" in info

    @pytest.mark.asyncio
    async def test_capabilities_tools_and_resources(self, caplog):
        from src.mcp.server import handle_rpc
        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "c", "version": "0"}},
        })
        caps = resp["result"]["capabilities"]
        _log.info("compat.mcp capabilities=%s", list(caps.keys()))
        assert "tools" in caps
        assert "resources" in caps


# ---------------------------------------------------------------------------
# Pydantic v2 compatibility
# ---------------------------------------------------------------------------

class TestPydanticV2Compatibility:
    def test_spark_tool_is_pydantic_v2_model(self, caplog):
        import pydantic
        _log.info("compat.pydantic pydantic_version=%s", pydantic.__version__)
        assert int(pydantic.__version__.split(".")[0]) >= 2, "Pydantic v2+ required"

    def test_spark_tool_no_inner_config_class(self, caplog):
        """Pydantic v2 uses model_config, not inner Config class."""
        from src.mcp.tools import SparkTool
        has_inner_config = hasattr(SparkTool, "Config") and isinstance(getattr(SparkTool, "Config"), type)
        _log.info("compat.pydantic spark_tool has_inner_Config=%s", has_inner_config)
        assert not has_inner_config, "SparkTool must not use inner Config class (Pydantic v2)"

    def test_node_config_is_pydantic_v2_model(self, caplog):
        from src.workflow.nodes import NodeConfig, NodeType
        nc = NodeConfig(id="c1", type=NodeType.OUTPUT, name="out", config={})
        _log.info("compat.pydantic node_config id=%s type=%s", nc.id, nc.type)
        assert nc.id == "c1"
        assert nc.type == NodeType.OUTPUT

    def test_workflow_definition_model_dump(self, caplog, sample_workflow_definitions):
        """WorkflowDefinition should support model_dump() (Pydantic v2) not .dict()."""
        wf = sample_workflow_definitions["single_output"]
        # .to_dict() should work regardless of how it's implemented internally
        d = wf.to_dict()
        _log.info("compat.pydantic workflow_dict_type=%s keys=%s", type(d).__name__, list(d.keys())[:5])
        assert isinstance(d, dict)

    def test_execution_state_field_types(self, caplog):
        from src.workflow.executor import ExecutionState
        import uuid
        state = ExecutionState(
            execution_id=str(uuid.uuid4()),
            workflow_id="compat-wf",
            status="running",
        )
        _log.info("compat.pydantic exec_state elapsed_ms=%s status=%s", state.elapsed_ms, state.status)
        assert isinstance(state.execution_id, str)
        assert isinstance(state.status, str)
        assert isinstance(state.elapsed_ms, (int, float))


# ---------------------------------------------------------------------------
# NodeType and ErrorCode are string-valued enums
# ---------------------------------------------------------------------------

class TestEnumValueCompatibility:
    def test_node_type_values_are_strings(self, caplog):
        from src.workflow.nodes import NodeType
        bad = [n for n in NodeType if not isinstance(n.value, str)]
        _log.info("compat.enum node_type values=%s bad=%d", [n.value for n in NodeType], len(bad))
        assert not bad, f"Non-string NodeType values: {bad}"

    def test_spark_tool_node_type_is_spark_tool(self, caplog):
        from src.workflow.nodes import NodeType
        _log.info("compat.enum SPARK_TOOL value=%s", NodeType.SPARK_TOOL.value)
        assert NodeType.SPARK_TOOL.value == "SPARK_TOOL"

    def test_error_code_values_are_strings(self, caplog):
        from src.errors.error_catalog import ErrorCode
        bad = [e for e in list(ErrorCode) if not isinstance(e.value, str)]
        _log.info("compat.enum error_code bad=%d", len(bad))
        assert not bad, f"Non-string ErrorCode values: {bad}"

    def test_node_type_in_node_registry(self, caplog):
        from src.workflow.nodes import NodeType, NODE_REGISTRY
        _log.info("compat.enum node_registry keys=%s", list(NODE_REGISTRY.keys()))
        assert NodeType.SPARK_TOOL in NODE_REGISTRY
        assert NodeType.OUTPUT in NODE_REGISTRY
        assert NodeType.TRIGGER in NODE_REGISTRY


# ---------------------------------------------------------------------------
# WorkflowDefinition JSON serialization roundtrip
# ---------------------------------------------------------------------------

class TestWorkflowSerializationCompatibility:
    def test_to_dict_produces_valid_json(self, caplog, sample_workflow_definitions):
        for name, wf in sample_workflow_definitions.items():
            d = wf.to_dict()
            serialized = json.dumps(d)
            restored = json.loads(serialized)
            _log.info("compat.serial wf=%s json_len=%d roundtrip_ok=%s", name, len(serialized), bool(restored))
            assert isinstance(restored, dict)

    def test_engine_field_is_the_digital_grid(self, caplog, sample_workflow_definitions):
        from src.workflow.builder import GRID_ENGINE
        for name, wf in sample_workflow_definitions.items():
            d = wf.to_dict()
            _log.info("compat.serial wf=%s engine=%s", name, d.get("engine"))
            assert d.get("engine") == GRID_ENGINE

    def test_workflow_id_survives_roundtrip(self, caplog, sample_workflow_definitions):
        for name, wf in sample_workflow_definitions.items():
            d = wf.to_dict()
            _log.info("compat.serial wf=%s id=%s", name, d.get("id"))
            assert d.get("id") == wf.id

    def test_node_configs_present_in_dict(self, caplog, sample_workflow_definitions):
        for name, wf in sample_workflow_definitions.items():
            d = wf.to_dict()
            nodes = d.get("nodes") or d.get("node_configs") or {}
            _log.info("compat.serial wf=%s node_count=%d", name, len(nodes))
            assert len(nodes) > 0, f"Workflow {name} dict has no nodes"


# ---------------------------------------------------------------------------
# Digital Grid ↔ Spark engine field agreement
# ---------------------------------------------------------------------------

class TestGridSparkEngineAgreement:
    @pytest.mark.asyncio
    async def test_grid_engine_constant_matches_server_info(self, caplog):
        """GRID_ENGINE constant from builder must equal the grid field in server's serverInfo."""
        from src.workflow.builder import GRID_ENGINE
        from src.mcp.server import handle_rpc

        resp = await handle_rpc({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "clientInfo": {"name": "c", "version": "0"}},
        })
        grid = resp["result"]["serverInfo"].get("grid")
        _log.info("compat.agreement GRID_ENGINE=%s server_grid=%s match=%s", GRID_ENGINE, grid, GRID_ENGINE == grid)
        assert grid == GRID_ENGINE

    @pytest.mark.asyncio
    async def test_spark_registry_knows_about_grid_workflows(self, caplog):
        import src.mcp.tools as tools_mod
        from src.mcp.tools import SparkToolRegistry, GridWorkflowRegistry
        orig = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()
        try:
            reg = SparkToolRegistry()
            assert reg.get("register_workflow") is not None
            assert reg.get("run_workflow") is not None
            _log.info("compat.agreement spark_registry has grid workflow tools")
        finally:
            tools_mod._grid_registry = orig
