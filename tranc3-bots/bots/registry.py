# bots/registry.py — BotRegistry: maps bot_type → handler, manages pool lifecycle.
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from bots.handlers import HANDLERS
from bots.pool import BotPool
from bots.types import JobResult, JobSpec, JobStatus

logger = logging.getLogger(__name__)


class BotRegistry:
    """
    Central registry that owns the BotPool and dispatches jobs to handlers.

    Usage:
        registry = BotRegistry()
        await registry.start()
        result = await registry.run("generate", prompt="Hello world")
        await registry.stop()
    """

    def __init__(self, num_workers: int = 2):
        self._pool = BotPool(
            num_workers=num_workers,
            worker_fn=self._dispatch,
        )

    async def start(self):
        await self._pool.start()
        logger.info("BotRegistry started")

    async def stop(self):
        await self._pool.stop()
        logger.info("BotRegistry stopped")

    # ── Public API ─────────────────────────────────────────────────────────────

    async def run(self, bot_type: str, timeout: float = 60.0, **kwargs) -> Dict[str, Any]:
        """Submit a job and await its result. Returns the result dict."""
        job = JobSpec(bot_type=bot_type, payload=kwargs)
        result = await self._pool.submit_and_wait(job, timeout=timeout)
        if result.status == JobStatus.FAILED:
            raise RuntimeError(result.error or f"Bot {bot_type} failed")
        return result.result or {}

    async def submit(self, bot_type: str, **kwargs) -> str:
        """Fire-and-forget submit. Returns job_id."""
        job = JobSpec(bot_type=bot_type, payload=kwargs)
        return await self._pool.submit(job)

    async def get_result(self, job_id: str, timeout: float = 30.0) -> Optional[JobResult]:
        return await self._pool.get_result(job_id, timeout=timeout)

    async def health(self) -> Dict[str, Any]:
        return {
            "status": "ok",
            "queue_length": await self._pool.queue_len(),
            "handlers": list(HANDLERS.keys()),
        }

    # ── Internal dispatcher ────────────────────────────────────────────────────

    async def _dispatch(self, job: JobSpec) -> Dict[str, Any]:
        handler = HANDLERS.get(job.bot_type)
        if handler is None:
            raise ValueError(f"Unknown bot_type: {job.bot_type!r}")
        logger.debug("Dispatching %s (job=%s)", job.bot_type, job.job_id)
        return await handler(job.payload)


# ── Module-level singleton ─────────────────────────────────────────────────────

_registry: Optional[BotRegistry] = None


def get_registry() -> BotRegistry:
    global _registry
    if _registry is None:
        _registry = BotRegistry()
    return _registry
