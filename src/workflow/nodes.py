"""
src/workflow/nodes.py — backward-compatibility shim.

All node types have been moved to the src/workflow/nodes/ package.
This module re-exports everything so existing imports continue to work.
"""

from src.workflow.nodes import (  # noqa: F401
    _PHASE4_NODE_REGISTRY,
    _SKILL_REGISTRY,
    _SPARK_TOOL_REGISTRY,
    NODE_REGISTRY,
    AgentCreateNode,
    AgentDecomposeNode,
    AgentGoalNode,
    AgentReflectNode,
    AgentRunStepNode,
    AttentionRouteNode,
    BaseNode,
    CausalReasonNode,
    CodeExecNode,
    CollectiveMemoryNode,
    ConditionNode,
    ForesightNode,
    HTTPNode,
    KnowledgeGraphNode,
    LLMNode,
    LoopNode,
    MergeNode,
    MetaLearnNode,
    MLPredictNode,
    NeuralMeshNode,
    NodeConfig,
    NodeResult,
    NodeType,
    OutputNode,
    ParallelNode,
    SkillCallNode,
    SparkToolNode,
    TransformNode,
    TriggerNode,
    VectorSearchNode,
    _deep_get,
    _ensure_phase4_nodes_loaded,
    create_node,
    register_skill,
    register_spark_tool,
)
