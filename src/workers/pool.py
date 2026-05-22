# src/workers/pool.py
# TRANC3 Worker Pool — Redis-backed asyncio task queue.
# Self-owned compute: no CF Workers AI, no external inference APIs.

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REDIS_URL    = os.getenv("REDIS_URL", "redis://localhost:6379")
_QUEUE_KEY    = "tranc3:tasks"          # LPUSH to submit, BRPOP to consume
_RESULT_PREFIX = "tranc3:result:"       # key = tranc3:result:<job_id>
_RESULT_TTL   = 300                     # seconds to keep results


class JobStatus(str, Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    DONE      = "done"
    FAILED    = "failed"


class JobType(str, Enum):
    GENERATE    = "generate"
    EMBED       = "embed"
    EMOTION     = "emotion"
    TOKENIZE    = "tokenize"
    CONSCIOUSNESS = "consciousness"
    PERSONALITY = "personality"
    PREDICT     = "predict"


@dataclass
class JobSpec:
    job_type: str                        # JobType value
    payload: Dict[str, Any]             # task-specific args
    job_id: str  = field(default_factory=lambda: str(uuid.uuid4()))
    priority: int = 5                   # 1 (high) … 10 (low) — reserved for future use
    created_at: float = field(default_factory=time.time)

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "JobSpec":
        data = json.loads(raw)
        return cls(**data)


@dataclass
class JobResult:
    job_id: str
    status: str                         # JobStatus value
    result: Optional[Dict[str, Any]] = None
    error:  Optional[str]            = None
    duration_ms: float               = 0.0
    worker_id: str                   = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "JobResult":
        data = json.loads(raw)
        return cls(**data)


class WorkerPool:
    """
    Manages a pool of asyncio workers backed by Redis.

    Workers are spawned as asyncio tasks within the same process (or as
    separate processes via inference_worker.py for CPU-heavy inference).

    Usage (submit a job and await result):
        pool = WorkerPool()
        await pool.start()
        job = JobSpec(job_type=JobType.GENERATE, payload={"prompt": "Hello"})
        result = await pool.submit_and_wait(job, timeout=30)
    """

    def __init__(
        self,
        num_workers: int = int(os.getenv("TRANC3_WORKERS", "2")),
        worker_fn=None,         # async callable(JobSpec) → dict — inject for testing
    ):
        self._num_workers = num_workers
        self._worker_fn   = worker_fn
        self._redis       = None
        self._tasks: List[asyncio.Task] = []
        self._running     = False

    # ─── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self):
        """Start workers. Call once at application startup."""
        if self._running:
            return
        self._redis   = await self._connect_redis()
        self._running = True

        if self._worker_fn:
            # In-process workers (testing / lightweight tasks)
            for i in range(self._num_workers):
                task = asyncio.create_task(
                    self._worker_loop(worker_id=f"pool-{i}"),
                    name=f"tranc3-worker-{i}",
                )
                self._tasks.append(task)
            logger.info("WorkerPool started: %d in-process workers", self._num_workers)
        else:
            # Heavy inference is handled by external inference_worker.py processes;
            # pool only manages queue + result store here.
            logger.info("WorkerPool started (queue-only mode — external workers expected)")

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
        logger.info("WorkerPool stopped")

    # ─── Submit ─────────────────────────────────────────────────────────────────

    async def submit(self, job: JobSpec) -> str:
        """Push a job onto the Redis queue. Returns job_id."""
        if not self._redis:
            self._redis = await self._connect_redis()
        await self._redis.lpush(_QUEUE_KEY, job.to_json())
        logger.debug("Submitted job %s (type=%s)", job.job_id, job.job_type)
        return job.job_id

    async def get_result(self, job_id: str, timeout: float = 30.0) -> Optional[JobResult]:
        """Poll Redis for a result until timeout."""
        key = f"{_RESULT_PREFIX}{job_id}"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = await self._redis.get(key)
            if raw:
                return JobResult.from_json(raw)
            await asyncio.sleep(0.1)
        return None

    async def submit_and_wait(self, job: JobSpec, timeout: float = 30.0) -> JobResult:
        """Submit job and block until result or timeout."""
        await self.submit(job)
        result = await self.get_result(job.job_id, timeout=timeout)
        if result is None:
            return JobResult(
                job_id=job.job_id,
                status=JobStatus.FAILED,
                error=f"Timeout after {timeout}s",
            )
        return result

    # ─── Internal worker loop (in-process only) ─────────────────────────────────

    async def _worker_loop(self, worker_id: str):
        logger.info("Worker %s started", worker_id)
        while self._running:
            try:
                # BRPOP blocks up to 1 s then returns None
                item = await self._redis.brpop(_QUEUE_KEY, timeout=1)
                if item is None:
                    continue
                _, raw = item
                job = JobSpec.from_json(raw)
                await self._process(job, worker_id)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.exception("Worker %s loop error: %s", worker_id, exc)
        logger.info("Worker %s stopped", worker_id)

    async def _process(self, job: JobSpec, worker_id: str):
        t0 = time.monotonic()
        result_data = None
        error = None
        try:
            ret = self._worker_fn(job)
            # Support both sync and async worker functions
            if asyncio.iscoroutine(ret):
                result_data = await ret
            else:
                result_data = ret
            status = JobStatus.DONE
        except Exception as exc:
            error  = str(exc)
            status = JobStatus.FAILED
            logger.exception("Job %s failed: %s", job.job_id, exc)

        result = JobResult(
            job_id      = job.job_id,
            status      = status,
            result      = result_data,
            error       = error,
            duration_ms = (time.monotonic() - t0) * 1000,
            worker_id   = worker_id,
        )
        key = f"{_RESULT_PREFIX}{job.job_id}"
        await self._redis.set(key, result.to_json(), ex=_RESULT_TTL)
        logger.debug("Job %s done in %.1f ms", job.job_id, result.duration_ms)

    # ─── Redis connection ────────────────────────────────────────────────────────

    @staticmethod
    async def _connect_redis():
        try:
            import redis.asyncio as aioredis
            client = aioredis.from_url(_REDIS_URL, decode_responses=True)
            await client.ping()
            logger.info("Redis connected: %s", _REDIS_URL)
            return client
        except Exception as exc:
            logger.warning("Redis unavailable (%s) — falling back to in-memory queue", exc)
            return _MemoryQueue()

    # ─── Queue stats ─────────────────────────────────────────────────────────────

    async def queue_length(self) -> int:
        if not self._redis:
            return 0
        return await self._redis.llen(_QUEUE_KEY)

    async def health(self) -> Dict[str, Any]:
        q = await self.queue_length()
        return {
            "workers":      self._num_workers,
            "running":      self._running,
            "queue_length": q,
            "redis_url":    _REDIS_URL,
        }


# ─── In-memory fallback queue ────────────────────────────────────────────────
# Used when Redis is not available (tests, local dev without Docker).

class _MemoryQueue:
    """Minimal asyncio-compatible in-memory Redis substitute."""

    def __init__(self):
        self._queue: asyncio.Queue = asyncio.Queue()
        self._store: Dict[str, str] = {}

    async def lpush(self, _key: str, value: str):
        await self._queue.put(value)

    async def brpop(self, _key: str, timeout: int = 1):
        try:
            val = await asyncio.wait_for(self._queue.get(), timeout=timeout)
            return (_key, val)
        except asyncio.TimeoutError:
            return None

    async def get(self, key: str) -> Optional[str]:
        return self._store.get(key)

    async def set(self, key: str, value: str, ex: int = None):
        self._store[key] = value

    async def llen(self, _key: str) -> int:
        return self._queue.qsize()

    async def ping(self):
        return True

    async def aclose(self):
        pass


# ─── Module-level singleton ───────────────────────────────────────────────────

_pool: Optional[WorkerPool] = None


def get_pool() -> WorkerPool:
    global _pool
    if _pool is None:
        _pool = WorkerPool()
    return _pool
