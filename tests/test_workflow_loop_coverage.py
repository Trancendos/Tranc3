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
