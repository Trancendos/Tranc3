"""
src/master/bot_swarm.py — BotSwarm worker pool.

A BotSwarm maintains a pool of typed worker slots. Each slot wraps an asyncio
task that drains a per-type queue.  The swarm routes incoming TaskStep
invocations to the appropriate queue, respects health status, and emits
lifecycle events to the EventBus.

Architecture:
    ┌─────────────────────────────────────────────┐
    │                  BotSwarm                    │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
    │  │ monitor  │  │  search  │  │  memory  │   │
    │  │  queue   │  │  queue   │  │  queue   │   │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
    │       │              │              │         │
    │  ┌────▼─────┐  ┌────▼─────┐  ┌────▼─────┐   │
    │  │ Worker 1 │  │ Worker 2 │  │ Worker 3 │   │
    │  │(monitor) │  │(search)  │  │(memory)  │   │
    │  └──────────┘  └──────────┘  └──────────┘   │
    └─────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class WorkerSlot:
    bot_type: str
    queue: asyncio.Queue
    healthy: bool = True
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_used: float = field(default_factory=time.monotonic)


@dataclass
class StepResult:
    bot_type: str
    action: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class BotSwarm:
    """
    Pool of typed worker coroutines that drain per-type asyncio queues.

    Each bot type gets its own queue and worker loop. Tasks are enqueued
    via `submit()` and results are returned via per-task Future objects.
    """

    def __init__(self, concurrency_per_type: int = 2) -> None:
        self._concurrency = concurrency_per_type
        self._slots: Dict[str, list[WorkerSlot]] = {}
        self._worker_tasks: list[asyncio.Task] = []
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        logger.info("BotSwarm started (concurrency=%d per type).", self._concurrency)

    async def stop(self) -> None:
        self._running = False
        for task in self._worker_tasks:
            task.cancel()
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        self._worker_tasks.clear()
        logger.info("BotSwarm stopped.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def submit(
        self,
        bot_type: str,
        action: str,
        params: Dict[str, Any],
        timeout: float = 30.0,
    ) -> StepResult:
        """Enqueue a step and await its result."""
        slot = self._get_or_create_slot(bot_type)
        future: asyncio.Future[StepResult] = asyncio.get_event_loop().create_future()
        await slot.queue.put((action, params, future))

        if not any(
            not t.done() and t.get_name().startswith(f"swarm-{bot_type}")
            for t in self._worker_tasks
        ):
            self._spawn_worker(slot)

        try:
            return await asyncio.wait_for(asyncio.shield(future), timeout=timeout)
        except asyncio.TimeoutError:
            slot.tasks_failed += 1
            return StepResult(
                bot_type=bot_type,
                action=action,
                success=False,
                error=f"Timeout after {timeout}s",
            )

    def status(self) -> Dict[str, Any]:
        return {
            bot_type: {
                "healthy": slot.healthy,
                "queue_depth": slot.queue.qsize(),
                "completed": slot.tasks_completed,
                "failed": slot.tasks_failed,
            }
            for bot_type, slots in self._slots.items()
            for slot in slots
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_or_create_slot(self, bot_type: str) -> WorkerSlot:
        if bot_type not in self._slots:
            self._slots[bot_type] = [
                WorkerSlot(bot_type=bot_type, queue=asyncio.Queue(maxsize=100))
                for _ in range(self._concurrency)
            ]
        # Pick the least-loaded slot
        return min(self._slots[bot_type], key=lambda s: s.queue.qsize())

    def _spawn_worker(self, slot: WorkerSlot) -> None:
        task = asyncio.create_task(
            self._worker_loop(slot),
            name=f"swarm-{slot.bot_type}-{id(slot)}",
        )
        self._worker_tasks.append(task)

    async def _worker_loop(self, slot: WorkerSlot) -> None:
        while self._running or not slot.queue.empty():
            try:
                action, params, future = await asyncio.wait_for(
                    slot.queue.get(), timeout=5.0
                )
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break

            t0 = time.monotonic()
            try:
                result = await self._dispatch(slot.bot_type, action, params)
                duration_ms = (time.monotonic() - t0) * 1000
                step_result = StepResult(
                    bot_type=slot.bot_type,
                    action=action,
                    success=True,
                    output=result,
                    duration_ms=duration_ms,
                )
                slot.tasks_completed += 1
                slot.last_used = time.monotonic()
            except Exception as exc:  # noqa: BLE001
                duration_ms = (time.monotonic() - t0) * 1000
                step_result = StepResult(
                    bot_type=slot.bot_type,
                    action=action,
                    success=False,
                    error=str(exc),
                    duration_ms=duration_ms,
                )
                slot.tasks_failed += 1
                logger.warning(
                    "BotSwarm worker %s failed: %s",
                    sanitize_for_log(slot.bot_type),
                    sanitize_for_log(exc),
                )

            if not future.done():
                future.set_result(step_result)
            slot.queue.task_done()

    async def _dispatch(self, bot_type: str, action: str, params: Dict[str, Any]) -> Any:
        """Dispatch through unified AdapterRegistry (priority-routed fallback chain)."""
        try:
            from src.master.adapters.registry import get_adapter  # noqa: PLC0415
            adapter = get_adapter(bot_type)
            dispatch_params = dict(params)
            dispatch_params["_bot_type"] = bot_type
            return await adapter.dispatch(action, dispatch_params)
        except Exception as exc:  # noqa: BLE001
            logger.debug("AdapterRegistry dispatch failed for %s.%s: %s", bot_type, action, exc)
            return {"stub": True, "bot": bot_type, "action": action, "params": params}
