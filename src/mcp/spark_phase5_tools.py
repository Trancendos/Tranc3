"""
spark_phase5_tools.py — Phase 5 Autonomous Agent tools for The Spark MCP server.

Registers 12 new SparkTool instances exposing Phase 5 agent orchestration
capabilities:

  Agent Lifecycle:
    - agent_create           — create a new autonomous agent
    - agent_start            — start an agent runtime
    - agent_stop             — gracefully stop an agent
    - agent_status           — query agent state and metrics

  Goal Management:
    - agent_assign_goal      — assign a goal to an agent
    - agent_list_goals       — list an agent's goals

  Task Decomposition:
    - agent_decompose_task   — decompose a goal into subtasks

  Memory & Reflection:
    - agent_retrieve_memory  — search an agent's episodic memory
    - agent_reflect          — trigger an agent's reflection cycle

  Multi-Agent:
    - agent_list_all         — list all active agents
    - agent_find_best        — find best agent type for given tags
    - agent_profiles         — list all agent profiles

All handlers are async. Each module is imported lazily so the server
starts cleanly even if optional dependencies are absent.

Usage:
    from src.mcp.spark_phase5_tools import register_phase5_tools
    register_phase5_tools(registry)   # registry: SparkToolRegistry
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy singletons for Phase 5 components
# ---------------------------------------------------------------------------

_agents: Dict[str, Any] = {}  # agent_id → AgentRuntime


def _get_agent(agent_id: str) -> Optional[Any]:
    """Retrieve an agent from the in-process registry."""
    return _agents.get(agent_id)


def _get_or_create_agent_runtime():
    """Lazy-import AgentRuntime class."""
    try:
        from src.agents.agent_runtime import AgentRuntime
        return AgentRuntime
    except Exception as exc:
        logger.warning("AgentRuntime unavailable: %s", exc)
        return None


def _get_goal_manager():
    """Lazy-import GoalManager class."""
    try:
        from src.agents.goal_manager import GoalManager
        return GoalManager
    except Exception as exc:
        logger.warning("GoalManager unavailable: %s", exc)
        return None


def _get_task_decomposer():
    """Lazy-import TaskDecomposer class."""
    try:
        from src.agents.task_decomposer import TaskDecomposer
        return TaskDecomposer
    except Exception as exc:
        logger.warning("TaskDecomposer unavailable: %s", exc)
        return None


def _get_memory_stream():
    """Lazy-import MemoryStream class."""
    try:
        from src.agents.memory_stream import MemoryStream
        return MemoryStream
    except Exception as exc:
        logger.warning("MemoryStream unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Helper: error / ok responses
# ---------------------------------------------------------------------------


def _err(msg: str) -> Dict[str, Any]:
    return {"error": msg, "ok": False}


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "ts": time.time(), **data}


# ---------------------------------------------------------------------------
# Agent Lifecycle handlers
# ---------------------------------------------------------------------------


async def _handle_agent_create(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a new autonomous agent with the specified type and configuration.

    Params:
        name (str): Human-readable agent name.
        agent_type (str): One of: general, researcher, coder, planner,
                          analyzer, orchestrator, guardian.
        max_concurrent_tasks (int, optional): Max parallel tasks (default 3).
        memory_capacity (int, optional): Episodic memory capacity (default 500).
    """
    AgentRuntime = _get_or_create_agent_runtime()
    if AgentRuntime is None:
        return _err("AgentRuntime module not available")

    from src.agents.agent_runtime import AgentConfig

    name = params.get("name", "unnamed-agent")
    agent_type = params.get("agent_type", "general")
    max_concurrent_tasks = int(params.get("max_concurrent_tasks", 3))
    memory_capacity = int(params.get("memory_capacity", 500))

    config = AgentConfig(
        name=name,
        agent_type=agent_type,
        max_concurrent_tasks=max_concurrent_tasks,
        memory_capacity=memory_capacity,
    )

    runtime = AgentRuntime(config=config)
    _agents[runtime.agent_id] = runtime

    return _ok({
        "agent_id": runtime.agent_id,
        "name": runtime.name,
        "agent_type": runtime.agent_type,
        "state": runtime.state.value,
    })


async def _handle_agent_start(params: Dict[str, Any]) -> Dict[str, Any]:
    """Start an agent runtime, initializing its sub-components.

    Params:
        agent_id (str): The agent to start.
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    await runtime.start()
    return _ok({
        "agent_id": runtime.agent_id,
        "state": runtime.state.value,
    })


async def _handle_agent_stop(params: Dict[str, Any]) -> Dict[str, Any]:
    """Gracefully stop an agent runtime.

    Params:
        agent_id (str): The agent to stop.
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    await runtime.stop()
    # Remove from registry
    _agents.pop(runtime.agent_id, None)
    return _ok({
        "agent_id": runtime.agent_id,
        "state": runtime.state.value,
        "metrics": runtime.metrics,
    })


async def _handle_agent_status(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query an agent's current state, metrics, and progress.

    Params:
        agent_id (str): The agent to query.
        include_results (bool, optional): Include step results (default False).
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    result = {
        "agent_id": runtime.agent_id,
        "name": runtime.name,
        "agent_type": runtime.agent_type,
        "state": runtime.state.value,
        "is_running": runtime.is_running,
        "metrics": runtime.metrics,
    }

    if params.get("include_results", False):
        result["results"] = runtime.get_results()

    return _ok(result)


# ---------------------------------------------------------------------------
# Goal Management handlers
# ---------------------------------------------------------------------------


async def _handle_agent_assign_goal(params: Dict[str, Any]) -> Dict[str, Any]:
    """Assign a new goal to an agent.

    Params:
        agent_id (str): The target agent.
        description (str): Goal description.
        priority (int, optional): Priority 1-10 (default 5).
        deadline (float, optional): Unix timestamp deadline.
        metadata (dict, optional): Arbitrary goal metadata.
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    description = params.get("description", "")
    if not description:
        return _err("Goal description is required")

    priority = int(params.get("priority", 5))
    deadline = params.get("deadline")
    metadata = params.get("metadata", {})

    goal_id = await runtime.assign_goal(
        description=description,
        priority=priority,
        metadata={
            **metadata,
            **({"deadline": deadline} if deadline else {}),
        },
    )

    return _ok({
        "agent_id": runtime.agent_id,
        "goal_id": goal_id,
        "description": description,
        "priority": priority,
    })


async def _handle_agent_list_goals(params: Dict[str, Any]) -> Dict[str, Any]:
    """List all goals for an agent.

    Params:
        agent_id (str): The target agent.
        state_filter (str, optional): Filter by goal state.
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    if runtime._goal_manager is None:
        return _ok({"goals": [], "total": 0})

    goals = await runtime._goal_manager.get_all_goals()
    state_filter = params.get("state_filter")
    if state_filter:
        goals = [g for g in goals if g.get("state") == state_filter]

    return _ok({
        "agent_id": runtime.agent_id,
        "goals": goals,
        "total": len(goals),
    })


# ---------------------------------------------------------------------------
# Task Decomposition handler
# ---------------------------------------------------------------------------


async def _handle_agent_decompose_task(params: Dict[str, Any]) -> Dict[str, Any]:
    """Decompose a goal description into executable subtasks.

    Params:
        goal_description (str): The goal to decompose.
        strategy (str, optional): Force a decomposition strategy.
    """
    TaskDecomposer = _get_task_decomposer()
    if TaskDecomposer is None:
        return _err("TaskDecomposer module not available")

    goal_description = params.get("goal_description", "")
    if not goal_description:
        return _err("goal_description is required")

    decomposer = TaskDecomposer()
    decomposition = await decomposer.decompose(goal_description)

    return _ok({
        "goal_description": decomposition.goal_description,
        "strategy": decomposition.strategy,
        "subtasks": [st.to_dict() for st in decomposition.subtasks],
        "total_complexity": decomposition.estimated_total_complexity,
    })


# ---------------------------------------------------------------------------
# Memory & Reflection handlers
# ---------------------------------------------------------------------------


async def _handle_agent_retrieve_memory(params: Dict[str, Any]) -> Dict[str, Any]:
    """Search an agent's episodic memory stream.

    Params:
        agent_id (str): The target agent.
        query (str, optional): Search query for relevance matching.
        tags (list[str], optional): Tags to filter by.
        top_k (int, optional): Max results to return (default 10).
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    if runtime._memory_stream is None:
        return _ok({"memories": [], "total": 0})

    query = params.get("query", "")
    tags = set(params.get("tags", []))
    top_k = int(params.get("top_k", 10))

    memories = await runtime._memory_stream.retrieve(
        query=query,
        query_tags=tags if tags else None,
        top_k=top_k,
    )

    return _ok({
        "agent_id": runtime.agent_id,
        "memories": [m.to_dict() for m in memories],
        "total": len(memories),
    })


async def _handle_agent_reflect(params: Dict[str, Any]) -> Dict[str, Any]:
    """Trigger an agent's reflection cycle over its episodic memories.

    Params:
        agent_id (str): The target agent.
        top_k (int, optional): Number of memories to reflect on (default 20).
    """
    runtime = _get_agent(params.get("agent_id", ""))
    if runtime is None:
        return _err(f"Agent not found: {params.get('agent_id')}")

    if runtime._memory_stream is None:
        return _ok({"reflections": [], "total": 0})

    top_k = int(params.get("top_k", 20))
    reflections = await runtime._memory_stream.reflect(top_k=top_k)

    return _ok({
        "agent_id": runtime.agent_id,
        "reflections": reflections,
        "total": len(reflections),
    })


# ---------------------------------------------------------------------------
# Multi-Agent handlers
# ---------------------------------------------------------------------------


async def _handle_agent_list_all(params: Dict[str, Any]) -> Dict[str, Any]:
    """List all registered agents and their states.

    Params: none required.
    """
    agents_info = []
    for agent_id, runtime in _agents.items():
        agents_info.append({
            "agent_id": runtime.agent_id,
            "name": runtime.name,
            "agent_type": runtime.agent_type,
            "state": runtime.state.value,
            "is_running": runtime.is_running,
        })

    return _ok({
        "agents": agents_info,
        "total": len(agents_info),
    })


async def _handle_agent_find_best(params: Dict[str, Any]) -> Dict[str, Any]:
    """Find the best agent profile for a set of required capabilities.

    Params:
        required_tags (list[str]): Required capability tags.
    """
    try:
        from src.agents.agent_types import find_best_profile
    except Exception as exc:
        return _err(f"Agent types module not available: {exc}")

    required_tags = set(params.get("required_tags", []))
    if not required_tags:
        return _err("required_tags must be a non-empty list")

    profile = find_best_profile(required_tags)

    return _ok({
        "best_match": profile.to_dict(),
        "required_tags": sorted(required_tags),
        "match_score": round(profile.matches_tags(required_tags), 4),
    })


async def _handle_agent_profiles(params: Dict[str, Any]) -> Dict[str, Any]:
    """List all available agent profiles with their capabilities.

    Params: none required.
    """
    try:
        from src.agents.agent_types import list_profiles
    except Exception as exc:
        return _err(f"Agent types module not available: {exc}")

    profiles = list_profiles()

    return _ok({
        "profiles": profiles,
        "total": len(profiles),
    })


# ---------------------------------------------------------------------------
# Tool definitions (matches SparkTool constructor args)
# ---------------------------------------------------------------------------


PHASE5_TOOLS: List[Dict[str, Any]] = [
    {
        "name": "agent_create",
        "description": (
            "Create a new autonomous agent with a specified specialist type. "
            "Agent types: general, researcher, coder, planner, analyzer, "
            "orchestrator, guardian. Returns the agent ID for subsequent operations."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Human-readable agent name.",
                },
                "agent_type": {
                    "type": "string",
                    "description": "Specialist agent type.",
                    "enum": ["general", "researcher", "coder", "planner",
                             "analyzer", "orchestrator", "guardian"],
                    "default": "general",
                },
                "max_concurrent_tasks": {
                    "type": "integer",
                    "description": "Maximum concurrent tasks (default 3).",
                    "default": 3,
                    "minimum": 1,
                    "maximum": 10,
                },
                "memory_capacity": {
                    "type": "integer",
                    "description": "Episodic memory capacity (default 500).",
                    "default": 500,
                    "minimum": 10,
                    "maximum": 10000,
                },
            },
            "required": ["name"],
        },
        "handler": _handle_agent_create,
        "category": "agents",
    },
    {
        "name": "agent_start",
        "description": (
            "Start an agent runtime, initializing its task decomposer, tool bridge, "
            "memory stream, and goal manager sub-components."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the agent to start.",
                },
            },
            "required": ["agent_id"],
        },
        "handler": _handle_agent_start,
        "category": "agents",
    },
    {
        "name": "agent_stop",
        "description": (
            "Gracefully stop an agent runtime. The agent will complete its current "
            "step, then transition to TERMINATED state. Returns final metrics."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the agent to stop.",
                },
            },
            "required": ["agent_id"],
        },
        "handler": _handle_agent_stop,
        "category": "agents",
    },
    {
        "name": "agent_status",
        "description": (
            "Query an agent's current state, metrics, and execution progress. "
            "Optionally include completed step results."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the agent to query.",
                },
                "include_results": {
                    "type": "boolean",
                    "description": "Include completed step results (default false).",
                    "default": False,
                },
            },
            "required": ["agent_id"],
        },
        "handler": _handle_agent_status,
        "category": "agents",
    },
    {
        "name": "agent_assign_goal",
        "description": (
            "Assign a new goal to an agent. The agent will plan and execute steps "
            "to achieve this goal when run. Goals have priority (1-10) and optional "
            "deadlines for time-sensitive tasks."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the target agent.",
                },
                "description": {
                    "type": "string",
                    "description": "Goal description.",
                },
                "priority": {
                    "type": "integer",
                    "description": "Priority 1-10 (default 5). Higher = more important.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 10,
                },
                "deadline": {
                    "type": "number",
                    "description": "Unix timestamp deadline (optional).",
                },
                "metadata": {
                    "type": "object",
                    "description": "Arbitrary goal metadata.",
                },
            },
            "required": ["agent_id", "description"],
        },
        "handler": _handle_agent_assign_goal,
        "category": "agents",
    },
    {
        "name": "agent_list_goals",
        "description": (
            "List all goals for an agent, optionally filtered by state "
            "(pending, active, completed, failed, cancelled)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the target agent.",
                },
                "state_filter": {
                    "type": "string",
                    "description": "Filter by goal state.",
                    "enum": ["pending", "active", "completed", "failed", "cancelled"],
                },
            },
            "required": ["agent_id"],
        },
        "handler": _handle_agent_list_goals,
        "category": "agents",
    },
    {
        "name": "agent_decompose_task",
        "description": (
            "Decompose a goal description into an ordered list of executable subtasks. "
            "Uses pattern matching to select an appropriate decomposition strategy "
            "(analysis, creation, debugging, research, security, planning, prediction, generic)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "goal_description": {
                    "type": "string",
                    "description": "The goal to decompose into subtasks.",
                },
            },
            "required": ["goal_description"],
        },
        "handler": _handle_agent_decompose_task,
        "category": "agents",
    },
    {
        "name": "agent_retrieve_memory",
        "description": (
            "Search an agent's episodic memory stream using combined recency, "
            "relevance, and importance scoring. Supports keyword queries and "
            "tag-based filtering."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the target agent.",
                },
                "query": {
                    "type": "string",
                    "description": "Search query for relevance matching.",
                },
                "tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Tags to filter by.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum results to return (default 10).",
                    "default": 10,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["agent_id"],
        },
        "handler": _handle_agent_retrieve_memory,
        "category": "agents",
    },
    {
        "name": "agent_reflect",
        "description": (
            "Trigger an agent's reflection cycle. Synthesizes insights from "
            "the agent's most important and recent episodic memories. Used "
            "for self-improvement and adaptive behavior."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "ID of the target agent.",
                },
                "top_k": {
                    "type": "integer",
                    "description": "Number of memories to reflect on (default 20).",
                    "default": 20,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
            "required": ["agent_id"],
        },
        "handler": _handle_agent_reflect,
        "category": "agents",
    },
    {
        "name": "agent_list_all",
        "description": (
            "List all registered agents and their current states. "
            "Returns agent IDs, names, types, and running status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "handler": _handle_agent_list_all,
        "category": "agents",
    },
    {
        "name": "agent_find_best",
        "description": (
            "Find the best agent profile for a set of required capability tags. "
            "Uses Jaccard similarity scoring across all specialist profiles. "
            "Useful for determining which agent type to create for a given task."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "required_tags": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required capability tags.",
                },
            },
            "required": ["required_tags"],
        },
        "handler": _handle_agent_find_best,
        "category": "agents",
    },
    {
        "name": "agent_profiles",
        "description": (
            "List all available specialist agent profiles with their capabilities, "
            "preferred tools, and behavioral parameters. Includes general, "
            "researcher, coder, planner, analyzer, orchestrator, and guardian profiles."
        ),
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": [],
        },
        "handler": _handle_agent_profiles,
        "category": "agents",
    },
]


# ---------------------------------------------------------------------------
# Registration entry-point
# ---------------------------------------------------------------------------


def register_phase5_tools(registry: Any) -> int:
    """Register all Phase 5 tools into the given SparkToolRegistry.

    Returns the number of tools registered.
    """
    from src.mcp.tools import SparkTool

    registered = 0
    for t in PHASE5_TOOLS:
        try:
            tool = SparkTool(
                name=t["name"],
                description=t["description"],
                input_schema=t["input_schema"],
                handler=t["handler"],
                category=t.get("category", "phase5"),
                version="5.0.0",
            )
            registry.register(tool)
            registered += 1
            logger.debug("Registered Phase 5 tool: %s", t["name"])
        except Exception as exc:
            logger.warning("Failed to register tool %s: %s", t["name"], exc)

    logger.info("Phase 5 tools registered: %d / %d", registered, len(PHASE5_TOOLS))
    return registered
