"""
Trancendos chaos-party — Central Testing Platform
=================================================
Alice in Wonderland-themed testing orchestration hub.
Manages test suites, runs, results, and chaos injection experiments.
Zero-cost: FastAPI + SQLite. No external CI services required.

Port: 8063  Entity: The Chaos Party  Lead AI: The Mad Hatter
"""

from __future__ import annotations

import json
import logging
import os
import random
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8063
WORKER_NAME = "chaos-party"
DB_PATH = Path(__file__).parent / "data" / "chaos.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

MAD_HATTER_QUOTES = [
    "Why is a raven like a writing desk?",
    "We're all mad here. I'm mad. You're mad.",
    "Off with their bugs!",
    "Curiouser and curiouser... this test is failing.",
    "The Mad Hatter's Tea Party: where every test is a surprise.",
    "Sometimes I believe in as many as six impossible test cases before breakfast.",
    "Chaos is just order waiting to be discovered.",
]

CHAOS_EXPERIMENTS = [
    {"name": "latency_injection", "description": "Add random 100-2000ms delay", "severity": "low"},
    {
        "name": "error_injection",
        "description": "Return 500 errors at rate X%",
        "severity": "medium",
    },
    {
        "name": "memory_pressure",
        "description": "Allocate large in-memory structures",
        "severity": "high",
    },
    {"name": "connection_drop", "description": "Drop connections mid-stream", "severity": "high"},
    {
        "name": "data_corruption",
        "description": "Flip random bits in responses",
        "severity": "critical",
    },
    {"name": "cpu_spike", "description": "CPU-intensive computation burst", "severity": "medium"},
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS test_suites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                service     TEXT,
                test_type   TEXT DEFAULT 'unit',
                created_by  TEXT DEFAULT 'mad_hatter',
                created_at  REAL NOT NULL,
                last_run_at REAL,
                pass_count  INTEGER DEFAULT 0,
                fail_count  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS test_runs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                suite_id    INTEGER,
                name        TEXT NOT NULL,
                status      TEXT NOT NULL,
                duration_ms INTEGER,
                error_msg   TEXT,
                ran_by      TEXT DEFAULT 'system',
                ran_at      REAL NOT NULL,
                metadata    TEXT DEFAULT '{}',
                FOREIGN KEY(suite_id) REFERENCES test_suites(id)
            );
            CREATE TABLE IF NOT EXISTS chaos_experiments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                target_service TEXT,
                experiment_type TEXT NOT NULL,
                severity    TEXT DEFAULT 'low',
                config      TEXT DEFAULT '{}',
                status      TEXT DEFAULT 'idle',
                started_at  REAL,
                ended_at    REAL,
                results     TEXT,
                created_by  TEXT DEFAULT 'mad_hatter',
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_runs_suite ON test_runs(suite_id);
            CREATE INDEX IF NOT EXISTS idx_runs_status ON test_runs(status);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="The Chaos Party — Testing Platform", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class SuiteIn(BaseModel):
    name: str
    description: Optional[str] = None
    service: Optional[str] = None
    test_type: str = "unit"
    created_by: str = "mad_hatter"


class TestRunIn(BaseModel):
    suite_id: Optional[int] = None
    name: str
    status: str
    duration_ms: Optional[int] = None
    error_msg: Optional[str] = None
    ran_by: str = "system"
    metadata: dict = {}


class BatchRunIn(BaseModel):
    suite_id: Optional[int] = None
    runs: list[TestRunIn]


class ChaosExperimentIn(BaseModel):
    name: str
    target_service: Optional[str] = None
    experiment_type: str
    severity: str = "low"
    config: dict = {}


@_router.get("/health")
async def health():
    with get_conn() as conn:
        suites = conn.execute("SELECT COUNT(*) FROM test_suites").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        pass_rate_row = conn.execute(
            "SELECT AVG(CASE WHEN status='pass' THEN 1.0 ELSE 0.0 END)*100 FROM test_runs"
        ).fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Chaos Party", "lead_ai": "The Mad Hatter"},
        "test_suites": suites,
        "total_runs": runs,
        "pass_rate_pct": round(pass_rate_row or 0, 1),
        "mad_hatter_quote": random.choice(MAD_HATTER_QUOTES),
    }


@_router.get("/metrics")
async def metrics():
    uptime = time.time() - _start_time
    return (
        f"# HELP requests_total Total requests\n# TYPE requests_total counter\n"
        f"requests_total {_req_count}\n"
        f"# HELP errors_total Total errors\n# TYPE errors_total counter\n"
        f"errors_total {_err_count}\n"
        f"# HELP uptime_seconds Uptime\n# TYPE uptime_seconds gauge\n"
        f"uptime_seconds {uptime:.2f}\n"
    )


@_router.get("/quote")
async def mad_hatter_quote():
    return {"quote": random.choice(MAD_HATTER_QUOTES), "from": "The Mad Hatter"}


# --- Test Suites ---


@_router.post("/suites", status_code=201)
async def create_suite(body: SuiteIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO test_suites (name, description, service, test_type, created_by, created_at) VALUES (?,?,?,?,?,?)",
            (body.name, body.description, body.service, body.test_type, body.created_by, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM test_suites WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/suites")
async def list_suites(
    service: Optional[str] = None,
    test_type: Optional[str] = None,
    limit: int = Query(50, le=500),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if service:
        clauses.append("service=?")
        params.append(service)
    if test_type:
        clauses.append("test_type=?")
        params.append(test_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM test_suites {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


# --- Test Runs ---


@_router.post("/runs", status_code=201)
async def record_run(body: TestRunIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.status not in ("pass", "fail", "skip", "error"):
        raise HTTPException(status_code=400, detail="status must be: pass, fail, skip, error")
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO test_runs (suite_id, name, status, duration_ms, error_msg, ran_by, ran_at, metadata) VALUES (?,?,?,?,?,?,?,?)",
            (
                body.suite_id,
                body.name,
                body.status,
                body.duration_ms,
                body.error_msg,
                body.ran_by,
                now,
                json.dumps(body.metadata),
            ),
        )
        conn.commit()
        if body.suite_id:
            # field is a hardcoded column name, never user input — not SQLi
            if body.status == "pass":
                conn.execute(
                    "UPDATE test_suites SET pass_count=pass_count+1, last_run_at=? WHERE id=?",
                    (now, body.suite_id),
                )
            else:
                conn.execute(
                    "UPDATE test_suites SET fail_count=fail_count+1, last_run_at=? WHERE id=?",
                    (now, body.suite_id),
                )
            conn.commit()
    return {"id": cur.lastrowid, "status": body.status, "ran_at": now}


@_router.post("/runs/batch", status_code=201)
async def record_batch_runs(body: BatchRunIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    results = []
    with get_conn() as conn:
        for run in body.runs:
            cur = conn.execute(
                "INSERT INTO test_runs (suite_id, name, status, duration_ms, error_msg, ran_by, ran_at, metadata) VALUES (?,?,?,?,?,?,?,?)",
                (
                    body.suite_id or run.suite_id,
                    run.name,
                    run.status,
                    run.duration_ms,
                    run.error_msg,
                    run.ran_by,
                    now,
                    json.dumps(run.metadata),
                ),
            )
            results.append({"id": cur.lastrowid, "name": run.name, "status": run.status})
        conn.commit()
    return {"inserted": len(results), "runs": results}


@_router.get("/runs")
async def list_runs(
    suite_id: Optional[int] = None,
    status: Optional[str] = None,
    since: Optional[float] = None,
    limit: int = Query(100, le=1000),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if suite_id:
        clauses.append("suite_id=?")
        params.append(suite_id)
    if status:
        clauses.append("status=?")
        params.append(status)
    if since:
        clauses.append("ran_at>=?")
        params.append(since)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM test_runs {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM test_runs {where} ORDER BY ran_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return {"total": total, "runs": [dict(r) for r in rows]}


# --- Chaos Experiments ---


@_router.get("/chaos/experiments")
async def list_chaos_experiments(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return {"available": CHAOS_EXPERIMENTS}


@_router.post("/chaos", status_code=201)
async def create_chaos_experiment(
    body: ChaosExperimentIn, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    known_types = [e["name"] for e in CHAOS_EXPERIMENTS]
    if body.experiment_type not in known_types:
        raise HTTPException(
            status_code=400, detail=f"Unknown experiment type. Known: {known_types}"
        )
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO chaos_experiments (name, target_service, experiment_type, severity, config, status, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                body.name,
                body.target_service,
                body.experiment_type,
                body.severity,
                json.dumps(body.config),
                "idle",
                now,
            ),
        )
        conn.commit()
    return {"id": cur.lastrowid, "name": body.name, "status": "idle", "created_at": now}


@_router.patch("/chaos/{experiment_id}/run")
async def run_chaos(experiment_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM chaos_experiments WHERE id=?", (experiment_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Experiment not found")
        conn.execute(
            "UPDATE chaos_experiments SET status='running', started_at=? WHERE id=?",
            (now, experiment_id),
        )
        conn.commit()
    return {
        "id": experiment_id,
        "status": "running",
        "started_at": now,
        "note": "Chaos experiment marked as running — implement actual injection in target service",
    }


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM test_runs").fetchone()[0]
        by_status = conn.execute(
            "SELECT status, COUNT(*) c FROM test_runs GROUP BY status"
        ).fetchall()
        avg_duration = conn.execute(
            "SELECT AVG(duration_ms) FROM test_runs WHERE duration_ms IS NOT NULL"
        ).fetchone()[0]
    pass_count = next((r["c"] for r in by_status if r["status"] == "pass"), 0)
    return {
        "total_runs": total,
        "by_status": [dict(r) for r in by_status],
        "pass_rate_pct": round(pass_count / total * 100, 1) if total else 0,
        "avg_duration_ms": round(avg_duration, 1) if avg_duration else None,
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
