#!/usr/bin/env python3
"""PR readiness audit for forks and branches.

Produces a concise readiness report for pull requests by inspecting:
  - source branch and base branch
  - whether the head branch comes from a fork owner
  - merge state and check status outcomes

Designed for production promotion gates where unstable PRs should block release.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from typing import Any

GH_PR_FIELDS = ",".join(
    [
        "number",
        "title",
        "state",
        "isDraft",
        "headRefName",
        "baseRefName",
        "headRepositoryOwner",
        "mergeStateStatus",
        "statusCheckRollup",
        "updatedAt",
        "url",
    ]
)

FAIL_STATES = {"FAILURE", "TIMED_OUT", "CANCELLED", "ERROR", "STARTUP_FAILURE"}
PENDING_STATES = {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING", "REQUESTED"}
UNSTABLE_MERGE_STATES = {"UNSTABLE", "BLOCKED", "BEHIND", "DIRTY", "UNKNOWN"}


@dataclass
class PullRequestReadiness:
    number: int
    title: str
    state: str
    head_ref: str
    base_ref: str
    head_owner: str
    merge_state: str
    failures: int
    action_required: int
    pending: int
    updated_at: str
    url: str

    @property
    def healthy(self) -> bool:
        return (
            self.merge_state not in UNSTABLE_MERGE_STATES
            and self.failures == 0
            and self.action_required == 0
            and self.pending == 0
        )


def _run_gh(args: list[str]) -> str:
    proc = subprocess.run(["gh", *args], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Unknown gh error")
    return proc.stdout


def _get_repo_owner() -> str:
    output = _run_gh(["repo", "view", "--json", "owner", "--jq", ".owner.login"])
    return output.strip()


def _status_counts(checks: list[dict[str, Any]]) -> tuple[int, int, int]:
    failures = 0
    action_required = 0
    pending = 0

    for check in checks:
        state = str(check.get("conclusion") or check.get("state") or "").upper()
        if not state:
            continue
        if state in FAIL_STATES:
            failures += 1
        elif state == "ACTION_REQUIRED":
            action_required += 1
        elif state in PENDING_STATES:
            pending += 1

    return failures, action_required, pending


def load_pull_requests(state: str, limit: int) -> list[dict[str, Any]]:
    output = _run_gh(
        [
            "pr",
            "list",
            "--state",
            state,
            "--limit",
            str(limit),
            "--json",
            GH_PR_FIELDS,
        ]
    )
    return json.loads(output)


def build_readiness(pr_raw: list[dict[str, Any]]) -> list[PullRequestReadiness]:
    readiness: list[PullRequestReadiness] = []
    for pr in pr_raw:
        checks = pr.get("statusCheckRollup") or []
        failures, action_required, pending = _status_counts(checks)
        readiness.append(
            PullRequestReadiness(
                number=int(pr["number"]),
                title=str(pr["title"]),
                state=str(pr["state"]),
                head_ref=str(pr["headRefName"]),
                base_ref=str(pr["baseRefName"]),
                head_owner=str((pr.get("headRepositoryOwner") or {}).get("login", "unknown")),
                merge_state=str(pr.get("mergeStateStatus") or "UNKNOWN"),
                failures=failures,
                action_required=action_required,
                pending=pending,
                updated_at=str(pr.get("updatedAt") or ""),
                url=str(pr.get("url") or ""),
            )
        )
    return readiness


def print_text_report(items: list[PullRequestReadiness], repo_owner: str) -> None:
    print("PR readiness audit")
    print("==================")
    print(
        "num  state   fork  merge      fail  action  pending  branch -> base                      "
        "updated"
    )
    print(
        "---  ------  ----  ---------  ----  ------  -------  ----------------------------------  "
        "--------------------"
    )

    for item in sorted(items, key=lambda x: x.number, reverse=True):
        fork = "yes" if item.head_owner and item.head_owner != repo_owner else "no"
        branch_pair = f"{item.head_ref} -> {item.base_ref}"
        print(
            f"{item.number:<3}  {item.state:<6}  {fork:<4}  {item.merge_state:<9}  "
            f"{item.failures:<4}  {item.action_required:<6}  {item.pending:<7}  "
            f"{branch_pair[:34]:<34}  {item.updated_at}"
        )

    healthy = sum(1 for item in items if item.healthy)
    unstable = len(items) - healthy
    print()
    print(f"Total PRs: {len(items)} | Healthy: {healthy} | Unstable: {unstable}")


def to_json_report(items: list[PullRequestReadiness], repo_owner: str) -> str:
    payload = {
        "repo_owner": repo_owner,
        "total": len(items),
        "healthy": sum(1 for item in items if item.healthy),
        "unstable": sum(1 for item in items if not item.healthy),
        "pull_requests": [
            {
                "number": item.number,
                "title": item.title,
                "state": item.state,
                "head_ref": item.head_ref,
                "base_ref": item.base_ref,
                "head_owner": item.head_owner,
                "is_fork": bool(item.head_owner and item.head_owner != repo_owner),
                "merge_state": item.merge_state,
                "failures": item.failures,
                "action_required": item.action_required,
                "pending": item.pending,
                "healthy": item.healthy,
                "updated_at": item.updated_at,
                "url": item.url,
            }
            for item in sorted(items, key=lambda x: x.number, reverse=True)
        ],
    }
    return json.dumps(payload, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit PR fork/branch readiness and gate unstable states."
    )
    parser.add_argument(
        "--state",
        choices=["open", "closed", "merged", "all"],
        default="open",
        help="PR state filter (default: open).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=100,
        help="Maximum PRs to scan (default: 100).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report instead of text.",
    )
    parser.add_argument(
        "--fail-on-unstable",
        action="store_true",
        help="Exit with status 1 if any PR is unstable.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        repo_owner = _get_repo_owner()
        items = build_readiness(load_pull_requests(args.state, args.limit))
    except (RuntimeError, json.JSONDecodeError) as exc:
        print(f"Failed to gather PR data: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(to_json_report(items, repo_owner))
    else:
        print_text_report(items, repo_owner)

    if args.fail_on_unstable and any(not item.healthy for item in items):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
