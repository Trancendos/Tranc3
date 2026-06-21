"""
Router — Infinity Portal Service
==================================
All FastAPI routes collected under an APIRouter.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException, Query, Request
from models import (
    GateRoutingResponse,
    PortalLogin,
    PortalRegister,
    PortalSessionResponse,
    PortalStatusResponse,
)
from service import (
    InfinityGate,
    _create_portal_session,
    _log_gate_routing,
    _log_portal_event,
    call_auth_service,
    gate,
)

from database import db
from Dimensional.infinity.nomenclature import (
    GATE_ROUTING,
    INFINITY_LOCATIONS,
    InfinityRole,
    Tier,
    TransferSystem,
)
from Dimensional.infinity.sentinel_station import SentinelEvent
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# Shared singletons — imported from main at app startup; populated via dependency
# injection pattern: router functions call get_sentinel_station() / worker_kit
# directly from the module-level objects created in main.py.  We expose a small
# "late-bind" hook so main.py can inject them after construction.

_sentinel = None
_worker_kit: InfinityWorkerKit | None = None


def init_router_deps(sentinel, worker_kit: InfinityWorkerKit) -> None:
    """Called by main.py after constructing sentinel & worker_kit."""
    global _sentinel, _worker_kit
    _sentinel = sentinel
    _worker_kit = worker_kit


router = APIRouter()

# ---------------------------------------------------------------------------
# Sentinel channel shortcut
# ---------------------------------------------------------------------------

from Dimensional.infinity.nomenclature import SentinelChannel  # noqa: E402

# ---------------------------------------------------------------------------
# Health & Status
# ---------------------------------------------------------------------------


@router.get("/health")
async def health():
    """Health check for the Infinity Portal service."""
    from Dimensional.dimensionals import get_dimensional_bus

    dimensional_bus = get_dimensional_bus()
    health_summary = _worker_kit.health.get_health_summary()
    return {
        "status": "healthy",
        "service": "infinity-portal",
        "location": "Infinity Portal",
        "purpose": "Central Login Page — The front entrance to the Infinity Ecosystem",
        "dimensional_bus": dimensional_bus.is_running,
        "sentinel": _sentinel.is_running,
        # Phase 22.6: Smart health info
        "health_score": health_summary.to_dict().get("health_score", 1.0),
        "health_tier": health_summary.to_dict().get("health_tier", "EXCELLENT"),
        "smart_adaptive": True,
    }


@router.get("/portal/status", response_model=PortalStatusResponse)
async def portal_status():
    """Get the current status and configuration of the Infinity Portal."""
    active_sessions = db.execute(
        "SELECT COUNT(*) as cnt FROM portal_sessions WHERE is_active = 1"
    ).fetchone()["cnt"]

    return PortalStatusResponse(
        status="operational",
        portal_name="Infinity Portal",
        ecosystem_name="Infinity Ecosystem",
        universe_name="Trancendos Universe",
        locations={loc.value: info.get("name", "") for loc, info in INFINITY_LOCATIONS.items()},
        gate_routing={role: loc.value for role, loc in GATE_ROUTING.items()},
        transfer_systems={
            ts.value: info.get("name", "")
            for ts, info in {
                TransferSystem.NEXUS: {"name": "The Nexus"},
                TransferSystem.HIVE: {"name": "The HIVE"},
                TransferSystem.BRIDGE: {"name": "The Infinity Bridge"},
            }.items()
        },
        active_sessions=active_sessions,
        uptime=time.time(),
    )


# ---------------------------------------------------------------------------
# Portal Login & Registration
# ---------------------------------------------------------------------------


@router.post("/portal/login", response_model=PortalSessionResponse)
async def portal_login(request: Request, login: PortalLogin):
    """Authenticate a user at the Infinity Portal.

    Delegates authentication to the Infinity Auth service, then routes
    the user through the Infinity Gate based on their role.

    Phase 22.6: Request evaluated by ProactiveDefenseLayer before processing.
    Routing confirmed by InfinityFluidicGateway for adaptive weighted routing.
    """
    t_start = time.time()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Phase 22.6: Proactive defense evaluation
    defense_result = await _worker_kit.defense.evaluate_request(
        {
            "ip": client_ip,
            "path": "/portal/login",
            "method": "POST",
            "user_agent": user_agent,
        }
    )
    if not defense_result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Request blocked by defense layer: {defense_result.reason}",
        )

    # Call Infinity Auth for authentication
    auth_data: dict = {
        "username": login.username,
        "password": login.password,
    }
    if login.totp_code:
        auth_data["totp_code"] = login.totp_code

    auth_result = await call_auth_service("POST", "/auth/login", auth_data)

    # Determine role and route through the Infinity Gate
    role = auth_result.get("role", "user")
    routing = gate.route(role)
    routing.user_id = auth_result["user_id"]
    routing.username = auth_result["username"]

    # Phase 22.6: Confirm routing via FluidicGateway for weighted adaptive routing
    try:
        fluid_route = await _worker_kit.gateway.route(role, auth_result["user_id"])
        _worker_kit.gateway.record_route_success(
            fluid_route.target_location, (time.time() - t_start) * 1000
        )
    except Exception:
        pass

    # Create portal session
    session_id = _create_portal_session(
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        role=role,
        tier=Tier(routing.tier),
        infinity_role=InfinityRole(routing.infinity_role),
        routed_to=routing.routed_to,
        access_token=auth_result["access_token"],
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Log the routing event
    _log_gate_routing(
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        role=role,
        from_location="infinity_portal",
        to_location=routing.routed_to,
        transfer_system=routing.transfer_system,
    )

    # Log portal event
    _log_portal_event(
        event_type="portal_login",
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        ip_address=client_ip,
        user_agent=user_agent,
        payload={"role": role, "routed_to": routing.routed_to},
    )

    # Phase 22.6: Record telemetry
    latency_ms = (time.time() - t_start) * 1000
    _worker_kit.health.record_request(latency_ms=latency_ms)
    _worker_kit.health.record_metric("portal_logins", 1.0)

    # Publish Sentinel event for auth activity
    await _sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="user_authenticated",
            source="infinity_portal",
            payload={
                "user_id": auth_result["user_id"],
                "username": auth_result["username"],
                "role": role,
                "routed_to": routing.routed_to,
                "transfer_system": routing.transfer_system,
                "latency_ms": latency_ms,
            },
        )
    )

    return PortalSessionResponse(
        session_id=session_id,
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        expires_in=auth_result["expires_in"],
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        role=role,
        tier=routing.tier,
        infinity_role=routing.infinity_role,
        routed_to=routing.routed_to,
        routing_url=routing.routing_url,
        transfer_system=routing.transfer_system,
    )


@router.post("/portal/register", response_model=PortalSessionResponse)
async def portal_register(request: Request, registration: PortalRegister):
    """Register a new user at the Infinity Portal.

    Delegates account creation to the Infinity Auth service, then routes
    the new user through the Infinity Gate.

    Phase 22.6: Defense evaluation + telemetry recording.
    """
    t_start = time.time()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    # Phase 22.6: Proactive defense evaluation
    defense_result = await _worker_kit.defense.evaluate_request(
        {
            "ip": client_ip,
            "path": "/portal/register",
            "method": "POST",
            "user_agent": user_agent,
        }
    )
    if not defense_result.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Request blocked by defense layer: {defense_result.reason}",
        )

    # Call Infinity Auth for registration
    auth_data = {
        "username": registration.username,
        "email": registration.email,
        "password": registration.password,
        "display_name": registration.display_name,
    }

    auth_result = await call_auth_service("POST", "/auth/register", auth_data)

    # Route through the Infinity Gate
    role = registration.role
    routing = gate.route(role)
    routing.user_id = auth_result["user_id"]
    routing.username = auth_result["username"]

    # Create portal session
    session_id = _create_portal_session(
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        role=role,
        tier=Tier(routing.tier),
        infinity_role=InfinityRole(routing.infinity_role),
        routed_to=routing.routed_to,
        access_token=auth_result["access_token"],
        ip_address=client_ip,
        user_agent=user_agent,
    )

    # Log the routing event
    _log_gate_routing(
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        role=role,
        from_location="infinity_portal",
        to_location=routing.routed_to,
        transfer_system=routing.transfer_system,
    )

    # Log portal event
    _log_portal_event(
        event_type="portal_register",
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        ip_address=client_ip,
        user_agent=user_agent,
        payload={"role": role, "routed_to": routing.routed_to, "email": registration.email},
    )

    # Phase 22.6: Record telemetry
    latency_ms = (time.time() - t_start) * 1000
    _worker_kit.health.record_request(latency_ms=latency_ms)
    _worker_kit.health.record_metric("portal_registrations", 1.0)

    # Publish Sentinel event
    await _sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="user_registered",
            source="infinity_portal",
            payload={
                "user_id": auth_result["user_id"],
                "username": auth_result["username"],
                "role": role,
                "routed_to": routing.routed_to,
                "latency_ms": latency_ms,
            },
        )
    )

    return PortalSessionResponse(
        session_id=session_id,
        access_token=auth_result["access_token"],
        refresh_token=auth_result["refresh_token"],
        expires_in=auth_result["expires_in"],
        user_id=auth_result["user_id"],
        username=auth_result["username"],
        role=role,
        tier=routing.tier,
        infinity_role=routing.infinity_role,
        routed_to=routing.routed_to,
        routing_url=routing.routing_url,
        transfer_system=routing.transfer_system,
    )


@router.post("/portal/logout")
async def portal_logout(request: Request):
    """Log out from the Infinity Portal and invalidate the session."""
    user = getattr(request.state, "user", None)
    user_id = user.get("sub", "unknown") if user else "unknown"
    username = user.get("username", "unknown") if user else "unknown"

    # Invalidate portal sessions
    db.execute(
        "UPDATE portal_sessions SET is_active = 0 WHERE user_id = ? AND is_active = 1",
        (user_id,),
    )
    db.commit()

    # Log event
    client_ip = request.client.host if request.client else "unknown"
    _log_portal_event(
        event_type="portal_logout",
        user_id=user_id,
        username=username,
        ip_address=client_ip,
    )

    # Publish Sentinel event
    await _sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="user_logout",
            source="infinity_portal",
            payload={"user_id": user_id, "username": username},
        )
    )

    return {"message": "Logged out from Infinity Portal", "redirect": "/portal/login"}


# ---------------------------------------------------------------------------
# Infinity Gate Routing
# ---------------------------------------------------------------------------


@router.post("/gate/route", response_model=GateRoutingResponse)
async def gate_route(request: Request):
    """Route an authenticated user through the Infinity Gate.

    This endpoint re-evaluates routing for an already-authenticated user,
    useful when a user's role changes or they request navigation.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = user.get("sub", "")
    username = user.get("username", "")
    role = user.get("role", "user")

    routing = gate.route(role)
    routing.user_id = user_id
    routing.username = username

    # Log routing event
    _log_gate_routing(
        user_id=user_id,
        username=username,
        role=role,
        from_location="infinity_gate",
        to_location=routing.routed_to,
        transfer_system=routing.transfer_system,
    )

    return routing


# ---------------------------------------------------------------------------
# Infinity Location Discovery
# ---------------------------------------------------------------------------


@router.get("/portal/locations")
async def list_locations():
    """List all Infinity Locations in the Trancendos Universe."""
    locations = []
    for loc, info in INFINITY_LOCATIONS.items():
        locations.append(
            {
                "id": loc.value,
                "name": info.get("name", ""),
                "purpose": info.get("purpose", ""),
                "description": info.get("description", ""),
            }
        )
    return {"locations": locations, "total": len(locations)}


@router.get("/portal/gate-info")
async def gate_info():
    """Get Infinity Gate routing configuration and rules."""
    routing_rules = []
    for role, location in InfinityGate.EXTENDED_ROUTING.items():
        info = INFINITY_LOCATIONS.get(location, {})
        routing_rules.append(
            {
                "role": role,
                "destination_id": location.value,
                "destination_name": info.get("name", ""),
                "purpose": info.get("purpose", ""),
            }
        )

    return {
        "gate_name": "Infinity Gate",
        "description": "Post-authentication role-based router for the Infinity Ecosystem",
        "routing_rules": routing_rules,
        "total_rules": len(routing_rules),
    }


@router.get("/portal/transfer-systems")
async def transfer_systems():
    """Get information about the three transfer systems."""
    from Dimensional.infinity.nomenclature import TRANSFER_SYSTEMS

    systems = []
    for ts, info in TRANSFER_SYSTEMS.items():
        systems.append(
            {
                "id": ts.value,
                "name": info.get("name", ""),
                "transfers": info.get("transfers", ""),
                "description": info.get("description", ""),
            }
        )
    return {"transfer_systems": systems, "total": len(systems)}


# ---------------------------------------------------------------------------
# Session Management
# ---------------------------------------------------------------------------


@router.get("/portal/session")
async def get_session(request: Request):
    """Get the current user's portal session information."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    user_id = user.get("sub", "")
    row = db.execute(
        "SELECT * FROM portal_sessions WHERE user_id = ? AND is_active = 1 ORDER BY created_at DESC LIMIT 1",
        (user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="No active portal session found")

    return dict(row)


@router.get("/portal/sessions")
async def list_sessions(limit: int = Query(20, ge=1, le=100)):
    """List recent portal sessions (admin endpoint)."""
    rows = db.execute(
        "SELECT session_id, user_id, username, role, tier, infinity_role, routed_to, created_at, is_active FROM portal_sessions ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"sessions": [dict(r) for r in rows], "total": len(rows)}


# ---------------------------------------------------------------------------
# Portal Events & Routing History
# ---------------------------------------------------------------------------


@router.get("/portal/events")
async def list_portal_events(limit: int = Query(50, ge=1, le=500)):
    """List recent portal events."""
    rows = db.execute(
        "SELECT * FROM portal_events ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"events": [dict(r) for r in rows], "total": len(rows)}


@router.get("/portal/routing-history")
async def routing_history(limit: int = Query(50, ge=1, le=500)):
    """List recent gate routing events."""
    rows = db.execute(
        "SELECT * FROM gate_routing_log ORDER BY routed_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"routing_history": [dict(r) for r in rows], "total": len(rows)}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
async def stats():
    """Get Infinity Portal service statistics including smart adaptive layer stats."""
    from Dimensional.dimensionals import get_dimensional_bus
    from Dimensional.dimensionals import get_sentinel_station as _gss

    dimensional_bus = get_dimensional_bus()
    sentinel = _gss()

    active_sessions = db.execute(
        "SELECT COUNT(*) as cnt FROM portal_sessions WHERE is_active = 1"
    ).fetchone()["cnt"]

    total_sessions = db.execute("SELECT COUNT(*) as cnt FROM portal_sessions").fetchone()["cnt"]

    total_events = db.execute("SELECT COUNT(*) as cnt FROM portal_events").fetchone()["cnt"]

    total_routing = db.execute("SELECT COUNT(*) as cnt FROM gate_routing_log").fetchone()["cnt"]

    from config import PORT

    return {
        "service": "infinity-portal",
        "port": PORT,
        "sessions": {
            "active": active_sessions,
            "total": total_sessions,
        },
        "events": {
            "total": total_events,
        },
        "gate_routing": {
            "total": total_routing,
        },
        "dimensional_bus": dimensional_bus.get_stats(),
        "sentinel": sentinel.get_stats(),
        # Phase 22.6: Smart adaptive layer stats
        "smart_adaptive": _worker_kit.get_kit_stats(),
    }
