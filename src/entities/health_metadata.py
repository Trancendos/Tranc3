"""
src/entities/health_metadata.py — Canonical /health entity block with admin overrides.

Use in every worker ``/health`` response::

    from src.entities.health_metadata import health_entity_block
    return {"status": "healthy", "service": "infinity-ws", "entity": health_entity_block(8004)}
"""

from __future__ import annotations

import os
from typing import Any

from src.entities.effective import resolve_entity
from src.entities.override_store import load_overrides_for_pid
from src.entities.platform import WORKER_ENTITY_MAP, get_entity_for_port


def _port_from_env() -> int | None:
    for key in ("WORKER_PORT", "PORT", "SERVICE_PORT"):
        raw = os.environ.get(key)
        if raw and str(raw).isdigit():
            return int(raw)
    return None


def health_entity_block(
    port: int | None = None,
    service: str | None = None,
    *,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the ``entity`` object for worker health JSON."""
    port = port if port is not None else _port_from_env()
    entity = get_entity_for_port(port) if port is not None else None
    pid = getattr(entity, "pid", None) if entity else None

    overrides = load_overrides_for_pid(pid) if pid else {}
    effective = resolve_entity(pid, overrides) if pid else None

    if effective is None:
        block: dict[str, Any] = {
            "location": WORKER_ENTITY_MAP.get(port, "Unknown") if port else "Unknown",
            "pillar": None,
            "lead_ai": None,
            "primes": [],
            "pid": None,
            "overrides_active": False,
        }
        if service:
            block["service"] = service
        if extra:
            block.update(extra)
        return block

    agents = {}
    if effective.agent_alpha:
        agents["alpha"] = {
            "name": effective.agent_alpha.code_name,
            "tier": effective.agent_alpha.tier,
            "canonical": effective.agent_alpha.canonical_name,
        }
    if effective.agent_beta:
        agents["beta"] = {
            "name": effective.agent_beta.code_name,
            "tier": effective.agent_beta.tier,
            "canonical": effective.agent_beta.canonical_name,
        }

    bots = {}
    for slot, bot in effective.bots.items():
        if bot:
            bots[slot] = {
                "name": bot.code_name,
                "tier": bot.tier,
                "canonical": bot.canonical_name,
            }

    raw_entity = get_entity_for_port(port) if port else None
    block = {
        "pid": effective.pid,
        "location": effective.location,
        "canonical_location": effective.canonical_location,
        "pillar": effective.pillar,
        "lead_ai": effective.lead_ai,
        "canonical_lead_ai": effective.canonical_lead_ai,
        "aid": effective.aid,
        "primes": effective.primes,
        "canonical_primes": effective.canonical_primes,
        "primary_function": getattr(raw_entity, "primary_function", None),
        "lead_ai_tier": effective.display_tier("lead_ai", 3),
        "agents": agents,
        "bots": bots,
        "overrides_active": bool(overrides),
        "worker_port": port,
    }
    if service:
        block["service"] = service
    if extra:
        block.update(extra)
    return block
