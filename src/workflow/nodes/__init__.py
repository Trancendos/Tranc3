"""
src/workflow/nodes — The Digital Grid workflow node package.

Public API re-exported for backward compatibility with:
  from src.workflow.nodes import NodeType, NodeConfig, NodeResult, BaseNode, create_node
"""

from .base import NodeType, NodeConfig, NodeResult, BaseNode, _deep_get
from .registry import (
    NODE_REGISTRY,
    _PHASE4_NODE_REGISTRY,
    _ensure_phase4_nodes_loaded,
    create_node,
)
from .ai import LLMNode, MLPredictNode
from .code import CodeExecNode
from .http import HTTPNode, VectorSearchNode
from .flow import ConditionNode, ParallelNode, LoopNode, MergeNode
from .data import TransformNode, OutputNode, TriggerNode
from .tools import (
    SparkToolNode,
    SkillCallNode,
    register_spark_tool,
    register_skill,
    _SPARK_TOOL_REGISTRY,
    _SKILL_REGISTRY,
)
from .neural import NeuralMeshNode, CollectiveMemoryNode, MetaLearnNode
from .reasoning import AttentionRouteNode, CausalReasonNode, KnowledgeGraphNode, ForesightNode
from .agents import (
    AgentCreateNode,
    AgentRunStepNode,
    AgentGoalNode,
    AgentReflectNode,
    AgentDecomposeNode,
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
