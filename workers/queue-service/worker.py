"""
The HIVE — Self-Hosted Worker
==============================
Priority task queue with retry logic, dead-letter, and stuck-task sweep.
Lead AI: The Queen

Port: 8027
Zero-cost: FastAPI + SQLite, asyncio background sweeper.
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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_PORT = int(os.getenv("PORT", "8027"))
WORKER_NAME = "the-hive"
DB_PATH = Path(__file__).parent / "data" / "hive.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

STUCK_TIMEOUT_SECONDS = 300  # 5 minutes

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tasks (
            id              TEXT PRIMARY KEY,
            queue_name      TEXT NOT NULL,
            payload         TEXT NOT NULL DEFAULT '{}',
            status          TEXT NOT NULL DEFAULT 'pending',
            priority        INTEGER NOT NULL DEFAULT 5,
            created_at      TEXT NOT NULL,
            started_at      TEXT,
            completed_at    TEXT,
            retries         INTEGER NOT NULL DEFAULT 0,
            max_retries     INTEGER NOT NULL DEFAULT 3,
            error           TEXT,
            worker_id       TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_tasks_queue_status
            ON tasks(queue_name, status, priority DESC, created_at ASC);
    """)
    conn.commit()
    conn.close()
    logger.info("The HIVE DB ready at %s", DB_PATH)


async def _stuck_task_sweeper() -> None:
    """Requeue tasks stuck in 'processing' longer than STUCK_TIMEOUT_SECONDS."""
    while True:
        await asyncio.sleep(60)
        try:
            conn = _get_conn()
            # Find tasks that have been processing too long
            now_iso = datetime.now(timezone.utc).isoformat()
            # SQLite datetime comparison via string (ISO-8601 sorts lexicographically)
            rows = conn.execute(
                """
                SELECT id, retries, max_retries
                FROM tasks
                WHERE status='processing'
                  AND started_at IS NOT NULL
                  AND (julianday('now') - julianday(started_at)) * 86400 > ?
                """,
                (STUCK_TIMEOUT_SECONDS,),
            ).fetchall()

            requeued = 0
            failed = 0
            for row in rows:
                task_id = row["id"]
                if row["retries"] + 1 >= row["max_retries"]:
                    conn.execute(
                        "UPDATE tasks SET status='failed', completed_at=?, error=? WHERE id=?",
                        (now_iso, "max_retries_exceeded_on_stuck", task_id),
                    )
                    failed += 1
                else:
                    conn.execute(
                        "UPDATE tasks SET status='pending', started_at=NULL, worker_id=NULL, retries=retries+1, error='requeued_after_stuck' WHERE id=?",
                        (task_id,),
                    )
                    requeued += 1

            if rows:
                conn.commit()
                logger.info("Stuck-task sweep: requeued=%d, failed=%d", requeued, failed)
            conn.close()
        except Exception:
            logger.exception("Stuck-task sweeper error")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class EnqueueRequest(BaseModel):
    queue_name: str
    payload: Any = {}
    priority: int = Field(5, ge=1, le=10, description="1=lowest, 10=highest")
    max_retries: int = Field(3, ge=0, le=20)


class CompleteRequest(BaseModel):
    result: Any = None


class FailRequest(BaseModel):
    error: str = "task_failed"


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.the-hive")
    init_db()
    sweeper = asyncio.create_task(_stuck_task_sweeper())
    yield
    sweeper.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="The HIVE",
    description="Priority task queue with retry logic, DLQ, and stuck-task sweep. Lead AI: The Queen.",
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
    conn = _get_conn()
    pending = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
    processing = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='processing'").fetchone()[0]
    done = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='done'").fetchone()[0]
    failed = conn.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0]
    conn.close()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "tasks": {"pending": pending, "processing": processing, "done": done, "failed": failed},
        "entity": {
            "name": "The HIVE",
            "lead_ai": "The Queen",
            "role": "Data transport hub, agent + queue coordination",
        },
    }


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------
@_router.post("/tasks", status_code=201)
async def enqueue(req: EnqueueRequest):
    """Enqueue a new task."""
    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute(
            """
            INSERT INTO tasks (id, queue_name, payload, priority, max_retries, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (task_id, req.queue_name, json.dumps(req.payload), req.priority, req.max_retries, now),
        )
        conn.commit()
    finally:
        conn.close()
    return {
        "id": task_id,
        "queue_name": req.queue_name,
        "status": "pending",
        "priority": req.priority,
        "created_at": now,
    }


# ---------------------------------------------------------------------------
# Dequeue (atomic)
# ---------------------------------------------------------------------------
@_router.get("/tasks/next/{queue_name}")
async def dequeue(queue_name: str, worker_id: str = Query(default="")):
    """Dequeue the highest-priority pending task (atomic)."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        conn.execute("BEGIN EXCLUSIVE")
        row = conn.execute(
            """
            SELECT id FROM tasks
            WHERE queue_name=? AND status='pending'
            ORDER BY priority DESC, created_at ASC
            LIMIT 1
            """,
            (queue_name,),
        ).fetchone()
        if not row:
            conn.rollback()
            return {"task": None}
        task_id = row["id"]
        conn.execute(
            "UPDATE tasks SET status='processing', started_at=?, worker_id=? WHERE id=?",
            (now, worker_id or None, task_id),
        )
        conn.commit()
        task_row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        task = dict(task_row)
        task["payload"] = json.loads(task["payload"])
        return {"task": task}
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Complete / Fail
# ---------------------------------------------------------------------------
@_router.post("/tasks/{task_id}/complete")
async def complete_task(task_id: str, req: CompleteRequest = CompleteRequest()):
    """Mark a task as done."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        row = conn.execute("SELECT status FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        if row["status"] not in ("processing", "pending"):
            raise HTTPException(409, f"Cannot complete task with status '{row['status']}'")
        conn.execute("UPDATE tasks SET status='done', completed_at=? WHERE id=?", (now, task_id))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "status": "done"}


@_router.post("/tasks/{task_id}/fail")
async def fail_task(task_id: str, req: FailRequest = FailRequest()):
    """Mark a task failed; requeue if retries remain."""
    now = datetime.now(timezone.utc).isoformat()
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT status, retries, max_retries FROM tasks WHERE id=?", (task_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        if row["status"] not in ("processing",):
            raise HTTPException(409, f"Task status is '{row['status']}', not 'processing'")

        new_retries = row["retries"] + 1
        if new_retries >= row["max_retries"]:
            conn.execute(
                "UPDATE tasks SET status='failed', completed_at=?, retries=?, error=? WHERE id=?",
                (now, new_retries, req.error, task_id),
            )
            new_status = "failed"
        else:
            conn.execute(
                "UPDATE tasks SET status='pending', started_at=NULL, worker_id=NULL, retries=?, error=? WHERE id=?",
                (new_retries, req.error, task_id),
            )
            new_status = "pending"
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "task_id": task_id, "status": new_status}


# ---------------------------------------------------------------------------
# Status & Queue listing
# ---------------------------------------------------------------------------
@_router.get("/tasks/status/{task_id}")
async def task_status(task_id: str):
    """Get task status."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise HTTPException(404, "Task not found")
        task = dict(row)
        task["payload"] = json.loads(task["payload"])
        return task
    finally:
        conn.close()


@_router.get("/queues")
async def list_queues():
    """List all queues with pending/processing/done/failed counts."""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT
                queue_name,
                COUNT(*) FILTER (WHERE status='pending')    AS pending,
                COUNT(*) FILTER (WHERE status='processing') AS processing,
                COUNT(*) FILTER (WHERE status='done')       AS done,
                COUNT(*) FILTER (WHERE status='failed')     AS failed,
                COUNT(*) AS total
            FROM tasks
            GROUP BY queue_name
            ORDER BY queue_name
            """
        ).fetchall()
        return {"queues": [dict(r) for r in rows]}
    finally:
        conn.close()


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
