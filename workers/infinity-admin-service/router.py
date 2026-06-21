"""
Infinity-Admin Service — Routes
================================
All FastAPI routes collected into a single APIRouter.
Imports from service.py, database.py, models.py, and config.py.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from models import (
    ConfigUpdate,
    EntityNameUpdate,
    EntityTierUpdate,
    FeatureFlagUpdate,
    OrchestratorRename,
)
from service import (
    _PLATFORM_ENTITIES_AVAILABLE,
    PLATFORM_ENTITIES,
    get_entity_by_pid,
    log_admin_action,
    resolve_entity_detail,
    upsert_override,
)

from config import _INTERNAL_SECRET, PORT
from database import db
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)
from Dimensional.infinity.nomenclature import (
    ECOSYSTEM_NAME,
    INFINITY_LOCATIONS,
    PILLAR_PRIME_MAP,
    PRIMES,
    TRANSFER_SYSTEMS,
    UNIVERSE_NAME,
    Pillar,
    Tier,
)
from Dimensional.infinity.sentinel_station import (
    SentinelEvent,
    get_sentinel_station,
)

# ---------------------------------------------------------------------------
# Shared singletons — defaults from module-level construction.
# main.py calls init_router_deps() immediately after creating these objects
# so that the router uses the exact same instances throughout the process.
# ---------------------------------------------------------------------------

sentinel = get_sentinel_station()
dimensional_registry = get_dimensional_registry()
dimensional_bus = get_dimensional_bus()
underverse_registry = get_underverse_registry()

# worker_kit is created in main.py and injected via init_router_deps
_worker_kit_ref: Any = None
_rbac_engine_ref: Any = None


def init_router_deps(sentinel: Any = None, worker_kit: Any = None, rbac_engine: Any = None) -> None:
    """Inject singletons created in main.py into the router module.

    Call this once, immediately after constructing the shared objects in
    main.py, before the ASGI app starts serving requests.
    """
    global _worker_kit_ref, _rbac_engine_ref
    import router as _self  # noqa: F401 — update this module's globals

    if sentinel is not None:
        import sys
        sys.modules[__name__].__dict__["sentinel"] = sentinel
    if worker_kit is not None:
        _worker_kit_ref = worker_kit
    if rbac_engine is not None:
        _rbac_engine_ref = rbac_engine


# ---------------------------------------------------------------------------
# Internal auth dependency
# ---------------------------------------------------------------------------


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


# ---------------------------------------------------------------------------
# Sentinel channel reference (imported inline to avoid circular import issues)
# ---------------------------------------------------------------------------

from Dimensional.infinity.nomenclature import SentinelChannel  # noqa: E402

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

_VALID_TIER_REFS = frozenset(
    {
        "lead_ai",
        "agent_alpha",
        "agent_beta",
        "bot_01",
        "bot_02",
        "bot_03",
        "bot_04",
    },
)

router = APIRouter(dependencies=[Depends(require_internal_auth)])


# ---------------------------------------------------------------------------
# System Configuration
# ---------------------------------------------------------------------------


@router.get("/admin/config")
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


@router.get("/admin/config/{key}")
async def get_config(key: str):
    """Get a specific configuration value."""
    row = db.execute(
        "SELECT * FROM system_config WHERE key = ?",
        (key,),
    ).fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Configuration key not found")

    return dict(row)


@router.put("/admin/config/{key}")
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

    log_admin_action(
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


@router.get("/admin/features")
async def list_features():
    """List all feature flags."""
    rows = db.execute("SELECT * FROM feature_flags ORDER BY key").fetchall()
    return {"features": [dict(r) for r in rows], "total": len(rows)}


@router.put("/admin/features/{key}")
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

    log_admin_action(
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


@router.get("/admin/primes")
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


@router.get("/admin/pillars")
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


@router.get("/admin/tiers")
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


@router.get("/admin/dimensionals")
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


@router.get("/admin/underverse")
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


@router.get("/admin/transfer")
async def transfer_systems_status():
    """Get the status of all three transfer systems."""
    systems = []
    for ts, info in TRANSFER_SYSTEMS.items():
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


@router.get("/admin/locations")
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


@router.get("/admin/audit")
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
    base = "SELECT * FROM admin_actions"
    if conditions:
        base += " WHERE " + " AND ".join(conditions)
    query = base + " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    rows = db.execute(
        query,
        params + [limit, offset],
    ).fetchall()

    count_base = "SELECT COUNT(*) as cnt FROM admin_actions"
    if conditions:
        count_base += " WHERE " + " AND ".join(conditions)
    total = db.execute(count_base, params).fetchone()["cnt"]

    return {"actions": [dict(r) for r in rows], "total": total}


@router.get("/admin/compliance")
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

    base = "SELECT * FROM compliance_events"
    if conditions:
        base += " WHERE " + " AND ".join(conditions)
    query = base + " ORDER BY created_at DESC LIMIT ?"
    rows = db.execute(
        query,
        params + [limit],
    ).fetchall()

    return {"events": [dict(r) for r in rows], "total": len(rows)}


# ---------------------------------------------------------------------------
# Sentinel Station Monitoring
# ---------------------------------------------------------------------------


@router.get("/admin/sentinel")
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


@router.get("/admin/overview")
async def ecosystem_overview():
    """Get a comprehensive overview of the entire Infinity Ecosystem."""
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


@router.get("/admin/entities")
async def list_entities(pillar: str | None = None):
    """List all 43 platform entities with current names (DB overrides applied)."""
    if not _PLATFORM_ENTITIES_AVAILABLE:
        return {
            "entities": [],
            "total": 0,
            "platform_available": False,
            "message": "Platform entity registry not accessible from this worker",
        }

    # Preload all overrides in one query — avoids N+1
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


@router.get("/admin/entities/{pid}")
async def get_entity(pid: str):
    """Get full detail for a platform entity with all overrides applied."""
    detail = resolve_entity_detail(pid)
    if detail is None:
        if not _PLATFORM_ENTITIES_AVAILABLE:
            raise HTTPException(
                status_code=503,
                detail="Platform entity registry not accessible from this worker",
            )
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    return detail.model_dump()


@router.patch("/admin/entities/{pid}/name")
async def rename_location(pid: str, body: EntityNameUpdate, request: Request):
    """Rename a Location (App). entity_type: 'location', slot: NULL"""
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
    upsert_override(pid, "location", None, original, body.new_name, actor)

    log_admin_action(
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


@router.patch("/admin/entities/{pid}/lead-ai")
async def rename_lead_ai(pid: str, body: EntityNameUpdate, request: Request):
    """Rename the Tier 3 Lead AI for a platform entity. entity_type: 'lead_ai', slot: NULL"""
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
    upsert_override(pid, "lead_ai", None, original, body.new_name, actor)

    log_admin_action(
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


@router.patch("/admin/entities/{pid}/primes/{prime_idx}")
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
    upsert_override(pid, "prime", slot, original, body.new_name, actor)

    log_admin_action(
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


@router.patch("/admin/entities/{pid}/agents/{role}")
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
    upsert_override(pid, "agent", role, original, body.new_name, actor)

    log_admin_action(
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


@router.patch("/admin/entities/{pid}/bots/{slot}")
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
    upsert_override(pid, "bot", slot, original, body.new_name, actor)

    log_admin_action(
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


@router.get("/admin/entities/{pid}/overrides")
async def list_entity_overrides(pid: str):
    """List all active name overrides for a given entity PID."""
    if _PLATFORM_ENTITIES_AVAILABLE and get_entity_by_pid(pid) is None:
        raise HTTPException(status_code=404, detail=f"Entity '{pid}' not found")

    rows = db.execute(
        "SELECT * FROM entity_overrides WHERE location_pid = ? ORDER BY entity_type, slot",
        (pid,),
    ).fetchall()

    return {"pid": pid, "overrides": [dict(r) for r in rows], "total": len(rows)}


@router.delete("/admin/entities/{pid}/overrides")
async def reset_entity_overrides(
    pid: str,
    request: Request,
    entity_type: str | None = Query(None, description="Limit reset to a specific entity_type"),
    slot: str | None = Query(
        None, description="Limit reset to a specific slot (pass empty string for no-slot rows)"
    ),
):
    """Reset name overrides for an entity — restores code defaults."""
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

    count_query = "SELECT COUNT(*) as cnt FROM entity_overrides WHERE " + where
    count_row = db.execute(count_query, tuple(params)).fetchone()
    count = count_row["cnt"]

    delete_query = "DELETE FROM entity_overrides WHERE " + where
    db.execute(delete_query, tuple(params))
    db.commit()

    log_admin_action(
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


@router.get("/admin/entities/{pid}/overrides/{entity_type}")
async def get_entity_overrides_by_type(pid: str, entity_type: str, slot: str | None = None):
    """Get overrides for a specific entity type (and optional slot) within an entity."""
    conditions = ["location_pid = ?", "entity_type = ?"]
    params: list[Any] = [pid, entity_type]

    if slot is not None:
        conditions.append("slot = ?")
        params.append(slot)

    rows = db.execute(
        "SELECT * FROM entity_overrides WHERE " + " AND ".join(conditions) + " ORDER BY slot",
        params,
    ).fetchall()

    return {"pid": pid, "entity_type": entity_type, "overrides": [dict(r) for r in rows]}


@router.patch("/admin/entities/{pid}/tier")
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
    upsert_override(
        pid,
        "tier",
        body.entity_ref,
        original,
        str(body.tier),
        actor,
    )

    log_admin_action(
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
        ),
    )

    return {
        "message": "Tier assignment saved",
        "pid": pid,
        "entity_ref": body.entity_ref,
        "tier": body.tier,
    }


@router.get("/admin/orchestrators")
async def list_orchestrators():
    """Tier 1 Orchestrators — effective names from admin DB overrides."""
    from src.entities.orchestrator_effective import get_orchestrator_display_name

    orchestrators = [p for p in PRIMES.values() if p.tier == Tier.ORCHESTRATOR]
    return {
        "tier": 1,
        "tier_name": Tier.ORCHESTRATOR.display_name,
        "orchestrators": [
            {
                "id": p.id,
                "name": get_orchestrator_display_name(p.id, p.name),
                "canonical_name": p.name,
                "pillar": p.pillar.value if p.pillar else None,
                "description": p.description,
            }
            for p in orchestrators
        ],
        "total": len(orchestrators),
        "note": "Rename via PATCH /admin/orchestrators/{id}; per-location primes use PATCH .../primes/{idx}",
    }


@router.patch("/admin/orchestrators/{orchestrator_id}")
async def rename_orchestrator(
    orchestrator_id: str,
    body: OrchestratorRename,
    request: Request,
):
    """Persist Tier-1 orchestrator display name (no nomenclature.py deploy)."""
    from src.entities.orchestrator_effective import ORCHESTRATOR_PID

    prime = PRIMES.get(orchestrator_id)
    if prime is None or prime.tier != Tier.ORCHESTRATOR:
        raise HTTPException(status_code=404, detail="Orchestrator not found")

    actor = request.headers.get("X-Admin-Actor", "admin")
    upsert_override(
        ORCHESTRATOR_PID,
        "orchestrator",
        orchestrator_id,
        prime.name,
        body.new_name,
        actor,
    )
    db.execute(
        """INSERT INTO admin_actions
           (id, action_type, actor_id, actor_username, target_type, target_id, details, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            uuid.uuid4().hex[:16],
            "orchestrator_renamed",
            actor,
            actor,
            "orchestrator",
            orchestrator_id,
            json.dumps(
                {
                    "canonical": prime.name,
                    "new_name": body.new_name,
                    "reason": body.reason,
                },
            ),
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    db.commit()
    return {
        "ok": True,
        "id": orchestrator_id,
        "canonical_name": prime.name,
        "name": body.new_name,
    }


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats")
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
        "smart_adaptive": _worker_kit_ref.get_kit_stats() if _worker_kit_ref else {},
    }
