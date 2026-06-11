#!/usr/bin/env python3
"""List or delete remote branches fully merged into main (0 commits ahead).

Dry-run by default. Requires maintainer credentials for --apply.
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
DEFAULT_REMOTE = "origin"

# Never auto-delete integration / long-lived work branches even if git reports 0 ahead
# (can happen after squash merges with divergent history).
PROTECTED_PREFIXES = (
    "main",
    "cursor/production-integration-",
    "claude/loving-mendel-",
    "phase-24/",
    "refactor/shared-core-to-dimensional",
    "infra/phase16-adaptive-storage",
)


@dataclass
class StaleBranch:
    name: str
    behind: int
    protected: bool
    reason: str


def _run(cmd: list[str], check: bool = True) -> str:
    return subprocess.check_output(cmd, cwd=ROOT, text=True, stderr=subprocess.STDOUT).strip()


def _remote_branches(remote: str) -> list[str]:
    out = _run(["git", "branch", "-r", "--format=%(refname:short)"])
    names: list[str] = []
    for line in out.splitlines():
        line = line.strip()
        if not line or line.endswith("/HEAD") or "->" in line:
            continue
        prefix = f"{remote}/"
        if line.startswith(prefix):
            names.append(line.removeprefix(prefix))
    return sorted(set(names))


def _is_protected(name: str) -> tuple[bool, str]:
    for prefix in PROTECTED_PREFIXES:
        if name == prefix or name.startswith(prefix):
            return True, f"protected prefix `{prefix}`"
    return False, ""


def discover(base: str, remote: str) -> list[StaleBranch]:
    stale: list[StaleBranch] = []
    for branch in _remote_branches(remote):
        if branch == base:
            continue
        try:
            ahead = int(_run(["git", "rev-list", "--count", f"{base}..{remote}/{branch}"]))
            behind = int(_run(["git", "rev-list", "--count", f"{remote}/{branch}..{base}"]))
        except subprocess.CalledProcessError:
            continue
        if ahead != 0:
            continue
        protected, reason = _is_protected(branch)
        stale.append(StaleBranch(name=branch, behind=behind, protected=protected, reason=reason))
    stale.sort(key=lambda b: (b.protected, b.name))
    return stale


def _write_outputs(stale: list[StaleBranch], base: str, remote: str) -> None:
    LOGS.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    deletable = [b for b in stale if not b.protected]
    payload = {
        "base": base,
        "remote": remote,
        "generated_at": ts,
        "total_merged_refs": len(stale),
        "deletable_count": len(deletable),
        "protected_count": sum(1 for b in stale if b.protected),
        "branches": [asdict(b) for b in stale],
    }
    json_path = LOGS / f"stale_branch_cleanup_{ts}.json"
    md_path = LOGS / "stale_branch_cleanup_latest.md"
    json_path.write_text(json.dumps(payload, indent=2))
    lines = [
        "# Stale branch cleanup",
        "",
        f"Base: `{base}` | Remote: `{remote}` | Generated: {ts}",
        "",
        f"Merged refs (0 ahead): **{len(stale)}** | Deletable: **{len(deletable)}** | Protected: **{payload['protected_count']}**",
        "",
        "| Branch | Behind main | Protected | Notes |",
        "|--------|------------:|-----------|-------|",
    ]
    for b in stale:
        note = b.reason or ("safe to delete" if not b.protected else "")
        lines.append(f"| `{b.name}` | {b.behind} | {'yes' if b.protected else 'no'} | {note} |")
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Delete remote branches fully contained in main")
    parser.add_argument("--base", default=DEFAULT_BASE)
    parser.add_argument("--remote", default=DEFAULT_REMOTE)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Delete deletable branches on remote (requires push permission)",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    args = parser.parse_args()

    subprocess.run(["git", "fetch", args.remote, "--prune"], cwd=ROOT, check=False)
    stale = discover(args.base, args.remote)
    deletable = [b.name for b in stale if not b.protected]
    _write_outputs(stale, args.base, args.remote)

    if args.json:
        print(
            json.dumps(
                {
                    "deletable": deletable,
                    "protected": [b.name for b in stale if b.protected],
                    "count": len(deletable),
                }
            )
        )

    if not args.apply:
        print(f"Would delete {len(deletable)} remote branch(es). Re-run with --apply to execute.")
        for name in deletable:
            print(f"  - {name}")
        return 0

    if not deletable:
        print("Nothing to delete.")
        return 0

    failed: list[str] = []
    for name in deletable:
        ref = f"{args.remote}/{name}"
        try:
            subprocess.run(
                ["git", "push", args.remote, "--delete", name],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"Deleted {ref}")
        except subprocess.CalledProcessError as exc:
            failed.append(name)
            print(f"FAILED {ref}: {exc.stderr or exc.stdout}", file=sys.stderr)

    if failed:
        print(f"Completed with {len(failed)} failure(s).", file=sys.stderr)
        return 1
    print(f"Deleted {len(deletable)} stale remote branch(es).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
