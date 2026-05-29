"""
Trancendos skills-benchmark-service — Self-Hosted Worker
==========================================================
AI capability benchmarking with skill gap detection and leaderboard.

Features:
    - Benchmark suite CRUD with task definitions
    - Model evaluation with scoring
    - Leaderboard with category filtering
    - Skill gap detection and recommendations
    - Default benchmark suite seeding on startup

Port: 8035
Zero-cost: FastAPI + SQLite, no external services required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "skills-benchmark-service"
PORT = 8035

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("BENCHMARK_DB_PATH", "data/benchmark.db")

logger = logging.getLogger("skills-benchmark-service")

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS suites (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            category TEXT DEFAULT 'general',
            tasks TEXT NOT NULL DEFAULT '[]',
            difficulty INTEGER DEFAULT 3,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS evaluations (
            id TEXT PRIMARY KEY,
            suite_id TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_id TEXT DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            scores TEXT DEFAULT '{}',
            total_score REAL DEFAULT 0.0,
            duration_ms REAL DEFAULT 0.0,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (suite_id) REFERENCES suites(id)
        );

        CREATE INDEX IF NOT EXISTS idx_eval_suite ON evaluations(suite_id);
        CREATE INDEX IF NOT EXISTS idx_eval_model ON evaluations(model_name);
        CREATE INDEX IF NOT EXISTS idx_eval_status ON evaluations(status);
    """)
    conn.commit()
    conn.close()
    _seed_default_suites()


def _seed_default_suites() -> None:
    conn = _get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM suites").fetchone()["c"]
    if count > 0:
        conn.close()
        return

    now = _now()
    defaults = [
        (
            "reasoning-v1",
            "Logical Reasoning Benchmark",
            "reasoning",
            [
                {
                    "id": "r1",
                    "prompt": "If all A are B and all B are C, what follows?",
                    "expected_output": "All A are C",
                    "difficulty": 2,
                },
                {
                    "id": "r2",
                    "prompt": "Solve: 2x + 5 = 13",
                    "expected_output": "x = 4",
                    "difficulty": 1,
                },
                {
                    "id": "r3",
                    "prompt": "What is the contrapositive of 'If P then Q'?",
                    "expected_output": "If not Q then not P",
                    "difficulty": 3,
                },
            ],
        ),
        (
            "coding-v1",
            "Coding Proficiency Benchmark",
            "coding",
            [
                {
                    "id": "c1",
                    "prompt": "Write a function to reverse a string",
                    "expected_output": "def reverse(s): return s[::-1]",
                    "difficulty": 1,
                },
                {
                    "id": "c2",
                    "prompt": "Implement binary search",
                    "expected_output": "O(log n) search implementation",
                    "difficulty": 2,
                },
                {
                    "id": "c3",
                    "prompt": "Implement a thread-safe singleton",
                    "expected_output": "Double-checked locking pattern",
                    "difficulty": 4,
                },
            ],
        ),
        (
            "knowledge-v1",
            "General Knowledge Benchmark",
            "knowledge",
            [
                {
                    "id": "k1",
                    "prompt": "What is the capital of France?",
                    "expected_output": "Paris",
                    "difficulty": 1,
                },
                {
                    "id": "k2",
                    "prompt": "Explain quantum entanglement",
                    "expected_output": "Physics explanation",
                    "difficulty": 4,
                },
                {
                    "id": "k3",
                    "prompt": "What is the halting problem?",
                    "expected_output": "Undecidability explanation",
                    "difficulty": 3,
                },
            ],
        ),
    ]
    for name, desc, cat, tasks in defaults:
        sid = _new_id()
        try:
            conn.execute(
                "INSERT INTO suites (id, name, description, category, tasks, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
                (sid, name, desc, cat, json.dumps(tasks), now, now),
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SuiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    category: str = "general"
    tasks: List[Dict[str, Any]] = Field(default_factory=list)
    difficulty: int = 3


class EvaluationCreate(BaseModel):
    suite_id: str
    model_name: str
    model_id: str = ""


class EvaluationComplete(BaseModel):
    scores: Dict[str, float] = Field(default_factory=dict)
    total_score: float = 0.0
    duration_ms: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("skills-benchmark-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 Skills Benchmark Service", version="0.1.0", lifespan=_lifespan)
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
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "skills-benchmark-service", "port": 8035}


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------


@_router.post("/suites", status_code=201)
async def create_suite(body: SuiteCreate):
    conn = _get_db()
    now = _now()
    sid = _new_id()
    try:
        conn.execute(
            "INSERT INTO suites (id, name, description, category, tasks, difficulty, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                sid,
                body.name,
                body.description,
                body.category,
                json.dumps(body.tasks),
                body.difficulty,
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Suite '{body.name}' already exists") from None
    conn.close()
    return {
        "id": sid,
        "name": body.name,
        "description": body.description,
        "category": body.category,
        "tasks": body.tasks,
        "difficulty": body.difficulty,
        "created_at": now,
        "updated_at": now,
    }


@_router.get("/suites")
async def list_suites(
    category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM suites WHERE 1=1"
    params: list = []
    if category:
        q += " AND category=?"
        params.append(category)
    q += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "category": r["category"],
            "tasks": json.loads(r["tasks"]),
            "difficulty": r["difficulty"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


@_router.get("/suites/{suite_id}")
async def get_suite(suite_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM suites WHERE id=?", (suite_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Suite not found") from None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "category": row["category"],
        "tasks": json.loads(row["tasks"]),
        "difficulty": row["difficulty"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# Evaluations
# ---------------------------------------------------------------------------


@_router.post("/evaluations", status_code=201)
async def create_evaluation(body: EvaluationCreate):
    conn = _get_db()
    # Verify suite exists
    suite = conn.execute("SELECT * FROM suites WHERE id=?", (body.suite_id,)).fetchone()
    if not suite:
        conn.close()
        raise HTTPException(404, "Suite not found") from None

    now = _now()
    eid = _new_id()
    conn.execute(
        "INSERT INTO evaluations (id, suite_id, model_name, model_id, status, started_at, created_at) VALUES (?,?,?,?,?,?,?)",
        (eid, body.suite_id, body.model_name, body.model_id, "pending", now, now),
    )
    conn.commit()
    conn.close()
    return {
        "id": eid,
        "suite_id": body.suite_id,
        "model_name": body.model_name,
        "model_id": body.model_id,
        "status": "pending",
        "created_at": now,
    }


@_router.get("/evaluations")
async def list_evaluations(
    suite_id: Optional[str] = None,
    model_name: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM evaluations WHERE 1=1"
    params: list = []
    if suite_id:
        q += " AND suite_id=?"
        params.append(suite_id)
    if model_name:
        q += " AND model_name=?"
        params.append(model_name)
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@_router.put("/evaluations/{evaluation_id}/complete")
async def complete_evaluation(evaluation_id: str, body: EvaluationComplete):
    conn = _get_db()
    now = _now()
    cur = conn.execute(
        "UPDATE evaluations SET status='completed', scores=?, total_score=?, duration_ms=?, completed_at=? WHERE id=?",
        (json.dumps(body.scores), body.total_score, body.duration_ms, now, evaluation_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Evaluation not found") from None
    return {"id": evaluation_id, "status": "completed", "total_score": body.total_score}


# ---------------------------------------------------------------------------
# Leaderboard
# ---------------------------------------------------------------------------


@_router.get("/leaderboard")
async def get_leaderboard(category: Optional[str] = None, limit: int = Query(50, ge=1, le=200)):
    conn = _get_db()
    q = """
        SELECT e.model_name, e.model_id, AVG(e.total_score) as avg_score,
               COUNT(*) as eval_count, s.category
        FROM evaluations e
        JOIN suites s ON e.suite_id = s.id
        WHERE e.status='completed'
    """
    params: list = []
    if category:
        q += " AND s.category=?"
        params.append(category)
    q += " GROUP BY e.model_name ORDER BY avg_score DESC LIMIT ?"
    params.append(limit)
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Skill Gaps
# ---------------------------------------------------------------------------


@_router.get("/skill-gaps")
async def get_skill_gaps():
    conn = _get_db()
    # Find categories where no model scores above 0.7
    rows = conn.execute("""
        SELECT s.category, MAX(e.total_score) as best_score, AVG(e.total_score) as avg_score
        FROM suites s
        LEFT JOIN evaluations e ON e.suite_id = s.id AND e.status='completed'
        GROUP BY s.category
    """).fetchall()
    gaps = []
    for r in rows:
        if r["best_score"] is None or r["best_score"] < 0.7:
            gaps.append(
                {
                    "category": r["category"],
                    "best_score": r["best_score"] or 0.0,
                    "avg_score": r["avg_score"] or 0.0,
                    "gap": "No model meets threshold (0.7)",
                }
            )
    conn.close()
    return gaps


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def get_stats():
    conn = _get_db()
    total_suites = conn.execute("SELECT COUNT(*) as c FROM suites").fetchone()["c"]
    total_evals = conn.execute("SELECT COUNT(*) as c FROM evaluations").fetchone()["c"]
    completed = conn.execute(
        "SELECT COUNT(*) as c FROM evaluations WHERE status='completed'"
    ).fetchone()["c"]
    pending = conn.execute(
        "SELECT COUNT(*) as c FROM evaluations WHERE status='pending'"
    ).fetchone()["c"]
    conn.close()
    return {
        "total_suites": total_suites,
        "total_evaluations": total_evals,
        "completed_evaluations": completed,
        "pending_evaluations": pending,
    }


_connected_ws: list[WebSocket] = []


@app.websocket("/ws")
async def _ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connected_ws.append(ws)
    try:
        # Push initial state
        stats = await _get_stats_async()
        await ws.send_text(json.dumps({"type": "initial_state", "data": stats}))
        # Keep alive — listen for client messages
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"type": "ping"}
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "get_stats":
                await ws.send_text(json.dumps({"type": "stats", "data": _get_stats()}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connected_ws:
            _connected_ws.remove(ws)


async def _broadcast_event(event_type: str, data: dict) -> None:
    msg = json.dumps({"type": event_type, "data": data})
    stale = []
    for ws in _connected_ws:
        try:
            await ws.send_text(msg)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _connected_ws.remove(ws)


@_router.get("/events")
async def _sse_events():
    async def _generator():
        while True:
            stats = await _get_stats_async()
            yield {"event": "stats", "data": json.dumps(stats)}
            await asyncio.sleep(5)

    return EventSourceResponse(_generator())


@_router.get("/dashboard/summary")
async def _dashboard_summary():
    """Aggregated summary optimized for dashboard consumption."""
    stats = await _get_stats_async()
    return {
        "service": stats.get("service", SERVICE_NAME),
        "port": stats.get("port", PORT),
        "status": "healthy",
        "summary": stats,
        "real_time": {
            "websocket": f"ws://localhost:{PORT}/ws",
            "sse": f"http://localhost:{PORT}/events",
        },
    }


async def _get_stats_async() -> dict:
    """Async version for use in async contexts."""
    try:
        result = await get_stats()
        if isinstance(result, dict):
            result["service"] = SERVICE_NAME
            result["port"] = PORT
            return result
    except Exception:
        pass
    return {"service": SERVICE_NAME, "port": PORT}


def _get_stats() -> dict:
    """Return basic service stats for real-time endpoints (sync fallback)."""
    return {"service": SERVICE_NAME, "port": PORT}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8035)
