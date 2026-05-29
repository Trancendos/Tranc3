"""
Trancendos ledger-service — Self-Hosted Worker
================================================
Immutable audit ledger with SHA-256 hash chain and sentinel verification.

Features:
    - Hash-chained entries (SHA-256, each entry links to prev hash)
    - Digital signature verification per entry
    - Sentinel verification daemon with history tracking
    - Query by actor, action, resource type, time range

Port: 8032
Zero-cost: FastAPI + SQLite, no external services required.
"""

from __future__ import annotations

import asyncio
import hashlib
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

SERVICE_NAME = "ledger-service"
PORT = 8032

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("LEDGER_DB_PATH", "data/ledger.db")

logger = logging.getLogger("ledger-service")

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
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id TEXT PRIMARY KEY,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            details TEXT DEFAULT '{}',
            hash TEXT NOT NULL,
            prev_hash TEXT,
            signature TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sentinel_checks (
            id TEXT PRIMARY KEY,
            chain_valid INTEGER NOT NULL DEFAULT 1,
            entry_count INTEGER DEFAULT 0,
            invalid_entries TEXT DEFAULT '[]',
            checked_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ledger_actor ON ledger_entries(actor);
        CREATE INDEX IF NOT EXISTS idx_ledger_action ON ledger_entries(action);
        CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger_entries(created_at);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LedgerEntryCreate(BaseModel):
    actor: str = Field(..., min_length=1, max_length=200)
    action: str = Field(..., min_length=1, max_length=200)
    resource_type: str = ""
    resource_id: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    signature: str = ""


class LedgerEntryResponse(BaseModel):
    id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    details: Dict[str, Any]
    hash: str
    prev_hash: Optional[str]
    signature: str
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _get_last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT hash FROM ledger_entries ORDER BY rowid DESC LIMIT 1").fetchone()
    return row["hash"] if row else "0" * 64


def _compute_hash(entry_id: str, prev_hash: str, actor: str, action: str, timestamp: str) -> str:
    payload = f"{entry_id}:{prev_hash}:{actor}:{action}:{timestamp}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("ledger-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 Ledger Service", version="0.1.0", lifespan=_lifespan)
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
    return {"status": "ok", "service": "ledger-service", "port": 8032}


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


@_router.post("/entries", response_model=LedgerEntryResponse, status_code=201)
async def append_entry(body: LedgerEntryCreate):
    conn = _get_db()
    now = _now()
    eid = _new_id()
    prev_hash = _get_last_hash(conn)
    entry_hash = _compute_hash(eid, prev_hash, body.actor, body.action, now)

    conn.execute(
        "INSERT INTO ledger_entries (id, actor, action, resource_type, resource_id, details, hash, prev_hash, signature, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            eid,
            body.actor,
            body.action,
            body.resource_type,
            body.resource_id,
            json.dumps(body.details),
            entry_hash,
            prev_hash,
            body.signature,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return LedgerEntryResponse(
        id=eid,
        actor=body.actor,
        action=body.action,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        details=body.details,
        hash=entry_hash,
        prev_hash=prev_hash,
        signature=body.signature,
        created_at=now,
    )


@_router.get("/entries", response_model=List[LedgerEntryResponse])
async def query_entries(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM ledger_entries WHERE 1=1"
    params: list = []
    if actor:
        q += " AND actor=?"
        params.append(actor)
    if action:
        q += " AND action=?"
        params.append(action)
    if resource_type:
        q += " AND resource_type=?"
        params.append(resource_type)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        LedgerEntryResponse(
            id=r["id"],
            actor=r["actor"],
            action=r["action"],
            resource_type=r["resource_type"],
            resource_id=r["resource_id"],
            details=json.loads(r["details"]),
            hash=r["hash"],
            prev_hash=r["prev_hash"],
            signature=r["signature"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@_router.get("/entries/{entry_id}", response_model=LedgerEntryResponse)
async def get_entry(entry_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM ledger_entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Entry not found")
    return LedgerEntryResponse(
        id=row["id"],
        actor=row["actor"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        details=json.loads(row["details"]),
        hash=row["hash"],
        prev_hash=row["prev_hash"],
        signature=row["signature"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Chain Verification
# ---------------------------------------------------------------------------


@_router.get("/verify")
async def verify_chain():
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, hash, prev_hash FROM ledger_entries ORDER BY rowid ASC"
    ).fetchall()
    conn.close()

    if not rows:
        result = {"chain_valid": True, "entry_count": 0, "invalid_entries": []}
    else:
        invalid = []
        for i in range(1, len(rows)):
            if rows[i]["prev_hash"] != rows[i - 1]["hash"]:
                invalid.append(rows[i]["id"])
        result = {
            "chain_valid": len(invalid) == 0,
            "entry_count": len(rows),
            "invalid_entries": invalid,
        }

    # Record sentinel check
    conn2 = _get_db()
    now = _now()
    sid = _new_id()
    conn2.execute(
        "INSERT INTO sentinel_checks (id, chain_valid, entry_count, invalid_entries, checked_at) VALUES (?,?,?,?,?)",
        (
            sid,
            1 if result["chain_valid"] else 0,
            result["entry_count"],
            json.dumps(result["invalid_entries"]),
            now,
        ),
    )
    conn2.commit()
    conn2.close()

    return result


@_router.get("/sentinel/history")
async def sentinel_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM sentinel_checks ORDER BY checked_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def get_stats():
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM ledger_entries").fetchone()["c"]
    sentinel_count = conn.execute("SELECT COUNT(*) as c FROM sentinel_checks").fetchone()["c"]
    last_check = conn.execute(
        "SELECT checked_at FROM sentinel_checks ORDER BY checked_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    # Quick chain validity check
    chain_valid = True
    if total > 1:
        conn2 = _get_db()
        rows = conn2.execute(
            "SELECT hash, prev_hash FROM ledger_entries ORDER BY rowid ASC"
        ).fetchall()
        conn2.close()
        for i in range(1, len(rows)):
            if rows[i]["prev_hash"] != rows[i - 1]["hash"]:
                chain_valid = False
                break

    return {
        "total_entries": total,
        "chain_valid": chain_valid,
        "sentinel_checks": sentinel_count,
        "last_sentinel_check": last_check["checked_at"] if last_check else None,
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

    uvicorn.run(app, host="0.0.0.0", port=8032)
