"""
Trancendos Infinity-One Service — Single Identity Management
=============================================================
Infinity-One is the user identity and management service in the Infinity Ecosystem.
It provides "one login, multi-app access" — a single identity that spans across
all applications and services in the Trancendos Universe.

Architecture:
    Infinity Portal (login) → Infinity-One (identity) → Arcadia/Citadel/Admin

Features:
    - User profile management (view, update, delete)
    - Role and tier management with Infinity Gate routing
    - Multi-app access tokens (one identity, many applications)
    - Identity resolution across the ecosystem
    - User preferences and settings
    - Session tracking and active device management
    - Dimensional Service heartbeat and Underverse module registration
    - Sentinel Station event publishing for identity events
    - RBAC/ABAC-aware access control
    - OWASP Top 10 hardening middleware

Port: 8043
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

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field

# Phase 22: Infinity Ecosystem security
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware
from Dimensional.infinity.nomenclature import (
    SentinelChannel,
)
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.rbac import RBACEngine

# Phase 22.3: Sentinel Station
from Dimensional.infinity.sentinel_station import (
    SentinelEvent,
    get_sentinel_station,
)

# Phase 22.4: Dimensional Services
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)

# Phase 22.6: Smart Adaptive Intelligence
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("INFINITY_ONE_PORT", "8043"))
DB_PATH = os.environ.get("INFINITY_ONE_DB_PATH", "data/infinity_one.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

logger = logging.getLogger("infinity-one-service")

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

# Phase 22.6: Smart adaptive worker kit
worker_kit = InfinityWorkerKit(
    "infinity-one",
    defense_threshold=15,
    defense_window_seconds=300,
    defense_block_seconds=600,
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class OneDatabase:
    """SQLite database for Infinity-One identity management."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS identities (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                display_name TEXT DEFAULT '',
                role TEXT NOT NULL DEFAULT 'user',
                tier INTEGER NOT NULL DEFAULT 0,
                infinity_role TEXT NOT NULL DEFAULT 'user',
                pillar TEXT,
                avatar_url TEXT,
                bio TEXT DEFAULT '',
                preferences TEXT DEFAULT '{}',
                metadata TEXT DEFAULT '{}',
                created_at TEXT NOT NULL,
                updated_at TEXT,
                last_active TEXT,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS app_access (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                app_name TEXT NOT NULL,
                app_role TEXT DEFAULT 'viewer',
                granted_at TEXT NOT NULL,
                granted_by TEXT,
                expires_at TEXT,
                is_revoked INTEGER DEFAULT 0,
                UNIQUE(user_id, app_name)
            );

            CREATE TABLE IF NOT EXISTS devices (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                device_name TEXT,
                device_type TEXT,
                ip_address TEXT,
                user_agent TEXT,
                last_seen TEXT,
                is_trusted INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS identity_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                actor_id TEXT,
                details TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_identities_username ON identities(username);
            CREATE INDEX IF NOT EXISTS idx_identities_role ON identities(role);
            CREATE INDEX IF NOT EXISTS idx_app_access_user ON app_access(user_id);
            CREATE INDEX IF NOT EXISTS idx_devices_user ON devices(user_id);
            CREATE INDEX IF NOT EXISTS idx_identity_events_user ON identity_events(user_id);
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


db = OneDatabase()

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class IdentityCreate(BaseModel):
    """Create a new identity in Infinity-One."""

    user_id: str
    username: str = Field(min_length=3, max_length=50)
    email: EmailStr
    display_name: str = Field(default="", max_length=100)
    role: str = Field(default="user")
    pillar: str | None = None
    avatar_url: str | None = None
    bio: str = Field(default="", max_length=500)


class IdentityUpdate(BaseModel):
    """Update an existing identity."""

    display_name: str | None = None
    email: EmailStr | None = None
    avatar_url: str | None = None
    bio: str | None = None
    preferences: dict | None = None
    role: str | None = None  # Admin-only: change user role
    pillar: str | None = None  # Admin-only: assign pillar


class AppAccessGrant(BaseModel):
    """Grant app access to a user."""

    app_name: str = Field(min_length=1, max_length=100)
    app_role: str = Field(default="viewer")
    expires_at: str | None = None


class IdentityResponse(BaseModel):
    """Response for an identity."""

    user_id: str
    username: str
    email: str
    display_name: str
    role: str
    tier: int
    infinity_role: str
    pillar: str | None
    avatar_url: str | None
    bio: str
    preferences: dict
    created_at: str
    updated_at: str | None
    last_active: str | None
    is_active: bool
    app_access_count: int


class AppAccessResponse(BaseModel):
    """Response for app access entry."""

    id: str
    user_id: str
    app_name: str
    app_role: str
    granted_at: str
    granted_by: str | None
    expires_at: str | None
    is_revoked: bool


class IdentitySummary(BaseModel):
    """Summary of identities in the system."""

    total_identities: int
    active_identities: int
    by_role: dict
    by_tier: dict
    by_pillar: dict


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup/shutdown lifecycle for the Infinity-One service."""
    # ── Startup ──
    logger.info("Infinity-One starting on port %d", PORT)

    # Start Sentinel Station
    await sentinel.start()

    # Start Dimensional Service Bus
    await dimensional_bus.start()

    # Phase 22.6: Start smart adaptive worker kit
    await worker_kit.startup(app, sentinel=sentinel)

    # Register pulse daemons
    worker_kit.health.register_daemon("identity_auditor", baseline_interval=600.0)
    worker_kit.health.register_daemon("health_reporter", baseline_interval=60.0)

    # Register heartbeats
    dimensional_registry.heartbeat("infinity_one")
    underverse_registry.heartbeat("identity_resolver")

    # Publish startup event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="infinity_one_started",
            source="infinity_one",
            payload={
                "port": PORT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "smart_adaptive": True,
            },
        )
    )

    logger.info("Infinity-One ready — single identity, multi-app access ✨")

    # Background health loop
    async def _background_loop():
        while True:
            try:
                await asyncio.sleep(15)
                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    summary_dict = summary.to_dict()
                    worker_kit.health.update_health(summary_dict.get("health_score", 1.0))
                    worker_kit.health.record_fire("health_reporter")
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="health_report",
                            source="infinity_one",
                            payload=summary_dict,
                        )
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Infinity-One background loop error: %s", exc)

    _bg_task = asyncio.create_task(_background_loop())

    yield

    # ── Shutdown ──
    logger.info("Infinity-One shutting down...")
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass
    await worker_kit.shutdown()
    await dimensional_bus.stop()
    await sentinel.stop()
    logger.info("Infinity-One stopped")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Infinity-One — Single Identity Management",
    description=(
        "Infinity-One provides single identity management for the Infinity Ecosystem. "
        "One login, multi-app access — a unified identity that spans across all "
        "applications and services in the Trancendos Universe."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OWASP Hardening
app.add_middleware(OWASPHardeningMiddleware)

# Auth Gateway
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
        "/one/identities",
        "/one/identities/{user_id}",
        "/one/identities/{user_id}/apps",
        "/one/identities/{user_id}/devices",
    },
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db() -> OneDatabase:
    return db


def _log_identity_event(
    event_type: str,
    user_id: str | None = None,
    actor_id: str | None = None,
    details: dict | None = None,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "INSERT INTO identity_events (id, event_type, user_id, actor_id, details, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            uuid.uuid4().hex[:16],
            event_type,
            user_id,
            actor_id,
            json.dumps(details) if details else "{}",
            now,
        ),
    )
    db.commit()


def _identity_from_row(row: sqlite3.Row) -> dict:
    """Convert a database row to an identity dictionary."""
    prefs = row["preferences"] or "{}"
    meta = row["metadata"] or "{}"
    try:
        preferences = json.loads(prefs) if isinstance(prefs, str) else prefs
    except (json.JSONDecodeError, TypeError):
        preferences = {}
    try:
        metadata = json.loads(meta) if isinstance(meta, str) else meta
    except (json.JSONDecodeError, TypeError):
        metadata = {}

    return {
        "user_id": row["user_id"],
        "username": row["username"],
        "email": row["email"],
        "display_name": row["display_name"],
        "role": row["role"],
        "tier": row["tier"],
        "infinity_role": row["infinity_role"],
        "pillar": row["pillar"],
        "avatar_url": row["avatar_url"],
        "bio": row["bio"],
        "preferences": preferences,
        "metadata": metadata,
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "last_active": row["last_active"],
        "is_active": bool(row["is_active"]),
    }


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check for the Infinity-One service."""
    health_summary = worker_kit.health.get_health_summary()
    return {
        "status": "healthy",
        "service": "infinity-one",
        "location": "Infinity-One",
        "purpose": "Single Identity Management — one login, multi-app access",
        "dimensional_bus": dimensional_bus.is_running,
        "sentinel": sentinel.is_running,
        "health_score": health_summary.to_dict().get("health_score", 1.0),
        "health_tier": health_summary.to_dict().get("health_tier", "EXCELLENT"),
        "smart_adaptive": True,
    }


# ---------------------------------------------------------------------------
# Identity CRUD
# ---------------------------------------------------------------------------


@app.post("/one/identities", response_model=IdentityResponse)
async def create_identity(request: Request, identity: IdentityCreate):
    """Create a new identity in Infinity-One."""
    # Check if identity already exists
    existing = db.execute(
        "SELECT user_id FROM identities WHERE user_id = ? OR username = ?",
        (identity.user_id, identity.username),
    ).fetchone()
    if existing:
        raise HTTPException(status_code=409, detail="Identity already exists")

    # Determine tier and infinity_role from role
    from Dimensional.infinity.nomenclature import (
        get_tier_for_role as _gtr,
        get_infinity_role_for_role as _girr,
    )

    tier = _gtr(identity.role)
    infinity_role = _girr(identity.role)

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """INSERT INTO identities
           (user_id, username, email, display_name, role, tier, infinity_role, pillar,
            avatar_url, bio, preferences, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            identity.user_id,
            identity.username,
            identity.email,
            identity.display_name,
            identity.role,
            tier.value,
            infinity_role.value,
            identity.pillar,
            identity.avatar_url,
            identity.bio,
            json.dumps({}),
            now,
        ),
    )
    db.commit()

    # Count app access
    app_count = 0

    _log_identity_event(
        event_type="identity_created",
        user_id=identity.user_id,
        actor_id=getattr(request.state, "user", {}).get("sub"),
        details={"username": identity.username, "role": identity.role},
    )

    # Publish Sentinel event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="identity_created",
            source="infinity_one",
            payload={
                "user_id": identity.user_id,
                "username": identity.username,
                "role": identity.role,
            },
        )
    )

    return IdentityResponse(
        user_id=identity.user_id,
        username=identity.username,
        email=identity.email,
        display_name=identity.display_name,
        role=identity.role,
        tier=tier.value,
        infinity_role=infinity_role.value,
        pillar=identity.pillar,
        avatar_url=identity.avatar_url,
        bio=identity.bio,
        preferences={},
        created_at=now,
        updated_at=None,
        last_active=None,
        is_active=True,
        app_access_count=app_count,
    )


@app.get("/one/identities")
async def list_identities(
    role: str | None = None,
    tier: int | None = None,
    pillar: str | None = None,
    is_active: bool | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    """List identities with optional filtering."""
    conditions = []
    params: list[Any] = []

    if role:
        conditions.append("role = ?")
        params.append(role)
    if tier is not None:
        conditions.append("tier = ?")
        params.append(tier)
    if pillar:
        conditions.append("pillar = ?")
        params.append(pillar)
    if is_active is not None:
        conditions.append("is_active = ?")
        params.append(1 if is_active else 0)

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    rows = db.execute(
        f"SELECT * FROM identities{where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()

    total = db.execute(f"SELECT COUNT(*) as cnt FROM identities{where}", params).fetchone()["cnt"]

    identities = [_identity_from_row(r) for r in rows]
    return {"identities": identities, "total": total, "limit": limit, "offset": offset}


@app.get("/one/identities/{user_id}")
async def get_identity(user_id: str):
    """Get a specific identity by user ID."""
    row = db.execute(
        "SELECT * FROM identities WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Identity not found")

    identity = _identity_from_row(row)

    # Get app access count
    app_count = db.execute(
        "SELECT COUNT(*) as cnt FROM app_access WHERE user_id = ? AND is_revoked = 0",
        (user_id,),
    ).fetchone()["cnt"]

    identity["app_access_count"] = app_count
    return identity


@app.patch("/one/identities/{user_id}")
async def update_identity(user_id: str, update: IdentityUpdate, request: Request):
    """Update an identity's profile information."""
    row = db.execute(
        "SELECT * FROM identities WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Identity not found")

    updates = []
    params: list[Any] = []

    if update.display_name is not None:
        updates.append("display_name = ?")
        params.append(update.display_name)
    if update.email is not None:
        updates.append("email = ?")
        params.append(update.email)
    if update.avatar_url is not None:
        updates.append("avatar_url = ?")
        params.append(update.avatar_url)
    if update.bio is not None:
        updates.append("bio = ?")
        params.append(update.bio)
    if update.preferences is not None:
        updates.append("preferences = ?")
        params.append(json.dumps(update.preferences))
    if update.role is not None:
        updates.append("role = ?")
        params.append(update.role)
        # Update tier and infinity_role based on new role
        from Dimensional.infinity.nomenclature import (
            get_tier_for_role as _gtr,
            get_infinity_role_for_role as _girr,
        )

        tier = _gtr(update.role)
        infinity_role = _girr(update.role)
        updates.append("tier = ?")
        params.append(tier.value)
        updates.append("infinity_role = ?")
        params.append(infinity_role.value)
    if update.pillar is not None:
        updates.append("pillar = ?")
        params.append(update.pillar)

    if not updates:
        return {"message": "No updates provided", "user_id": user_id}

    updates.append("updated_at = ?")
    params.append(datetime.now(timezone.utc).isoformat())
    params.append(user_id)

    db.execute(
        f"UPDATE identities SET {', '.join(updates)} WHERE user_id = ?",
        params,
    )
    db.commit()

    _log_identity_event(
        event_type="identity_updated",
        user_id=user_id,
        actor_id=getattr(request.state, "user", {}).get("sub"),
        details={"fields_updated": [u.split(" = ")[0] for u in updates[:-1]]},
    )

    # Publish Sentinel event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="identity_updated",
            source="infinity_one",
            payload={"user_id": user_id},
        )
    )

    return {"message": "Identity updated", "user_id": user_id}


@app.delete("/one/identities/{user_id}")
async def deactivate_identity(user_id: str, request: Request):
    """Deactivate (soft-delete) an identity."""
    row = db.execute(
        "SELECT user_id, username FROM identities WHERE user_id = ?",
        (user_id,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Identity not found")

    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        "UPDATE identities SET is_active = 0, updated_at = ? WHERE user_id = ?",
        (now, user_id),
    )
    db.commit()

    _log_identity_event(
        event_type="identity_deactivated",
        user_id=user_id,
        actor_id=getattr(request.state, "user", {}).get("sub"),
        details={"username": row["username"]},
    )

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.BRIDGE,
            event_type="identity_deactivated",
            source="infinity_one",
            payload={"user_id": user_id, "username": row["username"]},
        )
    )

    return {"message": "Identity deactivated", "user_id": user_id}


# ---------------------------------------------------------------------------
# App Access Management
# ---------------------------------------------------------------------------


@app.post("/one/identities/{user_id}/apps", response_model=AppAccessResponse)
async def grant_app_access(user_id: str, access: AppAccessGrant, request: Request):
    """Grant app access to a user (one login, multi-app access)."""
    # Verify identity exists
    identity = db.execute(
        "SELECT user_id, username FROM identities WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")

    # Check if access already exists
    existing = db.execute(
        "SELECT id FROM app_access WHERE user_id = ? AND app_name = ? AND is_revoked = 0",
        (user_id, access.app_name),
    ).fetchone()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Active access already exists for app '{access.app_name}'",
        )

    access_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    actor_id = getattr(request.state, "user", {}).get("sub")

    db.execute(
        """INSERT INTO app_access (id, user_id, app_name, app_role, granted_at, granted_by, expires_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (access_id, user_id, access.app_name, access.app_role, now, actor_id, access.expires_at),
    )
    db.commit()

    _log_identity_event(
        event_type="app_access_granted",
        user_id=user_id,
        actor_id=actor_id,
        details={"app_name": access.app_name, "app_role": access.app_role},
    )

    return AppAccessResponse(
        id=access_id,
        user_id=user_id,
        app_name=access.app_name,
        app_role=access.app_role,
        granted_at=now,
        granted_by=actor_id,
        expires_at=access.expires_at,
        is_revoked=False,
    )


@app.get("/one/identities/{user_id}/apps")
async def list_app_access(user_id: str):
    """List all app access for a user."""
    rows = db.execute(
        "SELECT * FROM app_access WHERE user_id = ? AND is_revoked = 0 ORDER BY granted_at DESC",
        (user_id,),
    ).fetchall()
    return {"app_access": [dict(r) for r in rows], "total": len(rows)}


@app.delete("/one/identities/{user_id}/apps/{app_name}")
async def revoke_app_access(user_id: str, app_name: str, request: Request):
    """Revoke app access for a user."""
    db.execute(
        "UPDATE app_access SET is_revoked = 1 WHERE user_id = ? AND app_name = ? AND is_revoked = 0",
        (user_id, app_name),
    )
    db.commit()

    _log_identity_event(
        event_type="app_access_revoked",
        user_id=user_id,
        actor_id=getattr(request.state, "user", {}).get("sub"),
        details={"app_name": app_name},
    )

    return {"message": f"Access to '{app_name}' revoked", "user_id": user_id}


# ---------------------------------------------------------------------------
# Device Management
# ---------------------------------------------------------------------------


@app.get("/one/identities/{user_id}/devices")
async def list_devices(user_id: str):
    """List all devices associated with a user."""
    rows = db.execute(
        "SELECT * FROM devices WHERE user_id = ? ORDER BY last_seen DESC",
        (user_id,),
    ).fetchall()
    return {"devices": [dict(r) for r in rows], "total": len(rows)}


@app.post("/one/identities/{user_id}/devices")
async def register_device(user_id: str, request: Request):
    """Register a device for a user."""
    device_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")

    db.execute(
        """INSERT INTO devices (id, user_id, device_name, device_type, ip_address, user_agent, last_seen, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (device_id, user_id, "Web Browser", "browser", client_ip, user_agent, now, now),
    )
    db.commit()

    return {"device_id": device_id, "user_id": user_id, "registered": True}


# ---------------------------------------------------------------------------
# Identity Resolution
# ---------------------------------------------------------------------------


@app.get("/one/resolve/{identifier}")
async def resolve_identity(identifier: str):
    """Resolve an identity by user_id, username, or email.

    This is the identity resolver — the core Underverse module that
    provides unified identity lookup across the ecosystem.
    """
    row = db.execute(
        "SELECT * FROM identities WHERE user_id = ? OR username = ? OR email = ?",
        (identifier, identifier, identifier),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Identity not found")

    return _identity_from_row(row)


# ---------------------------------------------------------------------------
# Identity Summary
# ---------------------------------------------------------------------------


@app.get("/one/summary")
async def identity_summary():
    """Get a summary of all identities in the system."""
    total = db.execute("SELECT COUNT(*) as cnt FROM identities").fetchone()["cnt"]
    active = db.execute("SELECT COUNT(*) as cnt FROM identities WHERE is_active = 1").fetchone()[
        "cnt"
    ]

    # By role
    role_rows = db.execute("SELECT role, COUNT(*) as cnt FROM identities GROUP BY role").fetchall()
    by_role = {r["role"]: r["cnt"] for r in role_rows}

    # By tier
    tier_rows = db.execute("SELECT tier, COUNT(*) as cnt FROM identities GROUP BY tier").fetchall()
    by_tier = {str(r["tier"]): r["cnt"] for r in tier_rows}

    # By pillar
    pillar_rows = db.execute(
        "SELECT pillar, COUNT(*) as cnt FROM identities WHERE pillar IS NOT NULL GROUP BY pillar"
    ).fetchall()
    by_pillar = {r["pillar"]: r["cnt"] for r in pillar_rows}

    return {
        "total_identities": total,
        "active_identities": active,
        "by_role": by_role,
        "by_tier": by_tier,
        "by_pillar": by_pillar,
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats")
async def stats():
    """Get Infinity-One service statistics."""
    total_identities = db.execute("SELECT COUNT(*) as cnt FROM identities").fetchone()["cnt"]
    active_identities = db.execute(
        "SELECT COUNT(*) as cnt FROM identities WHERE is_active = 1"
    ).fetchone()["cnt"]
    total_app_access = db.execute(
        "SELECT COUNT(*) as cnt FROM app_access WHERE is_revoked = 0"
    ).fetchone()["cnt"]
    total_devices = db.execute("SELECT COUNT(*) as cnt FROM devices").fetchone()["cnt"]
    total_events = db.execute("SELECT COUNT(*) as cnt FROM identity_events").fetchone()["cnt"]

    return {
        "service": "infinity-one",
        "port": PORT,
        "identities": {
            "total": total_identities,
            "active": active_identities,
        },
        "app_access": {
            "active_grants": total_app_access,
        },
        "devices": {
            "total": total_devices,
        },
        "events": {
            "total": total_events,
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
