"""
src/agents/ — Autonomous Agent Orchestration Layer (Phase 5)

Provides multi-agent orchestration for the Tranc3 platform:
  - AgentRuntime: lifecycle management for autonomous agents
  - TaskDecomposer: hierarchical task planning and decomposition
  - ToolBridge: unified tool execution across MCP / workflow / neural
  - MemoryStream: episodic memory with recency, relevance, importance
  - GoalManager: multi-goal tracking with priority and progress
  - AgentType: specialist agent profiles (researcher, coder, planner, etc.)

All modules are zero-cost: pure Python, no paid APIs, lazy-loaded singletons.
"""

from .agent_runtime import AgentRuntime, AgentState
from .agent_types import AgentProfile, AgentType
from .goal_manager import Goal, GoalManager, GoalState
from .memory_stream import EpisodicMemory, MemoryStream
from .task_decomposer import Decomposition, SubTask, TaskDecomposer
from .tool_bridge import ToolBridge, ToolResult

__all__ = [
    "AgentRuntime",
    "AgentState",
    "TaskDecomposer",
    "SubTask",
    "Decomposition",
    "ToolBridge",
    "ToolResult",
    "MemoryStream",
    "EpisodicMemory",
    "GoalManager",
    "Goal",
    "GoalState",
    "AgentType",
    "AgentProfile",
]
