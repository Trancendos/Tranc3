#!/usr/bin/env python3
"""Mark superseded open PRs when main already contains the integration work.

Requires `gh` CLI and GITHUB_TOKEN (or gh auth). Dry-run by default.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# PR numbers superseded by main integration (zero-cost + production entity + branch audit).
SUPERSEDED: dict[int, str] = {
    84: "KnowledgeBrain/RBAC/GBrain — partial pieces on main; full merge via production-integration branch only",
    85: "LoginPage a11y — merged on main (LoginPage.tsx)",
    86: "AeonMind polyglot — blocked; use targeted cherry-picks only",
    87: "Phase 16 Oracle — optional; not required for Citadel zero-cost core",
    88: "Phase 24 adaptive — overlaps main adaptive rotator + proactive orchestrator",
    89: "Palette empty states — dashboard already has empty prompts",
}


def _gh_json(args: list[str]) -> dict | list:
    cmd = ["gh", "pr", "view", *args, "--json", "number,state,title,headRefName"]
    out = subprocess.check_output(cmd, cwd=ROOT, text=True)
    data = json.loads(out)
    return data[0] if isinstance(data, list) and len(data) == 1 else data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Close PRs with comment (requires gh auth)")
    parser.add_argument("--repo", default="Trancendos/Tranc3")
    args = parser.parse_args()

    try:
        subprocess.run(["gh", "--version"], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("gh CLI not available — printing superseded PR list only", file=sys.stderr)
        for num, reason in SUPERSEDED.items():
            print(f"  #{num}: {reason}")
        return 0

    for num, reason in SUPERSEDED.items():
        try:
            pr = _gh_json([str(num)])
            state = pr.get("state", "?")
            title = pr.get("title", "")
            if state != "OPEN":
                print(f"#{num} already {state}: {title}")
                continue
            comment = (
                f"Superseded by integration on `main` (automated hygiene).\n\n"
                f"**Reason:** {reason}\n\n"
                f"See `docs/BRANCH_INTEGRATION_REPORT.md` and `logs/branch_benefit_audit_latest.md`."
            )
            if args.apply:
                subprocess.run(
                    ["gh", "pr", "close", str(num), "--comment", comment, "--repo", args.repo],
                    cwd=ROOT,
                    check=True,
                )
                print(f"Closed #{num}")
            else:
                print(f"Would close OPEN #{num}: {title}")
        except subprocess.CalledProcessError as exc:
            print(f"#{num}: skip ({exc})", file=sys.stderr)

    if not args.apply:
        print("\nRe-run with --apply to close superseded PRs (requires maintainer token).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
