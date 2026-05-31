"""Domain model viewer/editor — platform entities + tiers."""

from __future__ import annotations

from typing import Any

from src.entities.effective import list_all_effective, resolve_entity
from src.entities.override_store import load_all_overrides_by_pid
from src.entities.platform import PLATFORM_ENTITIES, Pillar


def domain_model_summary() -> dict[str, Any]:
    overrides = load_all_overrides_by_pid()
    entities = list_all_effective(overrides)
    by_pillar: dict[str, int] = {}
    for e in entities:
        p = e.pillar or "Unknown"
        by_pillar[p] = by_pillar.get(p, 0) + 1
    return {
        "entity_count": len(entities),
        "override_count": sum(len(v) for v in overrides.values()),
        "pillars": list(Pillar.__members__.keys()),
        "entities_by_pillar": by_pillar,
    }


def list_entities(*, pillar: str | None = None) -> list[dict[str, Any]]:
    overrides = load_all_overrides_by_pid()
    entities = list_all_effective(overrides)
    out: list[dict[str, Any]] = []
    for e in entities:
        if pillar and (e.pillar or "").lower() != pillar.lower():
            continue
        out.append(
            {
                "pid": e.pid,
                "location": e.location,
                "canonical_location": e.canonical_location,
                "pillar": e.pillar,
                "lead_ai": e.lead_ai,
                "canonical_lead_ai": e.canonical_lead_ai,
                "primes": e.primes,
                "worker_port": e.worker_port,
                "worker_path": e.worker_path,
                "override_keys": list(e.overrides_applied.keys()),
            }
        )
    return out


def get_entity_detail(pid: str) -> dict[str, Any] | None:
    overrides = load_all_overrides_by_pid()
    eff = resolve_entity(pid, overrides.get(pid))
    if not eff:
        return None
    return {
        "pid": eff.pid,
        "location": eff.location,
        "canonical_location": eff.canonical_location,
        "pillar": eff.pillar,
        "lead_ai": eff.lead_ai,
        "canonical_lead_ai": eff.canonical_lead_ai,
        "aid": eff.aid,
        "primes": eff.primes,
        "canonical_primes": eff.canonical_primes,
        "agent_alpha": eff.agent_alpha.__dict__ if eff.agent_alpha else None,
        "agent_beta": eff.agent_beta.__dict__ if eff.agent_beta else None,
        "bots": {k: v.__dict__ for k, v in eff.bots.items()},
        "worker_port": eff.worker_port,
        "worker_path": eff.worker_path,
        "overrides_applied": eff.overrides_applied,
        "tiers": {
            "lead_ai": eff.display_tier("lead_ai", 3),
            "sovereign": 1,
            "prime": 2,
            "agent": 4,
            "bot": 5,
        },
    }


def graph_nodes_edges() -> dict[str, Any]:
    """Lightweight graph for viewer (nodes + edges)."""
    overrides = load_all_overrides_by_pid()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    for e in list_all_effective(overrides):
        nodes.append(
            {
                "id": e.pid,
                "label": e.location,
                "type": "location",
                "pillar": e.pillar,
            }
        )
        nodes.append(
            {
                "id": f"{e.pid}-lead",
                "label": e.lead_ai,
                "type": "lead_ai",
            }
        )
        edges.append({"from": e.pid, "to": f"{e.pid}-lead", "relation": "lead_ai"})
        for i, prime in enumerate(e.primes):
            nid = f"{e.pid}-prime-{i}"
            nodes.append({"id": nid, "label": prime, "type": "prime"})
            edges.append({"from": e.pid, "to": nid, "relation": "prime"})
    return {"nodes": nodes, "edges": edges, "total_nodes": len(nodes)}


def canonical_entity_count() -> int:
    return len(PLATFORM_ENTITIES)
