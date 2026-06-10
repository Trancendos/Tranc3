#!/usr/bin/env python3
"""Audit GitHub forks for the canonical repo (requires gh CLI)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
DEFAULT_REPO = "Trancendos/Tranc3"


def _gh_available() -> bool:
    try:
        subprocess.run(["gh", "auth", "status"], cwd=ROOT, check=True, capture_output=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _repo_meta(repo: str) -> dict:
    out = subprocess.check_output(
        ["gh", "repo", "view", repo, "--json", "name,owner,forkCount,isFork,parent,updatedAt"],
        cwd=ROOT,
        text=True,
    )
    return json.loads(out)


def _list_forks(repo: str, limit: int) -> list[dict]:
    out = subprocess.check_output(
        [
            "gh",
            "api",
            f"repos/{repo}/forks",
            "--paginate",
            "-q",
            f".[:{limit}] | .[] | {{full_name, owner: .owner.login, default_branch, pushed_at, archived, fork: .fork}}",
        ],
        cwd=ROOT,
        text=True,
    )
    forks: list[dict] = []
    for line in out.splitlines():
        line = line.strip()
        if line:
            forks.append(json.loads(line))
    return forks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args()

    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")

    if not _gh_available():
        payload = {"skipped": True, "reason": "gh not authenticated", "repo": args.repo}
        path = LOGS / "fork_audit_latest.json"
        path.write_text(json.dumps(payload, indent=2))
        print("SKIP: gh CLI not authenticated")
        return 0

    meta = _repo_meta(args.repo)
    forks = _list_forks(args.repo, args.limit) if meta.get("forkCount", 0) else []

    payload = {
        "repo": args.repo,
        "generated_at": ts,
        "fork_count": meta.get("forkCount", 0),
        "is_fork": meta.get("isFork", False),
        "parent": meta.get("parent"),
        "updated_at": meta.get("updatedAt"),
        "forks_sampled": forks,
        "merged_into_main": "unknown — forks are external; audit individually on GitHub",
    }
    json_path = LOGS / f"fork_audit_{ts}.json"
    latest = LOGS / "fork_audit_latest.json"
    md_path = LOGS / "fork_audit_latest.md"
    json_path.write_text(json.dumps(payload, indent=2))
    latest.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Fork audit",
        "",
        f"Repo: `{args.repo}` | Generated: {ts}",
        "",
        f"**Fork count:** {payload['fork_count']}",
        f"**This repo is a fork:** {payload['is_fork']}",
        "",
    ]
    if not forks:
        lines.append("No forks returned (count is 0 or API returned empty sample).")
    else:
        lines.append("| Fork | Owner | Pushed | Archived |")
        lines.append("|------|-------|--------|----------|")
        for f in forks:
            lines.append(
                f"| `{f.get('full_name', '?')}` | {f.get('owner', '?')} | "
                f"{f.get('pushed_at', '?')} | {f.get('archived', False)} |"
            )
        lines.append("")
        lines.append(
            "Forks are not automatically merged into `main`. Track divergent forks manually "
            "or open upstream sync PRs from fork owners."
        )
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    print(f"Fork count: {payload['fork_count']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
