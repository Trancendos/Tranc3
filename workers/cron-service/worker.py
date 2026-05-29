"""
Trancendos cron-service — Self-Hosted Worker
============================================
Asyncio-based cron scheduler. Jobs are stored in SQLite with cron expressions
(minute/hour/day/month/weekday). The background loop fires HTTP callbacks
or records executions for polling consumers.

Port: 8021
Zero-cost: FastAPI + SQLite + asyncio, no external deps.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_PORT = 8021
WORKER_NAME = "cron-service"
DB_PATH = Path(__file__).parent / "data" / "cron.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


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
                error       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_runs_job ON job_runs(job_id, started_at);
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Cron expression parser (simplified 5-field: min hour dom mon dow)
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

    if job["url"]:
        try:
            headers = json.loads(job["headers"] or "{}")
            payload = json.loads(job["payload"] or "{}")
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.request(
                    job["method"], job["url"], json=payload, headers=headers
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
            "INSERT INTO job_runs (job_id, started_at, duration_ms, status, response, error) VALUES (?,?,?,?,?,?)",
            (job["id"], start, duration_ms, status, response_body, error),
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

    logger.info("Job %s (%s): %s in %.0fms", job["id"], job["name"], status, duration_ms)


async def _scheduler_loop() -> None:
    while True:
        await asyncio.sleep(60 - datetime.now().second)  # align to minute boundary
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
    init_db()
    logger.info("cron-service DB ready")
    task = asyncio.create_task(_scheduler_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="cron-service",
    description="Asyncio cron scheduler with SQLite persistence (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "entity": {
            "location": "ChronosSphere / ArcStream",
            "pillar": "DevOps",
            "lead_ai": "Chronos",
            "primes": ["Trancendos"],
            "primary_function": "Task, Time & Scheduling Management",
        },
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
    with get_conn() as conn:
        if conn.execute("SELECT id FROM jobs WHERE id = ?", (job_id,)).fetchone():
            raise HTTPException(status_code=409, detail="Job ID already exists")
        conn.execute(
            "INSERT INTO jobs (id, name, schedule, url, method, payload, headers, enabled, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                job_id,
                req.name,
                req.schedule,
                req.url,
                req.method,
                json.dumps(req.payload),
                json.dumps(req.headers),
                int(req.enabled),
                now,
            ),
        )
        conn.commit()
    return {"id": job_id, "name": req.name, "schedule": req.schedule}


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
