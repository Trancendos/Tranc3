# src/models/matrix.py
"""Trancendos Models Matrix — base tiers + specialized model variants.

Base models (already defined as the platform's orchestration tiers in
`src/entities/platform.py`):

    Trance-One (Tier 1, Sovereign/Orchestrator) — most capable
    T2ance     (Tier 2, Primes)
    Tranc3     (Tier 3, Lead AI / AI Base)      — least capable of the three

Every named AI resolves to exactly one base tier via
`entities.platform.get_orchestration_tier()`. This module adds the second,
orthogonal layer the user asked for: when an AI is associated with a
distinguishing skill matrix or role, its base model *expands* into a named
specialized variant (e.g. "The Dr." -> T2ance-CODE, "George Porter" ->
Tranc3-Crypto) without changing its underlying base tier.

This is a static registry, not a runtime-mutable one like the Role Assignment
Registry (`src/roles/registry.py`) — a specialized variant is earned through
the benchmarking + governance pipeline in `src/models/governance.py`, not
assigned on a whim. Adding a new variant here is itself expected to happen
only after a proposal clears Prime -> Cornelius -> Human review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

from src.entities.platform import (
    DEFAULT_ORCHESTRATION_TIER,
    PLATFORM_ENTITIES,
    OrchestrationTier,
    get_orchestration_tier,
)

# ---------------------------------------------------------------------------
# Specialized model variants
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ModelVariant:
    """A named AI's earned specialization on top of its base model tier."""

    ai_name: str
    base_tier: OrchestrationTier
    specialized_name: str  # e.g. "T2ance-CODE"
    skill_domain: str  # e.g. "Coder" — human-readable skill/role label
    description: str


# Seed set — real, currently-earned specializations. Each entry's base_tier
# must match entities.platform.get_orchestration_tier(ai_name); validated at
# import time by _validate() below so this table can never silently drift
# from the tier source of truth.
MODEL_VARIANTS: Dict[str, ModelVariant] = {
    "The Dr. (Nikolai O'denhime)": ModelVariant(
        ai_name="The Dr. (Nikolai O'denhime)",
        base_tier="T2ance",
        specialized_name="T2ance-CODE",
        skill_domain="Coder",
        description=(
            "The Lab's Prime, specialized for code creation/review — "
            "src/lab/, The Lab's Claude-Code-style platform."
        ),
    ),
    "George Porter": ModelVariant(
        ai_name="George Porter",
        base_tier="Tranc3",
        specialized_name="Tranc3-Crypto",
        skill_domain="Crypto Tokens",
        description=(
            "Arcadian Exchange Lead AI, specialized for digital-asset "
            "micro-transaction trading (Bitcoin, Ethereum, Litecoin, "
            "Shiba Inu, and similar tokens) per Arcadian Exchange's "
            "'Micro-Transaction Trading' ability."
        ),
    ),
}


def _all_lead_ai_names(entity) -> List[str]:
    """Every named AI running a Location: `lead_ais` for the 4 multi-AI
    Locations (already includes the primary `lead_ai` as its first entry),
    or just `lead_ai` for the ~39 single-AI Locations where `lead_ais`
    stays empty by design."""
    return list(entity.lead_ais) if entity.lead_ais else [entity.lead_ai]


def _validate() -> None:
    """Fail fast at import time if this table drifts from the tier/entity
    source of truth — a stale base_tier or an ai_name that no longer
    resolves to a real platform AI would otherwise fail silently."""
    known_ai_names = {
        name for entity in PLATFORM_ENTITIES.values() for name in _all_lead_ai_names(entity)
    }
    for variant in MODEL_VARIANTS.values():
        real_tier = get_orchestration_tier(variant.ai_name)
        if real_tier != variant.base_tier:
            raise RuntimeError(
                f"ModelVariant for {variant.ai_name!r} claims base_tier="
                f"{variant.base_tier!r}, but get_orchestration_tier() says "
                f"{real_tier!r} — MODEL_VARIANTS has drifted from "
                f"ORCHESTRATION_TIER in src/entities/platform.py"
            )
        if variant.ai_name not in known_ai_names:
            raise RuntimeError(
                f"ModelVariant references {variant.ai_name!r}, which is not "
                f"a lead_ai/lead_ais entry of any PLATFORM_ENTITIES location"
            )


_validate()


def get_variant(ai_name: str) -> Optional[ModelVariant]:
    """Return the named AI's earned specialized variant, if any."""
    return MODEL_VARIANTS.get(ai_name)


def resolve_effective_model(ai_name: str) -> str:
    """The name to actually use for this AI right now: its specialized
    variant if it has earned one, otherwise its bare base tier."""
    variant = MODEL_VARIANTS.get(ai_name)
    if variant:
        return variant.specialized_name
    return get_orchestration_tier(ai_name)


def list_variants() -> List[ModelVariant]:
    return list(MODEL_VARIANTS.values())


def tier_rank(tier: OrchestrationTier) -> int:
    """1 = most capable (Trance-One) ... 3 = least capable (Tranc3),
    matching Tier 1/2/3 in CLAUDE.md's Sovereign/Primes/Lead AI hierarchy."""
    return {"Trance-One": 1, "T2ance": 2, "Tranc3": 3}[tier]


def matrix_summary() -> Dict[str, object]:
    """A single snapshot of the whole Models Matrix: every AI across all 43
    Locations, its base tier, and any earned specialized variant."""
    rows = []
    for entity in PLATFORM_ENTITIES.values():
        for ai_name in _all_lead_ai_names(entity):
            variant = MODEL_VARIANTS.get(ai_name)
            rows.append(
                {
                    "ai_name": ai_name,
                    "location": entity.location,
                    "base_tier": get_orchestration_tier(ai_name),
                    "specialized_name": variant.specialized_name if variant else None,
                    "skill_domain": variant.skill_domain if variant else None,
                }
            )
    return {
        "default_base_tier": DEFAULT_ORCHESTRATION_TIER,
        "total_ais": len(rows),
        "specialized_count": len(MODEL_VARIANTS),
        "ais": rows,
    }
