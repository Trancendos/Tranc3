"""
Trancendos topology-service — Self-Hosted Worker
=================================================
Adaptive infrastructure topology management with automatic failover.

Features:
    - TopologyMode: TRUE_NAS, HYBRID, CLOUD_ONLY
    - Automatic failover: TRUE_NAS → HYBRID → CLOUD_ONLY
    - Node registration and health tracking
    - Migration orchestration between modes
    - History tracking for all mode changes

Port: 8031
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
from enum import Enum
from typing import List, Optional

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

from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "topology-service"
PORT = 8031

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("TOPOLOGY_DB_PATH", "data/topology.db")
FAILOVER_ORDER = ["TRUE_NAS", "HYBRID", "CLOUD_ONLY"]

logger = logging.getLogger("topology-service")


class TopologyMode(str, Enum):
    TRUE_NAS = "TRUE_NAS"
    HYBRID = "HYBRID"
    CLOUD_ONLY = "CLOUD_ONLY"


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
        CREATE TABLE IF NOT EXISTS topology_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            current_mode TEXT NOT NULL DEFAULT 'TRUE_NAS',
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS topology_history (
            id TEXT PRIMARY KEY,
            from_mode TEXT NOT NULL,
            to_mode TEXT NOT NULL,
            reason TEXT DEFAULT '',
            triggered_by TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS node_health (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            node_type TEXT NOT NULL DEFAULT 'nas',
            endpoint TEXT DEFAULT '',
            capabilities TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'healthy',
            latency_ms REAL DEFAULT 0.0,
            last_check TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS migrations (
            id TEXT PRIMARY KEY,
            from_mode TEXT NOT NULL,
            to_mode TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            progress REAL DEFAULT 0.0,
            total_steps INTEGER DEFAULT 0,
            completed_steps INTEGER DEFAULT 0,
            error_message TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    # Seed initial state
    state = conn.execute("SELECT * FROM topology_state").fetchone()
    if not state:
        conn.execute(
            "INSERT INTO topology_state (id, current_mode, updated_at) VALUES (1, 'TRUE_NAS', ?)",
            (_now(),),
        )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ModeSwitchRequest(BaseModel):
    mode: str
    reason: str = ""


class NodeRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    node_type: str = "nas"
    endpoint: str = ""
    capabilities: List[str] = Field(default_factory=list)


class NodeHealthUpdate(BaseModel):
    status: str = "healthy"
    latency_ms: float = 0.0


class MigrationCreate(BaseModel):
    from_mode: str
    to_mode: str


class MigrationProgressUpdate(BaseModel):
    progress: float = 0.0
    completed_steps: int = 0
    error_message: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _get_current_mode(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT current_mode FROM topology_state WHERE id=1").fetchone()
    return row["current_mode"] if row else "TRUE_NAS"


def _set_current_mode(
    conn: sqlite3.Connection, mode: str, reason: str = "", triggered_by: str = "manual"
) -> None:
    now = _now()
    prev = _get_current_mode(conn)
    conn.execute("UPDATE topology_state SET current_mode=?, updated_at=? WHERE id=1", (mode, now))
    hid = _new_id()
    conn.execute(
        "INSERT INTO topology_history (id, from_mode, to_mode, reason, triggered_by, created_at) VALUES (?,?,?,?,?,?)",
        (hid, prev, mode, reason, triggered_by, now),
    )


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("topology-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 Topology Service", version="0.1.0", lifespan=_lifespan)
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
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "topology-service", "port": 8031}


# ---------------------------------------------------------------------------
# Mode Management
# ---------------------------------------------------------------------------


@_router.get("/mode")
async def get_current_mode():
    conn = _get_db()
    mode = _get_current_mode(conn)
    conn.close()
    return {"mode": mode}


@_router.put("/mode")
async def switch_mode(body: ModeSwitchRequest):
    try:
        target = TopologyMode(body.mode)
    except ValueError:
        raise HTTPException(
            400, f"Invalid mode '{body.mode}'. Must be one of {[m.value for m in TopologyMode]}"
        ) from None

    conn = _get_db()
    _set_current_mode(conn, target.value, body.reason, "manual")
    conn.commit()
    conn.close()
    return {"mode": target.value, "reason": body.reason}


@_router.get("/mode/history")
async def get_mode_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM topology_history ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


@_router.post("/nodes", status_code=201)
async def register_node(body: NodeRegister):
    conn = _get_db()
    now = _now()
    nid = _new_id()
    try:
        conn.execute(
            "INSERT INTO node_health (id, name, node_type, endpoint, capabilities, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (
                nid,
                body.name,
                body.node_type,
                body.endpoint,
                json.dumps(body.capabilities),
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Node '{body.name}' already exists") from None
    conn.close()
    return {
        "id": nid,
        "name": body.name,
        "node_type": body.node_type,
        "status": "healthy",
        "created_at": now,
    }


@_router.get("/nodes")
async def list_nodes(
    status: Optional[str] = None, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)
):
    conn = _get_db()
    q = "SELECT * FROM node_health WHERE 1=1"
    params: list = []
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@_router.put("/nodes/{node_id}/health")
async def update_node_health(node_id: str, body: NodeHealthUpdate):
    conn = _get_db()
    now = _now()
    cur = conn.execute(
        "UPDATE node_health SET status=?, latency_ms=?, last_check=?, updated_at=? WHERE id=?",
        (body.status, body.latency_ms, now, now, node_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Node not found") from None
    return {"id": node_id, "status": body.status, "latency_ms": body.latency_ms}


@_router.delete("/nodes/{node_id}", status_code=204)
async def deregister_node(node_id: str):
    conn = _get_db()
    cur = conn.execute("DELETE FROM node_health WHERE id=?", (node_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Node not found") from None


# ---------------------------------------------------------------------------
# Migrations
# ---------------------------------------------------------------------------


@_router.post("/migrations", status_code=201)
async def create_migration(body: MigrationCreate):
    conn = _get_db()
    now = _now()
    mid = _new_id()
    conn.execute(
        "INSERT INTO migrations (id, from_mode, to_mode, created_at, updated_at) VALUES (?,?,?,?,?,?)",
        (mid, body.from_mode, body.to_mode, now, now),
    )
    conn.commit()
    conn.close()
    return {
        "id": mid,
        "from_mode": body.from_mode,
        "to_mode": body.to_mode,
        "status": "pending",
        "created_at": now,
    }


@_router.get("/migrations")
async def list_migrations(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM migrations ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@_router.put("/migrations/{migration_id}/progress")
async def update_migration_progress(migration_id: str, body: MigrationProgressUpdate):
    conn = _get_db()
    now = _now()
    status = "completed" if body.progress >= 100.0 else "in_progress"
    cur = conn.execute(
        "UPDATE migrations SET progress=?, completed_steps=?, status=?, error_message=?, updated_at=? WHERE id=?",
        (body.progress, body.completed_steps, status, body.error_message, now, migration_id),
    )
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Migration not found") from None
    return {"id": migration_id, "progress": body.progress, "status": status}


# ---------------------------------------------------------------------------
# Failover
# ---------------------------------------------------------------------------


@_router.post("/failover")
async def trigger_failover(reason: str = "Automatic failover"):
    conn = _get_db()
    current = _get_current_mode(conn)
    try:
        idx = FAILOVER_ORDER.index(current)
        if idx >= len(FAILOVER_ORDER) - 1:
            conn.close()
            return {"mode": current, "message": "Already at highest failover level"}
        new_mode = FAILOVER_ORDER[idx + 1]
    except ValueError:
        new_mode = "HYBRID"

    _set_current_mode(conn, new_mode, reason, "failover")
    conn.commit()
    conn.close()
    return {"previous_mode": current, "new_mode": new_mode, "reason": reason}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def get_stats():
    conn = _get_db()
    mode = _get_current_mode(conn)
    total_nodes = conn.execute("SELECT COUNT(*) as c FROM node_health").fetchone()["c"]
    healthy_nodes = conn.execute(
        "SELECT COUNT(*) as c FROM node_health WHERE status='healthy'"
    ).fetchone()["c"]
    total_migrations = conn.execute("SELECT COUNT(*) as c FROM migrations").fetchone()["c"]
    conn.close()
    return {
        "current_mode": mode,
        "total_nodes": total_nodes,
        "healthy_nodes": healthy_nodes,
        "total_migrations": total_migrations,
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

    uvicorn.run(app, host="0.0.0.0", port=8031)
