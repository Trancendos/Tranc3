"""
Trancendos tranquility — Wellbeing Central Hub
==============================================
Wellbeing journal, mood tracker, sleep log, mindfulness streaks.
Zero-cost: FastAPI + SQLite. No external wellness APIs.

Port: 8058  Entity: Tranquility  Lead AI: Savania
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT", "8058"))
WORKER_NAME = "tranquility"
DB_PATH = Path(__file__).parent / "data" / "tranquility.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

MOODS = {"1": "very_low", "2": "low", "3": "neutral", "4": "good", "5": "excellent"}
MOOD_VALUES = {1: "very_low", 2: "low", 3: "neutral", 4: "good", 5: "excellent"}


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS journal (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                content     TEXT NOT NULL,
                mood_score  INTEGER,
                mood_label  TEXT,
                tags        TEXT DEFAULT '[]',
                is_private  INTEGER DEFAULT 1,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mood_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                score       INTEGER NOT NULL CHECK(score BETWEEN 1 AND 5),
                label       TEXT NOT NULL,
                notes       TEXT,
                logged_at   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sleep_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                bedtime     REAL NOT NULL,
                wake_time   REAL NOT NULL,
                duration_h  REAL NOT NULL,
                quality     INTEGER CHECK(quality BETWEEN 1 AND 5),
                notes       TEXT,
                logged_at   REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS mindfulness (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT NOT NULL,
                activity    TEXT NOT NULL,
                duration_min INTEGER DEFAULT 5,
                notes       TEXT,
                logged_at   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_journal_user ON journal(user_id);
            CREATE INDEX IF NOT EXISTS idx_mood_user ON mood_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_sleep_user ON sleep_log(user_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="Tranquility — Wellbeing Hub", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class JournalIn(BaseModel):
    user_id: str
    content: str
    mood_score: Optional[int] = None
    tags: list[str] = []
    is_private: bool = True


class MoodIn(BaseModel):
    user_id: str
    score: int
    notes: Optional[str] = None


class SleepIn(BaseModel):
    user_id: str
    bedtime: float
    wake_time: float
    quality: Optional[int] = None
    notes: Optional[str] = None


class MindfulnessIn(BaseModel):
    user_id: str
    activity: str
    duration_min: int = 5
    notes: Optional[str] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        journals = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
        moods = conn.execute("SELECT COUNT(*) FROM mood_log").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "Tranquility", "lead_ai": "Savania"},
        "journal_entries": journals,
        "mood_logs": moods,
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


# --- Journal ---


@_router.post("/journal", status_code=201)
async def add_journal(body: JournalIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.mood_score and body.mood_score not in range(1, 6):
        raise HTTPException(status_code=400, detail="mood_score must be 1–5")
    now = time.time()
    label = MOOD_VALUES.get(body.mood_score) if body.mood_score else None
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO journal (user_id, content, mood_score, mood_label, tags, is_private, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                body.user_id,
                body.content,
                body.mood_score,
                label,
                json.dumps(body.tags),
                int(body.is_private),
                now,
            ),
        )
        conn.commit()
        return {"id": cur.lastrowid, "user_id": body.user_id, "created_at": now}


@_router.get("/journal/{user_id}")
async def get_journal(
    user_id: str,
    since: Optional[float] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = ["user_id=?"], [user_id]
    if since:
        clauses.append("created_at>=?")
        params.append(since)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM journal {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM journal {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "entries": [dict(r) for r in rows]}


# --- Mood ---


@_router.post("/mood", status_code=201)
async def log_mood(body: MoodIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.score not in range(1, 6):
        raise HTTPException(status_code=400, detail="score must be 1–5")
    now = time.time()
    label = MOOD_VALUES[body.score]
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO mood_log (user_id, score, label, notes, logged_at) VALUES (?,?,?,?,?)",
            (body.user_id, body.score, label, body.notes, now),
        )
        conn.commit()
    return {
        "id": cur.lastrowid,
        "user_id": body.user_id,
        "score": body.score,
        "label": label,
        "logged_at": now,
    }


@_router.get("/mood/{user_id}")
async def get_mood_history(
    user_id: str,
    since: Optional[float] = None,
    limit: int = Query(100, le=1000),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = ["user_id=?"], [user_id]
    if since:
        clauses.append("logged_at>=?")
        params.append(since)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM mood_log {where} ORDER BY logged_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        avg = conn.execute(f"SELECT AVG(score) FROM mood_log {where}", params).fetchone()[0]
    return {
        "user_id": user_id,
        "average_mood": round(avg, 2) if avg else None,
        "history": [dict(r) for r in rows],
    }


# --- Sleep ---


@_router.post("/sleep", status_code=201)
async def log_sleep(body: SleepIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.wake_time <= body.bedtime:
        raise HTTPException(status_code=400, detail="wake_time must be after bedtime")
    duration_h = round((body.wake_time - body.bedtime) / 3600, 2)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sleep_log (user_id, bedtime, wake_time, duration_h, quality, notes, logged_at) VALUES (?,?,?,?,?,?,?)",
            (body.user_id, body.bedtime, body.wake_time, duration_h, body.quality, body.notes, now),
        )
        conn.commit()
    return {
        "id": cur.lastrowid,
        "user_id": body.user_id,
        "duration_h": duration_h,
        "logged_at": now,
    }


@_router.get("/sleep/{user_id}")
async def get_sleep_history(
    user_id: str, limit: int = Query(30, le=365), x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM sleep_log WHERE user_id=? ORDER BY logged_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
        avg_dur = conn.execute(
            "SELECT AVG(duration_h) FROM sleep_log WHERE user_id=?", (user_id,)
        ).fetchone()[0]
    return {
        "user_id": user_id,
        "avg_duration_h": round(avg_dur, 2) if avg_dur else None,
        "history": [dict(r) for r in rows],
    }


# --- Mindfulness ---


@_router.post("/mindfulness", status_code=201)
async def log_mindfulness(body: MindfulnessIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO mindfulness (user_id, activity, duration_min, notes, logged_at) VALUES (?,?,?,?,?)",
            (body.user_id, body.activity, body.duration_min, body.notes, now),
        )
        conn.commit()
    return {
        "id": cur.lastrowid,
        "user_id": body.user_id,
        "activity": body.activity,
        "duration_min": body.duration_min,
    }


@_router.get("/summary/{user_id}")
async def wellbeing_summary(user_id: str, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    week_ago = time.time() - 7 * 86400
    with get_conn() as conn:
        mood_avg = conn.execute(
            "SELECT AVG(score) FROM mood_log WHERE user_id=? AND logged_at>=?", (user_id, week_ago)
        ).fetchone()[0]
        sleep_avg = conn.execute(
            "SELECT AVG(duration_h) FROM sleep_log WHERE user_id=? AND logged_at>=?",
            (user_id, week_ago),
        ).fetchone()[0]
        mindfulness_mins = conn.execute(
            "SELECT SUM(duration_min) FROM mindfulness WHERE user_id=? AND logged_at>=?",
            (user_id, week_ago),
        ).fetchone()[0]
        journal_count = conn.execute(
            "SELECT COUNT(*) FROM journal WHERE user_id=? AND created_at>=?", (user_id, week_ago)
        ).fetchone()[0]
    return {
        "user_id": user_id,
        "period": "last_7_days",
        "avg_mood_score": round(mood_avg, 2) if mood_avg else None,
        "avg_sleep_hours": round(sleep_avg, 2) if sleep_avg else None,
        "mindfulness_minutes": mindfulness_mins or 0,
        "journal_entries": journal_count,
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
