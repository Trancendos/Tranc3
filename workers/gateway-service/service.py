"""
service.py — Gateway Service business logic
Circuit breaker, upstream proxy, cache, ABAC/RBAC helpers,
WebSocket connection manager, and event broadcasting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException, Request

from config import (
    CACHE_TTL,
    JWT_SECRET,
    UPSTREAM_WORKERS,
    WS_HEARTBEAT_INTERVAL,
    WS_IDLE_TIMEOUT,
    WS_MAX_CONNECTIONS,
)
from database import log_access_audit

# Dimensional Services (Phase 22.4)
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)

# Dimensional security engines
from Dimensional.infinity.abac import ABACEngine, get_default_policies
from Dimensional.infinity.auth_gateway import WebSocketAuthManager
from Dimensional.infinity.nomenclature import InfinityRole, Tier
from Dimensional.infinity.rbac import RBACEngine

# Sentinel Station
from Dimensional.infinity.sentinel_station import SentinelEvent, get_sentinel_station

logger = logging.getLogger("gateway-service")

# ---------------------------------------------------------------------------
# Security Engines (Phase 22) — module-level singletons
# ---------------------------------------------------------------------------

rbac_engine = RBACEngine()
abac_engine = ABACEngine(policies=get_default_policies())
ws_auth_manager = WebSocketAuthManager(
    jwt_secret=JWT_SECRET,
    max_connections=WS_MAX_CONNECTIONS,
    heartbeat_interval=WS_HEARTBEAT_INTERVAL,
    idle_timeout=WS_IDLE_TIMEOUT,
)

# ---------------------------------------------------------------------------
# Sentinel Station singleton (shared with main.py via import)
# ---------------------------------------------------------------------------

sentinel = get_sentinel_station()

# Dimensional singletons (imported by router.py)
dimensional_registry = get_dimensional_registry()
dimensional_bus = get_dimensional_bus()
underverse_registry = get_underverse_registry()

# ---------------------------------------------------------------------------
# In-process cache and circuit-breaker state
# ---------------------------------------------------------------------------

_cache: dict[str, tuple[float, Any]] = {}
_circuit_breaker: dict[str, dict[str, Any]] = {}


def init_circuit_breakers() -> None:
    """Seed circuit-breaker state for all upstream workers (call at startup)."""
    for name in UPSTREAM_WORKERS:
        _circuit_breaker[name] = {
            "state": "closed",
            "failures": 0,
            "last_failure": 0.0,
            "last_success": 0.0,
        }


# ---------------------------------------------------------------------------
# Circuit Breaker
# ---------------------------------------------------------------------------


def _base_url(worker_name: str) -> str:
    cfg = UPSTREAM_WORKERS.get(worker_name)
    if not cfg:
        return ""
    return f"http://localhost:{cfg['port']}"


def _is_circuit_open(name: str) -> bool:
    cb = _circuit_breaker.get(name, {})
    if cb.get("state") == "open":
        # Half-open after 30 s
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


def get_circuit_breaker_states() -> dict[str, str]:
    return {k: v["state"] for k, v in _circuit_breaker.items()}


# ---------------------------------------------------------------------------
# Upstream Fetch
# ---------------------------------------------------------------------------


async def fetch_worker(name: str, path: str, timeout: float = 3.0) -> dict | None:
    """GET a path from an upstream worker, honouring the circuit breaker."""
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


async def fetch_all_stats() -> dict[str, Any]:
    """Fetch stats from all upstream workers concurrently."""
    tasks: dict[str, Any] = {
        name: fetch_worker(name, cfg["stats"]) for name, cfg in UPSTREAM_WORKERS.items()
    }
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    output: dict[str, Any] = {}
    for name, result in zip(tasks.keys(), results, strict=False):
        if isinstance(result, Exception) or result is None:
            output[name] = {"status": "unreachable"}
        else:
            output[name] = result
            output[name]["status"] = "ok"
    return output


async def fetch_worker_list(name: str, path: str) -> list:
    """Fetch a list endpoint from an upstream worker."""
    data = await fetch_worker(name, path)
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and "items" in data:
        return data["items"]
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                return v
    return []


# ---------------------------------------------------------------------------
# Cache Layer
# ---------------------------------------------------------------------------


async def get_cached_or_fetch(key: str, fetcher, ttl: float | None = None) -> Any:
    """Simple in-memory TTL cache."""
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


def get_cache_size() -> int:
    return len(_cache)


def evict_expired_cache() -> int:
    """Remove expired entries; return count removed."""
    now = time.time()
    expired = [k for k, (ts, _) in _cache.items() if now - ts > CACHE_TTL]
    for k in expired:
        _cache.pop(k, None)
    return len(expired)


# ---------------------------------------------------------------------------
# RBAC / ABAC helpers
# ---------------------------------------------------------------------------


def get_user(request: Request) -> dict[str, Any]:
    """Extract the authenticated user dict from request.state."""
    user = getattr(request.state, "user", None)
    return user or {"sub": "anonymous", "tier": "human", "role": "user", "is_active": False}


def tier_name_to_value(tier_name: str) -> int:
    try:
        return Tier[tier_name.upper()].value
    except (KeyError, AttributeError):
        return 0


def check_rbac(request: Request, endpoint: str, method: str) -> None:
    """Raise HTTP 403 if the authenticated user lacks RBAC permission."""
    user = get_user(request)
    if not rbac_engine.check_access(user, endpoint, method):
        try:
            audit = rbac_engine.get_audit_context(user, endpoint, method)
            log_access_audit(audit)
        except Exception:
            logger.warning("RBAC audit logging failed for %s %s", method, endpoint)
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: insufficient permissions for {method} {endpoint}",
        )


def check_abac(
    request: Request,
    resource_type: str,
    resource_id: str = "*",
    action: str = "read",
) -> None:
    """Raise HTTP 403 if the ABAC policy denies the action."""
    user = get_user(request)
    subject = {
        "sub": user.get("sub", "anonymous"),
        "role": user.get("role", "user"),
        "tier": user.get("tier", "human"),
        "tier_value": tier_name_to_value(user.get("tier", "human")),
        "pillar": user.get("pillar"),
    }
    resource = {"type": resource_type, "id": resource_id}
    action_attrs = {"action": action}
    environment = {"threat_level": abac_engine.threat_level.value}

    if not abac_engine.evaluate(subject, resource, action_attrs, environment):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: ABAC policy denies {action} on {resource_type}/{resource_id}",
        )


def require_admin(request: Request) -> dict[str, Any]:
    """Return the user dict if admin, else raise HTTP 403."""
    user = get_user(request)
    if user.get("role") != InfinityRole.ADMIN:
        raise HTTPException(403, "Only admins can perform this action")
    return user


# ---------------------------------------------------------------------------
# Event Broadcasting (via Sentinel Station + WebSocket)
# ---------------------------------------------------------------------------


async def broadcast_event(
    event_type: str,
    payload: Any,
    channel: str = "events",
) -> SentinelEvent | None:
    """Publish an event through Sentinel Station and all connected WebSocket clients."""
    event = None
    if sentinel.is_running:
        event = await sentinel.publish(
            channel=channel,
            payload=payload if isinstance(payload, dict) else {"data": payload},
            event_type=event_type,
            source="gateway-service",
        )
    else:
        event = SentinelEvent(
            channel=channel,
            event_type=event_type,
            source="gateway-service",
            payload=payload if isinstance(payload, dict) else {"data": payload},
        )

    # Push to WebSocket clients
    message = json.dumps(
        {
            "type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": payload,
            "channel": channel,
        }
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
