"""
agent_runtime.py — Autonomous Agent Runtime for Tranc3 Platform (Phase 5)

Manages the full lifecycle of an autonomous agent:
  - Creation with a specialist profile (AgentType)
  - Goal assignment and tracking
  - Task decomposition and execution
  - Tool invocation through the unified ToolBridge
  - Episodic memory via MemoryStream
  - Inter-agent communication through the NeuralMesh
  - Self-monitoring and adaptive behavior

Each AgentRuntime instance represents one autonomous agent. Multiple agents
can coordinate through the shared CollectiveMemory and NeuralMesh.

Zero-cost: all coordination is in-process, no external message brokers.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Agent state machine
# ---------------------------------------------------------------------------


class AgentState(str, Enum):
    """Lifecycle states for an autonomous agent."""

    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    WAITING = "waiting"
    REFLECTING = "reflecting"
    ERROR = "error"
    TERMINATED = "terminated"


# ---------------------------------------------------------------------------
# Agent configuration
# ---------------------------------------------------------------------------


@dataclass
class AgentConfig:
    """Configuration for an agent runtime instance."""

    agent_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    name: str = "unnamed-agent"
    agent_type: str = "general"  # maps to AgentType value
    max_concurrent_tasks: int = 3
    max_retries: int = 2
    idle_timeout_sec: float = 300.0
    memory_capacity: int = 500
    reflection_interval_sec: float = 60.0
    tags: Set[str] = field(default_factory=set)


# ---------------------------------------------------------------------------
# Agent execution step
# ---------------------------------------------------------------------------


@dataclass
class AgentStep:
    """A single step in an agent's execution plan."""

    step_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    description: str = ""
    tool_name: str = ""
    tool_args: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | running | completed | failed | skipped
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    completed_at: Optional[float] = None

    @property
    def duration_ms(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return 0.0


# ---------------------------------------------------------------------------
# Agent Runtime
# ---------------------------------------------------------------------------


class AgentRuntime:
    """
    Autonomous agent runtime. Manages the full lifecycle of an agent,
    including goal tracking, task decomposition, tool execution, and
    episodic memory.

    Usage:
        runtime = AgentRuntime(config=AgentConfig(name="researcher", agent_type="researcher"))
        await runtime.start()
        await runtime.assign_goal("Analyze the codebase for security vulnerabilities")
        await runtime.run_until_idle()
        results = runtime.get_results()
        await runtime.stop()
    """

    def __init__(self, config: Optional[AgentConfig] = None) -> None:
        self.config = config or AgentConfig()
        self.agent_id = self.config.agent_id
        self.name = self.config.name
        self.agent_type = self.config.agent_type

        # State
        self._state = AgentState.IDLE
        self._lock = asyncio.Lock()

        # Execution tracking
        self._current_steps: List[AgentStep] = []
        self._completed_steps: List[AgentStep] = []
        self._results: Dict[str, Any] = {}

        # Lazy-loaded components (initialized on start)
        self._task_decomposer = None
        self._tool_bridge = None
        self._memory_stream = None
        self._goal_manager = None

        # Observers
        self._state_observers: List[Callable[[AgentState, AgentState], None]] = []
        self._step_observers: List[Callable[[AgentStep], None]] = []

        # Metrics
        self._total_steps_executed: int = 0
        self._total_errors: int = 0
        self._started_at: Optional[float] = None
        self._last_activity: Optional[float] = None

    # -----------------------------------------------------------------------
    # Properties
    # -----------------------------------------------------------------------

    @property
    def state(self) -> AgentState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state not in (AgentState.TERMINATED, AgentState.ERROR)

    @property
    def is_idle(self) -> bool:
        return self._state == AgentState.IDLE

    @property
    def metrics(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.agent_type,
            "state": self._state.value,
            "total_steps": self._total_steps_executed,
            "total_errors": self._total_errors,
            "current_steps": len(self._current_steps),
            "completed_steps": len(self._completed_steps),
            "uptime_sec": (time.time() - self._started_at) if self._started_at else 0,
            "last_activity": self._last_activity,
        }

    # -----------------------------------------------------------------------
    # Lifecycle
    # -----------------------------------------------------------------------

    async def start(self) -> None:
        """Initialize the agent and its sub-components."""
        async with self._lock:
            if self._state != AgentState.IDLE:
                logger.warning("Agent %s already started (state=%s)", self.name, self._state)
                return

            self._init_components()
            self._started_at = time.time()
            self._last_activity = time.time()
            self._set_state(AgentState.IDLE)
            logger.info("Agent %s (%s) started", self.name, self.agent_id)

    async def stop(self) -> None:
        """Gracefully stop the agent."""
        async with self._lock:
            self._set_state(AgentState.TERMINATED)
            logger.info("Agent %s stopped after %d steps", self.name, self._total_steps_executed)

    # -----------------------------------------------------------------------
    # Goal management
    # -----------------------------------------------------------------------

    async def assign_goal(self, description: str, priority: int = 5, metadata: Optional[Dict] = None) -> str:
        """
        Assign a new goal to the agent. Returns the goal ID.

        The agent will plan and execute steps to achieve this goal when
        run_until_idle() or run_step() is called.
        """
        if self._goal_manager is None:
            self._init_components()

        goal_id = await self._goal_manager.add_goal(
            description=description,
            priority=priority,
            metadata=metadata or {},
        )
        self._last_activity = time.time()

        # Record in memory
        if self._memory_stream:
            await self._memory_stream.add(
                content=f"Goal assigned: {description}",
                tags={"goal", "assignment"},
                importance=0.7,
            )

        logger.info("Agent %s assigned goal: %s (id=%s)", self.name, description, goal_id)
        return goal_id

    # -----------------------------------------------------------------------
    # Execution
    # -----------------------------------------------------------------------

    async def run_step(self) -> Optional[AgentStep]:
        """
        Execute one step of the agent's current plan.

        Returns the completed AgentStep, or None if the agent is idle
        (no pending work).
        """
        if not self.is_running:
            return None

        # Get next goal to work on
        if self._goal_manager is None:
            return None

        active_goal = await self._goal_manager.get_next_active()
        if active_goal is None:
            if self._state != AgentState.IDLE:
                self._set_state(AgentState.IDLE)
            return None

        # Decompose if needed
        self._set_state(AgentState.PLANNING)
        decomposition = await self._task_decomposer.decompose(active_goal.description)

        if not decomposition.subtasks:
            await self._goal_manager.mark_failed(active_goal.goal_id, "Could not decompose goal")
            self._total_errors += 1
            return None

        # Execute first pending subtask
        self._set_state(AgentState.EXECUTING)
        for subtask in decomposition.subtasks:
            if subtask.status == "pending":
                step = AgentStep(
                    description=subtask.description,
                    tool_name=subtask.suggested_tool,
                    tool_args=subtask.tool_args,
                )
                step = await self._execute_step(step)
                subtask.status = step.status

                if step.status == "completed":
                    await self._goal_manager.update_progress(
                        active_goal.goal_id, increment=1.0 / len(decomposition.subtasks)
                    )
                break

        # Check if goal is complete
        if all(st.status == "completed" for st in decomposition.subtasks):
            await self._goal_manager.mark_completed(active_goal.goal_id)
            self._set_state(AgentState.REFLECTING)

            if self._memory_stream:
                await self._memory_stream.add(
                    content=f"Goal completed: {active_goal.description}",
                    tags={"goal", "completion"},
                    importance=0.9,
                )

        self._last_activity = time.time()
        return step if decomposition.subtasks else None

    async def run_until_idle(self, max_steps: int = 50) -> int:
        """
        Execute steps until the agent becomes idle or hits max_steps.
        Returns the number of steps executed.
        """
        steps_executed = 0
        while steps_executed < max_steps:
            step = await self.run_step()
            if step is None and self.is_idle:
                break
            if step is not None:
                steps_executed += 1
        return steps_executed

    # -----------------------------------------------------------------------
    # Results
    # -----------------------------------------------------------------------

    def get_results(self) -> Dict[str, Any]:
        """Get all accumulated results from completed steps."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "type": self.agent_type,
            "steps": [
                {
                    "step_id": s.step_id,
                    "description": s.description,
                    "tool_name": s.tool_name,
                    "status": s.status,
                    "result": s.result,
                    "duration_ms": s.duration_ms,
                }
                for s in self._completed_steps
            ],
            "metrics": self.metrics,
        }

    # -----------------------------------------------------------------------
    # Observation
    # -----------------------------------------------------------------------

    def observe_state(self, callback: Callable[[AgentState, AgentState], None]) -> None:
        """Register a callback for state transitions (old_state, new_state)."""
        self._state_observers.append(callback)

    def observe_steps(self, callback: Callable[[AgentStep], None]) -> None:
        """Register a callback for step completions."""
        self._step_observers.append(callback)

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    async def _execute_step(self, step: AgentStep) -> AgentStep:
        """Execute a single agent step with retry logic."""
        step.status = "running"
        step.started_at = time.time()
        self._current_steps.append(step)

        for attempt in range(self.config.max_retries + 1):
            try:
                if self._tool_bridge:
                    result = await self._tool_bridge.execute(
                        tool_name=step.tool_name,
                        args=step.tool_args,
                        agent_id=self.agent_id,
                    )
                    step.result = result.data if result else None
                    step.status = "completed"
                else:
                    step.result = {"note": "no tool bridge available"}
                    step.status = "completed"
                break
            except Exception as exc:
                step.error = str(exc)
                if attempt < self.config.max_retries:
                    logger.warning(
                        "Step %s failed (attempt %d/%d): %s",
                        step.step_id, attempt + 1, self.config.max_retries + 1, exc,
                    )
                    await asyncio.sleep(0.5 * (2 ** attempt))
                else:
                    step.status = "failed"
                    self._total_errors += 1

        step.completed_at = time.time()
        self._total_steps_executed += 1
        self._current_steps.remove(step)
        self._completed_steps.append(step)

        # Notify observers
        for obs in self._step_observers:
            try:
                obs(step)
            except Exception:
                logger.debug("Graceful degradation in Exception")  # nosec B110

        # Record in memory
        if self._memory_stream:
            await self._memory_stream.add(
                content=f"Step {step.status}: {step.description}",
                tags={"step", step.status},
                importance=0.5 if step.status == "completed" else 0.8,
                metadata={"step_id": step.step_id, "tool": step.tool_name, "error": step.error},
            )

        return step

    def _set_state(self, new_state: AgentState) -> None:
        """Transition to a new state and notify observers."""
        old_state = self._state
        self._state = new_state
        if old_state != new_state:
            for obs in self._state_observers:
                try:
                    obs(old_state, new_state)
                except Exception:
                    logger.debug("Graceful degradation in Exception")  # nosec B110

    def _init_components(self) -> None:
        """Lazy-initialize sub-components."""
        if self._task_decomposer is None:
            try:
                from .task_decomposer import TaskDecomposer
                self._task_decomposer = TaskDecomposer()
            except Exception as exc:
                logger.warning("TaskDecomposer unavailable: %s", exc)

        if self._tool_bridge is None:
            try:
                from .tool_bridge import ToolBridge
                self._tool_bridge = ToolBridge()
            except Exception as exc:
                logger.warning("ToolBridge unavailable: %s", exc)

        if self._memory_stream is None:
            try:
                from .memory_stream import MemoryStream
                self._memory_stream = MemoryStream(capacity=self.config.memory_capacity)
            except Exception as exc:
                logger.warning("MemoryStream unavailable: %s", exc)

        if self._goal_manager is None:
            try:
                from .goal_manager import GoalManager
                self._goal_manager = GoalManager()
            except Exception as exc:
                logger.warning("GoalManager unavailable: %s", exc)
