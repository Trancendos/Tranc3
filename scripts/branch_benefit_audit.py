#!/usr/bin/env python3
"""Audit remote branches ahead of main and rank safe integration candidates.

Writes JSON + markdown under logs/ for Forgejo artifacts and human review.
Zero-cost: uses local git only.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DEFAULT_BASE = "main"

# Branches known to be destructive or superseded — never auto-merge.
BLOCKLIST_PREFIXES = (
    "merge/aeonmind-into-main",
    "phase-24/aeonmind-polyglot",
    "refactor/shared-core-to-dimensional",
    "infra/phase16-adaptive-storage",
)


@dataclass
class BranchReport:
    name: str
    ahead: int
    behind: int
    files_changed: int
    insertions: int
    deletions: int
    verdict: str
    notes: str


def _run(cmd: list[str]) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def _remote_branches() -> list[str]:
    out = _run(["git", "branch", "-r", "--format=%(refname:short)"])
    names = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.endswith("/HEAD") or "->" in line:
            continue
        if line.startswith("origin/"):
            names.append(line.removeprefix("origin/"))
    return sorted(set(names))


def _diff_stats(base: str, branch: str) -> tuple[int, int, int]:
    try:
        stat = _run(["git", "diff", "--shortstat", f"{base}...origin/{branch}"])
    except subprocess.CalledProcessError:
        return 0, 0, 0
    if not stat:
        return 0, 0, 0
    files = insertions = deletions = 0
    parts = stat.replace(",", "").split()
    for i, part in enumerate(parts):
        if part == "file" or part == "files":
            files = int(parts[i - 1])
        elif part == "insertion" or part == "insertions":
            insertions = int(parts[i - 1])
        elif part == "deletion" or part == "deletions":
            deletions = int(parts[i - 1])
    return files, insertions, deletions


def _verdict(branch: str, ahead: int, files: int, deletions: int) -> tuple[str, str]:
    if any(branch.startswith(p) for p in BLOCKLIST_PREFIXES):
        return "blocked", "Known high-risk / superseded integration branch"
    if ahead == 0:
        return "merged", "No commits ahead of main"
    if deletions > 5000:
        return "blocked", "Mass deletions — likely destructive rebase"
    if files <= 15 and deletions < 500:
        return "cherry-pick", "Small, reviewable diff — safe to cherry-pick"
    if files <= 40 and deletions < 2000:
        return "review", "Medium diff — manual review + targeted cherry-pick"
    return "blocked", "Large diff — integrate via focused PRs only"


def audit(base: str = DEFAULT_BASE) -> list[BranchReport]:
    reports: list[BranchReport] = []
    for branch in _remote_branches():
        if branch == base:
            continue
        try:
            ahead = int(_run(["git", "rev-list", "--count", f"{base}..origin/{branch}"]))
            behind = int(_run(["git", "rev-list", "--count", f"origin/{branch}..{base}"]))
        except subprocess.CalledProcessError:
            continue
        if ahead == 0:
            continue
        files, ins, dels = _diff_stats(base, branch)
        verdict, notes = _verdict(branch, ahead, files, dels)
        reports.append(
            BranchReport(
                name=branch,
                ahead=ahead,
                behind=behind,
                files_changed=files,
                insertions=ins,
                deletions=dels,
                verdict=verdict,
                notes=notes,
            )
        )
    reports.sort(key=lambda r: (r.verdict != "cherry-pick", -r.ahead))
    return reports


def _write_outputs(reports: list[BranchReport], base: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    json_path = LOGS / f"branch_benefit_audit_{ts}.json"
    md_path = LOGS / "branch_benefit_audit_latest.md"
    payload = {
        "base": base,
        "generated_at": ts,
        "branches": [asdict(r) for r in reports],
    }
    json_path.write_text(json.dumps(payload, indent=2))
    lines = [
        "# Branch benefit audit",
        "",
        f"Base: `{base}` | Generated: {ts}",
        "",
        "| Branch | Ahead | Behind | Files | +/− | Verdict | Notes |",
        "|--------|------:|-------:|------:|-----|---------|-------|",
    ]
    for r in reports:
        lines.append(
            f"| `{r.name}` | {r.ahead} | {r.behind} | {r.files_changed} | "
            f"+{r.insertions}/−{r.deletions} | **{r.verdict}** | {r.notes} |"
        )
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit remote branches for safe main integration")
    parser.add_argument("--base", default=DEFAULT_BASE)
    args = parser.parse_args()
    subprocess.run(["git", "fetch", "origin", "--prune"], cwd=ROOT, check=False)
    reports = audit(args.base)
    _write_outputs(reports, args.base)
    blocked = sum(1 for r in reports if r.verdict == "blocked")
    cherry = sum(1 for r in reports if r.verdict == "cherry-pick")
    print(f"Summary: {len(reports)} branches ahead | {cherry} cherry-pick | {blocked} blocked")
    return 0


if __name__ == "__main__":
    sys.exit(main())
