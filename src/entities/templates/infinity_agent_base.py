"""
InfinityAgent — Tier 4 Agent Base Template
===========================================
Base class for all Tier 4 Agents in the Trancendos platform.

Agents are mid-tier automation units — each location has an Alpha and a
Beta agent, each with a focused specialty. They execute under supervision
of their location's Tier 3 Lead AI, handling recurring automation workflows
that are above bot complexity but below AI autonomy.

Design principles:
  - Nanoflow: zero-cost, SQLite-backed micro-worker
  - Task queuing: async FIFO task intake with backpressure
  - Specialised: one agent, one domain (Alpha = primary, Beta = secondary)
  - Supervised: reports health + results upstream to Tranc3 Lead AI
  - Adaptive: EWMA latency tracking, retry logic with exponential backoff
  - Modular: plug-in task handlers registered by type
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DNA
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AgentDNA:
    """Immutable identity for a Tier 4 Agent."""

    sid: str  # e.g. "SID-NXS-01"
    location_pid: str  # parent location PID
    name: str
    role: str  # "alpha" | "beta"
    tier: int = 4
    strand_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __str__(self) -> str:
        return f"Agent[{self.name}:{self.role}@{self.location_pid}]"


# ---------------------------------------------------------------------------
# Task record
# ---------------------------------------------------------------------------


@dataclass
class AgentTask:
    """A single unit of work assigned to an agent."""

    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    task_type: str = ""
    payload: dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1 (highest) to 10 (lowest)
    enqueued_at: float = field(default_factory=time.monotonic)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    retries: int = 0
    max_retries: int = 3

    def latency_ms(self) -> float | None:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None

    def wait_ms(self) -> float:
        start = self.started_at or time.monotonic()
        return (start - self.enqueued_at) * 1000


# ---------------------------------------------------------------------------
# InfinityAgent base class
# ---------------------------------------------------------------------------


class InfinityAgent:
    """
    Tier 4 Agent — mid-tier automation unit for a Trancendos location.

    Sub-class and register task handlers via `register_handler()`.

    Example::

        class PathfinderAgent(InfinityAgent):
            def __init__(self):
                super().__init__(
                    sid="SID-NXS-01",
                    location_pid="PID-NXS",
                    name="Pathfinder",
                    role="alpha",
                )
                self.register_handler("route_discovery", self._handle_route)

            async def _handle_route(self, task: AgentTask) -> dict:
                return {"path": "...", "latency_ms": 12}
    """

    TIER = 4
    _QUEUE_MAXSIZE = 200

    def __init__(
        self,
        sid: str,
        location_pid: str,
        name: str,
        role: str,
    ) -> None:
        if role not in ("alpha", "beta"):
            raise ValueError(f"Agent role must be 'alpha' or 'beta' — got {role!r}")
        self.dna = AgentDNA(sid=sid, location_pid=location_pid, name=name, role=role)
        self._queue: asyncio.PriorityQueue[tuple[int, int, AgentTask]] = asyncio.PriorityQueue(maxsize=self._QUEUE_MAXSIZE)
        self._enqueue_counter: int = 0
        self._handlers: dict[str, Callable[[AgentTask], Coroutine[Any, Any, dict]]] = {}
        self._running = False
        self._task: asyncio.Task | None = None
        self._completed: list[AgentTask] = []
        self._failed: list[AgentTask] = []
        self._cycle_count = 0
        self._error_count = 0
        self._health_score: float = 1.0
        self._ewma_latency_ms: float = 0.0

        logger.info("%s initialised (tier=%d)", self.dna, self.TIER)

    # ------------------------------------------------------------------
    # Handler registry
    # ------------------------------------------------------------------

    def register_handler(
        self,
        task_type: str,
        handler: Callable[[AgentTask], Coroutine[Any, Any, dict]],
    ) -> None:
        """Register an async handler for a given task_type."""
        if not inspect.iscoroutinefunction(handler):
            raise TypeError(
                f"Handler for '{task_type}' must be an async function (coroutinefunction), "
                f"got {handler!r}"
            )
        self._handlers[task_type] = handler
        logger.debug("%s registered handler for '%s'", self.dna, task_type)

    # ------------------------------------------------------------------
    # Task intake
    # ------------------------------------------------------------------

    async def enqueue(
        self, task_type: str, payload: dict[str, Any], priority: int = 5
    ) -> AgentTask:
        """Enqueue a task for processing. Raises QueueFull if backlog is at capacity."""
        task = AgentTask(task_type=task_type, payload=payload, priority=priority)
        self._enqueue_counter += 1
        await self._queue.put((priority, self._enqueue_counter, task))
        return task

    def enqueue_nowait(
        self, task_type: str, payload: dict[str, Any], priority: int = 5
    ) -> AgentTask:
        """Enqueue without blocking. Raises QueueFull if at capacity."""
        task = AgentTask(task_type=task_type, payload=payload, priority=priority)
        self._enqueue_counter += 1
        self._queue.put_nowait((priority, self._enqueue_counter, task))
        return task

    # ------------------------------------------------------------------
    # Processing loop
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._process_loop(), name=f"agent_{self.dna.sid}")
        logger.info("%s started", self.dna)

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected — task was cancelled by us
        logger.info(
            "%s stopped (completed=%d, failed=%d)",
            self.dna,
            len(self._completed),
            len(self._failed),
        )

    async def _process_loop(self) -> None:
        while self._running:
            try:
                _, _, task = await asyncio.wait_for(self._queue.get(), timeout=5.0)
            except asyncio.TimeoutError:
                continue  # idle tick — no task dequeued
            except asyncio.CancelledError:
                # loop cancelled externally; exit cleanly without marking an item done
                break
            try:
                await self._execute(task)
                self._cycle_count += 1
            except Exception as exc:
                self._error_count += 1
                self._health_score = max(0.0, self._health_score - 0.05)
                logger.error("%s process loop error: %s", self.dna, exc)
            finally:
                self._queue.task_done()

    async def _execute(self, task: AgentTask) -> None:
        handler = self._handlers.get(task.task_type)
        if not handler:
            task.error = f"No handler for task_type '{task.task_type}'"
            task.completed_at = time.monotonic()
            self._failed.append(task)
            logger.warning("%s unknown task_type '%s'", self.dna, task.task_type)
            return

        task.started_at = time.monotonic()
        backoff = 1.0
        for attempt in range(task.max_retries + 1):
            try:
                result = await handler(task)
                task.result = result
                task.completed_at = time.monotonic()
                # EWMA latency update (α=0.3)
                lat = task.latency_ms() or 0.0
                self._ewma_latency_ms = 0.3 * lat + 0.7 * self._ewma_latency_ms
                self._health_score = min(1.0, self._health_score + 0.01)
                self._completed.append(task)
                return
            except Exception as exc:
                task.retries += 1
                task.error = str(exc)
                if attempt < task.max_retries:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2.0, 16.0)  # exponential backoff, cap 16s

        task.completed_at = time.monotonic()
        self._failed.append(task)
        self._error_count += 1
        self._health_score = max(0.0, self._health_score - 0.1)
        logger.error("%s task %s failed after %d retries", self.dna, task.task_id, task.max_retries)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "sid": self.dna.sid,
            "name": self.dna.name,
            "tier": self.TIER,
            "role": self.dna.role,
            "location_pid": self.dna.location_pid,
            "running": self._running,
            "health_score": round(self._health_score, 3),
            "queue_size": self._queue.qsize(),
            "cycle_count": self._cycle_count,
            "error_count": self._error_count,
            "completed_tasks": len(self._completed),
            "failed_tasks": len(self._failed),
            "ewma_latency_ms": round(self._ewma_latency_ms, 2),
            "registered_handlers": list(self._handlers.keys()),
        }

    def __repr__(self) -> str:
        return f"<InfinityAgent name={self.dna.name!r} tier={self.TIER} role={self.dna.role!r}>"
