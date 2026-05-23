# bots/pool.py — Redis-backed asyncio task queue (standalone, no Tranc3 imports)
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Callable, Dict, List, Optional

from bots.types import JobResult, JobSpec, JobStatus

logger = logging.getLogger(__name__)

_REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
_QUEUE_KEY = "tranc3:bots:tasks"
_RESULT_PFX = "tranc3:bots:result:"
_RESULT_TTL = 300


class BotPool:
    """
    Redis-backed asyncio worker pool.

    In-memory fallback used automatically when Redis is not available
    (local dev, tests).

    Usage:
        pool = BotPool(num_workers=2, worker_fn=my_dispatch_fn)
        await pool.start()
        job    = JobSpec(bot_type="generate", payload={"prompt": "hello"})
        result = await pool.submit_and_wait(job, timeout=30)
    """

    def __init__(self, num_workers: int = 2, worker_fn: Callable = None):
        self._num_workers = num_workers
        self._worker_fn = worker_fn
        self._redis = None
        self._tasks: List[asyncio.Task] = []
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        if self._running:
            return
        self._redis = await self._connect()
        self._running = True
        if self._worker_fn:
            for i in range(self._num_workers):
                t = asyncio.create_task(self._loop(f"pool-{i}"), name=f"bot-worker-{i}")
                self._tasks.append(t)
        logger.info("BotPool started (%d workers)", self._num_workers)

    async def stop(self):
        self._running = False
        for t in self._tasks:
            t.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        if self._redis:
            await self._redis.aclose()
            self._redis = None
        logger.info("BotPool stopped")

    # ── Submit ────────────────────────────────────────────────────────────────

    async def submit(self, job: JobSpec) -> str:
        if not self._redis:
            self._redis = await self._connect()
        await self._redis.lpush(_QUEUE_KEY, job.to_json())
        logger.debug("Submitted %s (%s)", job.job_id, job.bot_type)
        return job.job_id

    async def get_result(self, job_id: str, timeout: float = 30.0) -> Optional[JobResult]:
        key = f"{_RESULT_PFX}{job_id}"
        dl = time.monotonic() + timeout
        while time.monotonic() < dl:
            raw = await self._redis.get(key)
            if raw:
                return JobResult.from_json(raw)
            await asyncio.sleep(0.05)
        return None

    async def submit_and_wait(self, job: JobSpec, timeout: float = 30.0) -> JobResult:
        await self.submit(job)
        r = await self.get_result(job.job_id, timeout=timeout)
        if r is None:
            return JobResult(
                job_id=job.job_id, status=JobStatus.FAILED, error=f"Timeout after {timeout}s"
            )
        return r

    async def queue_len(self) -> int:
        if not self._redis:
            return 0
        return await self._redis.llen(_QUEUE_KEY)

    # ── Internal loop ─────────────────────────────────────────────────────────

    async def _loop(self, wid: str):
        logger.info("Bot worker %s started", wid)
        while self._running:
            try:
                item = await self._redis.brpop(_QUEUE_KEY, timeout=1)
                if item is None:
                    continue
                _, raw = item
                job = JobSpec.from_json(raw)
                await self._execute(job, wid)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Worker %s error: %s", wid, exc)
        logger.info("Bot worker %s stopped", wid)

    async def _execute(self, job: JobSpec, wid: str):
        t0, error, data = time.monotonic(), None, None
        try:
            ret = self._worker_fn(job)
            data = (await ret) if asyncio.iscoroutine(ret) else ret
            status = JobStatus.DONE
        except Exception as exc:
            error, status = str(exc), JobStatus.FAILED
            logger.exception("Job %s failed: %s", job.job_id, exc)

        result = JobResult(
            job_id=job.job_id,
            status=status,
            result=data,
            error=error,
            duration_ms=(time.monotonic() - t0) * 1000,
            bot_id=wid,
        )
        await self._redis.set(f"{_RESULT_PFX}{job.job_id}", result.to_json(), ex=_RESULT_TTL)

    # ── Redis connection ───────────────────────────────────────────────────────

    @staticmethod
    async def _connect():
        try:
            import redis.asyncio as ar

            c = ar.from_url(_REDIS_URL, decode_responses=True)
            await c.ping()
            logger.info("Redis connected: %s", _REDIS_URL)
            return c
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — memory fallback", exc)
            return _MemQueue()


class _MemQueue:
    """Minimal in-memory Redis substitute (dev / no-Redis environments)."""

    def __init__(self):
        self._q: asyncio.Queue = asyncio.Queue()
        self._s: Dict[str, str] = {}

    async def lpush(self, _k, v):
        await self._q.put(v)

    async def brpop(self, _k, timeout=1):
        try:
            return (_k, await asyncio.wait_for(self._q.get(), timeout=timeout))
        except asyncio.TimeoutError:
            return None

    async def get(self, k):
        return self._s.get(k)

    async def set(self, k, v, ex=0):
        self._s[k] = v

    async def llen(self, _k):
        return self._q.qsize()

    async def ping(self):
        return True

    async def aclose(self):
        pass
