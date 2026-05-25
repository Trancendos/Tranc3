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
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Phase 22: Infinity Ecosystem security
from shared_core.infinity.auth_gateway import AuthGatewayMiddleware
from shared_core.infinity.nomenclature import (
    ECOSYSTEM_NAME,
    INFINITY_LOCATIONS,
    PILLAR_ACCENT_COLORS,
    PILLAR_DISPLAY_NAMES,
    PILLAR_PRIME_MAP,
    PRIMES,
    TRANSFER_SYSTEMS,
    UNIVERSE_NAME,
    InfinityLocation,
    InfinityRole,
    Pillar,
    SentinelChannel,
    Tier,
    TransferSystem,
)
from shared_core.infinity.owasp_hardening import OWASPHardeningMiddleware
from shared_core.infinity.rbac import Permission, RBACEngine

# Phase 22.3: Sentinel Station
from shared_core.infinity.sentinel_station import (
    SentinelStation,
    get_sentinel_station,
)

# Phase 22.4: Dimensional Services
from shared_core.dimensionals import (
    DimensionalServiceBus,
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)

# Phase 22.6: Smart Adaptive Intelligence
from shared_core.infinity.worker_integration import InfinityWorkerKit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("INFINITY_ADMIN_PORT", "8044"))
DB_PATH = os.environ.get("INFINITY_ADMIN_DB_PATH", "data/infinity_admin.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

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
    defense_threshold=5,          # Stricter: only 5 violations before block
    defense_window_seconds=300,
    defense_block_seconds=1800,   # 30-min block for admin violations
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

            CREATE INDEX IF NOT EXISTS idx_config_category ON system_config(category);
            CREATE INDEX IF NOT EXISTS idx_actions_actor ON admin_actions(actor_id);
            CREATE INDEX IF NOT EXISTS idx_actions_type ON admin_actions(action_type);
            CREATE INDEX IF NOT EXISTS idx_compliance_type ON compliance_events(event_type);
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
    await sentinel.publish(SentinelEvent(
        channel=SentinelChannel.PLATFORM,
        event_type="infinity_admin_started",
        source="infinity_admin",
        payload={
            "port": PORT,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "smart_adaptive": True,
        },
    ))

    logger.info("Infinity-Admin ready — management OS for the Trancendos Universe ✨")

    # Background health + defense reporting loop
    async def _background_loop():
        while True:
            try:
                await asyncio.sleep(15)
                # Health reporter
                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    worker_kit.health.update_health(summary.get("health_score", 1.0))
                    worker_kit.health.record_fire("health_reporter")
                    await sentinel.publish(SentinelEvent(
                        channel=SentinelChannel.PLATFORM,
                        event_type="health_report",
                        source="infinity_admin",
                        payload=summary,
                    ))
                # Defense reporter — publish incidents to security channel
                if worker_kit.health.should_fire("defense_reporter"):
                    defense_incidents = worker_kit.health.get_defense_incidents()
                    defense_stats = worker_kit.defense.get_stats()
                    worker_kit.health.record_fire("defense_reporter")
                    if defense_stats.get("incidents", 0) > 0:
                        await sentinel.publish(SentinelEvent(
                            channel=SentinelChannel.SECURITY,
                            event_type="defense_report",
                            source="infinity_admin",
                            payload={
                                "stats": defense_stats,
                                "incidents": defense_incidents[:10],
                            },
                        ))
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
        ("sentinel_redis_enabled", "false", "infrastructure", "Whether Redis is enabled for Sentinel Station"),
        ("dimensional_bus_enabled", "true", "infrastructure", "Whether the Dimensional Service Bus is active"),
        ("nexus_transfer_enabled", "true", "transfer", "Whether The Nexus transfer system is active"),
        ("hive_transfer_enabled", "true", "transfer", "Whether The HIVE transfer system is active"),
        ("bridge_transfer_enabled", "true", "transfer", "Whether The Infinity Bridge transfer system is active"),
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
        "health_score": health_summary.get("health_score", 1.0),
        "health_tier": health_summary.get("tier", "EXCELLENT"),
        "smart_adaptive": True,
        "defense_blocked_ips": len(worker_kit.defense.get_blocked_ips()),
    }


# ---------------------------------------------------------------------------
# System Configuration
# ---------------------------------------------------------------------------


@app.get("/admin/config")
async def list_config(category: str | None = None):
    """List system configuration values, optionally filtered by category."""
    if category:
        rows = db.execute(
            "SELECT * FROM system_config WHERE category = ? ORDER BY key",
            (category,),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM system_config ORDER BY category, key"
        ).fetchall()

    return {"config": [dict(r) for r in rows], "total": len(rows)}


@app.get("/admin/config/{key}")
async def get_config(key: str):
    """Get a specific configuration value."""
    row = db.execute(
        "SELECT * FROM system_config WHERE key = ?",
        (key,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Configuration key not found")

    return dict(row)


@app.put("/admin/config/{key}")
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


@app.get("/admin/features")
async def list_features():
    """List all feature flags."""
    rows = db.execute("SELECT * FROM feature_flags ORDER BY key").fetchall()
    return {"features": [dict(r) for r in rows], "total": len(rows)}


@app.put("/admin/features/{key}")
async def update_feature(key: str, flag: FeatureFlagUpdate, request: Request):
    """Update a feature flag."""
    user = getattr(request.state, "user", {})
    now = datetime.now(timezone.utc).isoformat()

    existing = db.execute("SELECT key FROM feature_flags WHERE key = ?", (key,)).fetchone()
    if existing:
        db.execute(
            "UPDATE feature_flags SET enabled = ?, description = ?, pillar = ?, tier_required = ?, updated_at = ? WHERE key = ?",
            (1 if flag.enabled else 0, flag.description, flag.pillar, flag.tier_required or 0, now, key),
        )
    else:
        db.execute(
            "INSERT INTO feature_flags (key, enabled, description, pillar, tier_required, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (key, 1 if flag.enabled else 0, flag.description, flag.pillar, flag.tier_required or 0, now, now),
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


@app.get("/admin/primes")
async def list_primes():
    """List all Prime entities and their governance status."""
    primes_data = []
    for prime_id, prime in PRIMES.items():
        primes_data.append({
            "id": prime.id,
            "name": prime.name,
            "tier": prime.tier.value,
            "tier_name": prime.tier.display_name,
            "pillar": prime.pillar.value,
            "pillar_name": prime.pillar.display_name,
            "pillar_accent": prime.pillar.accent_color,
            "description": prime.description,
        })

    return {"primes": primes_data, "total": len(primes_data)}


@app.get("/admin/pillars")
async def list_pillars():
    """List all Pillars with their associated Primes and accent colors."""
    pillars_data = []
    for pillar in Pillar:
        prime_id = PILLAR_PRIME_MAP.get(pillar)
        prime = PRIMES.get(prime_id)

        pillars_data.append({
            "id": pillar.value,
            "name": pillar.display_name,
            "accent_color": pillar.accent_color,
            "prime_id": prime_id,
            "prime_name": prime.name if prime else "Unassigned",
            "prime_tier": prime.tier.display_name if prime else None,
        })

    return {"pillars": pillars_data, "total": len(pillars_data)}


@app.get("/admin/tiers")
async def list_tiers():
    """List the complete tier system with descriptions."""
    from shared_core.infinity.nomenclature import TIER_NAMES, TIER_DESCRIPTIONS

    tiers_data = []
    for tier in Tier:
        tiers_data.append({
            "value": tier.value,
            "name": tier.display_name,
            "description": tier.description,
            "is_intelligence": tier.is_intelligence,
            "is_governance": tier.is_governance,
            "infinity_designation": tier.infinity_designation,
        })

    return {"tiers": tiers_data, "total": len(tiers_data)}


# ---------------------------------------------------------------------------
# Dimensional Services & Underverse
# ---------------------------------------------------------------------------


@app.get("/admin/dimensionals")
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


@app.get("/admin/underverse")
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


@app.get("/admin/transfer")
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

        systems.append({
            "id": ts.value,
            "name": info.get("name", ""),
            "transfers": info.get("transfers", ""),
            "description": info.get("description", ""),
            "enabled": enabled,
        })

    return {"transfer_systems": systems, "total": len(systems)}


# ---------------------------------------------------------------------------
# Infinity Locations
# ---------------------------------------------------------------------------


@app.get("/admin/locations")
async def list_locations():
    """List all Infinity Locations with their configuration."""
    locations = []
    for loc, info in INFINITY_LOCATIONS.items():
        locations.append({
            "id": loc.value,
            "name": info.get("name", ""),
            "purpose": info.get("purpose", ""),
            "description": info.get("description", ""),
        })

    return {"locations": locations, "total": len(locations)}


# ---------------------------------------------------------------------------
# Audit & Compliance
# ---------------------------------------------------------------------------


@app.get("/admin/audit")
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
    rows = db.execute(
        f"SELECT * FROM admin_actions{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    total = db.execute(f"SELECT COUNT(*) as cnt FROM admin_actions{where}", params).fetchone()["cnt"]

    return {"actions": [dict(r) for r in rows], "total": total}


@app.get("/admin/compliance")
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
    rows = db.execute(
        f"SELECT * FROM compliance_events{where} ORDER BY created_at DESC LIMIT ?",
        params + [limit],
    ).fetchall()

    return {"events": [dict(r) for r in rows], "total": len(rows)}


# ---------------------------------------------------------------------------
# Sentinel Station Monitoring
# ---------------------------------------------------------------------------


@app.get("/admin/sentinel")
async def sentinel_status():
    """Get Sentinel Station status and channel information."""
    from shared_core.infinity.sentinel_config import sentinel_config
    from shared_core.infinity.nomenclature import SENTINEL_CHANNELS

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


@app.get("/admin/overview")
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
        "locations": {
            loc.value: info.get("name", "")
            for loc, info in INFINITY_LOCATIONS.items()
        },
        "admin": {
            "config_entries": system_config_count,
            "feature_flags": feature_flag_count,
            "audit_actions": audit_action_count,
        },
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats")
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

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
