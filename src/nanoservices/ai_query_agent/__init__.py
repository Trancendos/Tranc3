"""AI Query Agent — Phase 9

Autonomous NRC query agent powered by SHI (Self-Hosted Inference)
that can understand natural language queries, translate them to NRC
DSL, optimize execution plans, and iteratively refine results.
"""

from .ai_query_agent import (
    AgentAction,
    AgentState,
    AIQueryAgent,
    QueryTask,
    ReasoningStep,
)

__all__ = [
    "AgentState",
    "QueryTask",
    "AgentAction",
    "ReasoningStep",
    "AIQueryAgent",
]
