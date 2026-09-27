#!/usr/bin/env python3
"""Emit the Trancendos taxonomy — Locations, AIs, Dimensionals — as docs + JSON.

The structure is the owner's, set on 2026-09-11. The *content* is measured:
every node names the file or symbol it was read from, and a level with no source
is reported as a gap rather than filled in.

That distinction is the whole point. This estate already has several registers
that describe an intended platform rather than the one in the repository, and
each of them decayed silently because nothing compared the two. `--check` makes
this one fail CI the moment the published tree stops equalling the measured one.

Usage:
    python3 scripts/build_taxonomy_tree.py           # write the tree
    python3 scripts/build_taxonomy_tree.py --check   # fail if stale
    python3 scripts/build_taxonomy_tree.py --gaps    # print gaps only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.taxonomy import build_tree, gaps  # noqa: E402

JSON_OUT = REPO / "docs" / "architecture" / "taxonomy.json"
MD_OUT = REPO / "docs" / "architecture" / "TAXONOMY.md"

#: How deep the Markdown view goes. The JSON carries every node; the document is
#: for reading, and a 1,800-node bullet list is not read by anyone.
MD_MAX_DEPTH = 3


def render_markdown(tree) -> str:
    root = tree.root
    counts = {
        kind: tree.count(kind)
        for kind in (
            "location",
            "ability",
            "component",
            "module",
            "nanoservice",
            "job_description",
            "power_up",
            "ai",
            "trait",
            "agent",
            "bot",
            "dimensional",
        )
    }
    missing = gaps(tree)

    lines: list[str] = [
        "# Trancendos Taxonomy",
        "",
        "> **Generated — do not edit.** `python3 scripts/build_taxonomy_tree.py`",
        "> regenerates this file and `taxonomy.json`; `--check` fails CI when they",
        "> drift from the code. The structure below is the owner's; every node's",
        "> content is read from the source named beside it.",
        "",
        "## What this is",
        "",
        "Three branches, each assembled from registers that already existed and had",
        "never been assembled:",
        "",
        "| Branch | Read from |",
        "|---|---|",
        "| **Locations** | `PLATFORM_ENTITIES` — 43 entities, their abilities, code paths and ports |",
        "| **AIs** | `get_orchestration_tier()` for the tier, `src/personality/profiles/` for profile and personality, `agent_teams` / `bot_01..04` for agents and bots |",
        "| **Dimensionals (Shared-Core)** | the `Dimensionals/` package, classified into Services, Middleware, Databases, Mesh and Routers |",
        "",
        "## Measured totals",
        "",
        "| Node kind | Count |",
        "|---|---:|",
    ]
    for kind, count in counts.items():
        lines.append(f"| {kind.replace('_', ' ').title()} | {count} |")

    lines += ["", "## Gaps", ""]
    if missing:
        lines.append(
            "Branches the structure declares and nothing in the repository populates. "
            "This is a queue, not a defect list — each one is a place the taxonomy is "
            "ahead of the code."
        )
        lines.append("")
        for gap in missing:
            lines.append(f"- `{gap['name']}`")
    else:
        lines.append(
            "None. Every branch of the structure is populated by a source in this "
            "repository. That is a statement about coverage, not quality: it says each "
            "level has content, not that the content is complete."
        )

    lines += ["", f"## Tree (to depth {MD_MAX_DEPTH})", ""]

    def emit(node, depth: int) -> None:
        if depth > MD_MAX_DEPTH:
            return
        indent = "  " * depth
        suffix = f" — `{node.source}`" if node.source else ""
        detail = f" · {node.detail}" if node.detail and depth <= 2 else ""
        lines.append(f"{indent}- **{node.name}**{suffix}{detail}")
        if depth == MD_MAX_DEPTH and node.children:
            lines.append(f"{indent}  - _{len(node.children)} more — see `taxonomy.json`_")
            return
        for child in node.children:
            emit(child, depth + 1)

    emit(root, 0)
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the output is stale")
    parser.add_argument("--gaps", action="store_true", help="print gaps and exit")
    args = parser.parse_args(argv)

    tree = build_tree()

    if args.gaps:
        missing = gaps(tree)
        for gap in missing:
            print(f"gap: {gap['name']}")
        print(f"{len(missing)} gap(s)")
        return 0

    payload = json.dumps(tree.to_dict(), indent=2, ensure_ascii=False) + "\n"
    markdown = render_markdown(tree)

    if args.check:
        stale = []
        if not JSON_OUT.is_file() or JSON_OUT.read_text(encoding="utf-8") != payload:
            stale.append(JSON_OUT)
        if not MD_OUT.is_file() or MD_OUT.read_text(encoding="utf-8") != markdown:
            stale.append(MD_OUT)
        if stale:
            for path in stale:
                print(f"STALE: {path.relative_to(REPO)}", file=sys.stderr)
            print(
                "\nThe published taxonomy no longer matches the code. Run:\n"
                "  python3 scripts/build_taxonomy_tree.py",
                file=sys.stderr,
            )
            return 1
        print("taxonomy is current")
        return 0

    JSON_OUT.parent.mkdir(parents=True, exist_ok=True)
    JSON_OUT.write_text(payload, encoding="utf-8")
    MD_OUT.write_text(markdown, encoding="utf-8")
    print(f"wrote {JSON_OUT.relative_to(REPO)} ({len(payload):,} bytes)")
    print(f"wrote {MD_OUT.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
