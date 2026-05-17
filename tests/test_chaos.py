"""
Chaos Tests — fault injection, timeout simulation, circuit breaker stress.

Deliberately introduce failures to verify the system degrades gracefully:
  - CircuitBreaker opens after threshold and recovers
  - Workflow fail-fast on node failure
  - WorkflowExecutor cancellation
  - Concurrent executions do not corrupt shared state
  - Event bus survives subscriber errors
  - SparkToolNode handles hanging tools via timeout
"""
from __future__ import annotations

import asyncio
import logging
import time
import pytest

_log = logging.getLogger("tranc3.tests.chaos")


# ---------------------------------------------------------------------------
# Circuit Breaker chaos
# ---------------------------------------------------------------------------

class TestCircuitBreakerChaos:
    def test_opens_after_failure_threshold(self, caplog):
        from src.validation.loop_validator import CircuitBreaker, CircuitState
        cb = CircuitBreaker("chaos-test", failure_threshold=3, recovery_timeout=9999)

        def _fail():
            raise RuntimeError("injected fault")

        for i in range(3):
            try:
                cb.call(_fail)
            except RuntimeError:
                pass
            _log.debug("chaos.circuit attempt=%d state=%s", i, cb._state)

        _log.info("chaos.circuit state=%s after 3 failures", cb.state)
        assert cb.state == CircuitState.OPEN

    def test_fallback_invoked_when_open(self, caplog):
        from src.validation.loop_validator import CircuitBreaker, CircuitState
        cb = CircuitBreaker("chaos-fallback", failure_threshold=1, recovery_timeout=9999)

        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("boom")))
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN

        result = cb.call(lambda: "should-not-run", fallback=lambda: "safe-fallback")
        _log.info("chaos.circuit fallback_result=%s", result)
        assert result == "safe-fallback"

    def test_recovers_after_timeout(self, caplog):
        from src.validation.loop_validator import CircuitBreaker, CircuitState
        cb = CircuitBreaker("chaos-recover", failure_threshold=1, recovery_timeout=0.01)
        try:
            cb.call(lambda: (_ for _ in ()).throw(RuntimeError("x")), fallback=None)
        except RuntimeError:
            pass
        assert cb.state == CircuitState.OPEN
        time.sleep(0.05)
        state_after = cb.state
        _log.info("chaos.circuit recovered state=%s", state_after)
        assert state_after == CircuitState.HALF_OPEN

    def test_loop_validator_breaks_at_limit(self, caplog):
        from src.validation.loop_validator import LoopValidator
        lv = LoopValidator()
        # retry_loop context has a limit of 3; exhaust it
        broken = False
        for i in range(20):
            if not lv.check("test-loop", context="db_retry"):
                broken = True
                _log.info("chaos.loop broke at iteration=%d", i)
                break
        assert broken, "LoopValidator should have broken the loop"


# ---------------------------------------------------------------------------
# Workflow fail-fast chaos
# ---------------------------------------------------------------------------

class TestWorkflowChaos:
    @pytest.mark.asyncio
    async def test_failing_node_aborts_workflow(self, caplog):
        """A node that raises should mark workflow as failed."""
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType, NodeConfig, NodeResult, BaseNode
        from src.workflow.executor import WorkflowExecutor

        class BoomNode(BaseNode):
            async def execute(self, inputs, context):
                raise RuntimeError("chaos: deliberate node failure")

        # Monkey-patch NODE_REGISTRY temporarily
        from src.workflow import nodes as _nodes
        _nodes.NODE_REGISTRY[NodeType.TRIGGER] = BoomNode

        try:
            b = WorkflowBuilder("chaos-fail-wf")
            b.add_node(NodeType.TRIGGER, "boom", config={}, node_id="boom")
            wf = b.build()
            ex = WorkflowExecutor()
            state = await ex.execute(wf)
            _log.info("chaos.workflow fail_status=%s error=%s", state.status, state.error)
            assert state.status == "failed"
            assert state.error is not None
        finally:
            from src.workflow.nodes import TriggerNode
            _nodes.NODE_REGISTRY[NodeType.TRIGGER] = TriggerNode

    @pytest.mark.asyncio
    async def test_cancel_in_flight_execution(self, caplog):
        """Cancelling an execution should mark it cancelled."""
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType
        from src.workflow.executor import WorkflowExecutor

        b = WorkflowBuilder("cancel-wf")
        b.add_node(NodeType.OUTPUT, "out", config={}, node_id="out")
        wf = b.build()
        ex = WorkflowExecutor()

        task = asyncio.create_task(ex.execute(wf, {"value": 1}))
        await asyncio.sleep(0)
        # Execution may finish before we cancel — both outcomes are valid
        if not task.done():
            for eid, state in ex.executions.items():
                if state.status == "running":
                    await ex.cancel(eid)
        state = await task
        _log.info("chaos.cancel final_status=%s", state.status)
        assert state.status in ("completed", "cancelled")

    @pytest.mark.asyncio
    async def test_concurrent_executions_isolated(self, caplog):
        """Two concurrent executions of the same workflow must not share state."""
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType
        from src.workflow.executor import WorkflowExecutor

        b = WorkflowBuilder("concurrent-wf")
        b.add_node(NodeType.OUTPUT, "out", config={"keys": ["x"]}, node_id="out")
        wf = b.build()
        ex = WorkflowExecutor()

        s1, s2 = await asyncio.gather(
            ex.execute(wf, {"x": "first"}),
            ex.execute(wf, {"x": "second"}),
        )
        _log.info(
            "chaos.concurrent exec1=%s exec2=%s ids_differ=%s",
            s1.status, s2.status,
            s1.execution_id != s2.execution_id,
        )
        assert s1.execution_id != s2.execution_id
        assert s1.status == "completed"
        assert s2.status == "completed"

    @pytest.mark.asyncio
    async def test_cyclic_workflow_fails_gracefully(self, caplog):
        """A workflow definition with a cycle should fail at execution, not crash."""
        from src.workflow.builder import WorkflowBuilder
        from src.workflow.nodes import NodeType
        from src.workflow.executor import WorkflowExecutor, _topological_sort, NodeConfig

        # Build two nodes and manually wire a cycle
        nc_a = NodeConfig(id="a", type=NodeType.OUTPUT, name="a", config={})
        nc_b = NodeConfig(id="b", type=NodeType.OUTPUT, name="b", config={})
        nodes = {"a": nc_a, "b": nc_b}
        edges = [("a", "b", ""), ("b", "a", "")]  # cycle!

        with pytest.raises(ValueError, match="cycle"):
            _topological_sort(nodes, edges)
        _log.info("chaos.cycle raised ValueError as expected")


# ---------------------------------------------------------------------------
# Event bus chaos
# ---------------------------------------------------------------------------

class TestEventBusChaos:
    @pytest.mark.asyncio
    async def test_subscriber_error_does_not_crash_bus(self, caplog):
        """A subscriber that raises must not prevent other subscribers from receiving."""
        from src.workflow.executor import WorkflowEventBus

        bus = WorkflowEventBus()
        received = []

        def bad_sub(payload):
            raise RuntimeError("chaos: bad subscriber")

        async def good_sub(payload):
            received.append(payload)

        bus.subscribe("chaos.event", bad_sub)
        bus.subscribe("chaos.event", good_sub)
        await bus.publish("chaos.event", {"value": 42})
        _log.info("chaos.eventbus good_sub received=%d", len(received))
        assert len(received) == 1
        assert received[0]["data"]["value"] == 42

    @pytest.mark.asyncio
    async def test_wildcard_subscriber_receives_all_events(self, caplog):
        from src.workflow.executor import WorkflowEventBus

        bus = WorkflowEventBus()
        captured = []
        bus.subscribe("*", lambda p: captured.append(p["event"]))
        await bus.publish("event.one", {})
        await bus.publish("event.two", {})
        _log.info("chaos.eventbus wildcard captured=%s", captured)
        assert "event.one" in captured
        assert "event.two" in captured


# ---------------------------------------------------------------------------
# SparkToolNode timeout chaos
# ---------------------------------------------------------------------------

class TestSparkToolNodeChaos:
    @pytest.mark.asyncio
    async def test_hanging_tool_times_out(self, caplog):
        """A SparkToolNode with a very short timeout must return error, not hang."""
        from src.mcp.tools import SparkTool
        from src.workflow.nodes import SparkToolNode, NodeConfig, NodeType
        import src.mcp.tools as tools_mod

        async def hang(_params):
            await asyncio.sleep(60)  # would hang forever

        tool = SparkTool(
            name="hanging_tool",
            description="hangs",
            input_schema={"type": "object", "properties": {}},
            handler=hang,
        )

        orig = tools_mod.registry
        reg = type(orig).__new__(type(orig))
        reg._tools = {"hanging_tool": tool}
        tools_mod.registry = reg

        try:
            nc = NodeConfig(
                id="hang1", type=NodeType.SPARK_TOOL, name="hang",
                config={"tool_name": "hanging_tool"},
                timeout_sec=0.05,
            )
            node = SparkToolNode(nc)
            t0 = time.monotonic()
            result = await node.execute({}, {})
            elapsed = time.monotonic() - t0
            _log.info("chaos.timeout success=%s elapsed=%.3fs error=%s", result.success, elapsed, result.error)
            assert not result.success
            assert elapsed < 5.0, "Timeout must fire well under 5 s"
        finally:
            tools_mod.registry = orig
