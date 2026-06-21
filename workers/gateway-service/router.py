"""
router.py — Gateway Service FastAPI routes
All HTTP, SSE, and WebSocket routes via APIRouter.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path as PathLib
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sse_starlette.sse import EventSourceResponse

# Dimensional imports
from Dimensional.infinity.abac import ThreatLevel
from Dimensional.infinity.nomenclature import InfinityRole, Pillar
from Dimensional.infinity.sentinel_station import SharedSSEGenerator

from config import UPSTREAM_WORKERS
from database import fetch_access_audit, fetch_events, insert_event
from models import AgentCreate, EventCreate, TopologySwitch, WorkflowCreate
from service import (
    abac_engine,
    broadcast_event,
    check_abac,
    check_rbac,
    dimensional_bus,
    dimensional_registry,
    fetch_all_stats,
    fetch_worker,
    fetch_worker_list,
    get_cached_or_fetch,
    get_user,
    require_admin,
    sentinel,
    tier_name_to_value,
    underverse_registry,
    ws_auth_manager,
)

logger = logging.getLogger("gateway-service")

router = APIRouter()

# Dashboard static files
DASHBOARD_DIR = PathLib(__file__).parent.parent.parent / "dashboard"

# Shared SSE generator — set by main.py lifespan after startup
sse_generator: SharedSSEGenerator | None = None


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    return {
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


@router.get("/stats")
async def stats():
    all_stats = await get_cached_or_fetch("all_stats", fetch_all_stats)
    reachable = sum(1 for v in all_stats.values() if v.get("status") == "ok")
    from service import get_cache_size, get_circuit_breaker_states
    return {
        "upstream_workers": len(UPSTREAM_WORKERS),
        "reachable": reachable,
        "unreachable": len(UPSTREAM_WORKERS) - reachable,
        "ws_connections": ws_auth_manager.connection_count,
        "ws_stats": ws_auth_manager.get_connection_stats(),
        "cache_entries": get_cache_size(),
        "circuit_breakers": get_circuit_breaker_states(),
        "abac_threat_level": abac_engine.threat_level.value,
        "abac_policy_count": len(abac_engine._policies),
        "sentinel_station": sentinel.get_stats(),
        "dimensional_bus": dimensional_bus.get_stats(),
        "dimensional_registry": dimensional_registry.get_stats(),
        "underverse": underverse_registry.get_stats(),
    }


# ---------------------------------------------------------------------------
# Aggregated Platform API
# ---------------------------------------------------------------------------


@router.get("/api/overview")
async def api_overview(request: Request):
    """Master overview of the entire Tranc3 AI Platform."""
    check_rbac(request, "/api/overview", "GET")

    all_stats = await get_cached_or_fetch("all_stats", fetch_all_stats)

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
            "status": (
                "operational" if reachable >= 6 else "degraded" if reachable >= 3 else "critical"
            ),
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


@router.get("/api/agents")
async def api_agents(request: Request):
    """Agent fleet overview from deepagents-orchestrator."""
    check_rbac(request, "/api/agents", "GET")
    check_abac(request, "agent", action="read")

    stats_data = await fetch_worker("deepagents", "/stats")
    agents_list = await fetch_worker_list("deepagents", "/agents")
    skills_list = await fetch_worker_list("deepagents", "/skills")
    tasks_list = await fetch_worker_list("deepagents", "/tasks")

    return {
        "agents": agents_list,
        "skills": skills_list,
        "tasks": tasks_list,
        "stats": stats_data or {},
        "total_agents": len(agents_list),
        "total_skills": len(skills_list),
        "total_tasks": len(tasks_list),
    }


@router.get("/api/models")
async def api_models(request: Request):
    """Model hub overview from model-router-service."""
    check_rbac(request, "/api/models", "GET")
    check_abac(request, "model", action="read")

    stats_data = await fetch_worker("model_router", "/stats")
    models_list = await fetch_worker_list("model_router", "/models")
    return {
        "models": models_list,
        "stats": stats_data or {},
        "total_models": len(models_list),
    }


@router.get("/api/workflows")
async def api_workflows(request: Request):
    """Workflow studio overview from workflow-engine-service."""
    check_rbac(request, "/api/workflows", "GET")
    check_abac(request, "workflow", action="read")

    stats_data = await fetch_worker("workflow", "/stats")
    workflows_list = await fetch_worker_list("workflow", "/workflows")
    return {
        "workflows": workflows_list,
        "stats": stats_data or {},
        "total_workflows": len(workflows_list),
    }


@router.get("/api/security")
async def api_security(request: Request):
    """Security vault overview from vault + ledger + topology."""
    check_rbac(request, "/api/security", "GET")
    check_abac(request, "security", action="read")

    vault_stats = await fetch_worker("vault", "/stats")
    ledger_stats = await fetch_worker("ledger", "/stats")
    topology_stats = await fetch_worker("topology", "/stats")
    secrets_list = await fetch_worker_list("vault", "/secrets")
    audit_list = await fetch_worker_list("vault", "/audit")
    ledger_entries = await fetch_worker_list("ledger", "/entries")

    return {
        "vault": {
            "secrets": secrets_list,
            "audit": audit_list,
            "stats": vault_stats or {},
        },
        "ledger": {
            "entries": ledger_entries[:50],
            "stats": ledger_stats or {},
        },
        "topology": {
            "stats": topology_stats or {},
        },
    }


@router.get("/api/audit")
async def api_audit(request: Request):
    """Audit timeline from ledger + vault."""
    check_rbac(request, "/api/audit", "GET")
    check_abac(request, "audit", action="read")

    ledger_entries = await fetch_worker_list("ledger", "/entries")
    vault_audit = await fetch_worker_list("vault", "/audit")
    return {
        "ledger": ledger_entries[-50:],
        "vault_audit": vault_audit[-50:],
        "total_ledger": len(ledger_entries),
        "total_vault_audit": len(vault_audit),
    }


# ---------------------------------------------------------------------------
# Action Endpoints (proxy writes to workers)
# ---------------------------------------------------------------------------


@router.post("/api/agents")
async def create_agent(body: AgentCreate, request: Request):
    """Create a new AI agent via the deepagents orchestrator."""
    check_rbac(request, "POST:/api/agents", "POST")
    check_abac(request, "agent", action="write")

    from service import _base_url
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('deepagents')}/agents",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await broadcast_event("agent_created", data, channel="agents")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "DeepAgents service unavailable") from None


@router.post("/api/workflows")
async def create_workflow(body: WorkflowCreate, request: Request):
    """Create a new workflow via the workflow engine."""
    check_rbac(request, "POST:/api/workflows", "POST")
    check_abac(request, "workflow", action="write")

    from service import _base_url
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('workflow')}/workflows",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await broadcast_event("workflow_created", data, channel="workflows")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Workflow engine unavailable") from None


@router.put("/api/topology/mode")
async def switch_topology(body: TopologySwitch, request: Request):
    """Switch topology mode via the topology service."""
    check_rbac(request, "PUT:/api/topology/mode", "PUT")
    check_abac(request, "topology", action="write")

    from service import _base_url
    async with httpx.AsyncClient() as client:
        try:
            r = await client.put(
                f"{_base_url('topology')}/mode",
                json=body.model_dump(),
                timeout=5.0,
            )
            if r.status_code == 200:
                data = r.json()
                await broadcast_event("topology_changed", data, channel="infrastructure")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Topology service unavailable") from None


@router.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, request: Request):
    """Execute a workflow run."""
    if not re.match(r"^[A-Za-z0-9_-]+$", workflow_id):
        raise HTTPException(400, detail="Invalid workflow_id")
    check_rbac(request, "POST:/api/workflows/{id}/run", "POST")
    check_abac(request, "workflow", resource_id=workflow_id, action="execute")

    from service import _base_url
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(
                f"{_base_url('workflow')}/workflows/{workflow_id}/run",
                json={},
                timeout=10.0,
            )
            if r.status_code in (200, 201):
                data = r.json()
                await broadcast_event("workflow_run", data, channel="workflows")
                return data
            raise HTTPException(r.status_code, detail=r.text)
        except httpx.ConnectError:
            raise HTTPException(503, "Workflow engine unavailable") from None


# ---------------------------------------------------------------------------
# Security & Access Control API (Phase 22)
# ---------------------------------------------------------------------------


@router.get("/api/access/audit")
async def access_audit(limit: int = Query(50, ge=1, le=500), request: Request = None):
    """Retrieve access audit log entries (OWASP A09)."""
    check_rbac(request, "/api/audit", "GET")
    check_abac(request, "audit", action="read")
    return fetch_access_audit(limit)


@router.get("/api/access/policies")
async def list_policies(request: Request):
    """List current ABAC policies (admin-only)."""
    check_rbac(request, "/api/security", "GET")
    check_abac(request, "security", action="read")
    require_admin(request)

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


@router.put("/api/access/threat-level")
async def set_threat_level(body: dict, request: Request):
    """Update the ABAC threat level (admin-only)."""
    check_rbac(request, "/api/security", "PUT")
    check_abac(request, "security", action="write")
    user = require_admin(request)

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
    await broadcast_event(
        "threat_level_changed",
        {"old_level": old_level.value, "new_level": new_level.value},
        channel="security",
    )

    return {
        "old_level": old_level.value,
        "new_level": new_level.value,
        "changed_by": user.get("sub", "unknown"),
    }


@router.get("/api/access/check")
async def check_access(
    endpoint: str = Query(None, description="Endpoint to check"),
    method: str = Query("GET", description="HTTP method"),
    resource_type: str = Query(None, description="Resource type for ABAC"),
    action: str = Query("read", description="Action for ABAC"),
    request: Request = None,
):
    """Check access for the current user against a given endpoint/resource."""
    from service import rbac_engine as _rbac
    user = get_user(request)

    rbac_result = True
    rbac_audit: dict[str, Any] = {}
    if endpoint:
        rbac_result = _rbac.check_access(user, endpoint, method)
        try:
            rbac_audit = _rbac.get_audit_context(user, endpoint, method)
        except Exception:
            rbac_audit = {}

    abac_result = True
    if resource_type:
        subject = {
            "sub": user.get("sub", "anonymous"),
            "role": user.get("role", "user"),
            "tier": user.get("tier", "human"),
            "tier_value": tier_name_to_value(user.get("tier", "human")),
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


@router.get("/api/sentinel/status")
async def sentinel_status(request: Request):
    """Get Sentinel Station status and statistics."""
    check_rbac(request, "/api/security", "GET")
    return {
        "running": sentinel.is_running,
        "backend": "redis" if sentinel.is_redis_connected else "fallback",
        "circuit_breaker": sentinel.circuit_breaker_state.value,
        "stats": sentinel.get_stats(),
        "health": await sentinel.health_check(),
    }


@router.get("/api/sentinel/channels")
async def sentinel_channels(request: Request):
    """List available Sentinel Station channels."""
    check_rbac(request, "/api/security", "GET")
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


@router.get("/api/dimensionals")
async def list_dimensionals(request: Request):
    """List all registered Dimensional's services."""
    check_rbac(request, "/api/overview", "GET")
    return {
        "dimensionals": dimensional_registry.list_all(),
        "pillar_summary": dimensional_registry.get_pillar_summary(),
        "stats": dimensional_registry.get_stats(),
    }


@router.get("/api/dimensionals/{service_id}")
async def get_dimensional(service_id: str, request: Request):
    """Get details for a specific Dimensional's service."""
    check_rbac(request, "/api/overview", "GET")
    svc = dimensional_registry.get(service_id)
    if not svc:
        raise HTTPException(404, f"Dimensional service not found: {service_id}")
    underverse_modules = underverse_registry.get_by_dimensional(service_id)
    return {
        **svc.to_dict(),
        "underverse_modules": [m.to_dict() for m in underverse_modules],
        "underverse_module_count": len(underverse_modules),
    }


@router.get("/api/dimensionals/pillars/{pillar}")
async def get_dimensionals_by_pillar(pillar: str, request: Request):
    """Get all Dimensional's services for a specific pillar."""
    check_rbac(request, "/api/overview", "GET")
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


@router.get("/api/underverse")
async def list_underverse(request: Request):
    """List all registered Underverse modules."""
    check_rbac(request, "/api/overview", "GET")
    return {
        "modules": underverse_registry.list_all(),
        "pillar_summary": underverse_registry.get_pillar_summary(),
        "capabilities_index": underverse_registry.get_capabilities_index(),
        "stats": underverse_registry.get_stats(),
    }


@router.get("/api/underverse/capability/{capability}")
async def get_underverse_by_capability(capability: str, request: Request):
    """Find Underverse modules offering a specific capability."""
    check_rbac(request, "/api/overview", "GET")
    modules = underverse_registry.get_by_capability(capability)
    return {
        "capability": capability,
        "modules": [m.to_dict() for m in modules],
        "total_modules": len(modules),
    }


# ---------------------------------------------------------------------------
# SSE Events Stream
# ---------------------------------------------------------------------------


async def _event_generator():
    """Generate SSE events; uses SharedSSEGenerator when available."""
    if sse_generator is not None:
        async for event in sse_generator.generate():
            yield event
    else:
        while True:
            try:
                all_stats = await fetch_all_stats()
                event_data = {
                    "type": "platform_update",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": all_stats,
                }
                yield {"event": "update", "data": json.dumps(event_data)}
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(10)


@router.get("/events")
async def sse_events():
    """SSE endpoint for real-time dashboard updates."""
    return EventSourceResponse(_event_generator())


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for bidirectional real-time communication (Phase 22)."""
    user = ws_auth_manager.authenticate_ws_upgrade(websocket)
    await websocket.accept()

    if not ws_auth_manager.register_connection(websocket, user):
        await websocket.close(code=1013, reason="Max connections reached")
        return

    try:
        overview = await get_cached_or_fetch("all_stats", fetch_all_stats)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "initial_state",
                    "data": overview,
                    "authenticated": user is not None,
                    "tier": user.get("tier", "human") if user else "human",
                }
            )
        )

        while True:
            data = await websocket.receive_text()
            ws_auth_manager.update_activity(websocket)

            try:
                msg = json.loads(data)
                msg_type = msg.get("type", "")

                if msg_type == "subscribe":
                    channels = msg.get("channels", ["all"])
                    if user is None:
                        channels = [c for c in channels if c in ("platform", "public", "all")]
                    await websocket.send_text(
                        json.dumps({"type": "subscribed", "channels": channels})
                    )
                elif msg_type == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                elif msg_type == "get_overview":
                    overview = await get_cached_or_fetch("all_stats", fetch_all_stats)
                    await websocket.send_text(
                        json.dumps({"type": "overview", "data": overview})
                    )
                elif msg_type == "heartbeat":
                    ws_auth_manager.update_activity(websocket)
                    await websocket.send_text(
                        json.dumps({"type": "heartbeat_ack", "ts": time.time()})
                    )
            except json.JSONDecodeError:
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "Invalid JSON"})
                )
    except WebSocketDisconnect:
        pass
    finally:
        ws_auth_manager.unregister_connection(websocket)


# ---------------------------------------------------------------------------
# Event Persistence
# ---------------------------------------------------------------------------


@router.post("/events")
async def create_event(body: EventCreate, request: Request):
    """Record a platform event."""
    user = get_user(request)
    check_rbac(request, "/events", "POST")

    import json as _json
    eid = insert_event(body.source, body.event_type, _json.dumps(body.payload))
    now = datetime.now(timezone.utc).isoformat()
    await broadcast_event(body.event_type, body.payload, channel="events")
    return {
        "id": eid,
        "source": body.source,
        "event_type": body.event_type,
        "created_at": now,
        "recorded_by": user.get("sub", "anonymous"),
    }


@router.get("/events/history")
async def event_history(limit: int = Query(50, ge=1, le=500), request: Request = None):
    """Retrieve recent platform events."""
    return fetch_events(limit)


# ---------------------------------------------------------------------------
# Dashboard Static Files
# ---------------------------------------------------------------------------


@router.get("/dashboard/{path:path}")
async def serve_dashboard(path: str = "index.html"):
    """Serve the AI Platform dashboard static files."""
    file_path = DASHBOARD_DIR / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))
    raise HTTPException(404, "File not found") from None


@router.get("/dashboard")
async def serve_dashboard_index():
    """Serve the dashboard index."""
    return FileResponse(str(DASHBOARD_DIR / "index.html"))
