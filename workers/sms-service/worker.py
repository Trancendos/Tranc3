"""
Trancendos sms-service — Self-Hosted Worker
============================================
SMS outbox queue with pluggable providers:
  - log: print to stdout (zero-cost, dev/test default)
  - webhook: POST to a configurable URL (zero-cost relay)
  - textbelt: textbelt.com free tier (1 SMS/day free key)

Messages are queued in SQLite and a background loop drains them.

Port: 8019
Zero-cost: FastAPI + SQLite + httpx, no mandatory paid deps.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.entities.health_metadata import health_entity_block

WORKER_PORT = 8019
WORKER_NAME = "sms-service"
DB_PATH = Path(__file__).parent / "data" / "sms.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

SMS_PROVIDER = os.getenv("SMS_PROVIDER", "log")  # log | webhook | textbelt
WEBHOOK_URL = os.getenv("SMS_WEBHOOK_URL", "")
TEXTBELT_KEY = os.getenv("TEXTBELT_KEY", "textbelt")  # "textbelt" = free (1/day)
DRAIN_INTERVAL = int(os.getenv("SMS_DRAIN_INTERVAL", "15"))
MAX_RETRIES = 3

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS outbox (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                to_number   TEXT NOT NULL,
                message     TEXT NOT NULL,
                status      TEXT NOT NULL DEFAULT 'pending',
                provider    TEXT NOT NULL,
                retry_count INTEGER NOT NULL DEFAULT 0,
                provider_id TEXT,
                error       TEXT,
                queued_at   REAL NOT NULL,
                sent_at     REAL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sms_status ON outbox(status, queued_at)")
        conn.commit()


async def _send_log(to: str, message: str) -> str:
    logger.info("SMS [log] to=%s: %s", to, message)
    return "log-ok"


async def _send_webhook(to: str, message: str) -> str:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(WEBHOOK_URL, json={"to": to, "message": message})
        resp.raise_for_status()
    return f"webhook-{resp.status_code}"


async def _send_textbelt(to: str, message: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://textbelt.com/text",
            data={"phone": to, "message": message, "key": TEXTBELT_KEY},
        )
    data = resp.json()
    if not data.get("success"):
        raise RuntimeError(data.get("error", "textbelt error"))
    return data.get("textId", "unknown")


async def _dispatch(to: str, message: str, provider: str) -> str:
    if provider == "log":
        return await _send_log(to, message)
    if provider == "webhook" and WEBHOOK_URL:
        return await _send_webhook(to, message)
    if provider == "textbelt":
        return await _send_textbelt(to, message)
    return await _send_log(to, message)


async def _drain_loop() -> None:
    while True:
        await asyncio.sleep(DRAIN_INTERVAL)
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM outbox WHERE status='pending' AND retry_count < ? ORDER BY queued_at LIMIT 20",
                (MAX_RETRIES,),
            ).fetchall()
        for row in rows:
            row = dict(row)
            try:
                provider_id = await _dispatch(row["to_number"], row["message"], row["provider"])
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE outbox SET status='sent', sent_at=?, provider_id=? WHERE id=?",
                        (time.time(), provider_id, row["id"]),
                    )
                    conn.commit()
            except Exception as exc:
                retry = row["retry_count"] + 1
                status = "failed" if retry >= MAX_RETRIES else "pending"
                with get_conn() as conn:
                    conn.execute(
                        "UPDATE outbox SET status=?, retry_count=?, error=? WHERE id=?",
                        (status, retry, str(exc), row["id"]),
                    )
                    conn.commit()
                logger.warning("SMS %d send error: %s", row["id"], exc)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SendIn(BaseModel):
    to: str
    message: str
    provider: Optional[str] = None


class BatchSendIn(BaseModel):
    messages: List[SendIn]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("sms-service DB ready (provider: %s)", SMS_PROVIDER)
    task = asyncio.create_task(_drain_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="sms-service",
    description="SMS outbox queue with pluggable providers (self-hosted)",
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
        pending = conn.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0]
        sent = conn.execute("SELECT COUNT(*) FROM outbox WHERE status='sent'").fetchone()[0]
        failed = conn.execute("SELECT COUNT(*) FROM outbox WHERE status='failed'").fetchone()[0]
    return {
        "entity": health_entity_block(8019, "sms-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "provider": SMS_PROVIDER,
        "pending": pending,
        "sent": sent,
        "failed": failed,
    }


@_router.post("/send", status_code=202)
async def send_sms(req: SendIn):
    provider = req.provider or SMS_PROVIDER
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO outbox (to_number, message, provider, queued_at) VALUES (?,?,?,?)",
            (req.to, req.message, provider, now),
        )
        conn.commit()
    return {"id": cur.lastrowid, "status": "queued", "to": req.to, "provider": provider}


@_router.post("/send/batch", status_code=202)
async def send_batch(req: BatchSendIn):
    now = time.time()
    rows = [(m.to, m.message, m.provider or SMS_PROVIDER, now) for m in req.messages]
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO outbox (to_number, message, provider, queued_at) VALUES (?,?,?,?)",
            rows,
        )
        conn.commit()
    return {"queued": len(rows)}


@_router.get("/outbox")
async def list_outbox(
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
):
    clauses, params = [], []
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM outbox {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT id, to_number, message, status, provider, retry_count, queued_at, sent_at, error FROM outbox {where} ORDER BY queued_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "messages": [dict(r) for r in rows]}


@_router.post("/outbox/{sms_id}/retry")
async def retry_sms(sms_id: int):
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM outbox WHERE id = ?", (sms_id,)).fetchone():
            raise HTTPException(status_code=404, detail="SMS not found")
        conn.execute(
            "UPDATE outbox SET status='pending', retry_count=0, error=NULL WHERE id=?",
            (sms_id,),
        )
        conn.commit()
    return {"retrying": sms_id}


@_router.get("/stats")
async def stats():
    with get_conn() as conn:
        by_status = conn.execute(
            "SELECT status, COUNT(*) as c FROM outbox GROUP BY status",
        ).fetchall()
        by_provider = conn.execute(
            "SELECT provider, COUNT(*) as c FROM outbox GROUP BY provider",
        ).fetchall()
    return {
        "by_status": [dict(r) for r in by_status],
        "by_provider": [dict(r) for r in by_provider],
    }


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
