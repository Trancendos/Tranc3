"""
Integration tests: The Spark (MCP tool registry) ↔ The Digital Grid (workflow executor) ↔ SparkToolNode.

These tests exercise the wiring added in the "enhance-ml-mcp-workflow" branch:
  - SparkToolNode falls back to The Spark's tool registry when a tool is not in
    the Digital Grid's local _SPARK_TOOL_REGISTRY.
  - register_workflow Spark tool stores a workflow for later execution in The Digital Grid.
  - run_workflow Spark tool executes a registered workflow synchronously and
    returns the final execution state.
  - get_system_health reflects real Spark server state.
"""

from __future__ import annotations

import asyncio

import pytest

from src.mcp.tools import GridWorkflowRegistry, SparkTool, SparkToolRegistry
from src.workflow.builder import WorkflowBuilder, WorkflowDefinition
from src.workflow.nodes import (
    _SPARK_TOOL_REGISTRY,
    NodeConfig,
    NodeType,
    SparkToolNode,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _simple_workflow(name: str = "test-wf") -> WorkflowDefinition:
    """Single-node OUTPUT workflow, always succeeds."""
    b = WorkflowBuilder(name)
    b.add_node(NodeType.OUTPUT, "out", config={"keys": ["value"]}, node_id="out")
    return b.build()


def _spark_then_output_workflow(tool_name: str) -> WorkflowDefinition:
    """TRIGGER → SPARK_TOOL → OUTPUT workflow."""
    b = WorkflowBuilder("spark-pipeline")
    trigger_id = b.add_node(NodeType.TRIGGER, "start", config={}, node_id="trigger")
    spark_id = b.add_node(
        NodeType.SPARK_TOOL,
        "call spark tool",
        config={"tool_name": tool_name, "args": {}},
        node_id="spark",
    )
    out_id = b.add_node(NodeType.OUTPUT, "done", config={}, node_id="out")
    b.connect(trigger_id, spark_id).connect(spark_id, out_id)
    return b.build()


# ---------------------------------------------------------------------------
# GridWorkflowRegistry unit tests
# ---------------------------------------------------------------------------


class TestGridWorkflowRegistry:
    def test_register_and_get(self):
        reg = GridWorkflowRegistry()
        wf = _simple_workflow()
        reg.register(wf)
        assert reg.get(wf.id) is wf

    def test_get_missing_returns_none(self):
        reg = GridWorkflowRegistry()
        assert reg.get("nonexistent-id") is None

    def test_list_ids(self):
        reg = GridWorkflowRegistry()
        wf1 = _simple_workflow("a")
        wf2 = _simple_workflow("b")
        reg.register(wf1)
        reg.register(wf2)
        ids = reg.list_ids()
        assert wf1.id in ids
        assert wf2.id in ids

    def test_list_all_metadata(self):
        reg = GridWorkflowRegistry()
        wf = _simple_workflow("meta-test")
        reg.register(wf)
        entries = reg.list_all()
        match = next((e for e in entries if e["id"] == wf.id), None)
        assert match is not None
        assert match["name"] == "meta-test"


# ---------------------------------------------------------------------------
# SparkToolNode → Spark registry fallback
# ---------------------------------------------------------------------------


class TestSparkToolNodeFallback:
    """SparkToolNode should resolve tools from The Spark's registry when the
    Digital Grid's local _SPARK_TOOL_REGISTRY has no entry for the tool."""

    @pytest.mark.asyncio
    async def test_calls_spark_registry_tool(self):
        reg = SparkToolRegistry.__new__(SparkToolRegistry)
        reg._tools = {}

        called_with: list = []

        async def echo_handler(params):
            called_with.append(params)
            return {"echoed": params.get("msg", "")}

        reg.register(
            SparkTool(
                name="echo_test_tool",
                description="Echo tool for testing",
                input_schema={"type": "object", "properties": {}},
                handler=echo_handler,
            )
        )

        # Patch the module-level singleton
        import src.mcp.tools as tools_mod

        original = tools_mod.registry
        tools_mod.registry = reg

        try:
            nc = NodeConfig(
                id="spark1",
                type=NodeType.SPARK_TOOL,
                name="spark node",
                config={"tool_name": "echo_test_tool", "args": {"msg": "hello"}},
            )
            node = SparkToolNode(nc)
            result = await node.execute({}, {})

            assert result.success, f"Expected success, got error: {result.error}"
            assert result.output == {"echoed": "hello"}
            assert called_with, "Handler was never called"
        finally:
            tools_mod.registry = original
        return None

    @pytest.mark.asyncio
    async def test_unknown_tool_returns_error(self):
        nc = NodeConfig(
            id="spark_bad",
            type=NodeType.SPARK_TOOL,
            name="bad node",
            config={"tool_name": "__nonexistent_tool_xyz__"},
        )
        node = SparkToolNode(nc)
        result = await node.execute({}, {})
        assert not result.success
        assert "not found" in (result.error or "").lower()

    @pytest.mark.asyncio
    async def test_grid_local_registry_takes_precedence(self):
        """If the tool is in _SPARK_TOOL_REGISTRY, it should be used over The Spark's registry."""
        local_called: list = []
        spark_called: list = []

        async def local_fn(**kwargs):
            local_called.append(kwargs)
            return {"source": "local"}

        async def spark_fn(params):
            spark_called.append(params)
            return {"source": "spark"}

        # Register in both
        _SPARK_TOOL_REGISTRY["precedence_test_tool"] = local_fn

        reg = SparkToolRegistry.__new__(SparkToolRegistry)
        reg._tools = {}
        reg.register(
            SparkTool(
                name="precedence_test_tool",
                description="test",
                input_schema={"type": "object", "properties": {}},
                handler=spark_fn,
            )
        )

        import src.mcp.tools as tools_mod

        original = tools_mod.registry
        tools_mod.registry = reg

        try:
            nc = NodeConfig(
                id="prec",
                type=NodeType.SPARK_TOOL,
                name="prec node",
                config={"tool_name": "precedence_test_tool"},
            )
            node = SparkToolNode(nc)
            result = await node.execute({}, {})
            assert result.success
            assert result.output == {"source": "local"}, (
                "Grid-local registry should take precedence"
            )
            assert local_called
            assert not spark_called
        finally:
            tools_mod.registry = original
            _SPARK_TOOL_REGISTRY.pop("precedence_test_tool", None)
        return None


# ---------------------------------------------------------------------------
# register_workflow Spark tool
# ---------------------------------------------------------------------------


class TestSparkRegisterGridWorkflow:
    @pytest.mark.asyncio
    async def test_register_template(self):
        reg = SparkToolRegistry()
        tool = reg.get("register_workflow")
        assert tool is not None

        # Use a fresh GridWorkflowRegistry to avoid polluting the global one
        import src.mcp.tools as tools_mod

        orig = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()
        try:
            result = await tool.handler({"template": "ml_training"})
            assert result.get("registered") is True
            assert result.get("workflow_id")
            assert "ML Training" in result.get("workflow_name", "")
            assert result.get("total_registered") == 1
        finally:
            tools_mod._grid_registry = orig

    @pytest.mark.asyncio
    async def test_register_custom_workflow_dict(self):
        reg = SparkToolRegistry()
        tool = reg.get("register_workflow")

        wf = _simple_workflow("custom-dict-wf")
        wf_dict = wf.to_dict()

        import src.mcp.tools as tools_mod

        orig = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()
        try:
            result = await tool.handler({"workflow": wf_dict})
            assert result.get("registered") is True
            assert result["workflow_name"] == "custom-dict-wf"
        finally:
            tools_mod._grid_registry = orig

    @pytest.mark.asyncio
    async def test_register_unknown_template_returns_error(self):
        reg = SparkToolRegistry()
        tool = reg.get("register_workflow")
        result = await tool.handler({"template": "does_not_exist"})
        assert "error" in result

    @pytest.mark.asyncio
    async def test_register_no_args_returns_error(self):
        reg = SparkToolRegistry()
        tool = reg.get("register_workflow")
        result = await tool.handler({})
        assert "error" in result


# ---------------------------------------------------------------------------
# run_workflow Spark tool — synchronous execution in The Digital Grid
# ---------------------------------------------------------------------------


class TestSparkRunGridWorkflow:
    @pytest.mark.asyncio
    async def test_run_unknown_workflow(self):
        reg = SparkToolRegistry()
        tool = reg.get("run_workflow")

        import src.mcp.tools as tools_mod

        orig = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()
        try:
            result = await tool.handler({"workflow_id": "no-such-id", "async_mode": False})
            assert "error" in result
        finally:
            tools_mod._grid_registry = orig

    @pytest.mark.asyncio
    async def test_run_workflow_sync(self):
        """Register a simple single-node workflow and run it synchronously via The Spark."""
        import src.mcp.tools as tools_mod

        orig_reg = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()

        try:
            wf = _simple_workflow("sync-run-test")
            tools_mod._grid_registry.register(wf)

            reg = SparkToolRegistry()
            tool = reg.get("run_workflow")
            result = await tool.handler(
                {
                    "workflow_id": wf.id,
                    "params": {"value": 42},
                    "async_mode": False,
                    "timeout_seconds": 10,
                }
            )

            assert "error" not in result or result.get("error") is None, (
                f"Unexpected error: {result.get('error')}"
            )
            assert result.get("status") == "completed"
            assert result.get("workflow_id") == wf.id
            assert result.get("execution_id")
        finally:
            tools_mod._grid_registry = orig_reg

    @pytest.mark.asyncio
    async def test_run_workflow_async_returns_started(self):
        """Async mode should return immediately with status='started'."""
        import src.mcp.tools as tools_mod

        orig_reg = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()

        try:
            wf = _simple_workflow("async-run-test")
            tools_mod._grid_registry.register(wf)

            reg = SparkToolRegistry()
            tool = reg.get("run_workflow")
            result = await tool.handler(
                {
                    "workflow_id": wf.id,
                    "async_mode": True,
                }
            )

            assert result.get("status") == "started"
            assert result.get("workflow_id") == wf.id
            # Give the background task a moment to finish cleanly
            await asyncio.sleep(0.05)
        finally:
            tools_mod._grid_registry = orig_reg


# ---------------------------------------------------------------------------
# get_system_health — Spark server subsystem reflects real state
# ---------------------------------------------------------------------------


class TestSparkSystemHealth:
    @pytest.mark.asyncio
    async def test_spark_health_reflects_tool_count(self):
        reg = SparkToolRegistry()
        tool = reg.get("get_system_health")
        result = await tool.handler({"subsystems": ["mcp_server"]})
        assert result["healthy"] is True
        mcp = result["subsystems"]["mcp_server"]
        assert mcp["tools_registered"] > 0
        assert "workflows_registered" in mcp

    @pytest.mark.asyncio
    async def test_verbose_includes_latency(self):
        reg = SparkToolRegistry()
        tool = reg.get("get_system_health")
        result = await tool.handler({"subsystems": ["mcp_server"], "verbose": True})
        mcp = result["subsystems"]["mcp_server"]
        assert "latency_ms" in mcp
        assert "last_checked" in mcp


# ---------------------------------------------------------------------------
# The Spark identity — server name and initialize response
# ---------------------------------------------------------------------------


class TestSparkIdentity:
    @pytest.mark.asyncio
    async def test_server_name_is_the_spark(self):
        from src.mcp.server import ENGINE_LABEL, SERVER_NAME

        assert SERVER_NAME == "the-spark"
        assert "Spark" in ENGINE_LABEL

    @pytest.mark.asyncio
    async def test_initialize_exposes_grid_reference(self):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "clientInfo": {"name": "test", "version": "0"},
                },
            }
        )
        info = resp["result"]["serverInfo"]
        assert info["name"] == "the-spark"
        assert info.get("grid") == "the-digital-grid"

    @pytest.mark.asyncio
    async def test_resources_use_spark_and_grid_uris(self):
        from src.mcp.server import handle_rpc

        resp = await handle_rpc(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "resources/list",
                "params": {},
            }
        )
        uris = [r["uri"] for r in resp["result"]["resources"]]
        assert any(u.startswith("spark://") for u in uris)
        assert any(u.startswith("grid://") for u in uris)
        assert "grid://events" in uris


# ---------------------------------------------------------------------------
# The Digital Grid identity — workflow definitions carry engine label
# ---------------------------------------------------------------------------


class TestDigitalGridIdentity:
    def test_workflow_dict_includes_engine(self):
        from src.workflow.builder import GRID_ENGINE

        wf = _simple_workflow("engine-test")
        d = wf.to_dict()
        assert d.get("engine") == GRID_ENGINE

    def test_grid_engine_constant(self):
        from src.workflow.builder import GRID_ENGINE

        assert GRID_ENGINE == "the-digital-grid"

    def test_spark_tool_node_type_value(self):
        assert NodeType.SPARK_TOOL == "SPARK_TOOL"


# ---------------------------------------------------------------------------
# Grid event bridge — Digital Grid events reach The Spark's SSE bus
# ---------------------------------------------------------------------------


class TestGridBridge:
    @pytest.mark.asyncio
    async def test_bridge_forwards_workflow_events(self):
        """Workflow lifecycle events should appear on The Spark's SSE bus."""
        import src.mcp.server as spark

        # Reset bridge so we can test initialisation
        spark._grid_bridge_started = False
        await spark._start_grid_bridge()
        assert spark._grid_bridge_started

        sub_id, queue = spark._bus.subscribe()
        try:
            # Publish a synthetic grid event through the workflow event bus
            from src.workflow.executor import event_bus as grid_bus

            await grid_bus.publish(
                "workflow.completed", {"workflow_id": "test-wf", "elapsed_ms": 1.0}
            )

            # The bridge should have forwarded it as "grid.workflow.completed"
            await asyncio.sleep(0)

            assert not queue.empty(), "SSE queue should contain the forwarded grid event"
            raw = queue.get_nowait()
            import json

            payload = json.loads(raw)
            assert payload["event"] == "grid.workflow.completed"
        finally:
            spark._bus.unsubscribe(sub_id)
            spark._grid_bridge_started = False  # reset for other tests
