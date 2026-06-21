"""
src/workflow/phase4_nodes.py — backward-compatibility shim.

Phase 4 nodes have been moved to src/workflow/nodes/neural.py and
src/workflow/nodes/reasoning.py. This module re-exports everything so
existing imports continue to work.
"""

from src.workflow.nodes.neural import (  # noqa: F401
    CollectiveMemoryNode,
    MetaLearnNode,
    NeuralMeshNode,
)
from src.workflow.nodes.reasoning import (  # noqa: F401
    AttentionRouteNode,
    CausalReasonNode,
    ForesightNode,
    KnowledgeGraphNode,
)

PHASE4_NODE_TYPES = {
    "NEURAL_MESH": NeuralMeshNode,
    "COLLECTIVE_MEMORY": CollectiveMemoryNode,
    "META_LEARN": MetaLearnNode,
    "ATTENTION_ROUTE": AttentionRouteNode,
    "CAUSAL_REASON": CausalReasonNode,
    "KNOWLEDGE_GRAPH": KnowledgeGraphNode,
    "FORESIGHT": ForesightNode,
}


def extend_node_registry(registry: dict) -> int:
    count = 0
    for key, cls in PHASE4_NODE_TYPES.items():
        if key not in registry:
            registry[key] = cls
            count += 1
    return count
