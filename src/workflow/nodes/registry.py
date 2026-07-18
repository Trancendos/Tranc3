"""
src/workflow/nodes/registry.py — Node registry and factory for The Digital Grid.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, Type

from .base import BaseNode, NodeConfig, NodeType

logger = logging.getLogger(__name__)

# NODE_REGISTRY is populated lazily on first call to create_node() to avoid
# circular imports: flow.py deferred-imports create_node from this module, so
# importing flow.py here at module level would create a detectable import cycle.
NODE_REGISTRY: Dict[NodeType, Type[BaseNode]] = {}
_REGISTRY_INITIALIZED = False


def _init_registry() -> None:
    # A dedicated flag, not dict truthiness: anything that seeds a single
    # entry into NODE_REGISTRY before this ever runs (e.g. a test swapping
    # in a fault-injection node for one NodeType) would otherwise make the
    # dict non-empty and permanently skip real initialization.
    global _REGISTRY_INITIALIZED
    if _REGISTRY_INITIALIZED:
        return
    _REGISTRY_INITIALIZED = True

    from .ai import LLMNode, MLPredictNode  # noqa: PLC0415
    from .code import CodeExecNode  # noqa: PLC0415
    from .data import OutputNode, TransformNode, TriggerNode  # noqa: PLC0415
    from .flow import ConditionNode, LoopNode, MergeNode, ParallelNode  # noqa: PLC0415
    from .http import HTTPNode, VectorSearchNode  # noqa: PLC0415
    from .tools import SkillCallNode, SparkToolNode  # noqa: PLC0415

    NODE_REGISTRY.update(
        {
            NodeType.LLM: LLMNode,
            NodeType.CODE_EXEC: CodeExecNode,
            NodeType.HTTP_REQUEST: HTTPNode,
            NodeType.CONDITION: ConditionNode,
            NodeType.TRANSFORM: TransformNode,
            NodeType.VECTOR_SEARCH: VectorSearchNode,
            NodeType.SPARK_TOOL: SparkToolNode,
            NodeType.PARALLEL: ParallelNode,
            NodeType.LOOP: LoopNode,
            NodeType.MERGE: MergeNode,
            NodeType.OUTPUT: OutputNode,
            NodeType.TRIGGER: TriggerNode,
            NodeType.SKILL_CALL: SkillCallNode,
            NodeType.ML_PREDICT: MLPredictNode,
        }
    )


_PHASE4_NODE_REGISTRY: Dict[str, Any] = {}
_PHASE4_LOADED = False


def _ensure_phase4_nodes_loaded() -> None:
    global _PHASE4_LOADED
    if _PHASE4_LOADED:
        return
    _PHASE4_LOADED = True
    try:
        from .neural import CollectiveMemoryNode, MetaLearnNode, NeuralMeshNode
        from .reasoning import (  # noqa: PLC0415
            AttentionRouteNode,
            CausalReasonNode,
            ForesightNode,
            KnowledgeGraphNode,
        )

        _PHASE4_NODE_REGISTRY.update(
            {
                "NEURAL_MESH": NeuralMeshNode,
                "COLLECTIVE_MEMORY": CollectiveMemoryNode,
                "META_LEARN": MetaLearnNode,
                "ATTENTION_ROUTE": AttentionRouteNode,
                "CAUSAL_REASON": CausalReasonNode,
                "KNOWLEDGE_GRAPH": KnowledgeGraphNode,
                "FORESIGHT": ForesightNode,
            }
        )
        logger.info("Phase 4 workflow nodes loaded")
    except Exception as exc:
        logger.warning("Phase 4 workflow nodes unavailable: %s", exc)
    try:
        from .agents import (
            AgentCreateNode,
            AgentDecomposeNode,
            AgentGoalNode,
            AgentReflectNode,
            AgentRunStepNode,
        )

        _PHASE4_NODE_REGISTRY.update(
            {
                "AGENT_CREATE": AgentCreateNode,
                "AGENT_RUN_STEP": AgentRunStepNode,
                "AGENT_GOAL": AgentGoalNode,
                "AGENT_REFLECT": AgentReflectNode,
                "AGENT_DECOMPOSE": AgentDecomposeNode,
            }
        )
        logger.info("Phase 5 workflow nodes loaded")
    except Exception as exc:
        logger.warning("Phase 5 workflow nodes unavailable: %s", exc)


def create_node(config: NodeConfig) -> BaseNode:
    """Factory: instantiate the correct BaseNode subclass for a given NodeConfig."""
    _init_registry()
    _ensure_phase4_nodes_loaded()
    node_class: Optional[Type[BaseNode]] = NODE_REGISTRY.get(config.type)
    if node_class is None:
        node_class = _PHASE4_NODE_REGISTRY.get(config.type)  # type: ignore[assignment]
    if node_class is None:
        raise ValueError(
            f"Unknown node type: {config.type!r}. "
            f"Available: {[t.value for t in NODE_REGISTRY] + list(_PHASE4_NODE_REGISTRY.keys())}"
        )
    return node_class(config)


__all__ = [
    "NODE_REGISTRY",
    "_PHASE4_NODE_REGISTRY",
    "_ensure_phase4_nodes_loaded",
    "create_node",
]
