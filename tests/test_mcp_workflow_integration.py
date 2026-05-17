"""
Integration tests: MCP tool registry ↔ workflow executor ↔ MCPToolNode.

These tests exercise the wiring added in the "enhance-ml-mcp-workflow" branch:
  - MCPToolNode falls back to the MCP tool registry when a tool is not in the
    workflow-local _MCP_TOOL_REGISTRY.
  - register_workflow MCP tool stores a workflow for later execution.
  - run_workflow MCP tool executes a registered workflow synchronously and
    returns the final execution state.
  - get_system_health reflects real mcp_server state.
"""
from __future__ import annotations

import asyncio
import pytest

from src.mcp.tools import MCPToolRegistry, MCPTool, WorkflowRegistry, _workflow_registry
from src.workflow.nodes import (
    NodeConfig,
    NodeType,
    MCPToolNode,
    register_mcp_tool,
    _MCP_TOOL_REGISTRY,
)
from src.workflow.builder import WorkflowBuilder, WorkflowDefinition
from src.workflow.executor import WorkflowExecutor


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _simple_workflow(name: str = "test-wf") -> WorkflowDefinition:
    """Single-node OUTPUT workflow, always succeeds."""
    b = WorkflowBuilder(name)
    b.add_node(NodeType.OUTPUT, "out", config={"keys": ["value"]}, node_id="out")
    return b.build()


def _mcp_then_output_workflow(tool_name: str) -> WorkflowDefinition:
    """TRIGGER → MCP_TOOL → OUTPUT workflow."""
    b = WorkflowBuilder("mcp-pipeline")
    trigger_id = b.add_node(NodeType.TRIGGER, "start", config={}, node_id="trigger")
    mcp_id = b.add_node(
        NodeType.MCP_TOOL,
        "call mcp tool",
        config={"tool_name": tool_name, "args": {}},
        node_id="mcp",
    )
    out_id = b.add_node(NodeType.OUTPUT, "done", config={}, node_id="out")
    b.connect(trigger_id, mcp_id).connect(mcp_id, out_id)
    return b.build()


# ---------------------------------------------------------------------------
# WorkflowRegistry unit tests
# ---------------------------------------------------------------------------

class TestWorkflowRegistry:
    def test_register_and_get(self):
        reg = WorkflowRegistry()
        wf = _simple_workflow()
        reg.register(wf)
        assert reg.get(wf.id) is wf

    def test_get_missing_returns_none(self):
        reg = WorkflowRegistry()
        assert reg.get("nonexistent-id") is None

    def test_list_ids(self):
        reg = WorkflowRegistry()
        wf1 = _simple_workflow("a")
        wf2 = _simple_workflow("b")
        reg.register(wf1)
        reg.register(wf2)
        ids = reg.list_ids()
        assert wf1.id in ids
        assert wf2.id in ids

    def test_list_all_metadata(self):
        reg = WorkflowRegistry()
        wf = _simple_workflow("meta-test")
        reg.register(wf)
        entries = reg.list_all()
        match = next((e for e in entries if e["id"] == wf.id), None)
        assert match is not None
        assert match["name"] == "meta-test"


# ---------------------------------------------------------------------------
# MCPToolNode → MCP registry fallback
# ---------------------------------------------------------------------------

class TestMCPToolNodeRegistryFallback:
    """MCPToolNode should resolve tools from src.mcp.tools.registry when the
    workflow-local _MCP_TOOL_REGISTRY has no entry for the tool."""

    @pytest.mark.asyncio
    async def test_calls_mcp_registry_tool(self):
        reg = MCPToolRegistry.__new__(MCPToolRegistry)
        reg._tools = {}

        called_with: list = []

        async def echo_handler(params):
            called_with.append(params)
            return {"echoed": params.get("msg", "")}

        reg.register(MCPTool(
            name="echo_test_tool",
            description="Echo tool for testing",
            input_schema={"type": "object", "properties": {}},
            handler=echo_handler,
        ))

        # Patch the module-level singleton
        import src.mcp.tools as tools_mod
        original = tools_mod.registry
        tools_mod.registry = reg

        try:
            nc = NodeConfig(
                id="mcp1",
                type=NodeType.MCP_TOOL,
                name="mcp node",
                config={"tool_name": "echo_test_tool", "args": {"msg": "hello"}},
            )
            node = MCPToolNode(nc)
            result = await node.execute({}, {})

            assert result.success, f"Expected success, got error: {result.error}"
            assert result.output == {"echoed": "hello"}
            assert called_with, "Handler was never called"
        finally:
            tools_mod.registry = original

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        nc = NodeConfig(
            id="mcp_bad",
            type=NodeType.MCP_TOOL,
            name="bad node",
            config={"tool_name": "__nonexistent_tool_xyz__"},
        )
        node = MCPToolNode(nc)
        result = await node.execute({}, {})
        assert not result.success
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_workflow_local_registry_takes_precedence(self):
        """If the tool is in _MCP_TOOL_REGISTRY, it should be used over the MCP registry."""
        local_called: list = []
        mcp_called: list = []

        async def local_fn(**kwargs):
            local_called.append(kwargs)
            return {"source": "local"}

        async def mcp_fn(params):
            mcp_called.append(params)
            return {"source": "mcp"}

        # Register in both
        _MCP_TOOL_REGISTRY["precedence_test_tool"] = local_fn

        reg = MCPToolRegistry.__new__(MCPToolRegistry)
        reg._tools = {}
        reg.register(MCPTool(
            name="precedence_test_tool",
            description="test",
            input_schema={"type": "object", "properties": {}},
            handler=mcp_fn,
        ))

        import src.mcp.tools as tools_mod
        original = tools_mod.registry
        tools_mod.registry = reg

        try:
            nc = NodeConfig(
                id="prec",
                type=NodeType.MCP_TOOL,
                name="prec node",
                config={"tool_name": "precedence_test_tool"},
            )
            node = MCPToolNode(nc)
            result = await node.execute({}, {})
            assert result.success
            assert result.output == {"source": "local"}, "Local registry should take precedence"
            assert local_called
            assert not mcp_called
        finally:
            tools_mod.registry = original
            _MCP_TOOL_REGISTRY.pop("precedence_test_tool", None)


# ---------------------------------------------------------------------------
# register_workflow MCP tool
# ---------------------------------------------------------------------------

class TestRegisterWorkflowTool:
    @pytest.mark.asyncio
    async def test_register_template(self):
        reg = MCPToolRegistry()
        tool = reg.get("register_workflow")
        assert tool is not None

        # Use a fresh WorkflowRegistry to avoid polluting the global one
        import src.mcp.tools as tools_mod
        orig = tools_mod._workflow_registry
        tools_mod._workflow_registry = WorkflowRegistry()
        try:
            result = await tool.handler({"template": "ml_training"})
            assert result.get("registered") is True
            assert result.get("workflow_id")
            assert "ML Training" in result.get("workflow_name", "")
            assert result.get("total_registered") == 1
        finally:
            tools_mod._workflow_registry = orig

    @pytest.mark.asyncio
    async def test_register_custom_workflow_dict(self):
        reg = MCPToolRegistry()
        tool = reg.get("register_workflow")

        wf = _simple_workflow("custom-dict-wf")
        wf_dict = wf.to_dict()

        import src.mcp.tools as tools_mod
        orig = tools_mod._workflow_registry
        tools_mod._workflow_registry = WorkflowRegistry()
        try:
            result = await tool.handler({"workflow": wf_dict})
            assert result.get("registered") is True
            assert result["workflow_name"] == "custom-dict-wf"
        finally:
            tools_mod._workflow_registry = orig

    @pytest.mark.asyncio
    async def test_register_unknown_template_returns_error(self):
        reg = MCPToolRegistry()
        tool = reg.get("register_workflow")
        result = await tool.handler({"template": "does_not_exist"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_register_no_args_returns_error(self):
        reg = MCPToolRegistry()
        tool = reg.get("register_workflow")
        result = await tool.handler({})
        assert "error" in result


# ---------------------------------------------------------------------------
# run_workflow MCP tool — synchronous execution
# ---------------------------------------------------------------------------

class TestRunWorkflowTool:
    @pytest.mark.asyncio
    async def test_run_unknown_workflow(self):
        reg = MCPToolRegistry()
        tool = reg.get("run_workflow")

        import src.mcp.tools as tools_mod
        orig = tools_mod._workflow_registry
        tools_mod._workflow_registry = WorkflowRegistry()
        try:
            result = await tool.handler({"workflow_id": "no-such-id", "async_mode": False})
            assert "error" in result
        finally:
            tools_mod._workflow_registry = orig

    @pytest.mark.asyncio
    async def test_run_workflow_sync(self):
        """Register a simple single-node workflow and run it synchronously."""
        import src.mcp.tools as tools_mod
        orig_reg = tools_mod._workflow_registry
        tools_mod._workflow_registry = WorkflowRegistry()

        try:
            wf = _simple_workflow("sync-run-test")
            tools_mod._workflow_registry.register(wf)

            reg = MCPToolRegistry()
            tool = reg.get("run_workflow")
            result = await tool.handler({
                "workflow_id": wf.id,
                "params": {"value": 42},
                "async_mode": False,
                "timeout_seconds": 10,
            })

            assert "error" not in result or result.get("error") is None, \
                f"Unexpected error: {result.get('error')}"
            assert result.get("status") == "completed"
            assert result.get("workflow_id") == wf.id
            assert result.get("execution_id")
        finally:
            tools_mod._workflow_registry = orig_reg

    @pytest.mark.asyncio
    async def test_run_workflow_async_returns_started(self):
        """Async mode should return immediately with status='started'."""
        import src.mcp.tools as tools_mod
        orig_reg = tools_mod._workflow_registry
        tools_mod._workflow_registry = WorkflowRegistry()

        try:
            wf = _simple_workflow("async-run-test")
            tools_mod._workflow_registry.register(wf)

            reg = MCPToolRegistry()
            tool = reg.get("run_workflow")
            result = await tool.handler({
                "workflow_id": wf.id,
                "async_mode": True,
            })

            assert result.get("status") == "started"
            assert result.get("workflow_id") == wf.id
            # Give the background task a moment to finish cleanly
            await asyncio.sleep(0.05)
        finally:
            tools_mod._workflow_registry = orig_reg


# ---------------------------------------------------------------------------
# get_system_health — mcp_server subsystem reflects real state
# ---------------------------------------------------------------------------

class TestGetSystemHealth:
    @pytest.mark.asyncio
    async def test_mcp_server_health_reflects_tool_count(self):
        reg = MCPToolRegistry()
        tool = reg.get("get_system_health")
        result = await tool.handler({"subsystems": ["mcp_server"]})
        assert result["healthy"] is True
        mcp = result["subsystems"]["mcp_server"]
        assert mcp["tools_registered"] > 0
        assert "workflows_registered" in mcp

    @pytest.mark.asyncio
    async def test_verbose_includes_latency(self):
        reg = MCPToolRegistry()
        tool = reg.get("get_system_health")
        result = await tool.handler({"subsystems": ["mcp_server"], "verbose": True})
        mcp = result["subsystems"]["mcp_server"]
        assert "latency_ms" in mcp
        assert "last_checked" in mcp
