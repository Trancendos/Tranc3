"""
src/workflow/nodes — The Digital Grid workflow node package.

Public API re-exported for backward compatibility with:
  from src.workflow.nodes import NodeType, NodeConfig, NodeResult, BaseNode, create_node
"""

from .agents import (
    AgentCreateNode,
    AgentDecomposeNode,
    AgentGoalNode,
    AgentReflectNode,
    AgentRunStepNode,
)
from .ai import LLMNode, MLPredictNode
from .base import BaseNode, NodeConfig, NodeResult, NodeType, _deep_get
from .code import CodeExecNode
from .data import OutputNode, TransformNode, TriggerNode
from .flow import ConditionNode, LoopNode, MergeNode, ParallelNode
from .http import HTTPNode, VectorSearchNode
from .neural import CollectiveMemoryNode, MetaLearnNode, NeuralMeshNode
from .reasoning import AttentionRouteNode, CausalReasonNode, ForesightNode, KnowledgeGraphNode
from .registry import (
    _PHASE4_NODE_REGISTRY,
    NODE_REGISTRY,
    _ensure_phase4_nodes_loaded,
    create_node,
)
from .tools import (
    _SKILL_REGISTRY,
    _SPARK_TOOL_REGISTRY,
    SkillCallNode,
    SparkToolNode,
    register_skill,
    register_spark_tool,
)

__all__ = [
    # Core types
    "NodeType",
    "NodeConfig",
    "NodeResult",
    "BaseNode",
    "_deep_get",
    # Registry
    "NODE_REGISTRY",
    "_PHASE4_NODE_REGISTRY",
    "_ensure_phase4_nodes_loaded",
    "create_node",
    # AI nodes
    "LLMNode",
    "MLPredictNode",
    # Code nodes
    "CodeExecNode",
    # HTTP / vector nodes
    "HTTPNode",
    "VectorSearchNode",
    # Flow control
    "ConditionNode",
    "ParallelNode",
    "LoopNode",
    "MergeNode",
    # Data nodes
    "TransformNode",
    "OutputNode",
    "TriggerNode",
    # Tool/skill nodes
    "SparkToolNode",
    "SkillCallNode",
    "register_spark_tool",
    "register_skill",
    "_SPARK_TOOL_REGISTRY",
    "_SKILL_REGISTRY",
    # Phase 4 neural nodes
    "NeuralMeshNode",
    "CollectiveMemoryNode",
    "MetaLearnNode",
    # Phase 4 reasoning nodes
    "AttentionRouteNode",
    "CausalReasonNode",
    "KnowledgeGraphNode",
    "ForesightNode",
    # Phase 5 agent nodes
    "AgentCreateNode",
    "AgentRunStepNode",
    "AgentGoalNode",
    "AgentReflectNode",
    "AgentDecomposeNode",
]
