"""
Trancendos queue-service — Self-Hosted Worker
=============================================
Persistent message queue: topics, publish, consume with visibility timeout,
ack/nack, and dead-letter queue after MAX_RETRIES failures.

Port: 8022
Zero-cost: FastAPI + SQLite, asyncio background loop for visibility restore.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.entities.health_metadata import health_entity_block

WORKER_PORT = 8022
WORKER_NAME = "queue-service"
DB_PATH = Path(__file__).parent / "data" / "queue.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

VISIBILITY_TIMEOUT = 30  # seconds before unacked message returns to pending
MAX_RETRIES = 3  # attempts before moving to dead-letter

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
            CREATE TABLE IF NOT EXISTS topics (
                name        TEXT PRIMARY KEY,
                description TEXT,
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                id              TEXT PRIMARY KEY,
                topic           TEXT NOT NULL,
                payload         TEXT NOT NULL,
                status          TEXT NOT NULL DEFAULT 'pending',
                retry_count     INTEGER NOT NULL DEFAULT 0,
                consumer_id     TEXT,
                visible_after   REAL NOT NULL DEFAULT 0,
                enqueued_at     REAL NOT NULL,
                delivered_at    REAL,
                acked_at        REAL,
                FOREIGN KEY (topic) REFERENCES topics(name)
            );
            CREATE INDEX IF NOT EXISTS idx_msg_topic_status ON messages(topic, status, visible_after);

            CREATE TABLE IF NOT EXISTS dead_letters (
                id          TEXT PRIMARY KEY,
                topic       TEXT NOT NULL,
                payload     TEXT NOT NULL,
                retry_count INTEGER NOT NULL,
                moved_at    REAL NOT NULL,
                last_error  TEXT
            );
        """)
        conn.commit()


async def _visibility_restore_loop() -> None:
    """Return timed-out messages (still in 'processing') back to pending."""
    while True:
        await asyncio.sleep(5)
        now = time.time()
        with get_conn() as conn:
            timed_out = conn.execute(
                "SELECT id, retry_count FROM messages WHERE status = 'processing' AND visible_after <= ?",
                (now,),
            ).fetchall()
            for row in timed_out:
                if row["retry_count"] + 1 >= MAX_RETRIES:
                    # promote to DLQ
                    msg = conn.execute(
                        "SELECT * FROM messages WHERE id = ?",
                        (row["id"],),
                    ).fetchone()
                    conn.execute(
                        "INSERT OR REPLACE INTO dead_letters (id, topic, payload, retry_count, moved_at, last_error) VALUES (?,?,?,?,?,?)",
                        (
                            msg["id"],
                            msg["topic"],
                            msg["payload"],
                            msg["retry_count"],
                            now,
                            "max_retries_exceeded",
                        ),
                    )
                    conn.execute("DELETE FROM messages WHERE id = ?", (row["id"],))
                else:
                    conn.execute(
                        "UPDATE messages SET status='pending', consumer_id=NULL, retry_count=retry_count+1 WHERE id=?",
                        (row["id"],),
                    )
            if timed_out:
                conn.commit()
                logger.info("Restored %d timed-out messages", len(timed_out))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TopicCreate(BaseModel):
    name: str
    description: Optional[str] = None


class PublishIn(BaseModel):
    payload: Any
    delay: int = Field(0, ge=0, description="Seconds before message becomes visible")


class BatchPublishIn(BaseModel):
    messages: List[PublishIn]


class ConsumeResponse(BaseModel):
    id: str
    topic: str
    payload: Any
    retry_count: int
    enqueued_at: float


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("queue-service DB ready")
    task = asyncio.create_task(_visibility_restore_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="queue-service",
    description="Persistent message queue with topics and DLQ (self-hosted)",
    version="1.0.0",
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
        pending = conn.execute("SELECT COUNT(*) FROM messages WHERE status='pending'").fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE status='processing'",
        ).fetchone()[0]
        dlq = conn.execute("SELECT COUNT(*) FROM dead_letters").fetchone()[0]
    return {
        "entity": health_entity_block(8022, "queue-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "pending": pending,
        "processing": processing,
        "dead_letters": dlq,
    }


# --- Topics ---


@_router.post("/topics", status_code=201)
async def create_topic(req: TopicCreate):
    with get_conn() as conn:
        existing = conn.execute("SELECT name FROM topics WHERE name = ?", (req.name,)).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="Topic already exists")
        conn.execute(
            "INSERT INTO topics (name, description, created_at) VALUES (?,?,?)",
            (req.name, req.description, time.time()),
        )
        conn.commit()
    return {"name": req.name, "description": req.description}


@_router.get("/topics")
async def list_topics():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM topics ORDER BY name").fetchall()
    return {"topics": [dict(r) for r in rows]}


@_router.delete("/topics/{topic}")
async def delete_topic(topic: str):
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM topics WHERE name = ?", (topic,)).fetchone():
            raise HTTPException(status_code=404, detail="Topic not found")
        conn.execute("DELETE FROM messages WHERE topic = ?", (topic,))
        conn.execute("DELETE FROM topics WHERE name = ?", (topic,))
        conn.commit()
    return {"deleted": topic}


def _ensure_topic(topic: str) -> None:
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM topics WHERE name = ?", (topic,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Topic '{topic}' not found")


# --- Publish ---


@_router.post("/topics/{topic}/publish", status_code=201)
async def publish(topic: str, req: PublishIn):
    _ensure_topic(topic)
    # Capacity hard stop — queue depth
    try:
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
        from src.capacity.guard import CapacityService, CapacityExceededError, get_capacity_guard
        get_capacity_guard().consume(CapacityService.QUEUE_DEPTH, amount=1)
    except Exception as _qe:
        from src.capacity.guard import CapacityExceededError
        if isinstance(_qe, CapacityExceededError):
            raise HTTPException(status_code=503, detail=str(_qe))
    now = time.time()
    msg_id = str(uuid.uuid4())
    visible_after = now + req.delay
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO messages (id, topic, payload, visible_after, enqueued_at) VALUES (?,?,?,?,?)",
            (msg_id, topic, json.dumps(req.payload), visible_after, now),
        )
        conn.commit()
    return {"id": msg_id, "topic": topic, "enqueued_at": now}


@_router.post("/topics/{topic}/publish/batch", status_code=201)
async def publish_batch(topic: str, req: BatchPublishIn):
    _ensure_topic(topic)
    now = time.time()
    rows = []
    for m in req.messages:
        msg_id = str(uuid.uuid4())
        rows.append((msg_id, topic, json.dumps(m.payload), now + m.delay, now))
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO messages (id, topic, payload, visible_after, enqueued_at) VALUES (?,?,?,?,?)",
            rows,
        )
        conn.commit()
    return {"published": len(rows), "topic": topic}


# --- Consume ---


@_router.get("/topics/{topic}/consume")
async def consume(
    topic: str,
    consumer_id: str = Query(...),
    max_messages: int = Query(1, ge=1, le=100),
):
    _ensure_topic(topic)
    now = time.time()
    deadline = now + VISIBILITY_TIMEOUT
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, payload, retry_count, enqueued_at FROM messages "
            "WHERE topic = ? AND status = 'pending' AND visible_after <= ? "
            "ORDER BY enqueued_at ASC LIMIT ?",
            (topic, now, max_messages),
        ).fetchall()
        if not rows:
            return {"messages": []}
        for row in rows:
            conn.execute(
                "UPDATE messages SET status='processing', consumer_id=?, delivered_at=?, visible_after=? WHERE id=?",
                (consumer_id, now, deadline, row["id"]),
            )
        conn.commit()
    return {
        "messages": [
            {
                "id": r["id"],
                "topic": topic,
                "payload": json.loads(r["payload"]),
                "retry_count": r["retry_count"],
                "enqueued_at": r["enqueued_at"],
            }
            for r in rows
        ],
    }


@_router.post("/topics/{topic}/ack/{message_id}")
async def ack(topic: str, message_id: str):
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM messages WHERE id = ? AND topic = ? AND status = 'processing'",
            (message_id, topic),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Message not found or not in processing state",
            )
        conn.execute(
            "UPDATE messages SET status='acknowledged', acked_at=? WHERE id=?",
            (now, message_id),
        )
        conn.commit()
    return {"acked": message_id}


@_router.post("/topics/{topic}/nack/{message_id}")
async def nack(topic: str, message_id: str):
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id, retry_count, payload FROM messages WHERE id = ? AND topic = ? AND status = 'processing'",
            (message_id, topic),
        ).fetchone()
        if not row:
            raise HTTPException(
                status_code=404,
                detail="Message not found or not in processing state",
            )
        if row["retry_count"] + 1 >= MAX_RETRIES:
            conn.execute(
                "INSERT OR REPLACE INTO dead_letters (id, topic, payload, retry_count, moved_at, last_error) VALUES (?,?,?,?,?,?)",
                (message_id, topic, row["payload"], row["retry_count"], now, "nacked"),
            )
            conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
        else:
            conn.execute(
                "UPDATE messages SET status='pending', consumer_id=NULL, retry_count=retry_count+1, visible_after=0 WHERE id=?",
                (message_id,),
            )
        conn.commit()
    return {"nacked": message_id}


@_router.get("/topics/{topic}/dead-letters")
async def dead_letters(topic: str, limit: int = Query(50, le=500)):
    _ensure_topic(topic)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM dead_letters WHERE topic = ? ORDER BY moved_at DESC LIMIT ?",
            (topic, limit),
        ).fetchall()
    return {"dead_letters": [dict(r) for r in rows]}


@_router.get("/topics/{topic}/stats")
async def topic_stats(topic: str):
    _ensure_topic(topic)
    with get_conn() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE topic=? AND status='pending'",
            (topic,),
        ).fetchone()[0]
        processing = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE topic=? AND status='processing'",
            (topic,),
        ).fetchone()[0]
        acked = conn.execute(
            "SELECT COUNT(*) FROM messages WHERE topic=? AND status='acknowledged'",
            (topic,),
        ).fetchone()[0]
        dlq = conn.execute("SELECT COUNT(*) FROM dead_letters WHERE topic=?", (topic,)).fetchone()[
            0
        ]
    return {
        "topic": topic,
        "pending": pending,
        "processing": processing,
        "acknowledged": acked,
        "dead_letters": dlq,
    }


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
