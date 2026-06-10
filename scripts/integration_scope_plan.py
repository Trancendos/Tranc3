#!/usr/bin/env python3
"""Break a large integration branch into scoped PR-sized work packages.

Analyzes path prefixes and change types (add/modify/delete) without merging.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import defaultdict
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"

SCOPE_RULES: list[tuple[str, str, str]] = [
    ("workers/", "Workers & Docker", "cherry-pick per worker; verify healthchecks (curl)"),
    ("deploy/", "Deploy / Citadel", "review compose + Traefik separately"),
    ("cloudflare/", "Cloudflare Workers", "legacy — prefer self-hosted migration path"),
    ("shared_core/", "Shared core", "BLOCK — integration branch deletes modules; do not bulk merge"),
    ("src/", "Backend src/", "review + test; avoid cross-cutting deletes"),
    ("Dimensional/", "Dimensional layer", "medium risk — run targeted tests"),
    ("web/", "Arcadia frontend", "UX/a11y scoped PRs"),
    ("tests/", "Tests", "port with matching production changes"),
    ("scripts/", "Ops scripts", "usually safe if additive"),
    ("monitoring/", "Observability", "safe if additive"),
    (".forgejo/", "CI/CD", "safe if additive workflows"),
    ("aeonmind/", "AeonMind polyglot", "blocked — large cross-language surface"),
    ("docs/", "Documentation", "safe"),
]


@dataclass
class ScopeBucket:
    prefix: str
    label: str
    guidance: str
    added: int
    modified: int
    deleted: int
    files: list[str]


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def _match_scope(path: str) -> tuple[str, str, str]:
    for prefix, label, guidance in SCOPE_RULES:
        if path.startswith(prefix) or path == prefix.rstrip("/"):
            return prefix, label, guidance
    top = path.split("/", 1)[0] if "/" in path else path
    return top + "/", top, "manual review"


def analyze(base: str, branch: str) -> tuple[list[ScopeBucket], dict[str, int]]:
    out = _run(["git", "diff", "--name-status", f"{base}...origin/{branch}"])
    buckets: dict[str, ScopeBucket] = {}
    totals = {"added": 0, "modified": 0, "deleted": 0, "files": 0}

    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        status, path = parts[0], parts[1]
        if status.startswith("R"):
            status = "M"
            path = path.split("\t")[-1] if "\t" in path else path
        prefix, label, guidance = _match_scope(path)
        key = prefix
        if key not in buckets:
            buckets[key] = ScopeBucket(
                prefix=prefix,
                label=label,
                guidance=guidance,
                added=0,
                modified=0,
                deleted=0,
                files=[],
            )
        b = buckets[key]
        b.files.append(f"{status} {path}")
        totals["files"] += 1
        if status == "A":
            b.added += 1
            totals["added"] += 1
        elif status == "D":
            b.deleted += 1
            totals["deleted"] += 1
        else:
            b.modified += 1
            totals["modified"] += 1

    ordered = sorted(buckets.values(), key=lambda b: (-b.deleted, -(b.added + b.modified), b.prefix))
    return ordered, totals


def _write_outputs(branch: str, base: str, buckets: list[ScopeBucket], totals: dict[str, int]) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    slug = branch.replace("/", "_")
    json_path = LOGS / f"integration_scope_{slug}_{ts}.json"
    md_path = LOGS / f"integration_scope_{slug}_latest.md"
    payload = {
        "branch": branch,
        "base": base,
        "generated_at": ts,
        "totals": totals,
        "scopes": [asdict(b) for b in buckets],
    }
    json_path.write_text(json.dumps(payload, indent=2))

    blocked = any(b.prefix == "shared_core/" and b.deleted > 0 for b in buckets)
    lines = [
        f"# Integration scope plan: `{branch}`",
        "",
        f"Base: `{base}` | Generated: {ts}",
        "",
        f"**Totals:** {totals['files']} files | +{totals['added']} / ~{totals['modified']} / −{totals['deleted']}",
        "",
        "## Verdict",
        "",
    ]
    if blocked:
        lines.append(
            "⛔ **Do not bulk-merge.** This branch deletes `shared_core/` modules and would regress "
            "encrypted SQLite, auth hardening, and zero-cost env defaults. Integrate only via "
            "scoped cherry-picks after review."
        )
    else:
        lines.append("⚠️ Review scoped buckets below; prefer cherry-pick over merge.")
    lines.extend(["", "## Scoped work packages", ""])
    for b in buckets:
        if not b.files:
            continue
        lines.append(f"### {b.label} (`{b.prefix}`)")
        lines.append("")
        lines.append(f"- Changes: +{b.added} / ~{b.modified} / −{b.deleted}")
        lines.append(f"- Guidance: {b.guidance}")
        lines.append("- Sample paths:")
        for sample in b.files[:8]:
            lines.append(f"  - `{sample}`")
        if len(b.files) > 8:
            lines.append(f"  - … and {len(b.files) - 8} more")
        lines.append("")

    md_path.write_text("\n".join(lines))
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--branch", required=True, help="Remote branch name (without origin/)")
    parser.add_argument("--base", default="main")
    args = parser.parse_args()

    subprocess.run(["git", "fetch", "origin", "--prune"], cwd=ROOT, check=False)
    buckets, totals = analyze(args.base, args.branch)
    _write_outputs(args.branch, args.base, buckets, totals)
    print(
        f"Scopes: {len(buckets)} | files={totals['files']} | "
        f"+{totals['added']}/~{totals['modified']}/−{totals['deleted']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
