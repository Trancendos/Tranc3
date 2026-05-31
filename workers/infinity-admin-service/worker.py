"""
Trancendos Infinity-Admin Service — Administrative Management OS
=================================================================
Infinity-Admin is the administrative management operating system for the
Trancendos Universe. It provides centralized control over the Infinity
Ecosystem, including system configuration, user management, dimensional
services, prime oversight, and infrastructure monitoring.

Architecture:
    Admin (Human, Tier 0) → Infinity-Admin → Full Ecosystem Control
    Prime (Tier 2)        → Infinity-Admin → Domain/Pillar Control

Features:
    - System configuration management (environment, feature flags)
    - User management (list, search, role changes, deactivation)
    - Dimensional services oversight (status, health, underverse modules)
    - Prime and Pillar dashboard (governance status, assignments)
    - Sentinel Station monitoring (channels, events, subscribers)
    - Infrastructure topology overview (nodes, modes, health)
    - Audit log and compliance reporting
    - Transfer system monitoring (Nexus, HIVE, Infinity Bridge)
    - RBAC/ABAC with admin-only access enforcement
    - OWASP Top 10 hardening middleware

Port: 8044
Zero-cost: FastAPI + SQLite. No external deps.
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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Phase 22: Infinity Ecosystem security
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware
from Dimensional.infinity.nomenclature import (
    ECOSYSTEM_NAME,
    INFINITY_LOCATIONS,
    PILLAR_PRIME_MAP,
    PRIMES,
    TRANSFER_SYSTEMS,
    UNIVERSE_NAME,
    Pillar,
    SentinelChannel,
    Tier,
)
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.rbac import RBACEngine

# Phase 22.3: Sentinel Station
from Dimensional.infinity.sentinel_station import (
    SentinelEvent,
    get_sentinel_station,
)

# Phase 22.6: Smart Adaptive Intelligence
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# Phase 22.4: Dimensional Services
try:
    from Dimensional.dimensionals import (
        get_dimensional_bus,
        get_dimensional_registry,
        get_underverse_registry,
    )

    _DIMENSIONAL_AVAILABLE = True
except ImportError:
    _DIMENSIONAL_AVAILABLE = False

    def get_dimensional_bus():  # type: ignore[misc]
        return None

    def get_dimensional_registry():  # type: ignore[misc]
        return None

    def get_underverse_registry():  # type: ignore[misc]
        return None


# Phase 25: Platform Entity Registry (entity name management)
try:
    from src.entities.platform import (
        PLATFORM_ENTITIES,
        get_entity_by_pid,
    )

    _PLATFORM_ENTITIES_AVAILABLE = True
except Exception:  # pragma: no cover
    _PLATFORM_ENTITIES_AVAILABLE = False
    PLATFORM_ENTITIES = {}

    def get_entity_by_pid(pid: str):  # type: ignore[misc]
        return None

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("INFINITY_ADMIN_PORT", "8044"))
DB_PATH = os.environ.get("INFINITY_ADMIN_DB_PATH", "data/infinity_admin.db")
_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. This service cannot validate tokens without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw

logger = logging.getLogger("infinity-admin-service")

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

# Phase 22.6: Smart adaptive worker kit (admin gets higher defense thresholds)
worker_kit = InfinityWorkerKit(
    "infinity-admin",
    defense_threshold=5,  # Stricter: only 5 violations before block
    defense_window_seconds=300,
    defense_block_seconds=1800,  # 30-min block for admin violations
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class AdminDatabase:
    """SQLite database for Infinity-Admin configuration and audit logs."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS system_config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT DEFAULT 'general',
                description TEXT,
                updated_at TEXT NOT NULL,
                updated_by TEXT
            );

            CREATE TABLE IF NOT EXISTS feature_flags (
                key TEXT PRIMARY KEY,
                enabled INTEGER DEFAULT 0,
                description TEXT,
                pillar TEXT,
                tier_required INTEGER DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS admin_actions (
                id TEXT PRIMARY KEY,
                action_type TEXT NOT NULL,
                actor_id TEXT NOT NULL,
                actor_username TEXT,
                target_type TEXT,
                target_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS compliance_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                severity TEXT DEFAULT 'info',
                pillar TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS entity_overrides (
                id TEXT PRIMARY KEY,
                location_pid TEXT NOT NULL,
                entity_type TEXT NOT NULL,
                slot TEXT NOT NULL DEFAULT '',
                original_name TEXT NOT NULL,
                override_name TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT,
                UNIQUE(location_pid, entity_type, slot)
            );

            CREATE INDEX IF NOT EXISTS idx_config_category ON system_config(category);
            CREATE INDEX IF NOT EXISTS idx_actions_actor ON admin_actions(actor_id);
            CREATE INDEX IF NOT EXISTS idx_actions_type ON admin_actions(action_type);
            CREATE INDEX IF NOT EXISTS idx_compliance_type ON compliance_events(event_type);
            CREATE INDEX IF NOT EXISTS idx_overrides_pid ON entity_overrides(location_pid);

            -- Migration: normalise legacy NULL slots to '' so ON CONFLICT upsert fires correctly.
            -- SQLite UNIQUE treats each NULL as distinct; '' is the correct sentinel for no-slot rows.
            -- This UPDATE is a no-op when no NULL rows exist (idempotent on every startup).
            UPDATE entity_overrides SET slot = '' WHERE slot IS NULL;
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


db = AdminDatabase()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ConfigUpdate(BaseModel):
    """Update a system configuration value."""

    value: str
    category: str = Field(default="general")
    description: str | None = None


class FeatureFlagUpdate(BaseModel):
    """Update a feature flag."""

    enabled: bool
    description: str | None = None
    pillar: str | None = None
    tier_required: int | None = None


class AdminActionLog(BaseModel):
    """Log entry for an admin action."""

    id: str
    action_type: str
    actor_id: str
    actor_username: str | None
    target_type: str | None
    target_id: str | None
    details: str | None
    created_at: str


# Phase 25: Entity name management models


class EntityNameUpdate(BaseModel):
    """Request body for renaming any named entity (location, AI, agent, bot)."""

    new_name: str = Field(..., min_length=1, max_length=120, description="The new display name")
    reason: str | None = Field(
        default=None, max_length=500, description="Optional reason for rename"
    )


class EntityTierUpdate(BaseModel):
    """Reassign display tier for an entity slot (admin UI correction).

    entity_ref examples: lead_ai, prime_0, agent_alpha, agent_beta, bot_01
    tier: 0=Human, 1=Orchestrator, 2=Prime, 3=AI, 4=Agent, 5=Bot
    """

    entity_ref: str = Field(..., min_length=1, max_length=40)
    tier: int = Field(..., ge=0, le=5)
    reason: str | None = Field(default=None, max_length=500)


class EntityOverrideRecord(BaseModel):
    """A single persisted name override."""

    id: str
    location_pid: str
    entity_type: str
    slot: str | None
    original_name: str
    override_name: str
    updated_at: str
    updated_by: str | None


class AgentDetail(BaseModel):
    """Detail for a Tier 4 Agent."""

    code_name: str
    description: str | None
    sid: str | None
    has_override: bool = False


class BotDetail(BaseModel):
    """Detail for a Tier 5 Bot."""

    code_name: str
    description: str | None
    nid: str | None
    has_override: bool = False


class EntityDetail(BaseModel):
    """Full detail for a platform entity with overrides applied."""

    pid: str
    location: str
    pillar: str | None
    lead_ai: str | None
    aid: str | None
    primes: list[str]
    agent_alpha: AgentDetail | None
    agent_beta: AgentDetail | None
    bots: dict[str, BotDetail | None]
    worker_port: int | None
    worker_path: str | None
    overrides_applied: dict[str, str]
    platform_available: bool


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the Infinity-Admin service."""
    # ── Startup ──
    logger.info("Infinity-Admin starting on port %d", PORT)

    # Start Sentinel Station
    await sentinel.start()

    # Start Dimensional Service Bus
    await dimensional_bus.start()

    # Phase 22.6: Start smart adaptive worker kit
    await worker_kit.startup(app, sentinel=sentinel)

    # Register pulse daemons
    worker_kit.health.register_daemon("config_auditor", baseline_interval=120.0)
    worker_kit.health.register_daemon("defense_reporter", baseline_interval=300.0)
    worker_kit.health.register_daemon("health_reporter", baseline_interval=60.0)

    # Register heartbeats
    dimensional_registry.heartbeat("infinity_admin")
    underverse_registry.heartbeat("config_manager")

    # Seed default configuration
    _seed_default_config()

    # Publish startup event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="infinity_admin_started",
            source="infinity_admin",
            payload={
                "port": PORT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "smart_adaptive": True,
            },
        )
    )

    logger.info("Infinity-Admin ready — management OS for the Trancendos Universe ✨")

    # Background health + defense reporting loop
    async def _background_loop():
        while True:
            try:
                await asyncio.sleep(15)
                # Health reporter
                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    summary_dict = summary.to_dict()
                    worker_kit.health.update_health(summary_dict.get("health_score", 1.0))
                    worker_kit.health.record_fire("health_reporter")
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="health_report",
                            source="infinity_admin",
                            payload=summary_dict,
                        )
                    )
                # Defense reporter — publish incidents to security channel
                if worker_kit.health.should_fire("defense_reporter"):
                    defense_incidents = worker_kit.health.get_defense_incidents()
                    defense_stats = worker_kit.defense.get_stats()
                    worker_kit.health.record_fire("defense_reporter")
                    if defense_stats.get("incidents", 0) > 0:
                        await sentinel.publish(
                            SentinelEvent(
                                channel=SentinelChannel.SECURITY,
                                event_type="defense_report",
                                source="infinity_admin",
                                payload={
                                    "stats": defense_stats,
                                    "incidents": defense_incidents[:10],
                                },
                            )
                        )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Admin background loop error: %s", exc)

    _bg_task = asyncio.create_task(_background_loop())

    yield

    # ── Shutdown ──
    logger.info("Infinity-Admin shutting down...")
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass
    await worker_kit.shutdown()
    await dimensional_bus.stop()
    await sentinel.stop()
    logger.info("Infinity-Admin stopped")


def _seed_default_config() -> None:
    """Seed default system configuration values."""
    defaults = [
        ("ecosystem_name", ECOSYSTEM_NAME, "general", "Name of the Infinity Ecosystem"),
        ("universe_name", UNIVERSE_NAME, "general", "Name of the Trancendos Universe"),
        ("default_role", "user", "auth", "Default role for new users"),
        ("mfa_required", "false", "security", "Whether MFA is required for all users"),
        ("session_timeout", "3600", "auth", "Session timeout in seconds"),
        ("max_login_attempts", "5", "security", "Maximum login attempts before lockout"),
        (
            "sentinel_redis_enabled",
            "false",
            "infrastructure",
            "Whether Redis is enabled for Sentinel Station",
        ),
        (
            "dimensional_bus_enabled",
            "true",
            "infrastructure",
            "Whether the Dimensional Service Bus is active",
        ),
        (
            "nexus_transfer_enabled",
            "true",
            "transfer",
            "Whether The Nexus transfer system is active",
        ),
        ("hive_transfer_enabled", "true", "transfer", "Whether The HIVE transfer system is active"),
        (
            "bridge_transfer_enabled",
            "true",
            "transfer",
            "Whether The Infinity Bridge transfer system is active",
        ),
    ]

    now = datetime.now(timezone.utc).isoformat()
    for key, value, category, description in defaults:
        existing = db.execute("SELECT key FROM system_config WHERE key = ?", (key,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO system_config (key, value, category, description, updated_at) VALUES (?, ?, ?, ?, ?)",
                (key, value, category, description, now),
            )
    db.commit()


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Infinity-Admin — Administrative Management OS",
    description=(
        "Infinity-Admin is the administrative management operating system for the "
        "Trancendos Universe. It provides centralized control over the Infinity "
        "Ecosystem, including system configuration, user management, dimensional "
        "services oversight, and infrastructure monitoring."
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


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
# OWASP Hardening
app.add_middleware(OWASPHardeningMiddleware)

# Auth Gateway — Admin enforces authentication on most endpoints
app.add_middleware(
    AuthGatewayMiddleware,
    jwt_secret=JWT_SECRET,
    public_paths={
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    },
    enforced_paths={
        "/admin/config",
        "/admin/features",
        "/admin/dimensionals",
        "/admin/underverse",
        "/admin/primes",
        "/admin/pillars",
        "/admin/transfer",
        "/admin/audit",
        "/admin/actions",
        "/admin/entities",
    },
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _log_admin_action(
    action_type: str,
    actor_id: str,
    actor_username: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO admin_actions (id, action_type, actor_id, actor_username, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex[:16],
            action_type,
            actor_id,
            actor_username,
            target_type,
            target_id,
            json.dumps(details) if details else "{}",
            now,
        ),
    )
    db.commit()


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check for the Infinity-Admin service."""
    health_summary = worker_kit.health.get_health_summary()
    return {
        "status": "healthy",
        "service": "infinity-admin",
        "location": "Infinity-Admin",
        "purpose": "Administrative Management OS for the Trancendos Universe",
        "dimensional_bus": dimensional_bus.is_running,
        "sentinel": sentinel.is_running,
        "health_score": health_summary.to_dict().get("health_score", 1.0),
        "health_tier": health_summary.to_dict().get("health_tier", "EXCELLENT"),
        "smart_adaptive": True,
        "defense_blocked_ips": len(worker_kit.defense.get_blocked_ips()),
    }


# ---------------------------------------------------------------------------
# System Configuration
# ---------------------------------------------------------------------------


@_router.get("/admin/config")
async def list_config(category: str | None = None):
    """List system configuration values, optionally filtered by category."""
    if category:
        rows = db.execute(
            "SELECT * FROM system_config WHERE category = ? ORDER BY key",
            (category,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM system_config ORDER BY category, key").fetchall()

    return {"config": [dict(r) for r in rows], "total": len(rows)}


@_router.get("/admin/config/{key}")
async def get_config(key: str):
    """Get a specific configuration value."""
    row = db.execute(
        "SELECT * FROM system_config WHERE key = ?",
        (key,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Configuration key not found")

    return dict(row)


@_router.put("/admin/config/{key}")
async def update_config(key: str, config: ConfigUpdate, request: Request):
    """Update a system configuration value."""
    user = getattr(request.state, "user", {})
    now = datetime.now(timezone.utc).isoformat()

    existing = db.execute("SELECT key FROM system_config WHERE key = ?", (key,)).fetchone()
    if existing:
        db.execute(
            "UPDATE system_config SET value = ?, category = ?, description = ?, updated_at = ?, updated_by = ? WHERE key = ?",
            (config.value, config.category, config.description, now, user.get("sub"), key),
        )
    else:
        db.execute(
            "INSERT INTO system_config (key, value, category, description, updated_at, updated_by) VALUES (?, ?, ?, ?, ?, ?)",
            (key, config.value, config.category, config.description, now, user.get("sub")),
        )
    db.commit()

    _log_admin_action(
        action_type="config_update",
        actor_id=user.get("sub", "unknown"),
        actor_username=user.get("username"),
        target_type="config",
        target_id=key,
        details={"value": config.value, "category": config.category},
    )

    return {"message": "Configuration updated", "key": key, "value": config.value}


# ---------------------------------------------------------------------------
# Feature Flags
# ---------------------------------------------------------------------------


@_router.get("/admin/features")
async def list_features():
    """List all feature flags."""
    rows = db.execute("SELECT * FROM feature_flags ORDER BY key").fetchall()
    return {"features": [dict(r) for r in rows], "total": len(rows)}


@_router.put("/admin/features/{key}")
async def update_feature(key: str, flag: FeatureFlagUpdate, request: Request):
    """Update a feature flag."""
    user = getattr(request.state, "user", {})
    now = datetime.now(timezone.utc).isoformat()

    existing = db.execute("SELECT key FROM feature_flags WHERE key = ?", (key,)).fetchone()
    if existing:
        db.execute(
            "UPDATE feature_flags SET enabled = ?, description = ?, pillar = ?, tier_required = ?, updated_at = ? WHERE key = ?",
            (
                1 if flag.enabled else 0,
                flag.description,
                flag.pillar,
                flag.tier_required or 0,
                now,
                key,
            ),
        )
    else:
        db.execute(
            "INSERT INTO feature_flags (key, enabled, description, pillar, tier_required, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                key,
                1 if flag.enabled else 0,
                flag.description,
                flag.pillar,
                flag.tier_required or 0,
                now,
                now,
            ),
        )
    db.commit()

    _log_admin_action(
        action_type="feature_flag_update",
        actor_id=user.get("sub", "unknown"),
        actor_username=user.get("username"),
        target_type="feature_flag",
        target_id=key,
        details={"enabled": flag.enabled},
    )

    return {"message": "Feature flag updated", "key": key, "enabled": flag.enabled}


# ---------------------------------------------------------------------------
# Primes & Pillars Dashboard
# ---------------------------------------------------------------------------


@_router.get("/admin/primes")
async def list_primes():
    """List all Prime entities and their governance status."""
    primes_data = []
    for _prime_id, prime in PRIMES.items():
        primes_data.append(
            {
                "id": prime.id,
                "name": prime.name,
                "tier": prime.tier.value,
                "tier_name": prime.tier.display_name,
                "pillar": prime.pillar.value,
                "pillar_name": prime.pillar.display_name,
                "pillar_accent": prime.pillar.accent_color,
                "description": prime.description,
            }
        )

    return {"primes": primes_data, "total": len(primes_data)}


@_router.get("/admin/pillars")
async def list_pillars():
    """List all Pillars with their associated Primes and accent colors."""
    pillars_data = []
    for pillar in Pillar:
        prime_id = PILLAR_PRIME_MAP.get(pillar)
        prime = PRIMES.get(prime_id)

        pillars_data.append(
            {
                "id": pillar.value,
                "name": pillar.display_name,
                "accent_color": pillar.accent_color,
                "prime_id": prime_id,
                "prime_name": prime.name if prime else "Unassigned",
                "prime_tier": prime.tier.display_name if prime else None,
            }
        )

    return {"pillars": pillars_data, "total": len(pillars_data)}


@_router.get("/admin/tiers")
async def list_tiers():
    """List the complete tier system with descriptions."""

    tiers_data = []
    for tier in Tier:
        tiers_data.append(
            {
                "value": tier.value,
                "name": tier.display_name,
                "description": tier.description,
                "is_intelligence": tier.is_intelligence,
                "is_governance": tier.is_governance,
                "infinity_designation": tier.infinity_designation,
            }
        )

    return {"tiers": tiers_data, "total": len(tiers_data)}


# ---------------------------------------------------------------------------
# Dimensional Services & Underverse
# ---------------------------------------------------------------------------


@_router.get("/admin/dimensionals")
async def list_dimensionals():
    """List all dimensional services with their status and health."""
    services = dimensional_registry.list_all()
    pillar_summary = dimensional_registry.get_pillar_summary()

    return {
        "services": [
            {
                "id": s.id,
                "name": s.name,
                "pillar": s.pillar.value,
                "pillar_name": s.pillar.display_name,
                "pillar_accent": s.pillar.accent_color,
                "tier": s.tier.value,
                "tier_name": s.tier.display_name,
                "status": s.status.value,
                "prime": s.prime,
                "description": s.description,
                "last_heartbeat": s.last_heartbeat,
            }
            for s in services
        ],
        "pillar_summary": pillar_summary,
        "total": len(services),
    }


@_router.get("/admin/underverse")
async def list_underverse():
    """List all Underverse modules with capabilities index."""
    modules = underverse_registry.list_all()
    capabilities = underverse_registry.get_capabilities_index()
    dimensional_summary = underverse_registry.get_dimensional_summary()

    return {
        "modules": [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "parent_dimensional": m.parent_dimensional,
                "pillar": m.pillar.value if m.pillar else None,
                "tier": m.tier.value if m.tier else None,
                "status": m.status.value,
                "capabilities": m.capabilities,
                "port": m.port,
                "version": m.version,
                "last_active": m.last_active,
            }
            for m in modules
        ],
        "capabilities_index": capabilities,
        "dimensional_summary": dimensional_summary,
        "total": len(modules),
    }


# ---------------------------------------------------------------------------
# Transfer Systems Monitoring
# ---------------------------------------------------------------------------


@_router.get("/admin/transfer")
async def transfer_systems_status():
    """Get the status of all three transfer systems."""
    systems = []
    for ts, info in TRANSFER_SYSTEMS.items():
        # Check if the transfer system is enabled via config
        config_key = f"{ts.value}_transfer_enabled"
        config_row = db.execute(
            "SELECT value FROM system_config WHERE key = ?",
            (config_key,),
        ).fetchone()
        enabled = config_row["value"] == "true" if config_row else True

        systems.append(
            {
                "id": ts.value,
                "name": info.get("name", ""),
                "transfers": info.get("transfers", ""),
                "description": info.get("description", ""),
                "enabled": enabled,
            }
        )

    return {"transfer_systems": systems, "total": len(systems)}


# ---------------------------------------------------------------------------
# Infinity Locations
# ---------------------------------------------------------------------------


@_router.get("/admin/locations")
async def list_locations():
    """List all Infinity Locations with their configuration."""
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


# ---------------------------------------------------------------------------
# Audit & Compliance
# ---------------------------------------------------------------------------


@_router.get("/admin/audit")
async def audit_log(
    action_type: str | None = None,
    actor_id: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    """Get the admin audit log."""
    conditions = []
    params: list[Any] = []

    if action_type:
        conditions.append("action_type = ?")
        params.append(action_type)
    if actor_id:
        conditions.append("actor_id = ?")
        params.append(actor_id)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"SELECT * FROM admin_actions{where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    rows = db.execute(
        query,
        params + [limit, offset],
    ).fetchall()

    count_query = f"SELECT COUNT(*) as cnt FROM admin_actions{where}"
    total = db.execute(count_query, params).fetchone()["cnt"]

    return {"actions": [dict(r) for r in rows], "total": total}


@_router.get("/admin/compliance")
async def compliance_events(
    severity: str | None = None,
    pillar: str | None = None,
    limit: int = Query(100, ge=1, le=1000),
):
    """Get compliance and security events."""
    conditions = []
    params: list[Any] = []

    if severity:
        conditions.append("severity = ?")
        params.append(severity)
    if pillar:
        conditions.append("pillar = ?")
        params.append(pillar)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"SELECT * FROM compliance_events{where} ORDER BY created_at DESC LIMIT ?"
    rows = db.execute(
        query,
        params + [limit],
    ).fetchall()

    return {"events": [dict(r) for r in rows], "total": len(rows)}


# ---------------------------------------------------------------------------
# Sentinel Station Monitoring
# ---------------------------------------------------------------------------


@_router.get("/admin/sentinel")
async def sentinel_status():
    """Get Sentinel Station status and channel information."""
    from Dimensional.infinity.nomenclature import SENTINEL_CHANNELS
    from Dimensional.infinity.sentinel_config import sentinel_config

    return {
        "running": sentinel.is_running,
        "stats": sentinel.get_stats(),
        "config": {
            "redis_enabled": sentinel_config.redis_enabled,
            "redis_url": sentinel_config.redis_url if sentinel_config.redis_enabled else None,
            "channels": [
                {
                    "id": ch.value,
                    "name": info.get("name", ""),
                    "description": info.get("description", ""),
                }
                for ch, info in SENTINEL_CHANNELS.items()
            ],
        },
    }


# ---------------------------------------------------------------------------
# Ecosystem Overview (Admin Dashboard Data)
# ---------------------------------------------------------------------------


@_router.get("/admin/overview")
async def ecosystem_overview():
    """Get a comprehensive overview of the entire Infinity Ecosystem.

    This is the main data source for the admin dashboard, providing
    a holistic view of all systems, services, and governance.
    """
    # System info
    system_config_count = db.execute("SELECT COUNT(*) as cnt FROM system_config").fetchone()["cnt"]
    feature_flag_count = db.execute("SELECT COUNT(*) as cnt FROM feature_flags").fetchone()["cnt"]
    audit_action_count = db.execute("SELECT COUNT(*) as cnt FROM admin_actions").fetchone()["cnt"]

    return {
        "ecosystem": {
            "name": ECOSYSTEM_NAME,
            "universe": UNIVERSE_NAME,
        },
        "governance": {
            "primes": len(PRIMES),
            "pillars": len(Pillar),
            "tiers": len(Tier),
        },
        "services": {
            "dimensionals": len(dimensional_registry.list_all()),
            "underverse_modules": len(underverse_registry.list_all()),
            "dimensional_bus_running": dimensional_bus.is_running,
            "sentinel_running": sentinel.is_running,
        },
        "transfer_systems": {
            ts.value: {"name": info.get("name", ""), "transfers": info.get("transfers", "")}
            for ts, info in TRANSFER_SYSTEMS.items()
        },
        "locations": {loc.value: info.get("name", "") for loc, info in INFINITY_LOCATIONS.items()},
        "admin": {
            "config_entries": system_config_count,
            "feature_flags": feature_flag_count,
            "audit_actions": audit_action_count,
        },
    }


# ---------------------------------------------------------------------------
# Phase 25: Platform Entity Name Management
# ---------------------------------------------------------------------------
# The PLATFORM_ENTITIES dict in src/entities/platform.py is the canonical
# code-level source of truth. Entity overrides are persisted in the
# entity_overrides SQLite table and merged at request time — no code deploys
# needed to rename locations, AIs, agents, or bots.


def _resolve_entity_detail(pid: str) -> EntityDetail | None:
    """Load a platform entity, merge DB overrides, return full detail."""
    if not _PLATFORM_ENTITIES_AVAILABLE:
        return None

    entity = get_entity_by_pid(pid)
    if entity is None:
        return None

    # Load all overrides for this PID
    ov_rows = db.execute(
        "SELECT entity_type, slot, override_name FROM entity_overrides WHERE location_pid = ?",
        (pid,),
    ).fetchall()
    overrides: dict[str, str] = {}
    for r in ov_rows:
        key = r["entity_type"] if not r["slot"] else f"{r['entity_type']}_{r['slot']}"
        overrides[key] = r["override_name"]

    # Resolve location name
    location = overrides.get("location", entity.location)

    # Resolve lead AI name
    lead_ai = overrides.get("lead_ai", entity.lead_ai)

    # Resolve primes list
    raw_primes: list[str] = list(entity.primes) if entity.primes else []
    primes: list[str] = []
    for i, p in enumerate(raw_primes):
        primes.append(overrides.get(f"prime_{i}", p))

    # Resolve agents
    def _agent(attr: str, role: str) -> AgentDetail | None:
        ag = getattr(entity, attr, None)
        if ag is None:
            return None
        name = overrides.get(f"agent_{role}", ag.code_name)
        return AgentDetail(
            code_name=name,
            description=getattr(ag, "description", None),
            sid=getattr(ag, "sid", None),
            has_override=f"agent_{role}" in overrides,
        )

    # Resolve bots
    def _bot(attr: str, slot: str) -> BotDetail | None:
        b = getattr(entity, attr, None)
        if b is None:
            return None
        name = overrides.get(f"bot_{slot}", b.code_name)
        return BotDetail(
            code_name=name,
            description=getattr(b, "description", None),
            nid=getattr(b, "nid", None),
            has_override=f"bot_{slot}" in overrides,
        )

    return EntityDetail(
        pid=entity.pid,
        location=location,
        pillar=entity.pillar.value if entity.pillar else None,
        lead_ai=lead_ai,
        aid=getattr(entity, "aid", None),
        primes=primes,
        agent_alpha=_agent("agent_alpha", "alpha"),
        agent_beta=_agent("agent_beta", "beta"),
        bots={
            "01": _bot("bot_01", "01"),
            "02": _bot("bot_02", "02"),
            "03": _bot("bot_03", "03"),
            "04": _bot("bot_04", "04"),
        },
        worker_port=getattr(entity, "worker_port", None),
        worker_path=getattr(entity, "worker_path", None),
        overrides_applied=overrides,
        platform_available=True,
    )


def _upsert_override(
    location_pid: str,
    entity_type: str,
    slot: str | None,
    original_name: str,
    override_name: str,
    updated_by: str,
) -> None:
    """Insert or replace an entity name override in the DB."""
    slot_val = slot if slot is not None else ""  # sentinel — SQLite UNIQUE treats NULL as distinct
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO entity_overrides
               (id, location_pid, entity_type, slot, original_name, override_name, updated_at, updated_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(location_pid, entity_type, slot)
           DO UPDATE SET override_name=excluded.override_name,
                         updated_at=excluded.updated_at,
                         updated_by=excluded.updated_by""",
        (
            uuid.uuid4().hex[:16],
            location_pid,
            entity_type,
            slot_val,
            original_name,
            override_name,
            now,
            updated_by,
        ),
    )
    db.commit()
    try:
        from src.entities.override_store import invalidate_override_cache

        invalidate_override_cache()
    except ImportError:
        pass


@_router.get("/admin/entities")
async def list_entities(pillar: str | None = None):
    """List all 43 platform entities with current names (DB overrides applied).

    Returns a summary of each entity: PID, location name, lead AI, prime count,
    worker port, and how many name overrides are active.
    """
    if not _PLATFORM_ENTITIES_AVAILABLE:
        return {
            "entities": [],
            "total": 0,
            "platform_available": False,
            "message": "Platform entity registry not accessible from this worker",
        }

    # Preload all overrides in one query — avoids N+1 (3 queries × 43 entities = 129 queries)
    all_ov_rows = db.execute(
        "SELECT location_pid, entity_type, slot, override_name FROM entity_overrides"
    ).fetchall()
    ov_loc_map: dict[str, str] = {}
    ov_ai_map: dict[str, str] = {}
    ov_count_map: dict[str, int] = {}
    for row in all_ov_rows:
        lpid = row["location_pid"]
        ov_count_map[lpid] = ov_count_map.get(lpid, 0) + 1
        if row["entity_type"] == "location" and not row["slot"]:
            ov_loc_map[lpid] = row["override_name"]
        elif row["entity_type"] == "lead_ai" and not row["slot"]:
            ov_ai_map[lpid] = row["override_name"]

    results = []
    for location_name, entity in PLATFORM_ENTITIES.items():
        if pillar and (entity.pillar is None or entity.pillar.value != pillar):
            continue

        pid = getattr(entity, "pid", None)
        if not pid:
            continue

        results.append(
            {
                "pid": pid,
                "location": ov_loc_map.get(pid, location_name),
                "location_original": location_name,
                "pillar": entity.pillar.value if entity.pillar else None,
                "lead_ai": ov_ai_map.get(pid, entity.lead_ai),
                "lead_ai_original": entity.lead_ai,
                "prime_count": len(entity.primes) if entity.primes else 0,
                "worker_port": getattr(entity, "worker_port", None),
                "active_overrides": ov_count_map.get(pid, 0),
            }
        )

    results.sort(key=lambda x: x["pid"])
    return {
        "entities": results,
        "total": len(results),
        "platform_available": True,
    }


@_router.get("/admin/entities/{pid}")
async def get_entity(pid: str):
    """Get full detail for a platform entity with all overrides applied."""
    detail = _resolve_entity_detail(pid)
    if detail is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    return detail.model_dump()


@_router.patch("/admin/entities/{pid}/name")
async def rename_location(pid: str, body: EntityNameUpdate, request: Request):
    """Rename a Location (App). Does not require a code deploy.

    entity_type: 'location', slot: NULL
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    entity = get_entity_by_pid(pid)
    if entity is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    original = entity.location
    _upsert_override(pid, "location", None, original, body.new_name, actor)

    _log_admin_action(
        action_type="entity_rename_location",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity_location",
        target_id=pid,
        details={"original": original, "new_name": body.new_name, "reason": body.reason},
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_renamed",
            source="infinity_admin",
            payload={
                "pid": pid,
                "entity_type": "location",
                "original": original,
                "new_name": body.new_name,
            },
        )
    )

    return {
        "message": "Location renamed",
        "pid": pid,
        "original": original,
        "new_name": body.new_name,
    }


@_router.patch("/admin/entities/{pid}/lead-ai")
async def rename_lead_ai(pid: str, body: EntityNameUpdate, request: Request):
    """Rename the Tier 3 Lead AI for a platform entity.

    entity_type: 'lead_ai', slot: NULL
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    entity = get_entity_by_pid(pid)
    if entity is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    original = entity.lead_ai or ""
    _upsert_override(pid, "lead_ai", None, original, body.new_name, actor)

    _log_admin_action(
        action_type="entity_rename_lead_ai",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity_lead_ai",
        target_id=pid,
        details={"original": original, "new_name": body.new_name, "tier": 3, "reason": body.reason},
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_renamed",
            source="infinity_admin",
            payload={
                "pid": pid,
                "entity_type": "lead_ai",
                "original": original,
                "new_name": body.new_name,
            },
        )
    )

    return {
        "message": "Lead AI renamed",
        "pid": pid,
        "original": original,
        "new_name": body.new_name,
        "tier": 3,
    }


@_router.patch("/admin/entities/{pid}/primes/{prime_idx}")
async def rename_prime(pid: str, prime_idx: int, body: EntityNameUpdate, request: Request):
    """Rename or reassign a Tier 2 Prime at a given index (0-based).

    entity_type: 'prime', slot: str(prime_idx)
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    entity = get_entity_by_pid(pid)
    if entity is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    primes = list(entity.primes) if entity.primes else []
    if prime_idx < 0 or prime_idx >= len(primes):
        raise HTTPException(
            status_code=400,
            detail=f"prime_idx {prime_idx} out of range (entity has {len(primes)} prime(s))",
        )

    original = primes[prime_idx]
    slot = str(prime_idx)
    _upsert_override(pid, "prime", slot, original, body.new_name, actor)

    _log_admin_action(
        action_type="entity_rename_prime",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity_prime",
        target_id=f"{pid}:prime:{prime_idx}",
        details={
            "original": original,
            "new_name": body.new_name,
            "prime_idx": prime_idx,
            "tier": 2,
            "reason": body.reason,
        },
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_renamed",
            source="infinity_admin",
            payload={
                "pid": pid,
                "entity_type": "prime",
                "slot": slot,
                "original": original,
                "new_name": body.new_name,
            },
        )
    )

    return {
        "message": "Prime renamed",
        "pid": pid,
        "prime_idx": prime_idx,
        "original": original,
        "new_name": body.new_name,
        "tier": 2,
    }


@_router.patch("/admin/entities/{pid}/agents/{role}")
async def rename_agent(pid: str, role: str, body: EntityNameUpdate, request: Request):
    """Rename a Tier 4 Agent. role must be 'alpha' or 'beta'.

    entity_type: 'agent', slot: 'alpha' | 'beta'
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    if role not in ("alpha", "beta"):
        raise HTTPException(status_code=400, detail="role must be 'alpha' or 'beta'")

    entity = get_entity_by_pid(pid)
    if entity is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    agent = entity.agent_alpha if role == "alpha" else entity.agent_beta
    if agent is None:
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' has no agent_{role}")

    original = agent.code_name
    _upsert_override(pid, "agent", role, original, body.new_name, actor)

    _log_admin_action(
        action_type="entity_rename_agent",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity_agent",
        target_id=f"{pid}:agent:{role}",
        details={
            "original": original,
            "new_name": body.new_name,
            "role": role,
            "tier": 4,
            "reason": body.reason,
        },
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_renamed",
            source="infinity_admin",
            payload={
                "pid": pid,
                "entity_type": "agent",
                "slot": role,
                "original": original,
                "new_name": body.new_name,
            },
        )
    )

    return {
        "message": "Agent renamed",
        "pid": pid,
        "role": role,
        "original": original,
        "new_name": body.new_name,
        "tier": 4,
    }


@_router.patch("/admin/entities/{pid}/bots/{slot}")
async def rename_bot(pid: str, slot: str, body: EntityNameUpdate, request: Request):
    """Rename a Tier 5 Bot. slot must be '01', '02', '03', or '04'.

    entity_type: 'bot', slot: '01' | '02' | '03' | '04'
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    valid_slots = ("01", "02", "03", "04")
    if slot not in valid_slots:
        raise HTTPException(status_code=400, detail=f"slot must be one of {valid_slots}")

    entity = get_entity_by_pid(pid)
    if entity is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    bot = getattr(entity, f"bot_{slot}", None)
    if bot is None:
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' has no bot_{slot}")

    original = bot.code_name
    _upsert_override(pid, "bot", slot, original, body.new_name, actor)

    _log_admin_action(
        action_type="entity_rename_bot",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity_bot",
        target_id=f"{pid}:bot:{slot}",
        details={
            "original": original,
            "new_name": body.new_name,
            "slot": slot,
            "tier": 5,
            "reason": body.reason,
        },
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_renamed",
            source="infinity_admin",
            payload={
                "pid": pid,
                "entity_type": "bot",
                "slot": slot,
                "original": original,
                "new_name": body.new_name,
            },
        )
    )

    return {
        "message": "Bot renamed",
        "pid": pid,
        "slot": slot,
        "original": original,
        "new_name": body.new_name,
        "tier": 5,
    }


@_router.get("/admin/entities/{pid}/overrides")
async def list_entity_overrides(pid: str):
    """List all active name overrides for a given entity PID."""
    if _PLATFORM_ENTITIES_AVAILABLE and get_entity_by_pid(pid) is None:
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    rows = db.execute(
        "SELECT * FROM entity_overrides WHERE location_pid = ? ORDER BY entity_type, slot",
        (pid,),
    ).fetchall()

    return {"pid": pid, "overrides": [dict(r) for r in rows], "total": len(rows)}


@_router.delete("/admin/entities/{pid}/overrides")
async def reset_entity_overrides(
    pid: str,
    request: Request,
    entity_type: str | None = Query(None, description="Limit reset to a specific entity_type"),
    slot: str | None = Query(
        None, description="Limit reset to a specific slot (pass empty string for no-slot rows)"
    ),
):
    """Reset name overrides for an entity — restores code defaults.

    Pass no query params to reset all overrides for the entity.
    Pass ?entity_type=lead_ai to reset only that type.
    Pass ?entity_type=location&slot= to reset a specific no-slot row.
    Pass ?entity_type=agent&slot=alpha to reset a specific slotted row.
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    conditions = ["location_pid = ?"]
    params: list[Any] = [pid]
    if entity_type:
        conditions.append("entity_type = ?")
        params.append(entity_type)
    if slot is not None:
        conditions.append("slot = ?")
        params.append("" if slot in ("null", "") else slot)
    where = " AND ".join(conditions)

    count_query = f"SELECT COUNT(*) as cnt FROM entity_overrides WHERE {where}"
    count_row = db.execute(
        count_query,
        tuple(params),
    ).fetchone()
    count = count_row["cnt"]

    delete_query = f"DELETE FROM entity_overrides WHERE {where}"
    db.execute(delete_query, tuple(params))
    db.commit()

    _log_admin_action(
        action_type="entity_overrides_reset",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity",
        target_id=pid,
        details={"overrides_cleared": count, "entity_type": entity_type, "slot": slot},
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_overrides_reset",
            source="infinity_admin",
            payload={
                "pid": pid,
                "overrides_cleared": count,
                "entity_type": entity_type,
                "slot": slot,
            },
        )
    )

    return {
        "message": "Entity overrides reset to code defaults",
        "pid": pid,
        "entity_type": entity_type,
        "slot": slot,
        "overrides_cleared": count,
    }


@_router.get("/admin/entities/{pid}/overrides/{entity_type}")
async def get_entity_overrides_by_type(pid: str, entity_type: str, slot: str | None = None):
    """Get overrides for a specific entity type (and optional slot) within an entity."""
    conditions = ["location_pid = ?", "entity_type = ?"]
    params: list[Any] = [pid, entity_type]

    if slot is not None:
        conditions.append("slot = ?")
        params.append(slot)

    rows = db.execute(
        f"SELECT * FROM entity_overrides WHERE {' AND '.join(conditions)} ORDER BY slot",
        params,
    ).fetchall()

    return {"pid": pid, "entity_type": entity_type, "overrides": [dict(r) for r in rows]}


_VALID_TIER_REFS = frozenset(
    {
        "lead_ai",
        "agent_alpha",
        "agent_beta",
        "bot_01",
        "bot_02",
        "bot_03",
        "bot_04",
    }
)


@_router.patch("/admin/entities/{pid}/tier")
async def assign_entity_tier(pid: str, body: EntityTierUpdate, request: Request):
    """Assign display tier for an entity slot (correct mislabeled UI tiers).

    Stores entity_type='tier', slot=entity_ref, override_name=str(tier).
    Does not move code-level class hierarchy — display/governance correction only.
    """
    user = getattr(request.state, "user", {})
    actor = user.get("sub", "unknown")

    if body.entity_ref.startswith("prime_"):
        pass
    elif body.entity_ref not in _VALID_TIER_REFS:
        raise HTTPException(
            status_code=400,
            detail=f"entity_ref must be one of {_VALID_TIER_REFS} or prime_N (e.g. prime_0)",
        )

    entity = get_entity_by_pid(pid)
    if entity is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    original = f"tier_default_{body.entity_ref}"
    _upsert_override(
        pid,
        "tier",
        body.entity_ref,
        original,
        str(body.tier),
        actor,
    )

    _log_admin_action(
        action_type="entity_tier_assigned",
        actor_id=actor,
        actor_username=user.get("username"),
        target_type="entity_tier",
        target_id=f"{pid}:{body.entity_ref}",
        details={
            "entity_ref": body.entity_ref,
            "tier": body.tier,
            "reason": body.reason,
        },
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="entity_tier_assigned",
            source="infinity_admin",
            payload={
                "pid": pid,
                "entity_ref": body.entity_ref,
                "tier": body.tier,
            },
        )
    )

    return {
        "message": "Tier assignment saved",
        "pid": pid,
        "entity_ref": body.entity_ref,
        "tier": body.tier,
    }


@_router.get("/admin/orchestrators")
async def list_orchestrators():
    """Tier 1 Orchestrators — Cornelius MacIntyre, The Queen, tAImra (canonical)."""
    orchestrators = [p for p in PRIMES.values() if p.tier == Tier.ORCHESTRATOR]
    return {
        "tier": 1,
        "tier_name": Tier.ORCHESTRATOR.display_name,
        "orchestrators": [
            {
                "id": p.id,
                "name": p.name,
                "pillar": p.pillar.value if p.pillar else None,
                "description": p.description,
            }
            for p in orchestrators
        ],
        "total": len(orchestrators),
        "note": "Global orchestrator names are edited in nomenclature.py; per-location primes use PATCH .../primes/{idx}",
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def stats():
    """Get Infinity-Admin service statistics."""
    system_config_count = db.execute("SELECT COUNT(*) as cnt FROM system_config").fetchone()["cnt"]
    feature_flag_count = db.execute("SELECT COUNT(*) as cnt FROM feature_flags").fetchone()["cnt"]
    audit_action_count = db.execute("SELECT COUNT(*) as cnt FROM admin_actions").fetchone()["cnt"]
    compliance_count = db.execute("SELECT COUNT(*) as cnt FROM compliance_events").fetchone()["cnt"]

    return {
        "service": "infinity-admin",
        "port": PORT,
        "admin": {
            "config_entries": system_config_count,
            "feature_flags": feature_flag_count,
            "audit_actions": audit_action_count,
            "compliance_events": compliance_count,
        },
        "dimensional_bus": dimensional_bus.get_stats(),
        "sentinel": sentinel.get_stats(),
        # Phase 22.6: Smart adaptive layer stats
        "smart_adaptive": worker_kit.get_kit_stats(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
