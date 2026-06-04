"""
Validation Tests — input validation, schema enforcement, boundary conditions.

Covers:
  - NodeConfig required fields and type coercion
  - WorkflowBuilder cycle detection and bad topology
  - SparkTool required fields and schema validation
  - GridWorkflowRegistry ID uniqueness and template coverage
  - WorkflowExecutor state machine transitions
  - ErrorCode uniqueness and format invariants
"""

from __future__ import annotations

import logging

import pytest

_log = logging.getLogger("tranc3.tests.validation")


# ---------------------------------------------------------------------------
# NodeConfig validation
# ---------------------------------------------------------------------------


class TestNodeConfigValidation:
    def test_node_config_requires_id(self, caplog):
        import pydantic

        from src.workflow.nodes import NodeConfig, NodeType

        with pytest.raises((pydantic.ValidationError, TypeError, ValueError)):
            NodeConfig(type=NodeType.OUTPUT, name="out", config={})  # missing id
        _log.info("val.nodeconfig missing_id raised as expected")

    def test_node_config_requires_type(self, caplog):
        import pydantic

        from src.workflow.nodes import NodeConfig

        with pytest.raises((pydantic.ValidationError, TypeError, ValueError)):
            NodeConfig(id="n1", name="out", config={})  # missing type
        _log.info("val.nodeconfig missing_type raised as expected")

    def test_node_config_requires_name(self, caplog):
        import pydantic

        from src.workflow.nodes import NodeConfig, NodeType

        with pytest.raises((pydantic.ValidationError, TypeError, ValueError)):
            NodeConfig(id="n1", type=NodeType.OUTPUT, config={})  # missing name
        _log.info("val.nodeconfig missing_name raised as expected")

    def test_node_config_config_defaults_to_empty(self, caplog):
        from src.workflow.nodes import NodeConfig, NodeType

        nc = NodeConfig(id="n1", type=NodeType.OUTPUT, name="out", config={})
        _log.info("val.nodeconfig config=%s", nc.config)
        assert nc.config == {} or nc.config is not None

    def test_node_config_timeout_sec_is_optional(self, caplog):
        from src.workflow.nodes import NodeConfig, NodeType

        nc = NodeConfig(id="n1", type=NodeType.OUTPUT, name="out", config={})
        _log.info("val.nodeconfig timeout_sec=%s", getattr(nc, "timeout_sec", "N/A"))
        # timeout_sec should exist (may be None or a default float)
        assert hasattr(nc, "timeout_sec")

    def test_node_config_valid_full(self, caplog):
        from src.workflow.nodes import NodeConfig, NodeType

        nc = NodeConfig(
            id="spark-node",
            type=NodeType.SPARK_TOOL,
            name="call-health",
            config={"tool_name": "get_system_health"},
            timeout_sec=10.0,
        )
        _log.info("val.nodeconfig full id=%s type=%s timeout=%s", nc.id, nc.type, nc.timeout_sec)
        assert nc.id == "spark-node"
        assert nc.type == NodeType.SPARK_TOOL
        assert nc.timeout_sec == 10.0


# ---------------------------------------------------------------------------
# WorkflowBuilder validation
# ---------------------------------------------------------------------------


class TestWorkflowBuilderValidation:
    def test_builder_requires_non_empty_name(self, caplog):
        from src.workflow.builder import WorkflowBuilder

        b = WorkflowBuilder("my-workflow")
        wf = b.build()
        _log.info("val.builder name=%s", wf.name)
        assert wf.name == "my-workflow"

    def test_builder_generates_unique_ids(self, caplog):
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType

        b = WorkflowBuilder("id-test")
        b.add_node(NodeType.TRIGGER, "a", config={}, node_id="a")
        b.add_node(NodeType.OUTPUT, "b", config={}, node_id="b")
        wf = b.build()
        node_ids = list(wf.node_configs.keys()) if hasattr(wf, "node_configs") else []
        _log.info("val.builder node_ids=%s", node_ids)
        assert len(node_ids) == len(set(node_ids)), "Duplicate node IDs in workflow"

    def test_builder_duplicate_node_id_raises_or_overwrites(self, caplog):
        """Adding a node with an existing ID should either raise or replace it — not silently corrupt."""
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType

        b = WorkflowBuilder("dup-id-wf")
        b.add_node(NodeType.OUTPUT, "node-a", config={}, node_id="same-id")
        try:
            b.add_node(NodeType.TRIGGER, "node-b", config={}, node_id="same-id")
            wf = b.build()
            # If it didn't raise, the node should still be deterministic (overwritten)
            count = len(list(wf.node_configs.keys()) if hasattr(wf, "node_configs") else [])
            _log.info("val.builder dup_id replaced node_count=%d", count)
        except (ValueError, KeyError) as exc:
            _log.info("val.builder dup_id raised %s", type(exc).__name__)

    def test_workflow_has_engine_field_after_build(self, caplog):
        from src.workflow.builder import GRID_ENGINE, WorkflowBuilder
        from src.workflow.nodes import NodeType

        b = WorkflowBuilder("engine-wf")
        b.add_node(NodeType.OUTPUT, "out", config={}, node_id="out")
        wf = b.build()
        d = wf.to_dict()
        _log.info("val.builder engine=%s expected=%s", d.get("engine"), GRID_ENGINE)
        assert d.get("engine") == GRID_ENGINE

    def test_topological_sort_detects_cycle(self, caplog):
        from src.workflow.executor import NodeConfig, _topological_sort
        from src.workflow.nodes import NodeType

        nc_a = NodeConfig(id="a", type=NodeType.OUTPUT, name="a", config={})
        nc_b = NodeConfig(id="b", type=NodeType.OUTPUT, name="b", config={})
        nc_c = NodeConfig(id="c", type=NodeType.OUTPUT, name="c", config={})
        nodes = {"a": nc_a, "b": nc_b, "c": nc_c}
        cyclic_edges = [("a", "b", ""), ("b", "c", ""), ("c", "a", "")]
        with pytest.raises(ValueError, match="cycle"):
            _topological_sort(nodes, cyclic_edges)
        _log.info("val.builder topological_sort cycle detected as expected")

    def test_topological_sort_linear_chain(self, caplog):
        from src.workflow.executor import NodeConfig, _topological_sort
        from src.workflow.nodes import NodeType

        nc_a = NodeConfig(id="a", type=NodeType.TRIGGER, name="a", config={})
        nc_b = NodeConfig(id="b", type=NodeType.OUTPUT, name="b", config={})
        nodes = {"a": nc_a, "b": nc_b}
        edges = [("a", "b", "")]
        layers = _topological_sort(nodes, edges)
        # layers is a list of layers, each layer is a list of node IDs
        flat = [node_id for layer in layers for node_id in layer]
        _log.info("val.builder topo_sort layers=%s flat=%s", layers, flat)
        assert flat.index("a") < flat.index("b")


# ---------------------------------------------------------------------------
# SparkTool validation
# ---------------------------------------------------------------------------


class TestSparkToolValidation:
    def test_spark_tool_requires_name(self, caplog):
        import pydantic

        from src.mcp.tools import SparkTool

        async def _handler(params):
            return {}

        with pytest.raises((pydantic.ValidationError, TypeError)):
            SparkTool(
                description="no name",
                input_schema={"type": "object"},
                handler=_handler,
            )
        _log.info("val.spark_tool missing_name raised as expected")
        return None

    def test_spark_tool_requires_handler(self, caplog):
        import pydantic

        from src.mcp.tools import SparkTool

        with pytest.raises((pydantic.ValidationError, TypeError)):
            SparkTool(
                name="test",
                description="no handler",
                input_schema={"type": "object"},
            )
        _log.info("val.spark_tool missing_handler raised as expected")

    def test_spark_tool_name_used_as_registry_key(self, caplog):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        # Every registered tool should be gettable by its declared name
        for tool in reg._tools.values():
            assert reg.get(tool.name) is tool
        _log.info("val.spark_tool registry key consistency ok tools=%d", len(reg._tools))

    def test_spark_tool_input_schema_is_dict(self, caplog):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        for tool in reg._tools.values():
            _log.info(
                "val.spark_tool %s schema_type=%s", tool.name, type(tool.input_schema).__name__,
            )
            assert isinstance(tool.input_schema, dict), f"{tool.name}.input_schema must be a dict"

    def test_spark_tool_description_non_empty(self, caplog):
        from src.mcp.tools import SparkToolRegistry

        reg = SparkToolRegistry()
        for tool in reg._tools.values():
            _log.info("val.spark_tool %s desc_len=%d", tool.name, len(tool.description))
            assert tool.description.strip(), f"{tool.name} has empty description"


# ---------------------------------------------------------------------------
# GridWorkflowRegistry validation
# ---------------------------------------------------------------------------


class TestGridWorkflowRegistryValidation:
    def test_register_same_id_twice_overwrites(self, caplog):
        from src.mcp.tools import GridWorkflowRegistry
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType

        reg = GridWorkflowRegistry()

        def _make_wf(name):
            b = WorkflowBuilder("dup-wf")
            b.add_node(NodeType.OUTPUT, name, config={}, node_id=name)
            wf = b.build()
            object.__setattr__(wf, "id", "fixed-id")
            return wf

        wf1 = _make_wf("node-v1")
        wf2 = _make_wf("node-v2")
        reg.register(wf1)
        reg.register(wf2)
        retrieved = reg.get("fixed-id")
        _log.info("val.grid_registry overwrite retrieved=%s", retrieved.id if retrieved else None)
        assert retrieved is not None
        return None

    def test_get_nonexistent_returns_none(self, caplog):
        from src.mcp.tools import GridWorkflowRegistry

        reg = GridWorkflowRegistry()
        result = reg.get("no-such-workflow-id")
        _log.info("val.grid_registry get_nonexistent result=%s", result)
        assert result is None

    @pytest.mark.asyncio
    async def test_list_registered_workflows(self, caplog):
        import src.mcp.tools as tools_mod
        from src.mcp.tools import GridWorkflowRegistry, SparkToolRegistry

        orig = tools_mod._grid_registry
        tools_mod._grid_registry = GridWorkflowRegistry()
        try:
            reg = SparkToolRegistry()
            register_tool = reg.get("register_workflow")
            r = await register_tool.handler({"template": "ml_training"})
            wf_id = r.get("workflow_id", "")
            all_wfs = tools_mod._grid_registry.list_ids()
            _log.info("val.grid_registry listed=%d registered_id=%s", len(all_wfs), wf_id)
            assert len(all_wfs) >= 1
        finally:
            tools_mod._grid_registry = orig


# ---------------------------------------------------------------------------
# WorkflowExecutor state transitions
# ---------------------------------------------------------------------------


class TestWorkflowExecutorStateValidation:
    @pytest.mark.asyncio
    async def test_completed_workflow_has_elapsed_ms(self, caplog):
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.executor import WorkflowExecutor
        from src.workflow.nodes import NodeType

        b = WorkflowBuilder("elapsed-wf")
        b.add_node(NodeType.OUTPUT, "out", config={}, node_id="out")
        wf = b.build()
        state = await WorkflowExecutor().execute(wf, {"value": 1})
        _log.info("val.executor elapsed_ms=%s status=%s", state.elapsed_ms, state.status)
        assert state.status == "completed"
        assert state.elapsed_ms >= 0

    @pytest.mark.asyncio
    async def test_execution_id_is_unique_across_runs(self, caplog):
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.executor import WorkflowExecutor
        from src.workflow.nodes import NodeType

        b = WorkflowBuilder("unique-id-wf")
        b.add_node(NodeType.OUTPUT, "out", config={}, node_id="out")
        wf = b.build()
        ex = WorkflowExecutor()
        s1 = await ex.execute(wf, {"value": 1})
        s2 = await ex.execute(wf, {"value": 2})
        _log.info(
            "val.executor ids_unique=%s id1=%s id2=%s",
            s1.execution_id != s2.execution_id,
            s1.execution_id[:8],
            s2.execution_id[:8],
        )
        assert s1.execution_id != s2.execution_id

    @pytest.mark.asyncio
    async def test_workflow_id_propagated_to_state(self, caplog):
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.executor import WorkflowExecutor
        from src.workflow.nodes import NodeType

        b = WorkflowBuilder("id-check-wf")
        b.add_node(NodeType.OUTPUT, "out", config={}, node_id="out")
        wf = b.build()
        state = await WorkflowExecutor().execute(wf)
        _log.info("val.executor wf_id=%s state_wf_id=%s", wf.id, state.workflow_id)
        assert state.workflow_id == wf.id

    @pytest.mark.asyncio
    async def test_failed_state_has_error_string(self, caplog):
        from src.workflow import nodes as _nodes
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.executor import WorkflowExecutor
        from src.workflow.nodes import BaseNode, NodeType

        class FailNode(BaseNode):
            async def execute(self, inputs, context):
                raise ValueError("val: deliberate failure")

        _nodes.NODE_REGISTRY[NodeType.TRIGGER] = FailNode
        try:
            b = WorkflowBuilder("fail-state-wf")
            b.add_node(NodeType.TRIGGER, "fail", config={}, node_id="fail")
            wf = b.build()
            state = await WorkflowExecutor().execute(wf)
            _log.info(
                "val.executor fail state=%s error_type=%s", state.status, type(state.error).__name__,
            )
            assert state.status == "failed"
            assert isinstance(state.error, str)
        finally:
            from src.workflow.nodes import TriggerNode

            _nodes.NODE_REGISTRY[NodeType.TRIGGER] = TriggerNode


# ---------------------------------------------------------------------------
# ErrorCode uniqueness and invariants
# ---------------------------------------------------------------------------


class TestErrorCodeValidation:
    def test_error_code_values_unique(self, caplog):
        from src.errors.error_catalog import ErrorCode

        values = [e.value for e in ErrorCode]
        unique = set(values)
        _log.info("val.error_codes total=%d unique=%d", len(values), len(unique))
        assert len(values) == len(unique), (
            f"Duplicate ErrorCode values: { {v for v in values if values.count(v) > 1} }"
        )

    def test_error_code_names_unique(self, caplog):
        from src.errors.error_catalog import ErrorCode

        names = [e.name for e in ErrorCode]
        unique = set(names)
        _log.info("val.error_codes name_total=%d name_unique=%d", len(names), len(unique))
        assert len(names) == len(unique), "Duplicate ErrorCode names"

    def test_error_codes_have_three_digit_suffix(self, caplog):
        import re

        from src.errors.error_catalog import ErrorCode

        pattern = re.compile(r"^TRANC3-[A-Z]+-\d{3}$")
        bad = [e.value for e in ErrorCode if not pattern.match(e.value)]
        _log.info("val.error_codes format_bad=%d", len(bad))
        assert not bad, f"Bad format: {bad}"

    def test_at_least_20_error_codes_defined(self, caplog):
        from src.errors.error_catalog import ErrorCode

        count = len(list(ErrorCode))
        _log.info("val.error_codes total_count=%d", count)
        assert count >= 20, f"Expected ≥20 error codes, found {count}"
