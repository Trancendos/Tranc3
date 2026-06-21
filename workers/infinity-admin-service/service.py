"""
Infinity-Admin Service — Business Logic
==========================================
Helper functions that implement business logic used by the router.
Separated from HTTP concerns so they can be tested independently.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from models import AgentDetail, BotDetail, EntityDetail

from database import db

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


def log_admin_action(
    action_type: str,
    actor_id: str,
    actor_username: str | None = None,
    target_type: str | None = None,
    target_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Persist an admin action to the audit log."""
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


def upsert_override(
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


def resolve_entity_detail(pid: str) -> EntityDetail | None:
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


def seed_default_config(
    ecosystem_name: str,
    universe_name: str,
) -> None:
    """Seed default system configuration values."""
    defaults = [
        ("ecosystem_name", ecosystem_name, "general", "Name of the Infinity Ecosystem"),
        ("universe_name", universe_name, "general", "Name of the Trancendos Universe"),
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
