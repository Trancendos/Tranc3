"""
src/workflow/nodes.py — backward-compatibility shim.

All node types have been moved to the src/workflow/nodes/ package.
This module re-exports everything so existing imports continue to work.
"""

from src.workflow.nodes import (  # noqa: F401
    NodeType,
    NodeConfig,
    NodeResult,
    BaseNode,
    _deep_get,
    NODE_REGISTRY,
    _PHASE4_NODE_REGISTRY,
    _ensure_phase4_nodes_loaded,
    create_node,
    LLMNode,
    MLPredictNode,
    CodeExecNode,
    HTTPNode,
    VectorSearchNode,
    ConditionNode,
    ParallelNode,
    LoopNode,
    MergeNode,
    TransformNode,
    OutputNode,
    TriggerNode,
    SparkToolNode,
    SkillCallNode,
    register_spark_tool,
    register_skill,
    _SPARK_TOOL_REGISTRY,
    _SKILL_REGISTRY,
    NeuralMeshNode,
    CollectiveMemoryNode,
    MetaLearnNode,
    AttentionRouteNode,
    CausalReasonNode,
    KnowledgeGraphNode,
    ForesightNode,
    AgentCreateNode,
    AgentRunStepNode,
    AgentGoalNode,
    AgentReflectNode,
    AgentDecomposeNode,
)
