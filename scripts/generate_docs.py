"""
Generate the repaired PLATFORM_ENTITIES.md and docs/matrix.md
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.entities.platform import LOCATION_ABBREVS, PLATFORM_ENTITIES, PRIME_ABBREVS


def generate_platform_entities_md():
    """Generate the full repaired PLATFORM_ENTITIES.md."""

    pillar_order = [
        "Architectural",
        "Commercial / Financial",
        "Creativity",
        "Development (Code)",
        "Knowledge",
        "Security",
        "DevOps",
        "Wellbeing",
    ]

    lines = []
    lines.append("# Trancendos Platform Entity Hierarchy")
    lines.append("")
    lines.append("Canonical reference for all 43 platform locations and their entity hierarchies.")
    lines.append("")
    lines.append("**Tier structure:**")
    lines.append("- **Tier 1 - The Sovereign**: Ultimate orchestrator of the Tranc3 ecosystem")
    lines.append(
        "- **Tier 2 - Primes**: Executive AI authorities that govern one or more locations",
    )
    lines.append("- **Tier 3 - Lead AI**: The named AI that runs each location day-to-day")
    lines.append(
        "- **Tier 4 - Agents**: Agent Alpha and Agent Beta - mid-tier automation per location",
    )
    lines.append("- **Tier 5 - Bots**: Bot 01-04 - task-specific micro-workers per location")
    lines.append("")
    lines.append(
        "**Pillars:** Architectural · Commercial/Financial · Creativity · Development (Code) · Knowledge · Security · DevOps · Wellbeing",
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Universal ID Taxonomy
    lines.append("## Universal ID Taxonomy")
    lines.append("")
    lines.append("| ID Format | Tier | Description | Example |")
    lines.append("|---|---|---|---|")
    lines.append("| PID-XXX | Location | Product/Location ID (3-letter abbreviation) | PID-NXS |")
    lines.append("| AID-XXX-NN | 2-3 | AI ID (location abbrev + 2-digit sequence) | AID-NXS-01 |")
    lines.append("| SID-XXX-NN | 4 | Service/Agent ID | SID-NXS-01 |")
    lines.append("| NID-XXX-NN | 5 | Nano-ID/Bot ID | NID-NXS-01 |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Naming Conventions (Resolved)
    lines.append("## Naming Conventions (Resolved)")
    lines.append("")
    lines.append("| Rule | Resolved Form | Original Issue |")
    lines.append("|---|---|---|")
    lines.append(
        "| Platform brain | The Digital Grid (with space) | The DigitalGrid (no space — typo) |",
    )
    lines.append(
        "| Location vs AI | tAimra (location) / tAImra (Lead AI) | tAImra vs tAimra casing mismatch |",
    )
    lines.append(
        "| Photo studio | Sashas Photo Studio (no apostrophe) | Sasha's Photo Studio (apostrophe) |",
    )
    lines.append(
        "| Guardian title | The Guardian (Marcus Magnolia) | The Guardian (Anchor: Orb of Orisis) vs The Guardian (Marcus Magnolia) |",
    )
    lines.append(
        "| Nexus AI | Nexus-Prime (Lead AI) | The Nexus (same name as location — tight coupling) |",
    )
    lines.append(
        "| Bot naming | All bots: Title-Case-Bot format | Inconsistent: some had -Bot suffix, some didn't |",
    )
    lines.append(
        "| Wireframe collision | Layout-Bot (Studio) / Wireframe-Bot (Turing's Hub) | Same name in two locations |",
    )
    lines.append(
        "| The Weaver collision | The Flow-Weaver (Digital Grid) / The Time-Weaver (ChronosSphere) / The Weaver (Fabulousa) | Same agent name in three locations |",
    )
    lines.append(
        "| The Guide collision | The Guide (Tranquility) / The VR-Guide (VRAR3D) | Same agent name in two locations |",
    )
    lines.append(
        "| Stamp collision | Stamp-Bot (Town Hall) / Seal-Stamp-Bot (Lighthouse) | Same bot name in two locations |",
    )
    lines.append(
        "| Scanner collision | Scanner-Bot (DocUtari) / Scan-Bot (Warp Tunnel) | Same bot name in two locations |",
    )
    lines.append(
        "| Tracer collision | Tracer-Bot (Observatory) / Trace-Bot (Cryptex) | Same bot name in two locations |",
    )
    lines.append(
        "| Lens collision | Lens-Bot (Sashas Photo Studio) / VR-Lens-Bot (VRAR3D) | Same bot name in two locations |",
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # Worker Port → Entity Mapping
    lines.append("## Worker Port → Entity Mapping")
    lines.append("")
    lines.append("| Port | Worker | Location | Lead AI | PID | Role |")
    lines.append("|------|--------|----------|---------|-----|------|")

    worker_map = [
        (8004, "infinity-ws", "The Nexus", "Nexus-Prime", "PID-NXS", "Primary worker"),
        (
            8005,
            "infinity-auth",
            "Infinity",
            "The Guardian (Marcus Magnolia)",
            "PID-INF",
            "Primary worker",
        ),
        (
            8006,
            "users-service",
            "Infinity",
            "The Guardian (Marcus Magnolia)",
            "PID-INF",
            "Supporting layer",
        ),
        (8007, "monitoring", "The Observatory", "Norman Hawkins", "PID-OBS", "Primary worker"),
        (8008, "notifications", "Arcadia", "Lilli SC", "PID-ARC", "Supporting layer"),
        (8009, "infinity-ai", "Luminous", "Cornelius MacIntyre", "PID-LUM", "Primary worker"),
        (8010, "the-grid", "The Digital Grid", "Tyler Towncroft", "PID-DGR", "Primary worker"),
        (
            8011,
            "products-service",
            "Arcadian Exchange",
            "The Porter Family",
            "PID-AEX",
            "Supporting layer",
        ),
        (
            8012,
            "orders-service",
            "Arcadian Exchange",
            "The Porter Family",
            "PID-AEX",
            "Primary worker",
        ),
        (
            8013,
            "payments-service",
            "Royal Bank of Arcadia",
            "Dorris Fontaine",
            "PID-RBA",
            "Primary worker",
        ),
        (8014, "files-service", "DocUtari", "Fiddsy", "PID-DOC", "Primary worker"),
        (8015, "identity-service", "The Lighthouse", "Rocking Ricki", "PID-LTH", "Primary worker"),
        (
            8016,
            "analytics-service",
            "The Observatory",
            "Norman Hawkins",
            "PID-OBS",
            "Supporting layer",
        ),
        (8017, "search-service", "The Library", "Zimik", "PID-LIB", "Primary worker"),
        (8018, "email-service", "Arcadia", "Lilli SC", "PID-ARC", "Supporting layer"),
        (8019, "sms-service", "The Nexus", "Nexus-Prime", "PID-NXS", "Supporting layer"),
        (8020, "storage-service", "DocUtari", "Fiddsy", "PID-DOC", "Supporting layer"),
        (8021, "cron-service", "ChronosSphere / ArcStream", "Chronos", "PID-CHR", "Primary worker"),
        (8022, "queue-service", "The HIVE", "The Queen", "PID-HVE", "Primary worker"),
        (8023, "cache-service", "The HIVE", "The Queen", "PID-HVE", "Supporting layer"),
        (8024, "config-service", "The Void", "Prometheus", "PID-VOI", "Primary worker"),
        (8025, "audit-service", "The Observatory", "Norman Hawkins", "PID-OBS", "Supporting layer"),
        (8026, "rate-limit-service", "Cryptex", "Renik", "PID-CRX", "Primary worker"),
        (8027, "geo-service", "The Dutchy", "Predictive lore", "PID-DUT", "Primary worker"),
        (8028, "cdn-service", "The Studio", "Voxx", "PID-STD", "Supporting layer"),
        (8029, "health-aggregator", "DevOcity", "Kitty", "PID-DEV", "Primary worker"),
    ]
    for port, worker, location, lead_ai, pid, role in worker_map:
        lines.append(f"| {port} | `{worker}` | {location} | {lead_ai} | {pid} | {role} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Full Entity Table with IDs
    lines.append("## Full Entity Table")
    lines.append("")
    lines.append(
        "| PID | Location | Pillar | Lead AI (AID) | Primes | Agent α (SID) | Agent β (SID) | Bot 01 (NID) | Bot 02 (NID) | Bot 03 (NID) | Bot 04 (NID) |",
    )
    lines.append(
        "|-----|----------|--------|---------------|--------|---------------|---------------|--------------|--------------|--------------|--------------|",
    )

    # Sort by pillar order then by location name
    for pillar_name in pillar_order:
        for loc_name, entity in PLATFORM_ENTITIES.items():
            if entity.pillar.value != pillar_name:
                continue
            abbrev = LOCATION_ABBREVS.get(loc_name, "???")
            lines.append(
                f"| **{entity.pid}** | **{loc_name}** | {entity.pillar.value} | "
                f"{entity.lead_ai} ({entity.aid}) | "
                f"{', '.join(entity.primes)} | "
                f"{entity.agent_alpha.code_name} ({entity.agent_alpha.sid}) | "
                f"{entity.agent_beta.code_name} ({entity.agent_beta.sid}) | "
                f"{entity.bot_01.code_name} ({entity.bot_01.nid}) | "
                f"{entity.bot_02.code_name} ({entity.bot_02.nid}) | "
                f"{entity.bot_03.code_name} ({entity.bot_03.nid}) | "
                f"{entity.bot_04.code_name} ({entity.bot_04.nid}) |",
            )

    lines.append("")
    lines.append("---")
    lines.append("")

    # Tier 2 Prime Authorities
    lines.append("## Tier 2 Prime Authorities")
    lines.append("")
    lines.append("| AID | Prime | Governs Locations |")
    lines.append("|-----|-------|-------------------|")

    prime_govs = {}
    for loc_name, entity in PLATFORM_ENTITIES.items():
        for p in entity.primes:
            if p not in prime_govs:
                prime_govs[p] = []
            prime_govs[p].append(loc_name)

    for prime_name, locs in prime_govs.items():
        abbrev = PRIME_ABBREVS.get(prime_name, "???")
        aid = f"AID-{abbrev}-01"
        lines.append(f"| **{aid}** | **{prime_name}** | {', '.join(locs)} |")

    lines.append("")
    lines.append("---")
    lines.append("")

    # Key Abilities by Location
    lines.append("## Key Abilities by Location")
    lines.append("")
    lines.append("| PID | Location | Ability 1 | Ability 2 |")
    lines.append("|-----|----------|-----------|-----------|")

    for loc_name, entity in PLATFORM_ENTITIES.items():
        ab1 = entity.abilities[0].split(":")[0] if entity.abilities else ""
        ab2 = entity.abilities[1].split(":")[0] if len(entity.abilities) > 1 else ""
        lines.append(f"| {entity.pid} | {loc_name} | {ab1} | {ab2} |")

    lines.append("")

    # Internal personality profiles note
    lines.append("---")
    lines.append("")
    lines.append("### Internal personality profiles not in entity table")
    lines.append(
        "The following profiles exist in `src/personality/profiles/` but have no entry in the platform entity hierarchy. They are legacy/internal profiles predating the entity table:",
    )
    lines.append("- `vesper-nightingale` — internal profile, unmapped")
    lines.append("- `atlas-meridian` — internal profile, unmapped")
    lines.append("")
    lines.append(
        "These are **not** named locations and should not be referenced as platform entities until explicitly assigned.",
    )
    lines.append("")

    return "\n".join(lines)


def generate_matrix_md():
    """Generate docs/matrix.md with pillar-by-pillar tables."""

    pillar_order = [
        ("Architectural", "ARCH"),
        ("Commercial / Financial", "COMM"),
        ("Creativity", "CREA"),
        ("Development (Code)", "DEVL"),
        ("Knowledge", "KNWL"),
        ("Security", "SECU"),
        ("DevOps", "DVOP"),
        ("Wellbeing", "WELL"),
    ]

    lines = []
    lines.append("# Tranc3 Repaired Entity Matrix — by Pillar")
    lines.append("")
    lines.append(
        "Auto-generated from `src/entities/platform.py` with all naming convention repairs applied.",
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("- **43 Locations** across 8 Pillars")
    lines.append("- **8 Primes** (Tier 2) + **1 Sovereign** (Tier 1)")
    lines.append("- **43 Lead AIs** (Tier 3)")
    lines.append("- **86 Agents** (Tier 4: 43 Alpha + 43 Beta)")
    lines.append("- **172 Bots** (Tier 5: 4 per location)")
    lines.append("- **310 Total Entities**")
    lines.append("")
    lines.append("---")
    lines.append("")

    for pillar_name, pillar_abbrev in pillar_order:
        locations_in_pillar = [
            (name, entity)
            for name, entity in PLATFORM_ENTITIES.items()
            if entity.pillar.value == pillar_name
        ]

        lines.append(f"## {pillar_name} ({pillar_abbrev})")
        lines.append("")
        lines.append(f"**{len(locations_in_pillar)} locations** in this pillar.")
        lines.append("")

        for loc_name, entity in locations_in_pillar:
            lines.append(f"### {loc_name} (`{entity.pid}`)")
            lines.append("")
            lines.append("| Tier | Role | Name | ID | Description |")
            lines.append("|------|------|------|----|-------------|")
            lines.append(
                f"| 3 | Lead AI | **{entity.lead_ai}** | `{entity.aid}` | {entity.primary_function} |",
            )
            lines.append(
                f"| 4 | Agent α | {entity.agent_alpha.code_name} | `{entity.agent_alpha.sid}` | {entity.agent_alpha.description} |",
            )
            lines.append(
                f"| 4 | Agent β | {entity.agent_beta.code_name} | `{entity.agent_beta.sid}` | {entity.agent_beta.description} |",
            )
            lines.append(
                f"| 5 | Bot 01 | {entity.bot_01.code_name} | `{entity.bot_01.nid}` | {entity.bot_01.description} |",
            )
            lines.append(
                f"| 5 | Bot 02 | {entity.bot_02.code_name} | `{entity.bot_02.nid}` | {entity.bot_02.description} |",
            )
            lines.append(
                f"| 5 | Bot 03 | {entity.bot_03.code_name} | `{entity.bot_03.nid}` | {entity.bot_03.description} |",
            )
            lines.append(
                f"| 5 | Bot 04 | {entity.bot_04.code_name} | `{entity.bot_04.nid}` | {entity.bot_04.description} |",
            )
            lines.append(f"| — | Primes | {', '.join(entity.primes)} | — | — |")
            lines.append(
                f"| — | Port | {entity.worker_port or 'N/A'} | — | {entity.worker_path or 'N/A'} |",
            )
            lines.append("")

        lines.append("---")
        lines.append("")

    # ID Reference Table
    lines.append("## Full ID Reference")
    lines.append("")
    lines.append("| ID | Tier | Name | Location |")
    lines.append("|----|------|------|----------|")

    # Sovereign
    lines.append("| AID-SOV-01 | 1 | The Sovereign | — |")

    # Primes
    for prime_name, abbrev in PRIME_ABBREVS.items():
        lines.append(f"| AID-{abbrev}-01 | 2 | {prime_name} | — |")

    # Per-location
    for loc_name, entity in PLATFORM_ENTITIES.items():
        lines.append(f"| {entity.aid} | 3 | {entity.lead_ai} | {loc_name} |")
        lines.append(
            f"| {entity.agent_alpha.sid} | 4 | {entity.agent_alpha.code_name} | {loc_name} |",
        )
        lines.append(
            f"| {entity.agent_beta.sid} | 4 | {entity.agent_beta.code_name} | {loc_name} |",
        )
        lines.append(f"| {entity.bot_01.nid} | 5 | {entity.bot_01.code_name} | {loc_name} |")
        lines.append(f"| {entity.bot_02.nid} | 5 | {entity.bot_02.code_name} | {loc_name} |")
        lines.append(f"| {entity.bot_03.nid} | 5 | {entity.bot_03.code_name} | {loc_name} |")
        lines.append(f"| {entity.bot_04.nid} | 5 | {entity.bot_04.code_name} | {loc_name} |")

    lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    # Generate PLATFORM_ENTITIES.md
    md_content = generate_platform_entities_md()
    output_path = os.path.join(os.path.dirname(__file__), "..", "PLATFORM_ENTITIES.md")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    print(f"✅ PLATFORM_ENTITIES.md written ({len(md_content)} chars)")

    # Generate docs/matrix.md
    matrix_content = generate_matrix_md()
    docs_dir = os.path.join(os.path.dirname(__file__), "..", "docs")
    os.makedirs(docs_dir, exist_ok=True)
    matrix_path = os.path.join(docs_dir, "matrix.md")
    with open(matrix_path, "w", encoding="utf-8") as f:
        f.write(matrix_content)
    print(f"✅ docs/matrix.md written ({len(matrix_content)} chars)")
