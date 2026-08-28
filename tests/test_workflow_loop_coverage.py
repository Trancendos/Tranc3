import pytest

from src.workflow.nodes.base import NodeConfig, NodeType
from src.workflow.nodes.flow import LoopNode


@pytest.mark.asyncio
async def test_loop_node_empty():
    config = NodeConfig(
        id="test_loop",
        type=NodeType.LOOP,
        name="test_loop",
        config={
            "items": [],
            "nodes": [{"id": "inner_1", "type": "TRANSFORM", "config": {"template": "foo"}}],
        },
    )
    node = LoopNode(config)
    res = await node.execute({"items": []}, {})
    assert res.success is True
    assert res.output["loop_results"] == []


@pytest.mark.asyncio
async def test_loop_node_error():
    config = NodeConfig(
        id="test_loop",
        type=NodeType.LOOP,
        name="test_loop",
        config={
            "items": [1],
            "nodes": [
                {"id": "inner_1", "type": "CONDITION", "config": {"expression": "invalid_syntax("}}
            ],
        },
    )
    node = LoopNode(config)
    res = await node.execute({"items": [1]}, {})
    assert res.success is True
    assert len(res.output["loop_results"]) == 1
    assert "error" in res.output["loop_results"][0]


@pytest.mark.asyncio
async def test_loop_node_no_inner_configs():
    config = NodeConfig(
        id="test_loop", type=NodeType.LOOP, name="test_loop", config={"items": [1, 2], "nodes": []}
    )
    node = LoopNode(config)
    res = await node.execute({"items": [1, 2]}, {})
    assert res.success is True
    assert res.output["loop_results"] == []


@pytest.mark.asyncio
async def test_loop_node_reuses_inner_nodes_across_concurrent_items():
    """Inner nodes are constructed once, yet each item still gets its own result.

    The inner node instances are shared across all items, so this is the case
    that would break if a node kept per-execution state on self: every item
    would see another item's value.
    """
    config = NodeConfig(
        id="test_loop",
        type=NodeType.LOOP,
        name="test_loop",
        config={
            "items": [1, 2, 3, 4],
            "max_concurrency": 4,
            "nodes": [
                {
                    "id": "inner_1",
                    "type": "TRANSFORM",
                    "config": {"template": "item-{item}"},
                }
            ],
        },
    )
    node = LoopNode(config)
    res = await node.execute({"items": [1, 2, 3, 4]}, {})

    assert res.success is True
    assert len(res.output["loop_results"]) == 4
    # Distinct results prove no cross-item contamination through the shared node.
    assert len(set(map(str, res.output["loop_results"]))) == 4


# ---------------------------------------------------------------------------
# WorkflowExecutor — sort-failure cleanup
#
# `execute()` bails out early when the DAG cannot be topologically sorted
# (a cycle, or a dangling edge). That early return used to skip the
# `_cancel_flags` cleanup that the main path's finally performs, so every
# unsortable workflow left an asyncio.Event behind in a long-lived executor —
# and `cancel()` reads that dict, so it answered for an execution that had
# already failed.
#
# These pin both halves: that the flag is gone afterwards, and that `cancel()`
# reports the failure rather than a live cancellation. The second matters more
# than the leak: a caller that gets True believes it stopped something.
# ---------------------------------------------------------------------------


def _cyclic_workflow():
    """Two nodes pointing at each other — no topological order exists."""
    from src.workflow.builder import WorkflowDefinition

    a = NodeConfig(id="a", type=NodeType.TRANSFORM, name="a", config={"template": "x"})
    b = NodeConfig(id="b", type=NodeType.TRANSFORM, name="b", config={"template": "y"})
    return WorkflowDefinition(
        name="cyclic", nodes={"a": a, "b": b}, edges=[("a", "b", ""), ("b", "a", "")]
    )


def _raise_publish_on(monkeypatch, topic):
    """Make event_bus.publish raise RuntimeError for one topic, pass for the rest."""
    import sys

    # sys.modules, not `import src.workflow.executor as m`: the package's
    # __init__ does `from .executor import ..., executor, ...`, binding a
    # WorkflowExecutor *instance* to the name `src.workflow.executor` and
    # shadowing its own submodule. The plain import returns that instance, so
    # patching through it silently targets the wrong object.
    executor_mod = sys.modules["src.workflow.executor"]
    real_publish = executor_mod.event_bus.publish

    async def _maybe_boom(event_type, *args, **kwargs):
        if event_type == topic:
            raise RuntimeError(f"event bus down for {event_type}")
        return await real_publish(event_type, *args, **kwargs)

    monkeypatch.setattr(executor_mod.event_bus, "publish", _maybe_boom)


@pytest.mark.asyncio
async def test_sort_failure_marks_failed_and_clears_cancel_flag():
    from src.workflow.executor import WorkflowExecutor

    ex = WorkflowExecutor()
    state = await ex.execute(_cyclic_workflow())

    assert state.status == "failed"
    assert state.error
    assert ex._cancel_flags == {}, "sort failure must not leave a cancel flag behind"


@pytest.mark.asyncio
async def test_cancel_after_sort_failure_reports_false():
    from src.workflow.executor import WorkflowExecutor

    ex = WorkflowExecutor()
    state = await ex.execute(_cyclic_workflow())

    # The execution is over and it failed; cancel() must not claim otherwise.
    assert await ex.cancel(state.execution_id) is False


@pytest.mark.asyncio
async def test_sort_failure_cleanup_survives_a_raising_publish(monkeypatch):
    """The cleanup is in a finally, so it runs even if the failure path raises.

    `_handle_sort_failure` awaits `event_bus.publish`; a CancelledError or any
    other exception there previously skipped the pop. Simulated here with a
    plain raise, which exercises the same code path as cancellation without
    the flakiness of racing a real task cancellation.

    The fake only raises on "workflow.failed" so that initialisation still
    succeeds -- raising on every topic would take out the "workflow.started"
    publish instead and never reach the branch under test.
    """
    from src.workflow.executor import WorkflowExecutor

    ex = WorkflowExecutor()
    _raise_publish_on(monkeypatch, "workflow.failed")

    with pytest.raises(RuntimeError):
        await ex.execute(_cyclic_workflow())

    assert ex._cancel_flags == {}, "finally must clear the flag even when publish raises"


@pytest.mark.asyncio
async def test_failed_start_publish_does_not_leak_a_cancel_flag(monkeypatch):
    """A failure inside _initialize_execution must roll back its own registration.

    The cancel flag is registered before "workflow.started" is published, and
    at that point execute() has entered neither of its try/finally blocks. So
    a raising (or cancelled) publish here leaks the asyncio.Event with no
    cleanup on any path, and a later cancel() reports success for an execution
    that never started.
    """
    from src.workflow.executor import WorkflowExecutor

    ex = WorkflowExecutor()
    _raise_publish_on(monkeypatch, "workflow.started")

    with pytest.raises(RuntimeError):
        await ex.execute(_cyclic_workflow())

    assert ex._cancel_flags == {}, "a failed start must not leave a cancel flag behind"
    assert ex.executions == {}, "a failed start must not leave an execution behind"
