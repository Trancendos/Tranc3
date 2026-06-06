"""
Bulkhead Pattern — Failure Isolation
=====================================
Isolates failures by limiting concurrent executions with a queue.
Prevents one failing service from consuming all resources.

Ported from: @trancendos/kernel resilience/bulkhead.ts (infinity-adminOS)
Zero-cost: Pure Python asyncio. No external dependencies.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


class BulkheadFullError(Exception):
    """Raised when the bulkhead queue is full and cannot accept more requests."""

    def __init__(self, message: str, active: int, queue_size: int) -> None:
        super().__init__(message)
        self.active = active
        self.queue_size = queue_size


class BulkheadTimeoutError(Exception):
    """Raised when a queued request times out waiting for execution slot."""

    def __init__(self, message: str, waited_s: float) -> None:
        super().__init__(message)
        self.waited_s = waited_s


@dataclass
class BulkheadMetrics:
    name: str
    active_count: int
    queue_size: int
    total_executions: int
    total_rejections: int
    total_timeouts: int
    avg_execution_time: float  # seconds


class Bulkhead:
    """
    Bulkhead isolation pattern.

    Limits concurrent executions to ``max_concurrent``.  Excess requests are
    queued up to ``max_queue``; if the queue is also full the request is
    rejected immediately.  Queued requests that have not started within
    ``queue_timeout`` seconds are cancelled with :class:`BulkheadTimeoutError`.
    """

    def __init__(
        self,
        name: str,
        max_concurrent: int = 10,
        max_queue: int = 100,
        queue_timeout: float = 5.0,
    ) -> None:
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_queue = max_queue
        self.queue_timeout = queue_timeout

        self._semaphore: asyncio.Semaphore | None = None
        self._active_count = 0
        self._queue_size = 0
        self._total_executions = 0
        self._total_rejections = 0
        self._total_timeouts = 0
        self._total_execution_time = 0.0

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    async def execute(self, coro: "Awaitable[Any] | Callable[[], Awaitable[Any]]") -> Any:
        """
        Execute *coro* within the bulkhead.

        *coro* may be either a pre-built coroutine/awaitable or a zero-argument
        async callable (factory).  Both forms are supported for convenience.

        Raises:
            BulkheadFullError: if both the execution slots and queue are full.
            BulkheadTimeoutError: if the request waited too long in the queue.
        """
        sem = self._get_semaphore()

        # Check capacity synchronously before queuing
        will_queue = self._active_count >= self.max_concurrent
        if will_queue:
            if self._queue_size >= self.max_queue:
                self._total_rejections += 1
                raise BulkheadFullError(
                    f"Bulkhead '{self.name}' is full — "
                    f"active={self._active_count}/{self.max_concurrent}, "
                    f"queue={self._queue_size}/{self.max_queue}",
                    active=self._active_count,
                    queue_size=self._queue_size,
                )
            self._queue_size += 1

        queued_at = time.monotonic()
        try:
            await asyncio.wait_for(sem.acquire(), timeout=self.queue_timeout)
        except asyncio.TimeoutError:
            if will_queue:
                self._queue_size = max(0, self._queue_size - 1)
            self._total_timeouts += 1
            waited = time.monotonic() - queued_at
            raise BulkheadTimeoutError(
                f"Bulkhead '{self.name}' queue timeout after {waited:.2f}s",
                waited_s=waited,
            ) from None

        if will_queue:
            self._queue_size = max(0, self._queue_size - 1)
        self._active_count += 1
        self._total_executions += 1

        start = time.monotonic()
        try:
            # Accept either a coroutine/awaitable or a callable factory
            if callable(coro) and not asyncio.iscoroutine(coro):
                result = await coro()
            else:
                result = await coro  # type: ignore[misc]
            return result
        finally:
            duration = time.monotonic() - start
            sem.release()
            self._active_count = max(0, self._active_count - 1)
            self._total_execution_time += duration

    def get_metrics(self) -> BulkheadMetrics:
        """Return a snapshot of current bulkhead metrics."""
        avg = (
            self._total_execution_time / self._total_executions
            if self._total_executions > 0
            else 0.0
        )
        return BulkheadMetrics(
            name=self.name,
            active_count=self._active_count,
            queue_size=self._queue_size,
            total_executions=self._total_executions,
            total_rejections=self._total_rejections,
            total_timeouts=self._total_timeouts,
            avg_execution_time=avg,
        )


# ── Registry ────────────────────────────────────────────────────────────────

_bulkheads: dict[str, Bulkhead] = {}


def create_bulkhead(
    name: str,
    max_concurrent: int = 10,
    max_queue: int = 100,
    queue_timeout: float = 5.0,
) -> Bulkhead:
    """
    Factory that creates (or retrieves a cached) :class:`Bulkhead` by *name*.

    Re-using the same name returns the existing instance so that limits are
    shared across callers within the same process.
    """
    if name not in _bulkheads:
        _bulkheads[name] = Bulkhead(
            name=name,
            max_concurrent=max_concurrent,
            max_queue=max_queue,
            queue_timeout=queue_timeout,
        )
    return _bulkheads[name]


__all__ = [
    "Bulkhead",
    "BulkheadFullError",
    "BulkheadMetrics",
    "BulkheadTimeoutError",
    "create_bulkhead",
]
