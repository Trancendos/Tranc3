"""
Trancendos Infinity Portal Service — The Front Door to Infinity
================================================================
The Infinity Portal is the central login page and entry point for the
entire Infinity Ecosystem. It handles user authentication, session
creation, and post-authentication routing through the Infinity Gate.

Architecture:
    User → Infinity Portal (login/register) → Infinity Gate (role router)
                                                     ├→ Infinity-Admin (admin)
                                                     ├→ Arcadia (user)
                                                     └→ The Citadel (developer/devops)

Features:
    - Unified login and registration endpoints
    - OAuth2 authorization code flow with JWT tokens
    - Tier-aware JWT claims (role, tier, pillar assignments)
    - Infinity Gate routing: post-auth redirect based on role
    - Session management with refresh token rotation
    - MFA (TOTP) support via Infinity Auth integration
    - Dimensional Service heartbeat and Underverse module registration
    - Sentinel Station event publishing for auth events
    - RBAC/ABAC-aware access control
    - OWASP Top 10 hardening middleware

Phase 22.6 Smart Adaptive Enhancements:
    - InfinityHealthOrchestrator: pulse + anomaly + self-repair + config tuning
    - ProactiveDefenseLayer: IP block, threat prediction, incident management
    - InfinityFluidicGateway: liquid-neural weighted routing with causal ordering
    - ForesightEngine: predictive health trajectory on portal events
    - Prometheus /metrics endpoint (auto-mounted by InfinityWorkerKit)
    - /health/smart, /defense/stats, /routing/topology endpoints
    - HotConfig: zero-downtime config hot-reload for portal settings
    - TelemetryMiddleware: auto per-request metrics collection
    - AdaptivePulseController: session-cleaner daemon with dynamic intervals

Port: 8042
Zero-cost: FastAPI + SQLite + httpx. Delegates to infinity-auth for core auth.
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
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

# Phase 22.4: Dimensional Services
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)

# Phase 22: Infinity Ecosystem security
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware
from Dimensional.infinity.nomenclature import (
    GATE_ROUTING,
    INFINITY_LOCATIONS,
    InfinityLocation,
    InfinityRole,
    SentinelChannel,
    Tier,
    TransferSystem,
)
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.rbac import RBACEngine

# Phase 22.3: Sentinel Station event bus
from Dimensional.infinity.sentinel_station import (
    SentinelEvent,
    get_sentinel_station,
)

# Phase 22.6: Smart Adaptive Intelligence
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("INFINITY_PORTAL_PORT", "8042"))
DB_PATH = os.environ.get("INFINITY_PORTAL_DB_PATH", "data/infinity_portal.db")
_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. This service cannot validate tokens without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw

# Upstream service ports
AUTH_SERVICE_PORT = int(os.environ.get("AUTH_SERVICE_PORT", "8005"))
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", f"http://localhost:{AUTH_SERVICE_PORT}")
GATEWAY_SERVICE_PORT = int(os.environ.get("GATEWAY_SERVICE_PORT", "8040"))
GATEWAY_SERVICE_URL = os.environ.get(
    "GATEWAY_SERVICE_URL", f"http://localhost:{GATEWAY_SERVICE_PORT}"
)

logger = logging.getLogger("infinity-portal-service")

# ---------------------------------------------------------------------------
# Security Engines
# ---------------------------------------------------------------------------

rbac_engine = RBACEngine()

# ---------------------------------------------------------------------------
# Sentinel Station & Dimensional Services
# ---------------------------------------------------------------------------

sentinel = get_sentinel_station()
dimensional_registry = get_dimensional_registry()
dimensional_bus = get_dimensional_bus()
underverse_registry = get_underverse_registry()

# Phase 22.6: Smart adaptive worker kit (health + defense + fluidic routing)
worker_kit = InfinityWorkerKit(
    "infinity-portal",
    defense_threshold=10,
    defense_window_seconds=300,
    defense_block_seconds=900,
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class PortalDatabase:
    """SQLite database for portal session and routing persistence."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS portal_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                tier INTEGER NOT NULL DEFAULT 0,
                infinity_role TEXT DEFAULT 'user',
                routed_to TEXT,
                access_token TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                ip_address TEXT,
                user_agent TEXT
            );

            CREATE TABLE IF NOT EXISTS gate_routing_log (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                from_location TEXT NOT NULL DEFAULT 'infinity_portal',
                to_location TEXT NOT NULL,
                routed_at TEXT NOT NULL,
                transfer_system TEXT DEFAULT 'bridge'
            );

            CREATE TABLE IF NOT EXISTS portal_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                username TEXT,
                ip_address TEXT,
                user_agent TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON portal_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_active ON portal_sessions(is_active);
            CREATE INDEX IF NOT EXISTS idx_routing_user ON gate_routing_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON portal_events(event_type);
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


db = PortalDatabase()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PortalLogin(BaseModel):
    """Login request for the Infinity Portal."""

    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=1, max_length=128)
    totp_code: str | None = None
    redirect_to: str | None = None  # Optional post-login redirect


class PortalRegister(BaseModel):
    """Registration request for the Infinity Portal."""

    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")  # user, admin, developer, devops


class PortalSessionResponse(BaseModel):
    """Response after successful login/registration."""

    session_id: str
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    username: str
    role: str
    tier: int
    infinity_role: str
    routed_to: str  # The Infinity Gate routing destination
    routing_url: str  # URL for the routed destination
    transfer_system: str  # bridge, nexus, hive


class GateRoutingResponse(BaseModel):
    """Response from the Infinity Gate routing."""

    user_id: str
    username: str
    role: str
    tier: int
    infinity_role: str
    routed_to: str
    routing_url: str
    location_name: str
    location_purpose: str
    transfer_system: str
    pillar: str | None = None


class PortalStatusResponse(BaseModel):
    """Current portal status and configuration."""

    status: str
    portal_name: str
    ecosystem_name: str
    universe_name: str
    locations: dict
    gate_routing: dict
    transfer_systems: dict
    active_sessions: int
    uptime: float


# ---------------------------------------------------------------------------
# Infinity Gate Routing Logic
# ---------------------------------------------------------------------------


class InfinityGate:
    """The Infinity Gate — role-based post-authentication routing.

    After a user authenticates at the Infinity Portal, the Gate determines
    which Infinity Location they should be routed to based on their role.

    Routing Rules (from nomenclature):
        admin      → Infinity-Admin (management OS)
        user       → Arcadia (user space)
        developer  → The Citadel (developer space)
        devops     → The Citadel (developer space)
        prime      → Infinity-Admin (domain management)
        ai         → Infinity (central hub)
        agent      → Infinity (central hub)
        bot        → Infinity (central hub)
        service    → Infinity (central hub)
    """

    # Extended routing beyond the base GATE_ROUTING from nomenclature
    EXTENDED_ROUTING: dict[str, InfinityLocation] = {
        **GATE_ROUTING,
        "prime": InfinityLocation.ADMIN,
        "ai": InfinityLocation.CENTRAL,
        "agent": InfinityLocation.CENTRAL,
        "bot": InfinityLocation.CENTRAL,
        "service": InfinityLocation.CENTRAL,
    }

    # Role to Tier mapping
    ROLE_TIER_MAP: dict[str, Tier] = {
        "admin": Tier.HUMAN,
        "user": Tier.HUMAN,
        "developer": Tier.HUMAN,
        "devops": Tier.HUMAN,
        "prime": Tier.PRIME,
        "ai": Tier.AI,
        "agent": Tier.AGENT,
        "bot": Tier.BOT,
        "service": Tier.BOT,
    }

    # Role to InfinityRole mapping
    ROLE_INFINITY_ROLE_MAP: dict[str, InfinityRole] = {
        "admin": InfinityRole.ADMIN,
        "user": InfinityRole.USER,
        "developer": InfinityRole.USER,
        "devops": InfinityRole.USER,
        "prime": InfinityRole.PRIME,
        "ai": InfinityRole.AI,
        "agent": InfinityRole.AGENT,
        "bot": InfinityRole.BOT,
        "service": InfinityRole.SERVICE,
    }

    @classmethod
    def route(cls, role: str) -> GateRoutingResponse:
        """Route a user based on their role to the appropriate Infinity Location.

        This is the core of the Infinity Gate — after Portal authentication,
        the user is routed through the Gate to their destination.
        """
        role_lower = role.lower().strip()
        destination = cls.EXTENDED_ROUTING.get(role_lower, InfinityLocation.ARCADIA)
        location_info = INFINITY_LOCATIONS.get(destination, {})
        tier = cls.ROLE_TIER_MAP.get(role_lower, Tier.HUMAN)
        infinity_role = cls.ROLE_INFINITY_ROLE_MAP.get(role_lower, InfinityRole.USER)

        # Determine transfer system based on destination
        if destination in (
            InfinityLocation.ADMIN,
            InfinityLocation.ARCADIA,
            InfinityLocation.CITADEL,
        ):
            transfer = TransferSystem.BRIDGE
        elif destination in (InfinityLocation.CENTRAL,):
            transfer = TransferSystem.NEXUS
        else:
            transfer = TransferSystem.BRIDGE

        # Build routing URL based on destination
        routing_urls = {
            InfinityLocation.PORTAL: "/infinity-portal",
            InfinityLocation.GATE: "/infinity-gate",
            InfinityLocation.CENTRAL: "/infinity",
            InfinityLocation.ONE: "/infinity-one",
            InfinityLocation.ADMIN: "/infinity-admin",
            InfinityLocation.BRIDGE: "/infinity-bridge",
            InfinityLocation.ARCADIA: "/arcadia",
            InfinityLocation.CITADEL: "/the-citadel",
            InfinityLocation.SENTINEL: "/sentinel-station",
        }

        return GateRoutingResponse(
            user_id="",  # Filled by caller
            username="",  # Filled by caller
            role=role_lower,
            tier=tier.value,
            infinity_role=infinity_role.value,
            routed_to=destination.value,
            routing_url=routing_urls.get(destination, "/arcadia"),
            location_name=location_info.get("name", destination.value),
            location_purpose=location_info.get("purpose", ""),
            transfer_system=transfer.value,
        )


gate = InfinityGate()


# ---------------------------------------------------------------------------
# Auth Service Client
# ---------------------------------------------------------------------------


async def call_auth_service(method: str, path: str, json_data: dict | None = None) -> dict:
    """Call the Infinity Auth service for authentication operations."""
    url = f"{AUTH_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            if method == "POST":
                response = await client.post(url, json=json_data)
            elif method == "GET":
                response = await client.get(url)
            else:
                raise ValueError(f"Unsupported method: {method}")

            if response.status_code >= 400:
                try:
                    error_detail = response.json().get("detail", response.text)
                except Exception:
                    error_detail = response.text
                raise HTTPException(status_code=response.status_code, detail=error_detail)

            return response.json()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail="Infinity Auth service unavailable. Please try again later.",
        ) from None
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Infinity Auth service timeout. Please try again later.",
        ) from None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the Infinity Portal service."""
    # ── Startup ──
    logger.info("Infinity Portal starting on port %d", PORT)

    # Start Sentinel Station
    await sentinel.start()

    # Start Dimensional Service Bus
    await dimensional_bus.start()

    # Phase 22.6: Start smart adaptive worker kit
    await worker_kit.startup(app, sentinel=sentinel)

    # Register pulse daemons for background tasks
    worker_kit.health.register_daemon("session_cleaner", baseline_interval=300.0)
    worker_kit.health.register_daemon("routing_log_pruner", baseline_interval=3600.0)
    worker_kit.health.register_daemon("health_reporter", baseline_interval=60.0)

    # Register heartbeats
    dimensional_registry.heartbeat("infinity_portal")
    underverse_registry.heartbeat("gate_router")
    underverse_registry.heartbeat("session_manager")

    # Publish portal startup event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="portal_started",
            source="infinity_portal",
            payload={
                "port": PORT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "smart_adaptive": True,
                "subsystems": list(worker_kit.get_kit_stats().get("subsystems", {}).keys()),
            },
        )
    )

    logger.info("Infinity Portal ready — the front door to the Infinity Ecosystem ✨")

    # Background health reporting loop
    async def _background_loop():
        while True:
            try:
                await asyncio.sleep(10)
                # Session cleaner daemon
                if worker_kit.health.should_fire("session_cleaner"):
                    active = db.execute(
                        "SELECT COUNT(*) as cnt FROM portal_sessions WHERE is_active = 1"
                    ).fetchone()["cnt"]
                    worker_kit.health.record_metric("portal_active_sessions", float(active))
                    worker_kit.health.record_fire("session_cleaner")

                # Health reporter daemon
                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    summary_dict = summary.to_dict()
                    score = summary_dict.get("health_score", 1.0)
                    worker_kit.health.update_health(score)
                    worker_kit.health.record_fire("health_reporter")

                    # Publish health to Sentinel
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="health_report",
                            source="infinity_portal",
                            payload=summary_dict,
                        )
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Background loop error: %s", exc)

    _bg_task = asyncio.create_task(_background_loop())

    yield

    # ── Shutdown ──
    logger.info("Infinity Portal shutting down...")
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass

    # Publish shutdown event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="portal_stopping",
            source="infinity_portal",
            payload={"timestamp": datetime.now(timezone.utc).isoformat()},
        )
    )

    # Stop all layers
    await worker_kit.shutdown()
    await dimensional_bus.stop()
    await sentinel.stop()

    logger.info("Infinity Portal stopped")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Infinity Portal — The Front Door to Infinity",
    description=(
        "The Infinity Portal is the central login page and entry point for the "
        "entire Infinity Ecosystem. Users authenticate here and are routed through "
        "the Infinity Gate to their designated location based on their role."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)

# CORS
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

# OWASP Hardening (outer middleware)
app.add_middleware(OWASPHardeningMiddleware)

# Auth Gateway (inner middleware — allows public portal paths)
app.add_middleware(
    AuthGatewayMiddleware,
    jwt_secret=JWT_SECRET,
    public_paths={
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/portal/login",
        "/portal/register",
        "/portal/status",
        "/portal/locations",
        "/portal/gate-info",
        "/portal/transfer-systems",
    },
    enforced_paths={
        "/portal/session",
        "/portal/route",
        "/portal/logout",
        "/gate/route",
    },
)


# ---------------------------------------------------------------------------
# Helper Functions
# ---------------------------------------------------------------------------


def _get_db() -> PortalDatabase:
    return db


def _log_portal_event(
    event_type: str,
    user_id: str | None = None,
    username: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    payload: dict | None = None,
) -> None:
    """Log a portal event to the database."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO portal_events (id, event_type, user_id, username, ip_address, user_agent, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (
            uuid.uuid4().hex[:16],
            event_type,
            user_id,
            username,
            ip_address,
            user_agent,
            json.dumps(payload) if payload else "{}",
            now,
        ),
    )
    db.commit()


def _create_portal_session(
    user_id: str,
    username: str,
    role: str,
    tier: Tier,
    infinity_role: InfinityRole,
    routed_to: str,
    access_token: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> str:
    """Create a portal session in the database."""
    session_id = uuid.uuid4().hex[:24]
    now = datetime.now(timezone.utc).isoformat()
    expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()

    db.execute(
        """INSERT INTO portal_sessions
           (session_id, user_id, username, role, tier, infinity_role, routed_to,
            access_token, created_at, expires_at, ip_address, user_agent)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            session_id,
            user_id,
            username,
            role,
            tier.value,
            infinity_role.value,
            routed_to,
            access_token,
            now,
            expires_at,
            ip_address,
            user_agent,
        ),
    )
    db.commit()
    return session_id


def _log_gate_routing(
    user_id: str,
    username: str,
    role: str,
    from_location: str,
    to_location: str,
    transfer_system: str = "bridge",
) -> None:
    """Log a gate routing event."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO gate_routing_log
           (id, user_id, username, role, from_location, to_location, routed_at, transfer_system)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex[:16],
            user_id,
            username,
            role,
            from_location,
            to_location,
            now,
            transfer_system,
        ),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Health & Status Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check for the Infinity Portal service."""
    health_summary = worker_kit.health.get_health_summary()
    return {
        "status": "healthy",
        "service": "infinity-portal",
        "location": "Infinity Portal",
        "purpose": "Central Login Page — The front entrance to the Infinity Ecosystem",
        "dimensional_bus": dimensional_bus.is_running,
        "sentinel": sentinel.is_running,
        # Phase 22.6: Smart health info
        "health_score": health_summary.to_dict().get("health_score", 1.0),
        "health_tier": health_summary.to_dict().get("health_tier", "EXCELLENT"),
        "smart_adaptive": True,
    }


@app.get("/portal/status", response_model=PortalStatusResponse)
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
# Portal Login & Registration (Delegates to Infinity Auth)
# ---------------------------------------------------------------------------


@app.post("/portal/login", response_model=PortalSessionResponse)
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
    defense_result = await worker_kit.defense.evaluate_request(
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
    auth_data = {
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
        fluid_route = await worker_kit.gateway.route(role, auth_result["user_id"])
        worker_kit.gateway.record_route_success(
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
    worker_kit.health.record_request(latency_ms=latency_ms)
    worker_kit.health.record_metric("portal_logins", 1.0)

    # Publish Sentinel event for auth activity
    await sentinel.publish(
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


@app.post("/portal/register", response_model=PortalSessionResponse)
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
    defense_result = await worker_kit.defense.evaluate_request(
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
    worker_kit.health.record_request(latency_ms=latency_ms)
    worker_kit.health.record_metric("portal_registrations", 1.0)

    # Publish Sentinel event
    await sentinel.publish(
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


@app.post("/portal/logout")
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
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="user_logout",
            source="infinity_portal",
            payload={"user_id": user_id, "username": username},
        )
    )

    return {"message": "Logged out from Infinity Portal", "redirect": "/portal/login"}


# ---------------------------------------------------------------------------
# Infinity Gate Routing Endpoint
# ---------------------------------------------------------------------------


@app.post("/gate/route", response_model=GateRoutingResponse)
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


@app.get("/portal/locations")
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


@app.get("/portal/gate-info")
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


@app.get("/portal/transfer-systems")
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


@app.get("/portal/session")
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


@app.get("/portal/sessions")
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


@app.get("/portal/events")
async def list_portal_events(limit: int = Query(50, ge=1, le=500)):
    """List recent portal events."""
    rows = db.execute(
        "SELECT * FROM portal_events ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return {"events": [dict(r) for r in rows], "total": len(rows)}


@app.get("/portal/routing-history")
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


@app.get("/stats")
async def stats():
    """Get Infinity Portal service statistics including smart adaptive layer stats."""
    active_sessions = db.execute(
        "SELECT COUNT(*) as cnt FROM portal_sessions WHERE is_active = 1"
    ).fetchone()["cnt"]

    total_sessions = db.execute("SELECT COUNT(*) as cnt FROM portal_sessions").fetchone()["cnt"]

    total_events = db.execute("SELECT COUNT(*) as cnt FROM portal_events").fetchone()["cnt"]

    total_routing = db.execute("SELECT COUNT(*) as cnt FROM gate_routing_log").fetchone()["cnt"]

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
        "smart_adaptive": worker_kit.get_kit_stats(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
