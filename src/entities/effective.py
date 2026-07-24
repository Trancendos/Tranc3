"""
src/entities/effective.py — Effective entity names with admin overrides.

Merges canonical PLATFORM_ENTITIES with SQLite overrides from
Infinity-Admin (entity_overrides table). Use this module anywhere
display names must reflect admin edits without redeploying code.

Override lookup is optional: pass a preloaded overrides dict from
Infinity-Admin DB, or call without overrides for canonical names only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.entities.platform import PLATFORM_ENTITIES, get_entity_by_pid


@dataclass
class EffectiveBot:
    slot: str
    code_name: str
    canonical_name: str
    tier: int = 5
    has_name_override: bool = False
    tier_override: int | None = None


@dataclass
class EffectiveAgent:
    role: str
    code_name: str
    canonical_name: str
    tier: int = 4
    has_name_override: bool = False
    tier_override: int | None = None


@dataclass
class EffectiveEntity:
    pid: str
    location_key: str
    location: str
    canonical_location: str
    pillar: str | None
    lead_ai: str
    canonical_lead_ai: str
    lead_ais: list[str]
    aid: str | None
    primes: list[str]
    canonical_primes: list[str]
    agent_alpha: EffectiveAgent | None
    agent_beta: EffectiveAgent | None
    bots: dict[str, EffectiveBot]
    worker_port: int | None
    worker_path: str | None
    overrides_applied: dict[str, str] = field(default_factory=dict)

    def display_tier(self, entity_ref: str, default: int) -> int:
        key = f"tier_{entity_ref}"
        raw = self.overrides_applied.get(key)
        if raw is not None and str(raw).isdigit():
            return int(raw)
        return default


def _override_key(entity_type: str, slot: str) -> str:
    return entity_type if not slot else f"{entity_type}_{slot}"


def _row_get(row: Any, key: str) -> str:
    return str(row[key])


def build_overrides_map(rows: list[Any]) -> dict[str, str]:
    """Build override dict from SQLite rows or admin API records."""
    out: dict[str, str] = {}
    for r in rows:
        et = _row_get(r, "entity_type")
        slot = _row_get(r, "slot")
        if not slot:
            slot = ""
        val = _row_get(r, "override_name")
        out[_override_key(et, slot)] = val
        if et == "tier":
            out[f"tier_{slot}"] = val
    return out


def resolve_entity(
    pid: str,
    overrides: dict[str, str] | None = None,
) -> EffectiveEntity | None:
    """Resolve one platform entity with optional override map."""
    entity = get_entity_by_pid(pid)
    if entity is None:
        return None

    ov = overrides or {}
    location_key = next(
        (k for k, e in PLATFORM_ENTITIES.items() if getattr(e, "pid", None) == pid),
        pid,
    )

    raw_primes = list(entity.primes) if entity.primes else []
    primes = [ov.get(f"prime_{i}", p) for i, p in enumerate(raw_primes)]

    def _agent(attr: str, role: str) -> EffectiveAgent | None:
        ag = getattr(entity, attr, None)
        if ag is None:
            return None
        canonical = ag.code_name
        name = ov.get(f"agent_{role}", canonical)
        tier_key = f"agent_{role}"
        tier_ov = ov.get(f"tier_{tier_key}")
        tier_override = int(tier_ov) if tier_ov and str(tier_ov).isdigit() else None
        return EffectiveAgent(
            role=role,
            code_name=name,
            canonical_name=canonical,
            tier=tier_override if tier_override is not None else 4,
            has_name_override=f"agent_{role}" in ov,
            tier_override=tier_override,
        )

    def _bot(attr: str, slot: str) -> EffectiveBot | None:
        b = getattr(entity, attr, None)
        if b is None:
            return None
        canonical = b.code_name
        name = ov.get(f"bot_{slot}", canonical)
        tier_key = f"bot_{slot}"
        tier_ov = ov.get(f"tier_{tier_key}")
        tier_override = int(tier_ov) if tier_ov and str(tier_ov).isdigit() else None
        return EffectiveBot(
            slot=slot,
            code_name=name,
            canonical_name=canonical,
            tier=tier_override if tier_override is not None else 5,
            has_name_override=f"bot_{slot}" in ov,
            tier_override=tier_override,
        )

    lead_canonical = entity.lead_ai
    lead_ai = ov.get("lead_ai", lead_canonical)
    lead_tier_ov = ov.get("tier_lead_ai")
    lead_tier = int(lead_tier_ov) if lead_tier_ov and str(lead_tier_ov).isdigit() else 3
    ov_out = dict(ov)
    ov_out.setdefault("tier_lead_ai", str(lead_tier))

    return EffectiveEntity(
        pid=pid,
        location_key=location_key,
        location=ov.get("location", location_key),
        canonical_location=location_key,
        pillar=entity.pillar.value if entity.pillar else None,
        lead_ai=lead_ai,
        canonical_lead_ai=lead_canonical,
        lead_ais=[lead_ai if name == lead_canonical else name for name in entity.lead_ais],
        aid=getattr(entity, "aid", None),
        primes=primes,
        canonical_primes=raw_primes,
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
        overrides_applied=ov_out,
    )


def list_all_effective(
    overrides_by_pid: dict[str, dict[str, str]] | None = None,
) -> list[EffectiveEntity]:
    """List all 43 entities with per-PID override maps."""
    overrides_by_pid = overrides_by_pid or {}
    results: list[EffectiveEntity] = []
    seen: set[str] = set()
    for _loc, entity in PLATFORM_ENTITIES.items():
        pid = getattr(entity, "pid", None)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        eff = resolve_entity(pid, overrides_by_pid.get(pid))
        if eff:
            results.append(eff)
    return sorted(results, key=lambda e: e.pid)
