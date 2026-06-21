"""
src/workflow/phase5_nodes.py — backward-compatibility shim.

Phase 5 nodes have been moved to src/workflow/nodes/agents.py.
This module re-exports everything so existing imports continue to work.
"""

from src.workflow.nodes.agents import (  # noqa: F401
    AgentCreateNode,
    AgentRunStepNode,
    AgentGoalNode,
    AgentReflectNode,
    AgentDecomposeNode,
)

PHASE5_NODE_TYPES = {
    "AGENT_CREATE": AgentCreateNode,
    "AGENT_RUN_STEP": AgentRunStepNode,
    "AGENT_GOAL": AgentGoalNode,
    "AGENT_REFLECT": AgentReflectNode,
    "AGENT_DECOMPOSE": AgentDecomposeNode,
}


def extend_node_registry(registry: dict) -> int:
    count = 0
    for key, cls in PHASE5_NODE_TYPES.items():
        if key not in registry:
            registry[key] = cls
            count += 1
    return count


def register_phase5_nodes() -> int:
    try:
        from src.workflow.nodes import _PHASE4_NODE_REGISTRY

        return extend_node_registry(_PHASE4_NODE_REGISTRY)
    except Exception:
        return 0
