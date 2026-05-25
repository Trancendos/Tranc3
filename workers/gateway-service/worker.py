"""
Trancendos gateway-service — Self-Hosted Worker
================================================
Unified aggregation gateway for the Tranc3 AI Platform.
Proxies and caches data from all P4 ecosystem workers into
a single API surface for the dashboard and external consumers.

Features:
    - Aggregated /api/overview with all platform metrics
    - Per-domain endpoints: /api/agents, /api/models, /api/workflows, /api/security
    - SSE /events stream for real-time dashboard updates
    - WebSocket /ws for bidirectional real-time communication
    - 5-second cache TTL with background refresh
    - Circuit breaker per upstream worker

Port: 8040
Zero-cost: FastAPI + httpx + SQLite cache, no external deps.
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
from pathlib import Path as PathLib
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("GATEWAY_DB_PATH", "data/gateway.db")
PORT = int(os.environ.get("GATEWAY_PORT", "8040"))
CACHE_TTL = int(os.environ.get("GATEWAY_CACHE_TTL", "5"))

UPSTREAM_WORKERS = {
    "vault": {"port": 8030, "health": "/health", "stats": "/stats"},
    "topology": {"port": 8031, "health": "/health", "stats": "/stats"},
    "ledger": {"port": 8032, "health": "/health", "stats": "/stats"},
    "model_router": {"port": 8033, "health": "/health", "stats": "/stats"},
    "workflow": {"port": 8034, "health": "/health", "stats": "/stats"},
    "benchmark": {"port": 8035, "health": "/health", "stats": "/stats"},
    "langchain": {"port": 8036, "health": "/health", "stats": "/stats"},
    "deepagents": {"port": 8037, "health": "/health", "stats": "/stats"},
}

logger = logging.getLogger("gateway-service")

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
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key     TEXT PRIMARY KEY,
            value   TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL
        );
        """
    )
    conn.close()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
_circuit_breaker: dict[str, dict[str, Any]] = {}
_connected_clients: list[WebSocket] = []


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    # Seed circuit breaker state
    for name in UPSTREAM_WORKERS:
        _circuit_breaker[name] = {
            "state": "closed",
            "failures": 0,
            "last_failure": 0.0,
            "last_success": 0.0,
        }
    yield


app = FastAPI(
    title="Tranc3 Gateway Service",
    version="0.6.0",
    lifespan=_lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Upstream Fetch with Circuit Breaker
# ---------------------------------------------------------------------------


def _base_url(worker_name: str) -> str:
    cfg = UPSTREAM_WORKERS.get(worker_name)
    if not cfg:
        return ""
    return f"http://localhost:{cfg['port']}"


def _is_circuit_open(name: str) -> bool:
    cb = _circuit_breaker.get(name, {})
    if cb.get("state") == "open":
        # Half-open after 30 seconds
        if time.time() - cb.get("last_failure", 0) > 30:
            cb["state"] = "half_open"
            return False
        return True
    return False


def _record_success(name: str) -> None:
    cb = _circuit_breaker.get(name, {})
    cb["state"] = "closed"
    cb["failures"] = 0
    cb["last_success"] = time.time()


def _record_failure(name: str) -> None:
    cb = _circuit_breaker.get(name, {})
    cb["failures"] = cb.get("failures", 0) + 1
    cb["last_failure"] = time.time()
    if cb["failures"] >= 3:
        cb["state"] = "open"


async def _fetch_worker(name: str, path: str, timeout: float = 3.0) -> dict | None:
    """Fetch data from an upstream worker with circuit breaker protection."""
    if _is_circuit_open(name):
        return None

    url = f"{_base_url(name)}{path}"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(url, timeout=timeout)
            if r.status_code == 200:
                _record_success(name)
                return r.json()
            _record_failure(name)
            return None
    except Exception:
        _record_failure(name)
        return None


async def _fetch_all_stats() -> dict[str, Any]:
    """Fetch stats from all upstream workers concurrently."""
    tasks = {}
    for name, cfg in UPSTREAM_WORKERS.items():
        tasks[name] = _fetch_worker(name, cfg["stats"])

    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    output = {}
    for name, result in zip(tasks.keys(), results, strict=False):
        if isinstance(result, Exception) or result is None:
            output[name] = {"status": "unreachable"}
        else:
            output[name] = result
            output[name]["status"] = "ok"
    return output


async def _fetch_worker_list(name: str, path: str) -> list:
    """Fetch a list endpoint from an upstream worker."""
    data = await _fetch_worker(name, path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, dict):
        # Some workers return {"agents": [...], "total": N} etc.
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


# ---------------------------------------------------------------------------
# Cache Layer
# ---------------------------------------------------------------------------


async def _get_cached_or_fetch(key: str, fetcher, ttl: float | None = None) -> Any:
    """Simple in-memory cache with TTL."""
    if ttl is None:
        ttl = CACHE_TTL
    now = time.time()
    if key in _cache:
        cached_time, cached_data = _cache[key]
        if now - cached_time < ttl:
            return cached_data
    data = await fetcher()
    _cache[key] = (now, data)
    return data


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class EventCreate(BaseModel):
    source: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class TopologySwitch(BaseModel):
    mode: str


class AgentCreate(BaseModel):
    name: str
    capabilities: list[str] = Field(default_factory=list)
    model_binding: str | None = None


class WorkflowCreate(BaseModel):
    name: str
    steps: list[dict[str, Any]]
    step_dependencies: list[list[str]] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "gateway-service",
        "version": "0.6.0",
        "upstream_workers": len(UPSTREAM_WORKERS),
        "connected_clients": len(_connected_clients),
    }


@app.get("/stats")
async def stats():
    all_stats = await _get_cached_or_fetch("all_stats", _fetch_all_stats)
    reachable = sum(1 for v in all_stats.values() if v.get("status") == "ok")
    return {
        "upstream_workers": len(UPSTREAM_WORKERS),
        "reachable": reachable,
        "unreachable": len(UPSTREAM_WORKERS) - reachable,
        "connected_clients": len(_connected_clients),
        "cache_entries": len(_cache),
        "circuit_breakers": {k: v["state"] for k, v in _circuit_breaker.items()},
    }


# ---------------------------------------------------------------------------
# Aggregated Platform API
# ---------------------------------------------------------------------------


@app.get("/api/overview")
async def api_overview():
    """Master overview of the entire Tranc3 AI Platform."""
    all_stats = await _get_cached_or_fetch("all_stats", _fetch_all_stats)

    # Aggregate key metrics
    vault = all_stats.get("vault", {})
    topology = all_stats.get("topology", {})
    model_router = all_stats.get("model_router", {})
    workflow = all_stats.get("workflow", {})
    benchmark = all_stats.get("benchmark", {})
    langchain = all_stats.get("langchain", {})
    deepagents = all_stats.get("deepagents", {})
    ledger = all_stats.get("ledger", {})

    reachable = sum(1 for v in all_stats.values() if v.get("status") == "ok")

    return {
        "platform": {
            "name": "Tranc3",
            "version": "0.6.0",
            "status": "operational"
            if reachable >= 6
            else "degraded"
            if reachable >= 3
            else "critical",
            "uptime_seconds": int(time.time()),
        },
        "services": {
            "total": len(UPSTREAM_WORKERS),
            "healthy": reachable,
            "degraded": len(UPSTREAM_WORKERS) - reachable,
        },
        "ai": {
            "active_models": model_router.get("total_models", 0),
            "total_workflows": workflow.get("total_workflows", 0),
            "active_agents": deepagents.get("agents", {}).get("active", 0),
            "total_agents": deepagents.get("agents", {}).get("total", 0),
            "benchmark_suites": benchmark.get("total_suites", 0),
            "chain_templates": langchain.get("prompt_templates", 0),
        },
        "security": {
            "active_secrets": vault.get("active_secrets", 0),
            "audit_entries": vault.get("audit_entries", 0),
            "chain_valid": ledger.get("chain_valid", False),
            "ledger_entries": ledger.get("total_entries", 0),
            "open_leaks": vault.get("open_leaks", 0),
        },
        "infrastructure": {
            "topology_mode": topology.get("current_mode", "UNKNOWN"),
            "registered_nodes": topology.get("total_nodes", 0),
            "healthy_nodes": topology.get("healthy_nodes", 0),
        },
        "workers": all_stats,
    }


@app.get("/api/agents")
async def api_agents():
    """Agent fleet overview from deepagents-orchestrator."""
    stats_data = await _fetch_worker("deepagents", "/stats")
    agents_list = await _fetch_worker_list("deepagents", "/agents")
    skills_list = await _fetch_worker_list("deepagents", "/skills")
    tasks_list = await _fetch_worker_list("deepagents", "/tasks")

    return {
        "agents": agents_list,
        "skills": skills_list,
        "tasks": tasks_list,
        "stats": stats_data or {},
        "total_agents": len(agents_list),
        "total_skills": len(skills_list),
        "total_tasks": len(tasks_list),
    }


@app.get("/api/models")
async def api_models():
    """Model hub overview from model-router-service."""
    stats_data = await _fetch_worker("model_router", "/stats")
    models_list = await _fetch_worker_list("model_router", "/models")
    return {
        "models": models_list,
        "stats": stats_data or {},
        "total_models": len(models_list),
    }


@app.get("/api/workflows")
async def api_workflows():
    """Workflow studio overview from workflow-engine-service."""
    stats_data = await _fetch_worker("workflow", "/stats")
    workflows_list = await _fetch_worker_list("workflow", "/workflows")
    return {
        "workflows": workflows_list,
        "stats": stats_data or {},
        "total_workflows": len(workflows_list),
    }


@app.get("/api/security")
async def api_security():
    """Security vault overview from vault + ledger + topology."""
    vault_stats = await _fetch_worker("vault", "/stats")
    ledger_stats = await _fetch_worker("ledger", "/stats")
    topology_stats = await _fetch_worker("topology", "/stats")
    secrets_list = await _fetch_worker_list("vault", "/secrets")
    audit_list = await _fetch_worker_list("vault", "/audit")
    ledger_entries = await _fetch_worker_list("ledger", "/entries")

    return {
        "vault": {
            "secrets": secrets_list,
            "audit": audit_list,
            "stats": vault_stats or {},
        },
        "ledger": {
            "entries": ledger_entries[:50],  # Last 50
            "stats": ledger_stats or {},
        },
        "topology": {
            "stats": topology_stats or {},
        },
    }


@app.get("/api/audit")
async def api_audit():
    """Audit timeline from ledger + vault."""
    ledger_entries = await _fetch_worker_list("ledger", "/entries")
    vault_audit = await _fetch_worker_list("vault", "/audit")
    return {
        "ledger": ledger_entries[-50:],
        "vault_audit": vault_audit[-50:],
        "total_ledger": len(ledger_entries),
        "total_vault_audit": len(vault_audit),
    }


# ---------------------------------------------------------------------------
# Action Endpoints (proxy writes to workers)
# ---------------------------------------------------------------------------


@app.post("/api/agents")
async def create_agent(body: AgentCreate):
    """Create a new AI agent via the deepagents orchestrator."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('deepagents')}/agents",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await _broadcast_event("agent_created", data)
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "DeepAgents service unavailable") from None


@app.post("/api/workflows")
async def create_workflow(body: WorkflowCreate):
    """Create a new workflow via the workflow engine."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('workflow')}/workflows",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await _broadcast_event("workflow_created", data)
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Workflow engine unavailable") from None


@app.put("/api/topology/mode")
async def switch_topology(body: TopologySwitch):
    """Switch topology mode via the topology service."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.put(
                f"{_base_url('topology')}/mode",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code == 200:
                data = r.json()
                await _broadcast_event("topology_changed", data)
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Topology service unavailable") from None


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str):
    """Execute a workflow run."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('workflow')}/workflows/{workflow_id}/run",
                json={},
                timeout=10.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await _broadcast_event("workflow_run", data)
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Workflow engine unavailable") from None


# ---------------------------------------------------------------------------
# SSE Events Stream
# ---------------------------------------------------------------------------


async def _event_generator():
    """Generate SSE events for connected clients."""
    while True:
        try:
            all_stats = await _fetch_all_stats()
            event_data = {
                "type": "platform_update",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data": all_stats,
            }
            yield {
                "event": "update",
                "data": json.dumps(event_data),
            }
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(10)


@app.get("/events")
async def sse_events():
    """SSE endpoint for real-time dashboard updates."""
    return EventSourceResponse(_event_generator())


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


async def _broadcast_event(event_type: str, payload: Any):
    """Broadcast an event to all connected WebSocket clients."""
    message = json.dumps(
        {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
        }
    )
    disconnected = []
    for ws in _connected_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        _connected_clients.remove(ws)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for bidirectional real-time communication."""
    await websocket.accept()
    _connected_clients.append(websocket)
    try:
        # Send initial overview
        overview = await _get_cached_or_fetch("all_stats", _fetch_all_stats)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "initial_state",
                    "data": overview,
                }
            )
        )

        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "subscribe":
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "subscribed",
                                "channels": msg.get("channels", ["all"]),
                            }
                        )
                    )
                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg_type == "get_overview":
                    overview = await _get_cached_or_fetch("all_stats", _fetch_all_stats)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "overview",
                                "data": overview,
                            }
                        )
                    )
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "Invalid JSON",
                        }
                    )
                )
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _connected_clients:
            _connected_clients.remove(websocket)


# ---------------------------------------------------------------------------
# Dashboard Static Files (serves the new AI Platform UI)
# ---------------------------------------------------------------------------

DASHBOARD_DIR = PathLib(__file__).parent.parent.parent / "dashboard"


@app.get("/dashboard/{path:path}")
async def serve_dashboard(path: str = "index.html"):
    """Serve the AI Platform dashboard static files."""
    file_path = DASHBOARD_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    raise HTTPException(404, "File not found") from None


@app.get("/dashboard")
async def serve_dashboard_index():
    """Serve the dashboard index."""
    return FileResponse(str(DASHBOARD_DIR / "index.html"))


# ---------------------------------------------------------------------------
# Event Persistence
# ---------------------------------------------------------------------------


@app.post("/events")
async def create_event(body: EventCreate):
    """Record a platform event."""
    eid = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    db = _get_db()
    try:
        db.execute(
            "INSERT INTO events (id, source, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (eid, body.source, body.event_type, json.dumps(body.payload), now),
        )
        db.commit()
    finally:
        db.close()
    await _broadcast_event(body.event_type, body.payload)
    return {"id": eid, "source": body.source, "event_type": body.event_type, "created_at": now}


@app.get("/events/history")
async def event_history(limit: int = Query(50, ge=1, le=500)):
    """Retrieve recent platform events."""
    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()
