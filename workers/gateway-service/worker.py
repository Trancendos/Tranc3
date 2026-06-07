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
    - JWT/OAuth2 authentication with tier-aware access (Phase 22)
    - RBAC endpoint authorization (Phase 22)
    - ABAC resource-level access decisions (Phase 22)
    - OWASP Top 10 hardening middleware (Phase 22)
    - Sentinel Station integration for cross-gateway event distribution (Phase 22.3)

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
from fastapi import FastAPI, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# Phase 22.4: Dimensional Services integration
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)

# Phase 22: Infinity Ecosystem security integration
from Dimensional.infinity.abac import ABACEngine, get_default_policies
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware, WebSocketAuthManager
from Dimensional.infinity.nomenclature import InfinityRole, Pillar, SentinelChannel, Tier
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.rbac import RBACEngine

# Phase 22.3: Sentinel Station event bus integration
from Dimensional.infinity.sentinel_station import (
    SentinelEvent,
    SharedSSEGenerator,
    get_sentinel_station,
)
from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("GATEWAY_DB_PATH", "data/gateway.db")
PORT = int(os.environ.get("GATEWAY_PORT", "8040"))
CACHE_TTL = int(os.environ.get("GATEWAY_CACHE_TTL", "5"))
_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. This service cannot validate tokens without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"',
    )
JWT_SECRET: str = _jwt_secret_raw

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
# Security Engines (Phase 22)
# ---------------------------------------------------------------------------

rbac_engine = RBACEngine()
abac_engine = ABACEngine(policies=get_default_policies())
ws_auth_manager = WebSocketAuthManager(
    jwt_secret=JWT_SECRET,
    max_connections=int(os.environ.get("WS_MAX_CONNECTIONS", "1000")),
    heartbeat_interval=int(os.environ.get("WS_HEARTBEAT_INTERVAL", "30")),
    idle_timeout=int(os.environ.get("WS_IDLE_TIMEOUT", "300")),
)

# ---------------------------------------------------------------------------
# Sentinel Station (Phase 22.3)
# ---------------------------------------------------------------------------

sentinel = get_sentinel_station()
sse_generator: SharedSSEGenerator | None = None

# ---------------------------------------------------------------------------
# Dimensional Services (Phase 22.4)
# ---------------------------------------------------------------------------

dimensional_registry = get_dimensional_registry()
dimensional_bus = get_dimensional_bus()
underverse_registry = get_underverse_registry()

# ---------------------------------------------------------------------------
# Phase 22.6: Smart Adaptive Intelligence for Gateway
# ---------------------------------------------------------------------------

from Dimensional.infinity.worker_integration import InfinityWorkerKit  # noqa: E402

worker_kit = InfinityWorkerKit(
    "gateway-service",
    defense_threshold=20,  # Gateway is public-facing — moderate threshold
    defense_window_seconds=300,
    defense_block_seconds=900,
)


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
        CREATE TABLE IF NOT EXISTS access_audit (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,
            tier        TEXT NOT NULL,
            endpoint    TEXT NOT NULL,
            method      TEXT NOT NULL,
            granted     INTEGER NOT NULL,
            reason      TEXT,
            timestamp   TEXT NOT NULL
        );
        """,
    )
    conn.close()


# ---------------------------------------------------------------------------
# Lifespan — starts/stops Sentinel Station
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
_circuit_breaker: dict[str, dict[str, Any]] = {}


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global sse_generator

    _init_db()
    # Seed circuit breaker state
    for name in UPSTREAM_WORKERS:
        _circuit_breaker[name] = {
            "state": "closed",
            "failures": 0,
            "last_failure": 0.0,
            "last_success": 0.0,
        }

    # Start Sentinel Station (connects to Redis or falls back)
    await sentinel.start()
    logger.info(
        "Sentinel Station started (backend: %s)",
        "redis" if sentinel.is_redis_connected else "fallback",
    )

    # Create shared SSE generator for broadcasting events
    sse_generator = SharedSSEGenerator(sentinel)
    await sse_generator.start()
    logger.info("Shared SSE generator started")

    # Start Dimensional Service Bus (Phase 22.4)
    await dimensional_bus.start()
    logger.info("Dimensional Service Bus started")

    # Phase 22.6: Start smart adaptive worker kit
    await worker_kit.startup(app, sentinel=sentinel)
    worker_kit.health.register_daemon("cache_janitor", baseline_interval=60.0)
    worker_kit.health.register_daemon("circuit_monitor", baseline_interval=30.0)
    worker_kit.health.register_daemon("gateway_reporter", baseline_interval=60.0)
    logger.info("Smart adaptive layer started for gateway-service")

    # Register gateway heartbeat with dimensional registry
    dimensional_registry.heartbeat("gateway")
    underverse_registry.heartbeat("cache_manager")
    underverse_registry.heartbeat("circuit_monitor")
    logger.info("Dimensional services heartbeat registered")

    # Background adaptive loop
    async def _bg_loop():
        while True:
            try:
                await asyncio.sleep(10)
                # Cache janitor
                if worker_kit.health.should_fire("cache_janitor"):
                    now = time.time()
                    expired = [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL]
                    for k in expired:
                        _cache.pop(k, None)
                    worker_kit.health.record_metric("gateway_cache_size", float(len(_cache)))
                    worker_kit.health.record_fire("cache_janitor")

                # Circuit monitor
                if worker_kit.health.should_fire("circuit_monitor"):
                    open_circuits = sum(
                        1 for v in _circuit_breaker.values() if v.get("state") == "open"
                    )
                    worker_kit.health.record_metric("gateway_open_circuits", float(open_circuits))
                    if open_circuits > 0:
                        worker_kit.health.update_health(max(0.3, 1.0 - open_circuits * 0.2))
                    worker_kit.health.record_fire("circuit_monitor")

                # Gateway reporter
                if worker_kit.health.should_fire("gateway_reporter"):
                    summary = worker_kit.health.get_health_summary().to_dict()
                    worker_kit.health.record_fire("gateway_reporter")
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="gateway_health_report",
                            source="gateway",
                            payload=summary,
                        ),
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Gateway background loop error: %s", exc)

    _bg_task = asyncio.create_task(_bg_loop())

    yield

    # Shutdown
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass
    await worker_kit.shutdown()
    # Shutdown Dimensional Service Bus
    await dimensional_bus.stop()
    logger.info("Dimensional Service Bus stopped")

    # Shutdown Sentinel Station
    await sentinel.stop()
    logger.info("Sentinel Station stopped")


app = FastAPI(
    title="Tranc3 Gateway Service",
    version="0.8.0",
    lifespan=_lifespan,
)

# ---------------------------------------------------------------------------
# Middleware Stack (Phase 22 — ordered outermost to innermost)
# ---------------------------------------------------------------------------

# 1. OWASP Hardening — outermost: security headers, input validation, CSRF
app.add_middleware(
    OWASPHardeningMiddleware,
    csrf_enabled=True,
    input_validation_enabled=True,
    remove_server_header=True,
)

# 2. Auth Gateway — JWT/OAuth2 authentication, sets request.state.user
app.add_middleware(
    AuthGatewayMiddleware,
    jwt_secret=JWT_SECRET,
)

# 3. CORS — innermost: must be last added (executed first)
_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Helper: Get authenticated user from request state
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> dict[str, Any]:
    """Extract the authenticated user dict from request.state (set by AuthGatewayMiddleware)."""
    user = getattr(request.state, "user", None)
    return user or {"sub": "anonymous", "tier": "human", "role": "user", "is_active": False}


def _check_rbac(request: Request, endpoint: str, method: str) -> None:
    """Check RBAC access for the given endpoint/method. Raises 403 if denied."""
    user = _get_user(request)
    if not rbac_engine.check_access(user, endpoint, method):
        try:
            audit = rbac_engine.get_audit_context(user, endpoint, method)
            _log_access_audit(audit)
        except Exception:
            logger.warning("RBAC audit logging failed for %s %s", method, endpoint)
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: insufficient permissions for {method} {endpoint}",
        )


def _check_abac(
    request: Request,
    resource_type: str,
    resource_id: str = "*",
    action: str = "read",
) -> None:
    """Check ABAC access for a resource-level decision. Raises 403 if denied."""
    user = _get_user(request)
    subject = {
        "sub": user.get("sub", "anonymous"),
        "role": user.get("role", "user"),
        "tier": user.get("tier", "human"),
        "tier_value": _tier_name_to_value(user.get("tier", "human")),
        "pillar": user.get("pillar"),
    }
    resource = {
        "type": resource_type,
        "id": resource_id,
    }
    action_attrs = {"action": action}
    environment = {"threat_level": abac_engine.threat_level.value}

    if not abac_engine.evaluate(subject, resource, action_attrs, environment):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: ABAC policy denies {action} on {resource_type}/{resource_id}",
        )


def _tier_name_to_value(tier_name: str) -> int:
    """Convert a tier name string to its numeric value."""
    try:
        return Tier[tier_name.upper()].value
    except (KeyError, AttributeError):
        return 0


def _log_access_audit(audit: dict[str, Any]) -> None:
    """Log an access audit entry to the database (OWASP A09)."""
    try:
        db = _get_db()
        eid = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        db.execute(
            "INSERT INTO access_audit (id, user_id, role, tier, endpoint, method, granted, reason, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                audit.get("user_id", "anonymous"),
                audit.get("role", "unknown"),
                audit.get("tier", "unknown"),
                audit.get("endpoint", "unknown"),
                audit.get("method", "unknown"),
                1 if audit.get("granted") else 0,
                audit.get("reason", ""),
                now,
            ),
        )
        db.commit()
        db.close()
    except Exception:
        logger.debug("Failed to write access audit", exc_info=True)


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
        "entity": health_entity_block(8040, "unknown"),
        "status": "ok",
        "service": "gateway-service",
        "version": "0.8.0",
        "upstream_workers": len(UPSTREAM_WORKERS),
        "ws_connections": ws_auth_manager.connection_count,
        "sentinel_station": {
            "running": sentinel.is_running,
            "backend": "redis" if sentinel.is_redis_connected else "fallback",
            "circuit_breaker": sentinel.circuit_breaker_state.value,
        },
        "dimensional_bus": {
            "running": dimensional_bus.is_running,
        },
    }


@app.get("/stats")
async def stats():
    all_stats = await _get_cached_or_fetch("all_stats", _fetch_all_stats)
    reachable = sum(1 for v in all_stats.values() if v.get("status") == "ok")
    return {
        "upstream_workers": len(UPSTREAM_WORKERS),
        "reachable": reachable,
        "unreachable": len(UPSTREAM_WORKERS) - reachable,
        "ws_connections": ws_auth_manager.connection_count,
        "ws_stats": ws_auth_manager.get_connection_stats(),
        "cache_entries": len(_cache),
        "circuit_breakers": {k: v["state"] for k, v in _circuit_breaker.items()},
        "abac_threat_level": abac_engine.threat_level.value,
        "abac_policy_count": len(abac_engine._policies),
        "sentinel_station": sentinel.get_stats(),
        "dimensional_bus": dimensional_bus.get_stats(),
        "dimensional_registry": dimensional_registry.get_stats(),
        "underverse": underverse_registry.get_stats(),
    }


# ---------------------------------------------------------------------------
# Aggregated Platform API (with RBAC + ABAC)
# ---------------------------------------------------------------------------


@app.get("/api/overview")
async def api_overview(request: Request):
    """Master overview of the entire Tranc3 AI Platform."""
    _check_rbac(request, "/api/overview", "GET")

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
            "version": "0.8.0",
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
async def api_agents(request: Request):
    """Agent fleet overview from deepagents-orchestrator."""
    _check_rbac(request, "/api/agents", "GET")
    _check_abac(request, "agent", action="read")

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
async def api_models(request: Request):
    """Model hub overview from model-router-service."""
    _check_rbac(request, "/api/models", "GET")
    _check_abac(request, "model", action="read")

    stats_data = await _fetch_worker("model_router", "/stats")
    models_list = await _fetch_worker_list("model_router", "/models")
    return {
        "models": models_list,
        "stats": stats_data or {},
        "total_models": len(models_list),
    }


@app.get("/api/workflows")
async def api_workflows(request: Request):
    """Workflow studio overview from workflow-engine-service."""
    _check_rbac(request, "/api/workflows", "GET")
    _check_abac(request, "workflow", action="read")

    stats_data = await _fetch_worker("workflow", "/stats")
    workflows_list = await _fetch_worker_list("workflow", "/workflows")
    return {
        "workflows": workflows_list,
        "stats": stats_data or {},
        "total_workflows": len(workflows_list),
    }


@app.get("/api/security")
async def api_security(request: Request):
    """Security vault overview from vault + ledger + topology."""
    _check_rbac(request, "/api/security", "GET")
    _check_abac(request, "security", action="read")

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
async def api_audit(request: Request):
    """Audit timeline from ledger + vault."""
    _check_rbac(request, "/api/audit", "GET")
    _check_abac(request, "audit", action="read")

    ledger_entries = await _fetch_worker_list("ledger", "/entries")
    vault_audit = await _fetch_worker_list("vault", "/audit")
    return {
        "ledger": ledger_entries[-50:],
        "vault_audit": vault_audit[-50:],
        "total_ledger": len(ledger_entries),
        "total_vault_audit": len(vault_audit),
    }


# ---------------------------------------------------------------------------
# Action Endpoints (proxy writes to workers — with RBAC + ABAC)
# ---------------------------------------------------------------------------


@app.post("/api/agents")
async def create_agent(body: AgentCreate, request: Request):
    """Create a new AI agent via the deepagents orchestrator."""
    _check_rbac(request, "POST:/api/agents", "POST")
    _check_abac(request, "agent", action="write")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('deepagents')}/agents",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await _broadcast_event("agent_created", data, channel="agents")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "DeepAgents service unavailable") from None


@app.post("/api/workflows")
async def create_workflow(body: WorkflowCreate, request: Request):
    """Create a new workflow via the workflow engine."""
    _check_rbac(request, "POST:/api/workflows", "POST")
    _check_abac(request, "workflow", action="write")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('workflow')}/workflows",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await _broadcast_event("workflow_created", data, channel="workflows")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Workflow engine unavailable") from None


@app.put("/api/topology/mode")
async def switch_topology(body: TopologySwitch, request: Request):
    """Switch topology mode via the topology service."""
    _check_rbac(request, "PUT:/api/topology/mode", "PUT")
    _check_abac(request, "topology", action="write")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.put(
                f"{_base_url('topology')}/mode",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code == 200:
                data = r.json()
                await _broadcast_event("topology_changed", data, channel="infrastructure")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Topology service unavailable") from None


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, request: Request):
    """Execute a workflow run."""
    _check_rbac(request, "POST:/api/workflows/{id}/run", "POST")
    _check_abac(request, "workflow", resource_id=workflow_id, action="execute")

    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('workflow')}/workflows/{workflow_id}/run",
                json={},
                timeout=10.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await _broadcast_event("workflow_run", data, channel="workflows")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Workflow engine unavailable") from None


# ---------------------------------------------------------------------------
# Security & Access Control API (Phase 22)
# ---------------------------------------------------------------------------


@app.get("/api/access/audit")
async def access_audit(limit: int = Query(50, ge=1, le=500), request: Request = None):
    """Retrieve access audit log entries (OWASP A09)."""
    _check_rbac(request, "/api/audit", "GET")
    _check_abac(request, "audit", action="read")

    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM access_audit ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@app.get("/api/access/policies")
async def list_policies(request: Request):
    """List current ABAC policies (admin-only)."""
    _check_rbac(request, "/api/security", "GET")
    _check_abac(request, "security", action="read")

    user = _get_user(request)
    if user.get("role") != InfinityRole.ADMIN:
        raise HTTPException(403, "Only admins can view ABAC policies")

    return {
        "policies": [
            {
                "id": p.id,
                "description": p.description,
                "effect": p.effect.value,
                "priority": p.priority,
                "subject_conditions": p.subject_conditions,
                "resource_conditions": p.resource_conditions,
                "action_conditions": p.action_conditions,
                "environment_conditions": p.environment_conditions,
            }
            for p in abac_engine._policies
        ],
        "threat_level": abac_engine.threat_level.value,
        "total": len(abac_engine._policies),
    }


@app.put("/api/access/threat-level")
async def set_threat_level(body: dict, request: Request):
    """Update the ABAC threat level (admin-only)."""
    _check_rbac(request, "/api/security", "PUT")
    _check_abac(request, "security", action="write")

    user = _get_user(request)
    if user.get("role") != InfinityRole.ADMIN:
        raise HTTPException(403, "Only admins can change threat level")

    from Dimensional.infinity.abac import ThreatLevel

    level_str = body.get("threat_level", body.get("level", "")).lower()
    try:
        new_level = ThreatLevel(level_str)
    except ValueError:
        raise HTTPException(
            400,
            detail=f"Invalid threat level: {level_str}. Use: low, medium, high, critical",
        ) from None

    old_level = abac_engine.threat_level
    abac_engine.threat_level = new_level
    await _broadcast_event(
        "threat_level_changed",
        {"old_level": old_level.value, "new_level": new_level.value},
        channel="security",
    )

    return {
        "old_level": old_level.value,
        "new_level": new_level.value,
        "changed_by": user.get("sub", "unknown"),
    }


@app.get("/api/access/check")
async def check_access(
    endpoint: str = Query(None, description="Endpoint to check"),
    method: str = Query("GET", description="HTTP method"),
    resource_type: str = Query(None, description="Resource type for ABAC"),
    action: str = Query("read", description="Action for ABAC"),
    request: Request = None,
):
    """Check access for the current user against a given endpoint/resource."""
    user = _get_user(request)

    rbac_result = True
    rbac_audit = {}
    if endpoint:
        rbac_result = rbac_engine.check_access(user, endpoint, method)
        try:
            rbac_audit = rbac_engine.get_audit_context(user, endpoint, method)
        except Exception:
            rbac_audit = {}

    abac_result = True
    if resource_type:
        subject = {
            "sub": user.get("sub", "anonymous"),
            "role": user.get("role", "user"),
            "tier": user.get("tier", "human"),
            "tier_value": _tier_name_to_value(user.get("tier", "human")),
            "pillar": user.get("pillar"),
        }
        resource = {"type": resource_type}
        action_attrs = {"action": action}
        environment = {"threat_level": abac_engine.threat_level.value}
        abac_result = abac_engine.evaluate(subject, resource, action_attrs, environment)

    return {
        "user": user.get("sub", "anonymous"),
        "role": user.get("role", "unknown"),
        "tier": user.get("tier", "unknown"),
        "endpoint": endpoint,
        "method": method,
        "rbac": {
            "granted": rbac_result,
            "required_permission": rbac_audit.get("required_permission"),
        },
        "abac": {
            "granted": abac_result,
            "resource_type": resource_type,
            "action": action,
        }
        if resource_type
        else None,
        "overall": rbac_result and abac_result,
    }


# ---------------------------------------------------------------------------
# Sentinel Station API (Phase 22.3)
# ---------------------------------------------------------------------------


@app.get("/api/sentinel/status")
async def sentinel_status(request: Request):
    """Get Sentinel Station status and statistics."""
    _check_rbac(request, "/api/security", "GET")
    return {
        "running": sentinel.is_running,
        "backend": "redis" if sentinel.is_redis_connected else "fallback",
        "circuit_breaker": sentinel.circuit_breaker_state.value,
        "stats": sentinel.get_stats(),
        "health": await sentinel.health_check(),
    }


@app.get("/api/sentinel/channels")
async def sentinel_channels(request: Request):
    """List available Sentinel Station channels and their configuration."""
    _check_rbac(request, "/api/security", "GET")
    from Dimensional.infinity.sentinel_config import sentinel_config

    channels = {}
    for name, cfg in sentinel_config.channels.items():
        channels[name] = {
            "name": cfg.name,
            "description": cfg.description,
            "max_message_size": cfg.max_message_size,
            "persistent": cfg.persistent,
            "retry_on_failure": cfg.retry_on_failure,
        }
    return {
        "channels": channels,
        "total": len(channels),
        "redis_prefix": sentinel_config.redis_channel_prefix,
    }


# ---------------------------------------------------------------------------
# Dimensional Services API (Phase 22.4)
# ---------------------------------------------------------------------------


@app.get("/api/dimensionals")
async def list_dimensionals(request: Request):
    """List all registered Dimensional's services."""
    _check_rbac(request, "/api/overview", "GET")
    return {
        "dimensionals": dimensional_registry.list_all(),
        "pillar_summary": dimensional_registry.get_pillar_summary(),
        "stats": dimensional_registry.get_stats(),
    }


@app.get("/api/dimensionals/{service_id}")
async def get_dimensional(service_id: str, request: Request):
    """Get details for a specific Dimensional's service."""
    _check_rbac(request, "/api/overview", "GET")
    svc = dimensional_registry.get(service_id)
    if not svc:
        raise HTTPException(404, f"Dimensional service not found: {service_id}")
    # Include underverse modules under this dimensional
    underverse_modules = underverse_registry.get_by_dimensional(service_id)
    return {
        **svc.to_dict(),
        "underverse_modules": [m.to_dict() for m in underverse_modules],
        "underverse_module_count": len(underverse_modules),
    }


@app.get("/api/dimensionals/pillars/{pillar}")
async def get_dimensionals_by_pillar(pillar: str, request: Request):
    """Get all Dimensional's services for a specific pillar."""
    _check_rbac(request, "/api/overview", "GET")
    try:
        p = Pillar(pillar)
    except ValueError:
        raise HTTPException(400, f"Invalid pillar: {pillar}") from None
    services = dimensional_registry.get_by_pillar(p)
    return {
        "pillar": pillar,
        "pillar_display": p.display_name,
        "accent_color": p.accent_color,
        "prime_id": p.prime_id,
        "services": [s.to_dict() for s in services],
        "total_services": len(services),
    }


@app.get("/api/underverse")
async def list_underverse(request: Request):
    """List all registered Underverse modules."""
    _check_rbac(request, "/api/overview", "GET")
    return {
        "modules": underverse_registry.list_all(),
        "pillar_summary": underverse_registry.get_pillar_summary(),
        "capabilities_index": underverse_registry.get_capabilities_index(),
        "stats": underverse_registry.get_stats(),
    }


@app.get("/api/underverse/capability/{capability}")
async def get_underverse_by_capability(capability: str, request: Request):
    """Find Underverse modules offering a specific capability."""
    _check_rbac(request, "/api/overview", "GET")
    modules = underverse_registry.get_by_capability(capability)
    return {
        "capability": capability,
        "modules": [m.to_dict() for m in modules],
        "total_modules": len(modules),
    }


# ---------------------------------------------------------------------------
# Event Broadcasting (via Sentinel Station)
# ---------------------------------------------------------------------------


async def _broadcast_event(
    event_type: str,
    payload: Any,
    channel: str = "events",
) -> SentinelEvent | None:
    """Broadcast an event through Sentinel Station to all subscribers.

    Events are published to both Redis Pub/Sub (for cross-gateway
    distribution) and the in-process fallback (for local subscribers).
    Also pushes to WebSocket clients and the SSE shared queue.

    Args:
        event_type: Type of event (e.g., "agent_created")
        payload: Event data
        channel: SentinelChannel name (e.g., "agents", "workflows")

    Returns:
        The published SentinelEvent, or None if station is not running
    """
    # Publish through Sentinel Station (Redis + fallback)
    event = None
    if sentinel.is_running:
        event = await sentinel.publish(
            channel=channel,
            payload=payload if isinstance(payload, dict) else {"data": payload},
            event_type=event_type,
            source="gateway-service",
        )
    else:
        # Station not running — create event for local broadcast only
        event = SentinelEvent(
            channel=channel,
            event_type=event_type,
            source="gateway-service",
            payload=payload if isinstance(payload, dict) else {"data": payload},
        )

    # Also broadcast to authenticated WebSocket clients
    message = json.dumps(
        {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
            "channel": channel,
        },
    )
    disconnected = []
    for ws in ws_auth_manager.connections:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ws_auth_manager.unregister_connection(ws)

    return event


# ---------------------------------------------------------------------------
# SSE Events Stream (shared generator — broadcasts to all clients)
# ---------------------------------------------------------------------------


async def _event_generator():
    """Generate SSE events for connected clients.

    Uses the SharedSSEGenerator from Sentinel Station: a single generator
    broadcasts to all clients, rather than spawning per-client loops.

    Falls back to periodic polling if the SSE generator is not available.
    """
    if sse_generator is not None:
        # Use Sentinel Station's shared SSE generator
        async for event in sse_generator.generate():
            yield event
    else:
        # Fallback: periodic platform stats polling
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
# WebSocket (with JWT authentication, connection limits, heartbeat)
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for bidirectional real-time communication.

    Phase 22: JWT authentication on upgrade, connection limits, heartbeat.
    """
    # Authenticate the WebSocket upgrade
    user = ws_auth_manager.authenticate_ws_upgrade(websocket)

    # Accept the connection (even unauthenticated for public access,
    # but with limited capabilities)
    await websocket.accept()

    # Register with the auth manager (enforces max connections)
    if not ws_auth_manager.register_connection(websocket, user):
        await websocket.close(code=1013, reason="Max connections reached")
        return

    try:
        # Send initial overview
        overview = await _get_cached_or_fetch("all_stats", _fetch_all_stats)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "initial_state",
                    "data": overview,
                    "authenticated": user is not None,
                    "tier": user.get("tier", "human") if user else "human",
                },
            ),
        )

        while True:
            data = await websocket.receive_text()
            ws_auth_manager.update_activity(websocket)

            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "subscribe":
                    # Tier-aware subscription: only authenticated users can
                    # subscribe to sensitive channels
                    channels = msg.get("channels", ["all"])
                    if user is None:
                        # Unauthenticated: only allow public channels
                        channels = [c for c in channels if c in ("platform", "public", "all")]
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "subscribed",
                                "channels": channels,
                            },
                        ),
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
                            },
                        ),
                    )
                elif msg_type == "heartbeat":
                    # Explicit heartbeat for connection keepalive
                    ws_auth_manager.update_activity(websocket)
                    await websocket.send_text(
                        json.dumps({"type": "heartbeat_ack", "ts": time.time()}),
                    )
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "error",
                            "message": "Invalid JSON",
                        },
                    ),
                )
    except WebSocketDisconnect:
        pass
    finally:
        ws_auth_manager.unregister_connection(websocket)


# ---------------------------------------------------------------------------
# Stale WebSocket Connection Cleanup (background task)
# ---------------------------------------------------------------------------


async def _cleanup_stale_connections():
    """Periodically clean up stale WebSocket connections."""
    while True:
        await asyncio.sleep(60)  # Check every minute
        stale = ws_auth_manager.get_stale_connections()
        for ws in stale:
            try:
                await ws.close(code=1000, reason="Idle timeout")
            except Exception:
                pass
            ws_auth_manager.unregister_connection(ws)
        if stale:
            logger.info("Cleaned up %d stale WebSocket connections", len(stale))


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
async def create_event(body: EventCreate, request: Request):
    """Record a platform event."""
    user = _get_user(request)
    _check_rbac(request, "/events", "POST")

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
    await _broadcast_event(body.event_type, body.payload, channel="events")
    return {
        "id": eid,
        "source": body.source,
        "event_type": body.event_type,
        "created_at": now,
        "recorded_by": user.get("sub", "anonymous"),
    }


@app.get("/events/history")
async def event_history(limit: int = Query(50, ge=1, le=500), request: Request = None):
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
