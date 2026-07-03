"""
Trancendos taimra — Opt-in Digital Twin & Life Assistant
=========================================================
User life data: preferences, goals, routines, context memory.
Opt-in personal AI twin — zero-cost, all data stored locally.

Port: 8065  Entity: tAimra  Lead AI: tAImra
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT", "8065"))
WORKER_NAME = "taimra"
DB_PATH = Path(__file__).parent / "data" / "taimra.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS twins (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT UNIQUE NOT NULL,
                display_name TEXT,
                opted_in    INTEGER DEFAULT 1,
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS preferences (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                category    TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                set_at      REAL NOT NULL,
                UNIQUE(user_id, category, key)
            );
            CREATE TABLE IF NOT EXISTS goals (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                title       TEXT NOT NULL,
                description TEXT,
                category    TEXT DEFAULT 'personal',
                priority    INTEGER DEFAULT 3,
                target_date REAL,
                status      TEXT DEFAULT 'active',
                progress_pct REAL DEFAULT 0.0,
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS routines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                name        TEXT NOT NULL,
                schedule    TEXT,
                steps       TEXT DEFAULT '[]',
                active      INTEGER DEFAULT 1,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS context_memory (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                importance  INTEGER DEFAULT 1,
                remembered_at REAL NOT NULL,
                expires_at  REAL,
                UNIQUE(user_id, key)
            );
            CREATE INDEX IF NOT EXISTS idx_prefs_user ON preferences(user_id);
            CREATE INDEX IF NOT EXISTS idx_goals_user ON goals(user_id);
            CREATE INDEX IF NOT EXISTS idx_ctx_user ON context_memory(user_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="tAimra — Digital Twin", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


def _get_or_create_twin(user_id: str) -> dict:
    now = time.time()
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM twins WHERE user_id=?", (user_id,)).fetchone()
        if not row:
            conn.execute(
                "INSERT INTO twins (user_id, opted_in, created_at, updated_at) VALUES (?,1,?,?)",
                (user_id, now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM twins WHERE user_id=?", (user_id,)).fetchone()
        return dict(row)


class TwinUpdate(BaseModel):
    display_name: Optional[str] = None
    opted_in: Optional[bool] = None


class PrefIn(BaseModel):
    category: str
    key: str
    value: str


class GoalIn(BaseModel):
    title: str
    description: Optional[str] = None
    category: str = "personal"
    priority: int = 3
    target_date: Optional[float] = None


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    progress_pct: Optional[float] = None


class RoutineIn(BaseModel):
    name: str
    schedule: Optional[str] = None
    steps: list[str] = []


class MemoryIn(BaseModel):
    key: str
    value: str
    importance: int = 1
    expires_at: Optional[float] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        twins = conn.execute("SELECT COUNT(*) FROM twins WHERE opted_in=1").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "tAimra", "lead_ai": "tAImra"},
        "active_twins": twins,
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


@_router.get("/twin/{user_id}")
async def get_twin(user_id: str, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return _get_or_create_twin(user_id)


@_router.patch("/twin/{user_id}")
async def update_twin(user_id: str, body: TwinUpdate, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    _get_or_create_twin(user_id)
    now = time.time()
    updates = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.opted_in is not None:
        updates["opted_in"] = int(body.opted_in)
    if updates:
        updates["updated_at"] = now
        set_clause = ", ".join(f"{k}=?" for k in updates)
        with get_conn() as conn:
            conn.execute(
                f"UPDATE twins SET {set_clause} WHERE user_id=?", list(updates.values()) + [user_id]
            )
            conn.commit()
    return _get_or_create_twin(user_id)


@_router.post("/twin/{user_id}/preferences", status_code=201)
async def set_preference(user_id: str, body: PrefIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    _get_or_create_twin(user_id)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO preferences (user_id, category, key, value, set_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(user_id, category, key) DO UPDATE SET value=excluded.value, set_at=excluded.set_at",
            (user_id, body.category, body.key, body.value, now),
        )
        conn.commit()
    return {"user_id": user_id, "category": body.category, "key": body.key, "value": body.value}


@_router.get("/twin/{user_id}/preferences")
async def get_preferences(
    user_id: str, category: Optional[str] = None, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    clauses, params = ["user_id=?"], [user_id]
    if category:
        clauses.append("category=?")
        params.append(category)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM preferences {where} ORDER BY category, key", params
        ).fetchall()
    return [dict(r) for r in rows]


@_router.post("/twin/{user_id}/goals", status_code=201)
async def add_goal(user_id: str, body: GoalIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    _get_or_create_twin(user_id)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO goals (user_id, title, description, category, priority, target_date, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                user_id,
                body.title,
                body.description,
                body.category,
                body.priority,
                body.target_date,
                now,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM goals WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/twin/{user_id}/goals")
async def list_goals(
    user_id: str, status: Optional[str] = None, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    clauses, params = ["user_id=?"], [user_id]
    if status:
        clauses.append("status=?")
        params.append(status)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM goals {where} ORDER BY priority, created_at DESC", params
        ).fetchall()
    return [dict(r) for r in rows]


@_router.patch("/twin/{user_id}/goals/{goal_id}")
async def update_goal(
    user_id: str, goal_id: int, body: GoalUpdate, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    now = time.time()
    updates = {"updated_at": now}
    if body.title is not None:
        updates["title"] = body.title
    if body.status is not None:
        updates["status"] = body.status
    if body.progress_pct is not None:
        updates["progress_pct"] = min(100, max(0, body.progress_pct))
    set_clause = ", ".join(f"{k}=?" for k in updates)
    with get_conn() as conn:
        conn.execute(
            f"UPDATE goals SET {set_clause} WHERE id=? AND user_id=?",
            list(updates.values()) + [goal_id, user_id],
        )
        conn.commit()
        row = conn.execute("SELECT * FROM goals WHERE id=?", (goal_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Goal not found")
    return dict(row)


@_router.post("/twin/{user_id}/memory")
async def remember(user_id: str, body: MemoryIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    _get_or_create_twin(user_id)
    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO context_memory (user_id, key, value, importance, remembered_at, expires_at) VALUES (?,?,?,?,?,?) "
            "ON CONFLICT(user_id, key) DO UPDATE SET value=excluded.value, importance=excluded.importance, "
            "remembered_at=excluded.remembered_at, expires_at=excluded.expires_at",
            (user_id, body.key, body.value, body.importance, now, body.expires_at),
        )
        conn.commit()
    return {"user_id": user_id, "key": body.key, "value": body.value, "remembered_at": now}


@_router.get("/twin/{user_id}/memory")
async def recall(
    user_id: str, key: Optional[str] = None, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    now = time.time()
    clauses, params = ["user_id=?", "(expires_at IS NULL OR expires_at > ?)"], [user_id, now]
    if key:
        clauses.append("key LIKE ?")
        params.append(f"%{key}%")
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM context_memory {where} ORDER BY importance DESC, remembered_at DESC",
            params,
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/twin/{user_id}/summary")
async def twin_summary(user_id: str, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    twin = _get_or_create_twin(user_id)
    with get_conn() as conn:
        pref_count = conn.execute(
            "SELECT COUNT(*) FROM preferences WHERE user_id=?", (user_id,)
        ).fetchone()[0]
        active_goals = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE user_id=? AND status='active'", (user_id,)
        ).fetchone()[0]
        memories = conn.execute(
            "SELECT COUNT(*) FROM context_memory WHERE user_id=? AND (expires_at IS NULL OR expires_at>?)",
            (user_id, time.time()),
        ).fetchone()[0]
        routines = conn.execute(
            "SELECT COUNT(*) FROM routines WHERE user_id=? AND active=1", (user_id,)
        ).fetchone()[0]
    return {
        "twin": twin,
        "preferences_set": pref_count,
        "active_goals": active_goals,
        "memories": memories,
        "active_routines": routines,
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
