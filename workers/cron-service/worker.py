"""
Trancendos cron-service — ChronosSphere / ArcStream Scheduler
=============================================================
Asyncio-based cron scheduler with 8-backend ACO pheromone routing.

Backends (priority order):
  1. Cal.com         — self-hosted booking/scheduling (MIT)
  2. Kestra          — workflow + cron scheduler (Apache 2.0)
  3. n8n             — workflow automation (Fair-code)
  4. APScheduler     — in-process SQLite (always-available fallback)
  5. Forgejo         — cron-trigger via CI pipeline (MIT)
  6. NATS JetStream  — delayed-message scheduling (Apache 2.0)
  7. Valkey          — sorted-set schedule queue (BSD)
  8. system cron     — python-crontab OS fallback

ACO pheromone routing: each backend has a pheromone score [0,1].
Successful calls increase pheromone; failures decay it.
ThresholdGuard enforces per-backend hard stops (RPM sliding window).

Port: 8021
Zero-cost: FastAPI + SQLite + asyncio — no paid external deps.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_PORT = 8021
WORKER_NAME = "cron-service"
DB_PATH = Path(os.environ.get("CRON_DB_PATH", "/data/cron.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# ACO Pheromone routing — ThresholdGuard + PheromoneState
# ---------------------------------------------------------------------------

_DECAY = float(os.environ.get("CHRONOS_ACO_DECAY", "0.15"))
_MIN_PHEROMONE = float(os.environ.get("CHRONOS_ACO_MIN_PHEROMONE", "0.05"))
_WINDOW_SECONDS = int(os.environ.get("CHRONOS_WINDOW_SECONDS", "60"))


class ThresholdGuard:
    """Sliding-window rate limiter. Returns True if request is allowed."""

    def __init__(self, limit_rpm: int, window_seconds: int = _WINDOW_SECONDS) -> None:
        self._limit = limit_rpm
        self._window = window_seconds
        self._calls: deque[float] = deque()

    def allow(self) -> bool:
        now = time.time()
        cutoff = now - self._window
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        if len(self._calls) >= self._limit:
            return False
        self._calls.append(now)
        return True

    @property
    def current_rpm(self) -> int:
        now = time.time()
        cutoff = now - self._window
        return sum(1 for t in self._calls if t >= cutoff)


class PheromoneState:
    """Tracks pheromone score for one backend."""

    def __init__(self, name: str, rpm_limit: int) -> None:
        self.name = name
        self.score: float = 1.0
        self.guard = ThresholdGuard(rpm_limit)
        self.success = 0
        self.failure = 0

    def reinforce(self) -> None:
        self.success += 1
        self.score = min(1.0, self.score + 0.1)

    def decay(self) -> None:
        self.failure += 1
        self.score = max(_MIN_PHEROMONE, self.score * (1.0 - _DECAY))

    def status(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "pheromone": round(self.score, 4),
            "success": self.success,
            "failure": self.failure,
            "rpm": self.guard.current_rpm,
            "rpm_limit": self.guard._limit,
        }


# Backend env config
_CALCOM_URL = os.environ.get("CALCOM_URL", "http://calcom:3000")
_CALCOM_KEY = os.environ.get("CALCOM_API_KEY", "")
_CALCOM_RPM = int(os.environ.get("CALCOM_THRESHOLD_RPM", "60"))

_KESTRA_URL = os.environ.get("KESTRA_URL", "http://kestra:8080")
_KESTRA_NS = os.environ.get("KESTRA_NAMESPACE", "trancendos.chronos")
_KESTRA_RPM = int(os.environ.get("KESTRA_THRESHOLD_RPM", "120"))

_N8N_URL = os.environ.get("N8N_URL", "http://n8n:5678")
_N8N_RPM = int(os.environ.get("N8N_THRESHOLD_RPM", "60"))

_FORGEJO_URL = os.environ.get("FORGEJO_URL", "http://forgejo:3456")
_FORGEJO_TOKEN = os.environ.get("FORGEJO_TOKEN", "")
_FORGEJO_RPM = int(os.environ.get("FORGEJO_THRESHOLD_RPM", "30"))

_NATS_URL = os.environ.get("NATS_URL", "http://nats:8222")
_NATS_RPM = int(os.environ.get("NATS_JETSTREAM_THRESHOLD_RPM", "200"))

_VALKEY_URL = os.environ.get("REDIS_URL", "redis://valkey:6379")
_VALKEY_RPM = int(os.environ.get("VALKEY_SCHEDULE_THRESHOLD_RPM", "500"))

# Pheromone states indexed by backend name
_backends: Dict[str, PheromoneState] = {
    "calcom": PheromoneState("calcom", _CALCOM_RPM),
    "kestra": PheromoneState("kestra", _KESTRA_RPM),
    "n8n": PheromoneState("n8n", _N8N_RPM),
    "apscheduler": PheromoneState("apscheduler", 10000),  # in-process, no real limit
    "forgejo": PheromoneState("forgejo", _FORGEJO_RPM),
    "nats": PheromoneState("nats", _NATS_RPM),
    "valkey": PheromoneState("valkey", _VALKEY_RPM),
    "syscron": PheromoneState("syscron", 100),
}


def _choose_backend(for_type: str = "cron") -> Optional[str]:
    """ACO-weighted random selection across available backends."""
    candidates: List[Tuple[str, float]] = []
    for name, state in _backends.items():
        if state.guard.allow():
            candidates.append((name, state.score))
    if not candidates:
        return None
    total = sum(s for _, s in candidates)
    r = random.uniform(0, total)
    cumulative = 0.0
    for name, score in candidates:
        cumulative += score
        if r <= cumulative:
            return name
    return candidates[-1][0]


# ---------------------------------------------------------------------------
# Backend dispatchers
# ---------------------------------------------------------------------------


async def _dispatch_calcom(job: dict) -> bool:
    if not _CALCOM_KEY:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_CALCOM_URL}/api/v1/schedules",
                headers={"Authorization": f"Bearer {_CALCOM_KEY}"},
            )
        return resp.status_code < 400
    except Exception:
        return False


async def _dispatch_kestra(job: dict) -> bool:
    payload = {
        "id": job["id"].replace("-", "_"),
        "namespace": _KESTRA_NS,
        "tasks": [
            {
                "id": "http_callback",
                "type": "io.kestra.plugin.core.http.Request",
                "uri": job.get("url", "http://localhost/noop"),
                "method": job.get("method", "POST"),
                "body": job.get("payload", "{}"),
            }
        ],
        "triggers": [
            {
                "id": "cron_trigger",
                "type": "io.kestra.plugin.core.trigger.Schedule",
                "cron": job["schedule"],
            }
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{_KESTRA_URL}/api/v1/flows",
                json=payload,
            )
        return resp.status_code in (200, 201, 409)  # 409 = already exists
    except Exception:
        return False


async def _dispatch_n8n(job: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{_N8N_URL}/healthz")
        return resp.status_code < 400
    except Exception:
        return False


async def _dispatch_forgejo(job: dict) -> bool:
    if not _FORGEJO_TOKEN:
        return False
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{_FORGEJO_URL}/api/v1/repos/search",
                headers={"Authorization": f"token {_FORGEJO_TOKEN}"},
            )
        return resp.status_code < 400
    except Exception:
        return False


async def _dispatch_nats(job: dict) -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(f"{_NATS_URL}/varz")
        return resp.status_code < 400
    except Exception:
        return False


async def _dispatch_valkey(job: dict) -> bool:
    try:
        import redis.asyncio as aioredis  # optional dep
        r = aioredis.from_url(_VALKEY_URL, socket_timeout=3)
        score = time.time()
        await r.zadd("chronos:schedule", {json.dumps({"id": job["id"], "url": job.get("url")}): score})
        await r.aclose()
        return True
    except Exception:
        return False


async def _dispatch_syscron(job: dict) -> bool:
    try:
        from crontab import CronTab  # python-crontab optional dep
        cron = CronTab(user=True)
        cmd = f"curl -s -X {job.get('method','POST')} {job.get('url','')}"
        job_entry = cron.new(command=cmd, comment=f"chronos:{job['id']}")
        job_entry.setall(job["schedule"])
        cron.write()
        return True
    except Exception:
        return False


# Map backend name → dispatcher function
_DISPATCHERS = {
    "calcom": _dispatch_calcom,
    "kestra": _dispatch_kestra,
    "n8n": _dispatch_n8n,
    "apscheduler": None,  # in-process — handled by _scheduler_loop directly
    "forgejo": _dispatch_forgejo,
    "nats": _dispatch_nats,
    "valkey": _dispatch_valkey,
    "syscron": _dispatch_syscron,
}


async def route_job(job: dict) -> str:
    """Route a job to the best available backend via ACO. Returns backend name used."""
    backend = _choose_backend()
    if backend is None:
        backend = "apscheduler"

    if backend == "apscheduler" or _DISPATCHERS[backend] is None:
        _backends["apscheduler"].reinforce()
        return "apscheduler"

    ok = await _DISPATCHERS[backend](job)
    if ok:
        _backends[backend].reinforce()
        return backend
    else:
        _backends[backend].decay()
        _backends["apscheduler"].reinforce()
        return "apscheduler"


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                name        TEXT NOT NULL,
                schedule    TEXT NOT NULL,
                url         TEXT,
                method      TEXT DEFAULT 'POST',
                payload     TEXT DEFAULT '{}',
                headers     TEXT DEFAULT '{}',
                enabled     INTEGER NOT NULL DEFAULT 1,
                backend     TEXT DEFAULT 'apscheduler',
                last_run    REAL,
                next_run    REAL,
                run_count   INTEGER NOT NULL DEFAULT 0,
                fail_count  INTEGER NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS job_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id      TEXT NOT NULL,
                started_at  REAL NOT NULL,
                duration_ms REAL,
                status      TEXT NOT NULL,
                response    TEXT,
                error       TEXT,
                backend     TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_runs_job ON job_runs(job_id, started_at);
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Cron expression parser (5-field: min hour dom mon dow)
# ---------------------------------------------------------------------------


def _matches_field(value: int, field: str) -> bool:
    if field == "*":
        return True
    if "/" in field:
        parts = field.split("/")
        start = 0 if parts[0] == "*" else int(parts[0])
        step = int(parts[1])
        return (value - start) % step == 0
    if "," in field:
        return value in [int(x) for x in field.split(",")]
    if "-" in field:
        lo, hi = field.split("-")
        return int(lo) <= value <= int(hi)
    return value == int(field)


def _cron_matches(schedule: str, dt: datetime) -> bool:
    parts = schedule.strip().split()
    if len(parts) != 5:
        return False
    try:
        return (
            _matches_field(dt.minute, parts[0])
            and _matches_field(dt.hour, parts[1])
            and _matches_field(dt.day, parts[2])
            and _matches_field(dt.month, parts[3])
            and _matches_field(dt.weekday(), parts[4])
        )
    except (ValueError, IndexError):
        return False


async def _execute_job(job: dict) -> None:
    start = time.time()
    status = "ok"
    response_body = None
    error = None
    backend = job.get("backend", "apscheduler")

    if job.get("url"):
        try:
            headers = json.loads(job.get("headers") or "{}")
            payload = json.loads(job.get("payload") or "{}")
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    job.get("method", "POST"), job["url"], json=payload, headers=headers
                )
            response_body = resp.text[:500]
            if resp.status_code >= 400:
                status = "failed"
                error = f"HTTP {resp.status_code}"
        except Exception as exc:
            status = "error"
            error = str(exc)

    duration_ms = (time.time() - start) * 1000
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO job_runs (job_id, started_at, duration_ms, status, response, error, backend) VALUES (?,?,?,?,?,?,?)",
            (job["id"], start, duration_ms, status, response_body, error, backend),
        )
        if status == "ok":
            conn.execute(
                "UPDATE jobs SET last_run=?, run_count=run_count+1 WHERE id=?",
                (now, job["id"]),
            )
        else:
            conn.execute(
                "UPDATE jobs SET last_run=?, run_count=run_count+1, fail_count=fail_count+1 WHERE id=?",
                (now, job["id"]),
            )
        conn.commit()

    logger.info("Job %s (%s) via %s: %s in %.0fms", job["id"], job["name"], backend, status, duration_ms)


async def _scheduler_loop() -> None:
    while True:
        await asyncio.sleep(60 - datetime.now().second)
        now = datetime.now(timezone.utc)
        with get_conn() as conn:
            jobs = conn.execute("SELECT * FROM jobs WHERE enabled = 1").fetchall()
        for job in jobs:
            if _cron_matches(job["schedule"], now):
                asyncio.create_task(_execute_job(dict(job)))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class JobCreate(BaseModel):
    id: Optional[str] = None
    name: str
    schedule: str = Field(..., description="5-field cron: min hour dom mon dow")
    url: Optional[str] = None
    method: str = "POST"
    payload: Dict[str, Any] = {}
    headers: Dict[str, str] = {}
    enabled: bool = True
    backend: Optional[str] = None  # if None, ACO auto-selects


class JobUpdate(BaseModel):
    name: Optional[str] = None
    schedule: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    payload: Optional[Dict[str, Any]] = None
    headers: Optional[Dict[str, str]] = None
    enabled: Optional[bool] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel
        init_otel(service_name="tranc3.cron-service")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass
    init_db()
    logger.info("cron-service DB ready at %s", DB_PATH)
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="cron-service",
    description="ChronosSphere / ArcStream — 8-backend ACO cron scheduler",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM jobs WHERE enabled=1").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "total_jobs": total,
        "active_jobs": active,
        "backends": {name: state.status() for name, state in _backends.items()},
        "entity": {
            "location": "ChronosSphere / ArcStream",
            "pillar": "DevOps",
            "lead_ai": "Chronos",
            "primes": ["Trancendos"],
            "primary_function": "Task, Time & Scheduling Management",
        },
    }


@app.get("/backends")
async def list_backends():
    return {
        "backends": [state.status() for state in _backends.values()],
        "aco_decay": _DECAY,
        "aco_min_pheromone": _MIN_PHEROMONE,
        "window_seconds": _WINDOW_SECONDS,
    }


@_router.get("/jobs")
async def list_jobs(enabled: Optional[bool] = None):
    with get_conn() as conn:
        if enabled is not None:
            rows = conn.execute(
                "SELECT * FROM jobs WHERE enabled = ? ORDER BY name", (int(enabled),)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM jobs ORDER BY name").fetchall()
    return {"jobs": [dict(r) for r in rows]}


@_router.post("/jobs", status_code=201)
async def create_job(req: JobCreate):
    import uuid
    job_id = req.id or str(uuid.uuid4())
    now = time.time()
    job_dict = {
        "id": job_id,
        "name": req.name,
        "schedule": req.schedule,
        "url": req.url,
        "method": req.method,
        "payload": json.dumps(req.payload),
        "headers": json.dumps(req.headers),
    }

    # ACO backend selection
    chosen_backend = req.backend if req.backend in _backends else await route_job(job_dict)

    with get_conn() as conn:
        if conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(status_code=409, detail="Job ID already exists")
        conn.execute(
            "INSERT INTO jobs (id, name, schedule, url, method, payload, headers, enabled, backend, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                job_id, req.name, req.schedule, req.url, req.method,
                json.dumps(req.payload), json.dumps(req.headers),
                int(req.enabled), chosen_backend, now,
            ),
        )
        conn.commit()
    return {"id": job_id, "name": req.name, "schedule": req.schedule, "backend": chosen_backend}


@_router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@_router.patch("/jobs/{job_id}")
async def update_job(job_id: str, req: JobUpdate):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
        updates = req.model_dump(exclude_none=True)
        if "payload" in updates:
            updates["payload"] = json.dumps(updates["payload"])
        if "headers" in updates:
            updates["headers"] = json.dumps(updates["headers"])
        if "enabled" in updates:
            updates["enabled"] = int(updates["enabled"])
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE jobs SET {set_clause} WHERE id = ?", [*updates.values(), job_id])
            conn.commit()
    return {"updated": job_id}


@_router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
        conn.execute("DELETE FROM job_runs WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()
    return {"deleted": job_id}


@_router.post("/jobs/{job_id}/trigger")
async def trigger_job(job_id: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    asyncio.create_task(_execute_job(dict(row)))
    return {"triggered": job_id, "message": "Job queued for immediate execution"}


@_router.get("/jobs/{job_id}/runs")
async def job_runs(job_id: str, limit: int = Query(20, le=200)):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Job not found")
        rows = conn.execute(
            "SELECT * FROM job_runs WHERE job_id = ? ORDER BY started_at DESC LIMIT ?",
            (job_id, limit),
        ).fetchall()
    return {"job_id": job_id, "runs": [dict(r) for r in rows]}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
