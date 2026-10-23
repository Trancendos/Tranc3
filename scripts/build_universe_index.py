#!/usr/bin/env python3
"""Derive the Universe Index: every named AI, Agent and Bot, with its tier.

Nothing here is a second register. Every fact is read from the two places that
already hold it -- `src/entities/platform.py` (the 43 Locations, their Lead AIs,
Primes, Agents and Bots, and `ORCHESTRATION_TIER`) and
`config/estate/registry.yaml` (the TRC estate refs) -- and the output is
regenerated, never hand-edited. A hand-maintained index would be a 44th
description of the estate and would drift the way registry.yaml's Lead AI for
The Spark already had (it still said Norman Hawkins a month after
`CLAUDE.md` recorded the correction to Imfy).

What it adds is measurement against three owner rules that no existing guard
checks. It *reports* them; it does not gate on them, because the current
entity model predates the rules and changing it is a Tier 0 decision:

1. Span: one AI manages one Agent and three Bot types. The entity model gives
   every Location two Agents (alpha/beta) and four Bots, so this is measured
   per Location and the excess is listed, not "fixed".
2. Tier ceiling: a Tier-1 Orchestrator should not occupy a Tier-2 Prime seat.
   Read from `ORCHESTRATION_TIER` against each Location's `primes`.
3. Three modes: every AI offers Offline, Local Online and Web. The model holds
   `online_mode` and `offline_mode` only, so Local Online vs Web cannot be
   told apart from the register and is counted as unrecorded, not as present.

Usage:
    python3 scripts/build_universe_index.py           # writes both outputs
    python3 scripts/build_universe_index.py --check   # fails if they are stale
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.entities.platform import (  # noqa: E402
    ORCHESTRATION_TIER,
    PLATFORM_ENTITIES,
    get_orchestration_tier,
)

REGISTRY = REPO / "config" / "estate" / "registry.yaml"
OUT_JSON = REPO / "docs" / "governance" / "universe-index.json"
OUT_MD = REPO / "docs" / "governance" / "UNIVERSE-INDEX.md"

SPAN_AGENTS = 1
SPAN_BOTS = 3
TIER_NUMBER = {"Trance-One": 1, "T2ance": 2, "Tranc3": 3}


def _registry_lead_ais() -> dict[str, str | None]:
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    return {c["name"]: c.get("lead_ai") for c in data.get("components", [])}


def _names_in(registry_value: str | None) -> set[str]:
    """registry.yaml writes multi-AI Locations as 'A & B, C' -- split them."""
    if not registry_value:
        return set()
    parts: set[str] = set()
    for chunk in registry_value.replace(" & ", ",").split(","):
        if chunk.strip():
            parts.add(chunk.strip())
    return parts


def build() -> dict:
    registry = _registry_lead_ais()
    locations = []
    ais: dict[str, dict] = {}
    drift = []
    tier_ceiling = []

    for name in sorted(PLATFORM_ENTITIES):
        e = PLATFORM_ENTITIES[name]
        lead_ais = list(e.lead_ais) or [e.lead_ai]
        agents = [e.agent_alpha, e.agent_beta]
        for pair in e.agent_teams.values():
            for agent in (pair.alpha, pair.beta):
                if agent.code_name not in {a.code_name for a in agents}:
                    agents.append(agent)
        bots = [e.bot_01, e.bot_02, e.bot_03, e.bot_04]

        span_agents_allowed = SPAN_AGENTS * len(lead_ais)
        span_bots_allowed = SPAN_BOTS * len(lead_ais)
        locations.append(
            {
                "location": name,
                "pid": e.pid,
                "pillar": e.pillar.value,
                "lead_ais": lead_ais,
                "primes": list(e.primes),
                "agents": [{"name": a.code_name, "sid": a.sid} for a in agents],
                "bots": [{"name": b.code_name, "nid": b.nid} for b in bots],
                "modes": {
                    "offline": bool(e.offline_mode.strip()),
                    "online": bool(e.online_mode.strip()),
                    "local_online_vs_web_recorded": False,
                },
                "span": {
                    "agents": len(agents),
                    "agents_allowed": span_agents_allowed,
                    "bots": len(bots),
                    "bots_allowed": span_bots_allowed,
                    "conforms": len(agents) <= span_agents_allowed
                    and len(bots) <= span_bots_allowed,
                },
                "worker_port": e.worker_port,
                "worker_path": e.worker_path,
            }
        )

        for ai in lead_ais:
            rec = ais.setdefault(
                ai,
                {"name": ai, "tier": TIER_NUMBER[get_orchestration_tier(ai)], "leads": []},
            )
            rec["leads"].append(name)

        for prime in e.primes:
            if TIER_NUMBER[get_orchestration_tier(prime)] < 2:
                tier_ceiling.append({"location": name, "seat": "prime", "holder": prime})

        reg_value = registry.get(name)
        expected = set(lead_ais) | {e.lead_ai}
        if name == "The Nexus":  # same entity: AID name vs common name, see CLAUDE.md
            expected.add("The Nexus")
        # registry.yaml abbreviates shared surnames ("Ann, George ... Porter"),
        # so a bare given name counts when exactly one expected name starts with it.
        reg_names = {
            n
            if n in expected
            else next(
                (x for x in expected if x.startswith(n + " ")),
                n,
            )
            for n in _names_in(reg_value)
        }
        if reg_value is not None and not reg_names <= expected:
            drift.append(
                {
                    "location": name,
                    "registry_yaml": reg_value,
                    "platform_py": lead_ais,
                    "unexpected": sorted(reg_names - expected),
                }
            )

    for ai, tier in ORCHESTRATION_TIER.items():
        ais.setdefault(ai, {"name": ai, "tier": TIER_NUMBER[tier], "leads": []})

    span_breaches = [loc for loc in locations if not loc["span"]["conforms"]]
    return {
        "generated_from": [
            "src/entities/platform.py",
            "config/estate/registry.yaml",
        ],
        "rules": {
            "span": f"{SPAN_AGENTS} Agent + {SPAN_BOTS} Bot types per AI",
            "tier_ceiling": "a Tier-1 Orchestrator does not hold a Tier-2 Prime seat",
            "modes": "Offline, Local Online and Web per AI",
        },
        "summary": {
            "locations": len(locations),
            "named_ais": len(ais),
            "agents": sum(len(loc["agents"]) for loc in locations),
            "bots": sum(len(loc["bots"]) for loc in locations),
            "span_breaches": len(span_breaches),
            "tier_ceiling_breaches": len(tier_ceiling),
            "registry_drift": len(drift),
            "mode_gap_local_online_vs_web": sum(
                1 for loc in locations if not loc["modes"]["local_online_vs_web_recorded"]
            ),
        },
        "registry_drift": drift,
        "tier_ceiling_breaches": tier_ceiling,
        "ais": sorted(ais.values(), key=lambda a: (a["tier"], a["name"])),
        "locations": locations,
    }


def render_md(index: dict) -> str:
    s = index["summary"]
    lines = [
        "# Universe Index",
        "",
        "Generated by `scripts/build_universe_index.py` from "
        "`src/entities/platform.py` and `config/estate/registry.yaml`. "
        "Do not edit by hand; run the script. `--check` fails when this is stale.",
        "",
        "This is a measurement, not a second register. The rules below are the "
        "owner's; the entity model predates them, so breaches are reported here "
        "for a Tier 0 decision rather than gated.",
        "",
        "## Summary",
        "",
        "| Measure | Count |",
        "|---|---|",
        f"| Locations | {s['locations']} |",
        f"| Named AIs (Tier 1–3) | {s['named_ais']} |",
        f"| Agents | {s['agents']} |",
        f"| Bots | {s['bots']} |",
        f"| Locations exceeding {index['rules']['span']} | {s['span_breaches']} |",
        f"| Orchestrator-held Prime seats | {s['tier_ceiling_breaches']} |",
        f"| registry.yaml Lead AI drift | {s['registry_drift']} |",
        f"| Locations with Local Online vs Web unrecorded | {s['mode_gap_local_online_vs_web']} |",
        "",
        "## Registry drift",
        "",
    ]
    if index["registry_drift"]:
        lines += ["| Location | registry.yaml | platform.py |", "|---|---|---|"]
        for d in index["registry_drift"]:
            lines.append(
                f"| {d['location']} | {d['registry_yaml']} | {', '.join(d['platform_py'])} |"
            )
    else:
        lines.append("None.")
    lines += ["", "## Orchestrator-held Prime seats", ""]
    if index["tier_ceiling_breaches"]:
        by_holder: dict[str, list[str]] = {}
        for b in index["tier_ceiling_breaches"]:
            by_holder.setdefault(b["holder"], []).append(b["location"])
        for holder, locs in by_holder.items():
            lines.append(f"- **{holder}** (Tier 1) is Prime for {len(locs)}: {', '.join(locs)}")
    else:
        lines.append("None.")
    lines += [
        "",
        "## AIs by tier",
        "",
        "| Tier | AI | Leads |",
        "|---|---|---|",
    ]
    for ai in index["ais"]:
        lines.append(f"| {ai['tier']} | {ai['name']} | {', '.join(ai['leads']) or '—'} |")
    lines += [
        "",
        "## Span by Location",
        "",
        "| Location | Lead AIs | Agents (allowed) | Bots (allowed) |",
        "|---|---|---|---|",
    ]
    for loc in index["locations"]:
        sp = loc["span"]
        lines.append(
            f"| {loc['location']} | {len(loc['lead_ais'])} | "
            f"{sp['agents']} ({sp['agents_allowed']}) | {sp['bots']} ({sp['bots_allowed']}) |"
        )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if outputs are stale")
    args = parser.parse_args()

    index = build()
    json_text = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    md_text = render_md(index)

    if args.check:
        stale = [
            str(p.relative_to(REPO))
            for p, text in ((OUT_JSON, json_text), (OUT_MD, md_text))
            if not p.exists() or p.read_text(encoding="utf-8") != text
        ]
        if stale:
            print("stale: " + ", ".join(stale) + " -- run scripts/build_universe_index.py")
            return 1
        print("universe index is current")
        return 0

    OUT_JSON.write_text(json_text, encoding="utf-8")
    OUT_MD.write_text(md_text, encoding="utf-8")
    print(json.dumps(index["summary"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
