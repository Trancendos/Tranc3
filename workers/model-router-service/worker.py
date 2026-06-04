"""
Trancendos model-router-service — Self-Hosted Worker
======================================================
Smart adaptive multi-model routing with zero-cost enforcement.

Features:
    - 4 routing strategies: cost_aware, latency_aware, priority, round_robin
    - Circuit breaker: auto-deactivates unhealthy models
    - Zero-cost enforcement: only routes to is_free=1 models
    - Model health tracking and latency monitoring
    - Free-tier model seeding on startup

Port: 8033
Zero-cost: FastAPI + SQLite, routes to free-tier LLMs only.
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

from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "model-router-service"
PORT = 8033

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("MODEL_ROUTER_DB_PATH", "data/model_router.db")

logger = logging.getLogger("model-router-service")

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3_connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            provider TEXT NOT NULL DEFAULT '',
            model_id TEXT NOT NULL DEFAULT '',
            is_free INTEGER NOT NULL DEFAULT 1,
            capabilities TEXT NOT NULL DEFAULT '[]',
            cost_per_1k_tokens REAL DEFAULT 0.0,
            avg_latency_ms REAL DEFAULT 0.0,
            priority INTEGER DEFAULT 5,
            is_active INTEGER NOT NULL DEFAULT 1,
            total_requests INTEGER DEFAULT 0,
            failed_requests INTEGER DEFAULT 0,
            last_used TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()
    _seed_default_models()


def _seed_default_models() -> None:
    conn = _get_db()
    count = conn.execute("SELECT COUNT(*) as c FROM models").fetchone()["c"]
    if count > 0:
        conn.close()
        return

    now = _now()
    defaults = [
        (
            "gemini-2.0-flash",
            "google",
            "gemini-2.0-flash",
            1,
            ["chat", "completion", "vision"],
            0.0,
            120,
            8,
        ),
        (
            "gemini-2.5-pro",
            "google",
            "gemini-2.5-pro-preview-05-06",
            1,
            ["chat", "completion", "reasoning", "vision"],
            0.0,
            250,
            7,
        ),
        # gpt-4o-mini removed — OpenAI is a paid API (~$0.00015/1k tokens); zero-cost violation
        ("llama3.1:8b", "ollama", "llama3.1:8b", 1, ["chat", "completion"], 0.0, 200, 5),
        (
            "qwen2.5-coder:7b",
            "ollama",
            "qwen2.5-coder:7b",
            1,
            ["chat", "completion", "coding"],
            0.0,
            220,
            5,
        ),
        ("nomic-embed-text", "ollama", "nomic-embed-text", 1, ["embedding"], 0.0, 50, 3),
        # Cerebras free tier — 60k TPM / 1M TPD; zero-cost
        (
            "cerebras-llama3.3-70b",
            "cerebras",
            "llama3.3-70b",
            1,
            ["chat", "completion", "reasoning"],
            0.0,
            180,
            6,
        ),
    ]
    for name, provider, model_id, is_free, caps, cost, latency, priority in defaults:
        mid = _new_id()
        try:
            conn.execute(
                "INSERT INTO models (id, name, provider, model_id, is_free, capabilities, cost_per_1k_tokens, avg_latency_ms, priority, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    mid,
                    name,
                    provider,
                    model_id,
                    is_free,
                    json.dumps(caps),
                    cost,
                    latency,
                    priority,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError:
            pass
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ModelRegister(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    provider: str = ""
    model_id: str = ""
    is_free: bool = True
    capabilities: List[str] = Field(default_factory=list)
    cost_per_1k_tokens: float = 0.0
    avg_latency_ms: float = 0.0
    priority: int = 5


class RouteRequest(BaseModel):
    prompt: str = ""
    strategy: str = "round_robin"
    capabilities: List[str] = Field(default_factory=list)
    max_cost: float = 0.0


class HealthReport(BaseModel):
    status: str = "healthy"
    latency_ms: float = 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _select_model(models: list, strategy: str) -> Optional[dict]:
    """Select a model based on routing strategy."""
    if not models:
        return None

    if strategy == "cost_aware":
        return min(models, key=lambda m: m["cost_per_1k_tokens"])
    elif strategy == "latency_aware":
        return min(models, key=lambda m: m["avg_latency_ms"])
    elif strategy == "priority":
        return max(models, key=lambda m: m["priority"])
    else:  # round_robin
        return models[0]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("model-router-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 Model Router Service", version="0.1.0", lifespan=_lifespan)
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
    return {
        "status": "ok",
        "service": "model-router-service",
        "port": 8033,
        "entity": health_entity_block(8033, "model-router-service"),
    }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


@_router.post("/models", status_code=201)
async def register_model(body: ModelRegister):
    conn = _get_db()
    now = _now()
    mid = _new_id()
    try:
        conn.execute(
            "INSERT INTO models (id, name, provider, model_id, is_free, capabilities, cost_per_1k_tokens, avg_latency_ms, priority, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                mid,
                body.name,
                body.provider,
                body.model_id,
                1 if body.is_free else 0,
                json.dumps(body.capabilities),
                body.cost_per_1k_tokens,
                body.avg_latency_ms,
                body.priority,
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Model '{body.name}' already exists") from None
    conn.close()
    return {
        "id": mid,
        "name": body.name,
        "provider": body.provider,
        "is_free": body.is_free,
        "created_at": now,
    }


@_router.get("/models")
async def list_models(
    active_only: bool = True, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM models WHERE 1=1"
    params: list = []
    if active_only:
        q += " AND is_active=1"
    q += " ORDER BY priority DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@_router.get("/models/{model_id}")
async def get_model(model_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM models WHERE id=?", (model_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Model not found") from None
    return dict(row)


@_router.delete("/models/{model_id}", status_code=204)
async def deregister_model(model_id: str):
    conn = _get_db()
    cur = conn.execute("DELETE FROM models WHERE id=?", (model_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Model not found") from None


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------


@_router.post("/route")
async def route_request(body: RouteRequest):
    conn = _get_db()
    q = "SELECT * FROM models WHERE is_active=1 AND is_free=1"
    params: list = []

    if body.capabilities:
        # Filter for models that have any of the requested capabilities
        rows = conn.execute(q, params).fetchall()
        models = []
        for r in rows:
            caps = json.loads(r["capabilities"])
            if any(c in caps for c in body.capabilities):
                models.append(dict(r))
    else:
        models = [dict(r) for r in conn.execute(q, params).fetchall()]

    conn.close()

    if not models:
        raise HTTPException(404, "No available models match the criteria") from None

    selected = _select_model(models, body.strategy)

    if not selected:
        raise HTTPException(404, "No model selected") from None

    # Update last_used
    conn2 = _get_db()
    conn2.execute(
        "UPDATE models SET last_used=?, total_requests=total_requests+1 WHERE id=?",
        (_now(), selected["id"]),
    )
    conn2.commit()
    conn2.close()

    return {
        "model": selected["name"],
        "model_id": selected["id"],
        "provider": selected["provider"],
        "strategy": body.strategy,
        "is_free": bool(selected["is_free"]),
    }


# ---------------------------------------------------------------------------
# Health Reporting
# ---------------------------------------------------------------------------


@_router.put("/models/{model_id}/health")
async def report_health(model_id: str, body: HealthReport):
    conn = _get_db()
    now = _now()
    if body.status == "unhealthy":
        # Circuit breaker: deactivate unhealthy model
        conn.execute("UPDATE models SET is_active=0, updated_at=? WHERE id=?", (now, model_id))
    else:
        conn.execute(
            "UPDATE models SET avg_latency_ms=?, updated_at=? WHERE id=?",
            (body.latency_ms, now, model_id),
        )
    conn.commit()
    conn.close()
    return {"id": model_id, "status": body.status}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def get_stats():
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM models").fetchone()["c"]
    free = conn.execute("SELECT COUNT(*) as c FROM models WHERE is_free=1").fetchone()["c"]
    active = conn.execute("SELECT COUNT(*) as c FROM models WHERE is_active=1").fetchone()["c"]
    total_requests = conn.execute(
        "SELECT COALESCE(SUM(total_requests), 0) as c FROM models",
    ).fetchone()["c"]
    conn.close()
    return {
        "total_models": total,
        "free_models": free,
        "active_models": active,
        "total_requests": total_requests,
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

    uvicorn.run(app, host="0.0.0.0", port=8033)
