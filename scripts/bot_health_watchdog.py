#!/usr/bin/env python3
"""
bot_health_watchdog.py — detects a silently-broken CI review-bot integration.

Nothing currently watches for a bot integration failing quietly. Kilo Code
Review's billing lapse this session is the concrete example: every PR shows
a dangling "action_required" check with a "could not run — your account is
out of credits" message, and that's the *only* symptom — no alert, no
notification, nothing distinguishing it from a one-off flake unless a human
happens to read the check output on enough PRs to notice the pattern.

This script fetches the check-runs GitHub actually recorded on the most
recent N pull requests, groups them by bot name, and flags a bot whose
*consecutive*, most-recent runs all show a known-degraded signal (an
action_required/failure conclusion whose output text matches a
known-degraded phrase for that bot, e.g. "credits", "billing", "rate limit").
A single bad run is noise — most of these bots occasionally hit a rate limit
and recover next PR. A run of consecutive bad results across multiple PRs is
signal: something is actually broken, not flaky.

This intentionally does NOT flag known non-blocking integrations that are
*expected* to be red today (see KNOWN_NONBLOCKING_BOTS) — CircleCI has no
config in this repo and always errors; that's a pre-existing, understood
state, not something worth alerting on repeatedly.

Usage:
    GITHUB_TOKEN=... python scripts/bot_health_watchdog.py Trancendos/Tranc3
    GITHUB_TOKEN=... python scripts/bot_health_watchdog.py Trancendos/Tranc3 --limit 15 --threshold 4

Exit code 0: every known bot is healthy (or too little data to judge).
Exit code 1: at least one bot shows a persistent degraded pattern — this is
the alert. A scheduled workflow failing on this is the notification
mechanism, matching this repo's existing "Notify The Citadel on failure"
pattern rather than adding a new notification channel.
"""

from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass, field

import httpx

GITHUB_API = "https://api.github.com"

# Known review-bot check-run names (substring match, case-insensitive) and
# the phrases in their output that indicate a *broken integration* rather
# than a normal "no issues found" or "found N issues" result.
KNOWN_BOTS: dict[str, tuple[str, ...]] = {
    "Kilo Code Review": (
        "out of credits",
        "could not run",
        "billing",
        "assistant request failed",
    ),
    "CodeRabbit": ("review limit reached", "couldn't start this review"),
}

# Conclusions that are always healthy, regardless of bot — never worth
# flagging even if the phrase-match logic below would otherwise trigger.
_HEALTHY_CONCLUSIONS = {"success", "neutral", "skipped"}

# Check-run names known to be red for a pre-existing, understood, non-bot
# reason (e.g. CircleCI has no config in this repo) — not what this
# watchdog exists to catch, so excluded rather than repeatedly re-flagged.
KNOWN_NONBLOCKING_BOTS = {"CircleCI Pipeline"}


@dataclass
class CheckRunResult:
    pr_number: int
    name: str
    conclusion: str | None
    summary_text: str = ""


@dataclass
class DegradedFinding:
    bot_name: str
    consecutive_degraded_prs: list[int] = field(default_factory=list)


def _is_degraded_for_bot(bot_name: str, result: CheckRunResult) -> bool:
    if result.conclusion in _HEALTHY_CONCLUSIONS:
        return False
    phrases = KNOWN_BOTS.get(bot_name, ())
    haystack = result.summary_text.lower()
    return any(phrase in haystack for phrase in phrases)


def detect_degraded_bots(
    results_by_pr: list[list[CheckRunResult]],
    threshold: int = 3,
) -> list[DegradedFinding]:
    """*results_by_pr* is ordered most-recent-PR-first, each element the
    check-runs recorded on that PR. Flags a bot whose most recent
    `threshold` (or more) PRs, counting from the most recent PR backward
    with NO gap, all show a degraded signal for that bot. A bot that
    recovers on any PR within that window resets the streak — this is
    deliberately about *persistent*, not merely *frequent*, failure.
    """
    findings: dict[str, DegradedFinding] = {}
    still_streaking: set[str] = set(KNOWN_BOTS.keys())

    for pr_results in results_by_pr:
        seen_this_pr = {r.name for r in pr_results}
        for bot_name in list(still_streaking):
            if bot_name not in seen_this_pr:
                # Bot didn't run on this PR at all — not evidence either way,
                # streak continues without counting this PR.
                continue
            result = next(r for r in pr_results if r.name == bot_name)
            if _is_degraded_for_bot(bot_name, result):
                findings.setdefault(bot_name, DegradedFinding(bot_name=bot_name))
                findings[bot_name].consecutive_degraded_prs.append(result.pr_number)
            else:
                still_streaking.discard(bot_name)
                findings.pop(bot_name, None)

    return [
        f for f in findings.values() if len(f.consecutive_degraded_prs) >= threshold
    ]


async def fetch_recent_pr_check_runs(
    owner: str, repo: str, token: str, limit: int
) -> list[list[CheckRunResult]]:
    """Fetch check-runs for the `limit` most recently updated PRs (any
    state), most-recent-first."""
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    }
    async with httpx.AsyncClient(
        base_url=GITHUB_API, headers=headers, timeout=30.0
    ) as client:
        pr_resp = await client.get(
            f"/repos/{owner}/{repo}/pulls",
            params={
                "state": "all",
                "sort": "updated",
                "direction": "desc",
                "per_page": limit,
            },
        )
        pr_resp.raise_for_status()
        prs = pr_resp.json()

        results_by_pr: list[list[CheckRunResult]] = []
        for pr in prs:
            head_sha = pr["head"]["sha"]
            pr_number = pr["number"]
            runs_resp = await client.get(
                f"/repos/{owner}/{repo}/commits/{head_sha}/check-runs",
                params={"per_page": 100},
            )
            runs_resp.raise_for_status()
            check_runs = runs_resp.json().get("check_runs", [])
            pr_results = [
                CheckRunResult(
                    pr_number=pr_number,
                    name=cr["name"],
                    conclusion=cr.get("conclusion"),
                    summary_text=((cr.get("output") or {}).get("summary") or ""),
                )
                for cr in check_runs
                if cr["name"] in KNOWN_BOTS
            ]
            results_by_pr.append(pr_results)
        return results_by_pr


async def main_async(
    owner: str, repo: str, token: str, limit: int, threshold: int
) -> int:
    results_by_pr = await fetch_recent_pr_check_runs(owner, repo, token, limit)
    findings = detect_degraded_bots(results_by_pr, threshold=threshold)

    print("=" * 60)
    print(f"Bot Health Watchdog — {owner}/{repo}")
    print("=" * 60)
    print(f"Checked {len(results_by_pr)} most recent PR(s), threshold={threshold}\n")

    if not findings:
        print("✓ No known review-bot integration shows a persistent degraded pattern.")
        return 0

    print(f"✗ {len(findings)} bot(s) show a persistent degraded pattern:\n")
    for finding in findings:
        prs = ", ".join(f"#{n}" for n in finding.consecutive_degraded_prs)
        print(
            f"  ⚠ {finding.bot_name}: degraded on {len(finding.consecutive_degraded_prs)} "
            f"consecutive PR(s): {prs}"
        )
        print(
            "    This is not a one-off flake — investigate the integration (billing, auth, config)."
        )
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repo", help="owner/repo, e.g. Trancendos/Tranc3")
    parser.add_argument(
        "--limit", type=int, default=10, help="How many recent PRs to check"
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=3,
        help="Consecutive degraded PRs before flagging (default 3)",
    )
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        print("ERROR: GITHUB_TOKEN environment variable is required.", file=sys.stderr)
        return 1

    owner, _, repo = args.repo.partition("/")
    if not owner or not repo:
        print(f"ERROR: repo must be 'owner/repo', got {args.repo!r}", file=sys.stderr)
        return 1

    import asyncio

    return asyncio.run(main_async(owner, repo, token, args.limit, args.threshold))


if __name__ == "__main__":
    sys.exit(main())
