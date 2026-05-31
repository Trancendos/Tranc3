"""
InfinityBot — Tier 5 Bot / Service Worker Base Template
=========================================================
Base class for all Tier 5 Bots and Service Workers in the Trancendos platform.

Each location has up to four specialised bots (01–04), each with a single
focused task. Bots are the most granular automation unit — they execute
deterministic micro-tasks, report metrics upward, and restart automatically
on failure.

Design principles:
  - Nanoservice: one bot, one job — never multi-purpose
  - Zero-cost: no external deps, pure asyncio + stdlib
  - Self-healing: automatic restart on error with exponential backoff
  - Metric-emitting: all bots emit structured metrics on each run
  - Adaptive: dynamic interval tuning based on recent latency
  - Supervised: slot identity (01–04) enforced for management clarity
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DNA
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BotDNA:
    """Immutable identity for a Tier 5 Bot."""

    nid: str  # e.g. "NID-NXS-01"
    location_pid: str  # parent location PID
    name: str
    slot: str  # "01" | "02" | "03" | "04"
    tier: int = 5
    strand_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])

    def __str__(self) -> str:
        return f"Bot[{self.name}:slot{self.slot}@{self.location_pid}]"


# ---------------------------------------------------------------------------
# Bot run record
# ---------------------------------------------------------------------------


@dataclass
class BotRun:
    """A single execution record for a bot."""

    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=time.monotonic)
    completed_at: float | None = None
    success: bool = False
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def duration_ms(self) -> float | None:
        if self.completed_at:
            return (self.completed_at - self.started_at) * 1000
        return None


# ---------------------------------------------------------------------------
# InfinityBot base class
# ---------------------------------------------------------------------------


class InfinityBot(ABC):
    """
    Tier 5 Bot — atomic service worker for a Trancendos location.

    Sub-class and override `run_task()` with the bot's single responsibility.

    Example::

        class PingBot(InfinityBot):
            def __init__(self):
                super().__init__(
                    nid="NID-NXS-01",
                    location_pid="PID-NXS",
                    name="Ping-Bot",
                    slot="01",
                    interval_seconds=10.0,
                )

            async def run_task(self) -> dict:
                latency = await measure_latency()
                return {"latency_ms": latency}
    """

    TIER = 5
    _MAX_HISTORY = 100
    _MIN_INTERVAL = 1.0
    _MAX_INTERVAL = 300.0

    def __init__(
        self,
        nid: str,
        location_pid: str,
        name: str,
        slot: str,
        interval_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        valid_slots = ("01", "02", "03", "04")
        if slot not in valid_slots:
            raise ValueError(f"Bot slot must be one of {valid_slots} — got {slot!r}")
        self.dna = BotDNA(nid=nid, location_pid=location_pid, name=name, slot=slot)
        self._base_interval = max(self._MIN_INTERVAL, min(self._MAX_INTERVAL, interval_seconds))
        self._interval = self._base_interval
        self._max_retries = max_retries
        self._running = False
        self._task: asyncio.Task | None = None
        self._runs: list[BotRun] = []
        self._consecutive_failures = 0
        self._total_runs = 0
        self._successful_runs = 0
        self._health_score: float = 1.0
        self._ewma_duration_ms: float = 0.0

        logger.info(
            "%s initialised (tier=%d, interval=%.1fs)", self.dna, self.TIER, interval_seconds
        )

    # ------------------------------------------------------------------
    # Core task — override this
    # ------------------------------------------------------------------

    @abstractmethod
    async def run_task(self) -> dict[str, Any]:
        """The bot's single micro-task. Implement in each bot subclass."""
        ...

    # ------------------------------------------------------------------
    # Adaptive interval
    # ------------------------------------------------------------------

    def _adapt_interval(self, last_duration_ms: float) -> None:
        """Adjust polling interval based on recent execution duration.

        Slow tasks → back off interval; fast tasks → recover toward base.
        """
        alpha = 0.2
        self._ewma_duration_ms = alpha * last_duration_ms + (1 - alpha) * self._ewma_duration_ms

        # Back off when execution > 50% of interval
        if self._ewma_duration_ms > self._interval * 500:  # 500ms per interval second
            self._interval = min(self._MAX_INTERVAL, self._interval * 1.2)
        else:
            # Recover toward base interval
            self._interval = max(self._base_interval, self._interval * 0.95)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name=f"bot_{self.dna.nid}")
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
            "%s stopped (total=%d, success=%d, health=%.2f)",
            self.dna,
            self._total_runs,
            self._successful_runs,
            self._health_score,
        )

    async def _run_loop(self) -> None:
        backoff = 1.0
        while self._running:
            run = BotRun()
            self._total_runs += 1
            attempt = 0
            success = False

            for attempt in range(self._max_retries + 1):
                run.started_at = time.monotonic()  # reset for accurate per-attempt latency
                try:
                    result = await self.run_task()
                    run.result = result or {}
                    run.success = True
                    run.completed_at = time.monotonic()
                    success = True
                    break
                except asyncio.CancelledError:
                    return
                except Exception as exc:
                    run.error = str(exc)
                    if attempt < self._max_retries:
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2.0, 16.0)

            if success:
                self._successful_runs += 1
                self._consecutive_failures = 0
                self._health_score = min(1.0, self._health_score + 0.02)
                backoff = 1.0
                dur = run.duration_ms() or 0.0
                self._adapt_interval(dur)
            else:
                run.completed_at = time.monotonic()
                self._consecutive_failures += 1
                self._health_score = max(0.0, self._health_score - 0.1 * self._consecutive_failures)
                logger.warning(
                    "%s failed after %d attempts (consecutive=%d)",
                    self.dna,
                    attempt + 1,
                    self._consecutive_failures,
                )

            # Store run (cap history)
            self._runs.append(run)
            if len(self._runs) > self._MAX_HISTORY:
                self._runs = self._runs[-self._MAX_HISTORY :]

            # Emit metrics hook
            try:
                await self.on_metrics(run)
            except asyncio.CancelledError:
                raise  # propagate cancellation
            except Exception as exc:
                logger.warning("%s on_metrics raised: %s", self.dna, exc)

            try:
                await asyncio.sleep(self._interval)
            except asyncio.CancelledError:
                break

    # ------------------------------------------------------------------
    # Override points
    # ------------------------------------------------------------------

    async def on_metrics(self, run: BotRun) -> None:  # noqa: B027 - optional override hook
        """Called after each run. Override to emit metrics upstream."""
        return None

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    def last_run(self) -> BotRun | None:
        return self._runs[-1] if self._runs else None

    def success_rate(self) -> float:
        if not self._total_runs:
            return 0.0
        return self._successful_runs / self._total_runs

    def recent_latency_ms(self, n: int = 10) -> float:
        """Mean duration of the last n successful runs in ms."""
        recent = [r for r in self._runs[-n:] if r.success and r.duration_ms() is not None]
        if not recent:
            return 0.0
        return sum(r.duration_ms() for r in recent) / len(recent)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {
            "nid": self.dna.nid,
            "name": self.dna.name,
            "tier": self.TIER,
            "slot": self.dna.slot,
            "location_pid": self.dna.location_pid,
            "running": self._running,
            "health_score": round(self._health_score, 3),
            "total_runs": self._total_runs,
            "successful_runs": self._successful_runs,
            "success_rate": round(self.success_rate(), 3),
            "consecutive_failures": self._consecutive_failures,
            "interval_seconds": round(self._interval, 2),
            "ewma_duration_ms": round(self._ewma_duration_ms, 2),
            "recent_latency_ms": round(self.recent_latency_ms(), 2),
        }

    def __repr__(self) -> str:
        return f"<InfinityBot name={self.dna.name!r} tier={self.TIER} slot={self.dna.slot!r}>"
