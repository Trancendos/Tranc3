"""
src/workflow/nodes/agents.py — Phase 5 autonomous agent nodes for The Digital Grid.

Covers: AgentCreateNode, AgentRunStepNode, AgentGoalNode, AgentReflectNode, AgentDecomposeNode.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _agent_runtime_cls():
    try:
        from src.agents.agent_runtime import AgentRuntime

        return AgentRuntime
    except Exception as exc:
        logger.warning("AgentRuntime unavailable: %s", exc)
        return None


def _get_agent_registry():
    try:
        from src.mcp.spark_phase5_tools import _agents

        return _agents
    except Exception:
        return {}


def _get_cfg(config: Any) -> Dict[str, Any]:
    if isinstance(config, dict):
        return config
    return getattr(config, "config", {})


def _get_node_id(config: Any) -> str:
    if isinstance(config, dict):
        return config.get("id", "unknown")
    return getattr(config, "id", "unknown")


class AgentCreateNode:
    """Creates a new autonomous agent within a workflow step."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AgentCreateNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = _get_cfg(self.config)
        name = cfg.get("name", inputs.get("name", "workflow-agent"))
        agent_type = cfg.get("agent_type", inputs.get("agent_type", "general"))
        max_concurrent = int(cfg.get("max_concurrent_tasks", 3))
        memory_cap = int(cfg.get("memory_capacity", 500))

        AgentRuntime = _agent_runtime_cls()
        if AgentRuntime is None:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error="AgentRuntime unavailable",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        from src.agents.agent_runtime import AgentConfig

        agent_cfg = AgentConfig(
            name=name,
            agent_type=agent_type,
            max_concurrent_tasks=max_concurrent,
            memory_capacity=memory_cap,
        )
        runtime = AgentRuntime(config=agent_cfg)
        await runtime.start()

        agent_registry = _get_agent_registry()
        agent_registry[runtime.agent_id] = runtime

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
            duration_ms=(time.monotonic() - t0) * 1000,
            metadata={"node_type": "AGENT_CREATE"},
        )


class AgentRunStepNode:
    """Executes one step of an agent's execution plan."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AgentRunStepNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = _get_cfg(self.config)
        agent_id = cfg.get("agent_id", inputs.get("agent_id", ""))
        max_steps = int(cfg.get("max_steps", inputs.get("max_steps", 1)))

        runtime = _get_agent_registry().get(agent_id)
        if runtime is None:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error=f"Agent '{agent_id}' not found",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        steps_executed = await runtime.run_until_idle(max_steps=max_steps)
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
            duration_ms=(time.monotonic() - t0) * 1000,
            metadata={"node_type": "AGENT_RUN_STEP"},
        )


class AgentGoalNode:
    """Assigns a goal to an agent within a workflow."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AgentGoalNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = _get_cfg(self.config)
        agent_id = cfg.get("agent_id", inputs.get("agent_id", ""))
        description = cfg.get("description", inputs.get("description", ""))
        priority = int(cfg.get("priority", inputs.get("priority", 5)))

        runtime = _get_agent_registry().get(agent_id)
        if runtime is None:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error=f"Agent '{agent_id}' not found",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        if not description:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error="Goal description is required",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        goal_id = await runtime.assign_goal(description=description, priority=priority)
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
            duration_ms=(time.monotonic() - t0) * 1000,
            metadata={"node_type": "AGENT_GOAL"},
        )


class AgentReflectNode:
    """Triggers an agent's reflection cycle over its episodic memories."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AgentReflectNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = _get_cfg(self.config)
        agent_id = cfg.get("agent_id", inputs.get("agent_id", ""))
        top_k = int(cfg.get("top_k", inputs.get("top_k", 20)))

        runtime = _get_agent_registry().get(agent_id)
        if runtime is None:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error=f"Agent '{agent_id}' not found",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        if runtime._memory_stream is None:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=True,
                output={"reflections": [], "total": 0},
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        reflections = await runtime._memory_stream.reflect(top_k=top_k)
        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output={
                "agent_id": runtime.agent_id,
                "reflections": reflections,
                "total": len(reflections),
            },
            error=None,
            duration_ms=(time.monotonic() - t0) * 1000,
            metadata={"node_type": "AGENT_REFLECT"},
        )


class AgentDecomposeNode:
    """Decomposes a task description into an ordered list of subtasks."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AgentDecomposeNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = _get_cfg(self.config)
        goal_description = cfg.get("goal_description", inputs.get("goal_description", ""))

        if not goal_description:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error="goal_description is required",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        try:
            from src.agents.task_decomposer import TaskDecomposer

            decomposer = TaskDecomposer()
            decomposition = await decomposer.decompose(goal_description)
        except Exception as exc:
            return NodeResult(
                node_id=_get_node_id(self.config),
                success=False,
                output=None,
                error=f"TaskDecomposer failed: {exc}",
                duration_ms=(time.monotonic() - t0) * 1000,
            )

        return NodeResult(
            node_id=_get_node_id(self.config),
            success=True,
            output=decomposition.to_dict(),
            error=None,
            duration_ms=(time.monotonic() - t0) * 1000,
            metadata={
                "node_type": "AGENT_DECOMPOSE",
                "strategy": decomposition.strategy,
                "subtask_count": len(decomposition.subtasks),
            },
        )


__all__ = [
    "AgentCreateNode",
    "AgentRunStepNode",
    "AgentGoalNode",
    "AgentReflectNode",
    "AgentDecomposeNode",
]
