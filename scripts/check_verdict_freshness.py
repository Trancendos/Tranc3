#!/usr/bin/env python3
"""The merge gate's own verdict must still be true when it is relied on.

`scripts/vulnerability_census.py` answers a question about a LIVE advisory
feed, and the Production merge gate records that answer as a check-run
conclusion. GitHub then satisfies the required check from any green on the head
commit, however old -- so when a head stops moving, the green stops being
re-earned and nothing notices it has aged out.

Measured on 2026-10-13: nine open pull requests, including `main` itself, held
a green Production merge gate timestamped inside one forty-five-minute window
on 2026-10-05. All nine predated the seventeen advisories that landed in
between; seven also read `mergeable_state: clean`. Nothing was wrong with those
check-runs -- they were true when they ran. What was missing was anything able
to tell a pass earned an hour ago from one earned eight days ago.

This script is that. It reads the census output, builds a
`src.immune.verdict.Verdict` from it, and fails when the verdict does not count
as a live pass. `src/immune/verdict.py` carries the reasoning, including why a
stale verdict degrades to `unknown` rather than staying a pass: an expired
suppression delays a fix, an expired pass ships.

Exit codes
----------
0  the verdict is a live pass
1  the verdict is stale, unknown, malformed, or a fail

`--github-output` additionally writes `state`, `context` and `description` to
`$GITHUB_OUTPUT` so a workflow step can publish the verdict as a commit status
beside the aging one. The posting is left to the workflow on purpose: this
script measures, and a step that measures should not also hold a write token.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.immune.verdict import (  # noqa: E402  - path set above
    DEFAULT_TTL_HOURS,
    STALE,
    UNKNOWN,
    VerdictReport,
    load_verdict,
)

CENSUS_OUTPUT = REPO / "logs" / "vulnerability_census.json"

#: Commit-status context. Named for what it asserts rather than which script
#: produced it, so the status survives this file being renamed.
STATUS_CONTEXT = "immune/census-verdict"


def _github_state(report: VerdictReport) -> str:
    """A commit-status state for the verdict.

    `unknown` maps to `error`, not `failure`: GitHub renders both as not-green,
    but they mean different things and the estate's founding rule is that "I
    could not look" must never read the same as "I looked and it was fine".
    """
    if report.holds:
        return "success"
    if report.unknown or report.malformed:
        return "error"
    return "failure"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--census",
        type=Path,
        default=CENSUS_OUTPUT,
        help="census output to read (default: logs/vulnerability_census.json)",
    )
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_TTL_HOURS,
        help=(
            "how long a census answer stays current. Defaults to the estate's own "
            f"re-measurement interval ({DEFAULT_TTL_HOURS:g}h, per "
            "supply-chain-watch.yml and MC-045)."
        ),
    )
    parser.add_argument(
        "--github-output",
        action="store_true",
        help="also write state/context/description to $GITHUB_OUTPUT",
    )
    parser.add_argument(
        "--warn-only",
        action="store_true",
        help=(
            "report and exit 0. For adopting this on a branch whose verdict is "
            "already stale, so the finding is visible before it blocks."
        ),
    )
    args = parser.parse_args(argv)

    now = datetime.now(timezone.utc)
    verdict = load_verdict(args.census, ttl_hours=args.max_age_hours)
    report = VerdictReport(verdicts=[verdict], checked_at=now)

    print(report.explain())

    defects = verdict.defects()
    if defects:
        print("\nThis verdict is not a usable answer:")
        for problem in defects:
            print(f"  - {problem}")

    state = _github_state(report)
    if args.github_output:
        description = verdict.explain(now)[:140]
        out = os.environ.get("GITHUB_OUTPUT")
        payload = f"state={state}\ncontext={STATUS_CONTEXT}\ndescription={description}\n"
        if out:
            with open(out, "a", encoding="utf-8") as handle:
                handle.write(payload)
        else:
            # No $GITHUB_OUTPUT means this is not running in Actions. Print it
            # rather than failing: the caller asked for the values, and
            # inventing a file to write them to would be worse.
            print(f"\n(not in GitHub Actions; would have written)\n{payload}", end="")

    if report.holds:
        print(f"\nVerdict freshness: PASSED — {verdict.name} is a live pass")
        return 0

    freshness = verdict.freshness(now)
    if freshness == STALE:
        print(
            f"\nVerdict freshness: FAILED — this verdict is {freshness} and no longer "
            "answers for today's advisory feed. Re-run the census on this head "
            "(pushing to the branch is enough) rather than relying on the "
            "recorded green."
        )
    elif freshness == UNKNOWN:
        print(
            f"\nVerdict freshness: FAILED — freshness is {UNKNOWN}, so nothing has "
            "been established. This is not the same as a failing scan and must "
            "not be read as one, nor as a pass."
        )
    else:
        print(
            f"\nVerdict freshness: FAILED — the verdict is {freshness} but its outcome "
            f"is {verdict.outcome!r}. The census itself is the thing to fix."
        )

    if args.warn_only:
        print("(--warn-only: reporting without blocking)")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
