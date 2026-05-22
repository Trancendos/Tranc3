"""
phase5_nodes.py — Phase 5 Autonomous Agent workflow nodes for The Digital Grid.

Adds 5 new node types that expose Phase 5 agent orchestration capabilities
as first-class workflow steps in the DAG executor:

  AGENT_CREATE      — create a new autonomous agent
  AGENT_RUN_STEP    — execute one step of an agent's plan
  AGENT_GOAL        — assign a goal to an agent
  AGENT_REFLECT     — trigger an agent's reflection cycle
  AGENT_DECOMPOSE   — decompose a task into subtasks

Each node follows the BaseNode contract: async execute(inputs, context) → NodeResult.
All Phase 5 components are imported lazily; the workflow executor starts cleanly
even if optional dependencies are absent.

Integration:
    Import register_phase5_nodes() and call it once at startup, or import
    and call extend_node_registry() to patch the existing NODE_REGISTRY dict.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy component accessors
# ---------------------------------------------------------------------------


def _agent_runtime_cls():
    """Lazy-import AgentRuntime class."""
    try:
        from src.agents.agent_runtime import AgentRuntime
        return AgentRuntime
    except Exception as exc:
        logger.warning("AgentRuntime unavailable: %s", exc)
        return None


def _get_agent_registry():
    """Get the shared agent registry from spark_phase5_tools."""
    try:
        from src.mcp.spark_phase5_tools import _agents  # codeql[py/cyclic-import]
        return _agents
    except Exception:
        return {}


# ---------------------------------------------------------------------------
# Phase 5 Node Types (string-keyed for compatibility with _PHASE4_NODE_REGISTRY pattern)
# ---------------------------------------------------------------------------

PHASE5_NODE_TYPES: Dict[str, Any] = {}


def _get_cfg(config: Any) -> Dict[str, Any]:
    """Extract the config dict from either a NodeConfig or a plain dict."""
    if isinstance(config, dict):
        return config
    return getattr(config, "config", {})


def _get_node_id(config: Any) -> str:
    """Extract the node id from either a NodeConfig or a plain dict."""
    if isinstance(config, dict):
        return config.get("id", "unknown")
    return getattr(config, "id", "unknown")


# ---------------------------------------------------------------------------
# Agent Create Node
# ---------------------------------------------------------------------------


class AgentCreateNode:
    """Creates a new autonomous agent within a workflow step."""

    def __init__(self, config: Any) -> None:
        self.config = config
        _cid = getattr(config, "id", "agent-create")
        self.logger = logging.getLogger(f"{__name__}.AgentCreateNode.{_cid}")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult  # codeql[py/cyclic-import]
        t0 = time.monotonic()
        cfg = _get_cfg(self.config)

        name = cfg.get("name", inputs.get("name", "workflow-agent"))
        agent_type = cfg.get("agent_type", inputs.get("agent_type", "general"))
        max_concurrent = int(cfg.get("max_concurrent_tasks", 3))
        memory_cap = int(cfg.get("memory_capacity", 500))

        AgentRuntime = _agent_runtime_cls()
        if AgentRuntime is None:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error="AgentRuntime unavailable", duration_ms=duration_ms,
            )

        from src.agents.agent_runtime import AgentConfig
        config = AgentConfig(
            name=name,
            agent_type=agent_type,
            max_concurrent_tasks=max_concurrent,
            memory_capacity=memory_cap,
        )
        runtime = AgentRuntime(config=config)
        await runtime.start()

        # Register in shared registry
        agent_registry = _get_agent_registry()
        agent_registry[runtime.agent_id] = runtime

        duration_ms = (time.monotonic() - t0) * 1000
        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output={
                "agent_id": runtime.agent_id,
                "name": runtime.name,
                "agent_type": runtime.agent_type,
                "state": runtime.state.value,
            },
            error=None,
            duration_ms=duration_ms,
            metadata={"node_type": "AGENT_CREATE"},
        )


PHASE5_NODE_TYPES["AGENT_CREATE"] = AgentCreateNode


# ---------------------------------------------------------------------------
# Agent Run Step Node
# ---------------------------------------------------------------------------


class AgentRunStepNode:
    """Executes one step of an agent's execution plan."""

    def __init__(self, config: Any) -> None:
        self.config = config
        _cid = getattr(config, "id", "agent-run-step")
        self.logger = logging.getLogger(f"{__name__}.AgentRunStepNode.{_cid}")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult  # codeql[py/cyclic-import]
        t0 = time.monotonic()
        cfg = _get_cfg(self.config)

        agent_id = cfg.get("agent_id", inputs.get("agent_id", ""))
        max_steps = int(cfg.get("max_steps", inputs.get("max_steps", 1)))

        agent_registry = _get_agent_registry()
        runtime = agent_registry.get(agent_id)
        if runtime is None:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error=f"Agent '{agent_id}' not found", duration_ms=duration_ms,
            )

        steps_executed = await runtime.run_until_idle(max_steps=max_steps)

        duration_ms = (time.monotonic() - t0) * 1000
        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output={
                "agent_id": runtime.agent_id,
                "steps_executed": steps_executed,
                "state": runtime.state.value,
                "metrics": runtime.metrics,
            },
            error=None,
            duration_ms=duration_ms,
            metadata={"node_type": "AGENT_RUN_STEP"},
        )


PHASE5_NODE_TYPES["AGENT_RUN_STEP"] = AgentRunStepNode


# ---------------------------------------------------------------------------
# Agent Goal Node
# ---------------------------------------------------------------------------


class AgentGoalNode:
    """Assigns a goal to an agent within a workflow."""

    def __init__(self, config: Any) -> None:
        self.config = config
        _cid = getattr(config, "id", "agent-goal")
        self.logger = logging.getLogger(f"{__name__}.AgentGoalNode.{_cid}")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult  # codeql[py/cyclic-import]
        t0 = time.monotonic()
        cfg = _get_cfg(self.config)

        agent_id = cfg.get("agent_id", inputs.get("agent_id", ""))
        description = cfg.get("description", inputs.get("description", ""))
        priority = int(cfg.get("priority", inputs.get("priority", 5)))

        agent_registry = _get_agent_registry()
        runtime = agent_registry.get(agent_id)
        if runtime is None:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error=f"Agent '{agent_id}' not found", duration_ms=duration_ms,
            )

        if not description:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error="Goal description is required", duration_ms=duration_ms,
            )

        goal_id = await runtime.assign_goal(description=description, priority=priority)

        duration_ms = (time.monotonic() - t0) * 1000
        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output={
                "agent_id": runtime.agent_id,
                "goal_id": goal_id,
                "description": description,
                "priority": priority,
            },
            error=None,
            duration_ms=duration_ms,
            metadata={"node_type": "AGENT_GOAL"},
        )


PHASE5_NODE_TYPES["AGENT_GOAL"] = AgentGoalNode


# ---------------------------------------------------------------------------
# Agent Reflect Node
# ---------------------------------------------------------------------------


class AgentReflectNode:
    """Triggers an agent's reflection cycle over its episodic memories."""

    def __init__(self, config: Any) -> None:
        self.config = config
        _cid = getattr(config, "id", "agent-reflect")
        self.logger = logging.getLogger(f"{__name__}.AgentReflectNode.{_cid}")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult  # codeql[py/cyclic-import]
        t0 = time.monotonic()
        cfg = _get_cfg(self.config)

        agent_id = cfg.get("agent_id", inputs.get("agent_id", ""))
        top_k = int(cfg.get("top_k", inputs.get("top_k", 20)))

        agent_registry = _get_agent_registry()
        runtime = agent_registry.get(agent_id)
        if runtime is None:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error=f"Agent '{agent_id}' not found", duration_ms=duration_ms,
            )

        if runtime._memory_stream is None:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=True,
                output={"reflections": [], "total": 0},
                error=None,
                duration_ms=duration_ms,
            )

        reflections = await runtime._memory_stream.reflect(top_k=top_k)

        duration_ms = (time.monotonic() - t0) * 1000
        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output={
                "agent_id": runtime.agent_id,
                "reflections": reflections,
                "total": len(reflections),
            },
            error=None,
            duration_ms=duration_ms,
            metadata={"node_type": "AGENT_REFLECT"},
        )


PHASE5_NODE_TYPES["AGENT_REFLECT"] = AgentReflectNode


# ---------------------------------------------------------------------------
# Agent Decompose Node
# ---------------------------------------------------------------------------


class AgentDecomposeNode:
    """Decomposes a task description into an ordered list of subtasks."""

    def __init__(self, config: Any) -> None:
        self.config = config
        _cid = getattr(config, "id", "agent-decompose")
        self.logger = logging.getLogger(f"{__name__}.AgentDecomposeNode.{_cid}")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult  # codeql[py/cyclic-import]
        t0 = time.monotonic()
        cfg = _get_cfg(self.config)

        goal_description = cfg.get("goal_description", inputs.get("goal_description", ""))
        if not goal_description:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error="goal_description is required", duration_ms=duration_ms,
            )

        try:
            from src.agents.task_decomposer import TaskDecomposer
            decomposer = TaskDecomposer()
            decomposition = await decomposer.decompose(goal_description)
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return NodeResult(
                node_id=_get_node_id(self.config), success=False, output=None,
                error=f"TaskDecomposer failed: {exc}", duration_ms=duration_ms,
            )

        duration_ms = (time.monotonic() - t0) * 1000
        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output=decomposition.to_dict(),
            error=None,
            duration_ms=duration_ms,
            metadata={
                "node_type": "AGENT_DECOMPOSE",
                "strategy": decomposition.strategy,
                "subtask_count": len(decomposition.subtasks),
            },
        )


PHASE5_NODE_TYPES["AGENT_DECOMPOSE"] = AgentDecomposeNode


# ---------------------------------------------------------------------------
# Registration helper
# ---------------------------------------------------------------------------


def extend_node_registry(registry: Dict[str, Any]) -> int:
    """Add Phase 5 node types to an existing node registry dict.

    Returns the number of node types added.
    """
    count = 0
    for key, cls in PHASE5_NODE_TYPES.items():
        if key not in registry:
            registry[key] = cls
            count += 1
            logger.debug("Registered Phase 5 node type: %s", key)
    logger.info("Phase 5 workflow nodes: %d types registered", count)
    return count


def register_phase5_nodes() -> int:
    """Convenience: register Phase 5 nodes into the global _PHASE4_NODE_REGISTRY."""
    # Phase 4's registry is stored in nodes.py as _PHASE4_NODE_REGISTRY
    # We'll also update it directly
    try:
        from src.workflow.nodes import _PHASE4_NODE_REGISTRY  # codeql[py/cyclic-import]
        return extend_node_registry(_PHASE4_NODE_REGISTRY)
    except Exception as exc:
        logger.warning("Could not register Phase 5 nodes: %s", exc)
        return 0
