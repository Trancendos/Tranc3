"""
goal_manager.py — Multi-Goal Tracking & Prioritization for Tranc3 Platform (Phase 5)

Manages an agent's goals through their full lifecycle:
  - Creation with priority, metadata, and deadline
  - Progress tracking with incremental updates
  - State transitions: PENDING → ACTIVE → COMPLETED / FAILED / CANCELLED
  - Priority-based ordering for selecting the next goal to work on
  - Deadline enforcement with automatic escalation of overdue goals
  - Goal dependency tracking (prerequisite goals)

The GoalManager is per-agent: each AgentRuntime owns its own GoalManager
instance. For inter-agent goal coordination, use the CollectiveMemory
and NeuralMesh to propagate status updates.

Zero-cost: pure Python, no external dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Goal state machine
# ---------------------------------------------------------------------------


class GoalState(str, Enum):
    """Lifecycle states for a goal."""

    PENDING = "pending"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------------------
# Goal data model
# ---------------------------------------------------------------------------


@dataclass
class Goal:
    """
    Represents a single goal that an agent is working towards.

    Goals have:
      - A human-readable description of the desired outcome
      - A priority (1–10, higher = more important)
      - A progress value (0.0–1.0)
      - Optional deadline for time-sensitive tasks
      - Optional prerequisite goal IDs that must complete first
      - Arbitrary metadata for domain-specific context
    """

    goal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    description: str = ""
    priority: int = 5
    state: GoalState = GoalState.PENDING
    progress: float = 0.0
    deadline: Optional[float] = None
    prerequisites: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    error: Optional[str] = None

    @property
    def is_overdue(self) -> bool:
        """Check if the goal has passed its deadline."""
        if self.deadline is None:
            return False
        return time.time() > self.deadline and self.state not in (
            GoalState.COMPLETED,
            GoalState.CANCELLED,
        )

    @property
    def is_terminal(self) -> bool:
        """Check if the goal is in a terminal state."""
        return self.state in (GoalState.COMPLETED, GoalState.FAILED, GoalState.CANCELLED)

    @property
    def effective_priority(self) -> float:
        """
        Compute effective priority considering deadline urgency.
        Overdue goals get a boost. Goals closer to deadline get a gradual boost.
        """
        base = float(self.priority)
        if self.deadline is not None and not self.is_terminal:
            remaining = self.deadline - time.time()
            if remaining <= 0:
                base += 5.0  # urgent: overdue
            elif remaining < 60:
                base += 3.0  # very close
            elif remaining < 300:
                base += 1.5  # approaching
        return base

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the goal to a plain dict."""
        return {
            "goal_id": self.goal_id,
            "description": self.description,
            "priority": self.priority,
            "effective_priority": round(self.effective_priority, 2),
            "state": self.state.value,
            "progress": round(self.progress, 4),
            "deadline": self.deadline,
            "prerequisites": sorted(self.prerequisites),
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "completed_at": self.completed_at,
            "is_overdue": self.is_overdue,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# Goal Manager
# ---------------------------------------------------------------------------


class GoalManager:
    """
    Manages an agent's goals with priority-based selection and state tracking.

    Usage:
        gm = GoalManager()
        goal_id = await gm.add_goal("Analyze codebase", priority=7)
        await gm.mark_active(goal_id)
        await gm.update_progress(goal_id, increment=0.3)
        await gm.mark_completed(goal_id)
        next_goal = await gm.get_next_active()
    """

    def __init__(self, max_goals: int = 100) -> None:
        self._goals: Dict[str, Goal] = {}
        self._max_goals = max_goals
        self._lock = asyncio.Lock()

    # -------------------------------------------------------------------
    # Goal CRUD
    # -------------------------------------------------------------------

    async def add_goal(
        self,
        description: str,
        priority: int = 5,
        deadline: Optional[float] = None,
        prerequisites: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Add a new goal. Returns the goal ID.

        If the goal count exceeds max_goals, the lowest-priority terminal
        goals are evicted first.
        """
        async with self._lock:
            goal = Goal(
                description=description,
                priority=max(1, min(10, priority)),
                deadline=deadline,
                prerequisites=prerequisites or set(),
                metadata=metadata or {},
            )
            self._goals[goal.goal_id] = goal

            # Evict if over capacity
            while len(self._goals) > self._max_goals:
                self._evict_one()

            logger.debug(
                "Goal added: %s (id=%s, priority=%d)",
                description,
                goal.goal_id,
                priority,
            )
            return goal.goal_id
        return None

    async def get_goal(self, goal_id: str) -> Optional[Goal]:
        """Retrieve a goal by ID."""
        return self._goals.get(goal_id)

    async def remove_goal(self, goal_id: str) -> bool:
        """Remove a goal. Returns True if found and removed."""
        async with self._lock:
            if goal_id in self._goals:
                del self._goals[goal_id]
                return True
            return False
        return None

    # -------------------------------------------------------------------
    # State transitions
    # -------------------------------------------------------------------

    async def mark_active(self, goal_id: str) -> bool:
        """Transition a goal from PENDING to ACTIVE."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.state != GoalState.PENDING:
                return False
            goal.state = GoalState.ACTIVE
            goal.updated_at = time.time()
            logger.debug("Goal activated: %s", goal_id)
            return True
        return None

    async def mark_completed(self, goal_id: str) -> bool:
        """Transition a goal to COMPLETED."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.is_terminal:
                return False
            goal.state = GoalState.COMPLETED
            goal.progress = 1.0
            goal.completed_at = time.time()
            goal.updated_at = time.time()
            logger.info("Goal completed: %s (%s)", goal.description, goal_id)
            return True
        return None

    async def mark_failed(self, goal_id: str, error: str = "") -> bool:
        """Transition a goal to FAILED."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.is_terminal:
                return False
            goal.state = GoalState.FAILED
            goal.error = error
            goal.updated_at = time.time()
            logger.warning("Goal failed: %s (%s) — %s", goal.description, goal_id, error)
            return True
        return None

    async def mark_cancelled(self, goal_id: str, reason: str = "") -> bool:
        """Transition a goal to CANCELLED."""
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None or goal.is_terminal:
                return False
            goal.state = GoalState.CANCELLED
            goal.error = reason
            goal.updated_at = time.time()
            logger.info("Goal cancelled: %s (%s) — %s", goal.description, goal_id, reason)
            return True
        return None

    # -------------------------------------------------------------------
    # Progress tracking
    # -------------------------------------------------------------------

    async def update_progress(
        self,
        goal_id: str,
        increment: float = 0.0,
        absolute: Optional[float] = None,
    ) -> bool:
        """
        Update a goal's progress. Use increment for relative updates or
        absolute to set a specific value. Progress is clamped to [0.0, 1.0].
        """
        async with self._lock:
            goal = self._goals.get(goal_id)
            if goal is None:
                return False

            if absolute is not None:
                goal.progress = max(0.0, min(1.0, absolute))
            else:
                goal.progress = max(0.0, min(1.0, goal.progress + increment))

            # Auto-transition PENDING → ACTIVE on first progress
            if goal.state == GoalState.PENDING and goal.progress > 0.0:
                goal.state = GoalState.ACTIVE

            # Auto-complete at 100%
            if goal.progress >= 1.0 and goal.state == GoalState.ACTIVE:
                goal.state = GoalState.COMPLETED
                goal.completed_at = time.time()

            goal.updated_at = time.time()
            return True
        return None

    # -------------------------------------------------------------------
    # Goal selection
    # -------------------------------------------------------------------

    async def get_next_active(self) -> Optional[Goal]:
        """
        Get the highest-priority goal that is ready to be worked on.

        Selection criteria (in order):
        1. Goal must be PENDING or ACTIVE (not terminal)
        2. All prerequisite goals must be COMPLETED
        3. Highest effective_priority wins
        4. Ties broken by creation time (oldest first)
        """
        async with self._lock:
            candidates = []
            for goal in self._goals.values():
                if goal.is_terminal:
                    continue
                if not self._prerequisites_met(goal):
                    continue
                candidates.append(goal)

            if not candidates:
                return None

            # Sort by effective_priority (desc), then created_at (asc)
            candidates.sort(key=lambda g: (-g.effective_priority, g.created_at))
            return candidates[0]

    async def get_active_goals(self) -> List[Goal]:
        """Return all goals that are currently ACTIVE, sorted by priority."""
        async with self._lock:
            active = [g for g in self._goals.values() if g.state == GoalState.ACTIVE]
            active.sort(key=lambda g: -g.effective_priority)
            return active
        return None

    async def get_pending_goals(self) -> List[Goal]:
        """Return all PENDING goals, sorted by priority."""
        async with self._lock:
            pending = [g for g in self._goals.values() if g.state == GoalState.PENDING]
            pending.sort(key=lambda g: -g.effective_priority)
            return pending
        return None

    # -------------------------------------------------------------------
    # Queries
    # -------------------------------------------------------------------

    async def get_overdue_goals(self) -> List[Goal]:
        """Return all overdue goals."""
        async with self._lock:
            return [g for g in self._goals.values() if g.is_overdue]
        return None

    async def get_goal_summary(self) -> Dict[str, Any]:
        """Return a summary of all goals by state."""
        async with self._lock:
            by_state: Dict[str, int] = {}
            for state in GoalState:  # codeql[py/non-iterable-in-for-loop] – Enum is iterable
                by_state[state.value] = 0
            for goal in self._goals.values():
                by_state[goal.state.value] += 1

            return {
                "total": len(self._goals),
                "by_state": by_state,
                "overdue": sum(1 for g in self._goals.values() if g.is_overdue),
                "avg_progress": (
                    sum(g.progress for g in self._goals.values()) / len(self._goals)
                    if self._goals
                    else 0.0
                ),
            }
        return None

    async def get_all_goals(self) -> List[Dict[str, Any]]:
        """Return serialized representations of all goals."""
        async with self._lock:
            return [g.to_dict() for g in self._goals.values()]
        return None

    # -------------------------------------------------------------------
    # Internal
    # -------------------------------------------------------------------

    def _prerequisites_met(self, goal: Goal) -> bool:
        """Check if all prerequisite goals are completed."""
        if not goal.prerequisites:
            return True
        for prereq_id in goal.prerequisites:
            prereq = self._goals.get(prereq_id)
            if prereq is None or prereq.state != GoalState.COMPLETED:
                return False
        return True

    def _evict_one(self) -> None:
        """Evict the lowest-priority terminal goal. If none, evict the lowest-priority pending goal."""
        # First try to evict terminal goals (completed, failed, cancelled)
        terminal = [g for g in self._goals.values() if g.is_terminal]
        if terminal:
            victim = min(terminal, key=lambda g: g.priority)
            del self._goals[victim.goal_id]
            logger.debug("Evicted terminal goal: %s", victim.goal_id)
            return

        # Fall back to lowest-priority pending goal
        pending = [g for g in self._goals.values() if g.state == GoalState.PENDING]
        if pending:
            victim = min(pending, key=lambda g: g.priority)
            del self._goals[victim.goal_id]
            logger.debug("Evicted pending goal: %s", victim.goal_id)
