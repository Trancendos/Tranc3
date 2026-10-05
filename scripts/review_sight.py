#!/usr/bin/env python3
"""Report which pull requests were actually reviewed, and which only looked it.

Nine review bots post on this repository. Three of them were out of credits,
out of quota or unsubscribed on 2026-10-05, and said so in a comment nobody
reads -- while the pull request page showed what a clean review shows. See
`src/immune/reviewers.py` for the measurement and `docs/governance/IMMUNE-SYSTEM.md`
for the rule it extends.

    python scripts/review_sight.py                  # open pull requests
    python scripts/review_sight.py 1372 1371        # named ones
    python scripts/review_sight.py --expect sourcery-ai[bot] --require

`--require` exits non-zero when a pull request has NO trustworthy reviewer, so
this can gate rather than merely report. It is deliberately not wired into CI
here: which reviewers this estate depends on is a decision to write down, not
one for this script to assume.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.immune.reviewers import assess, load_manifest  # noqa: E402

REPO = "Trancendos/Tranc3"


def _gh(path: str) -> object:
    proc = subprocess.run(  # nosec B603 — list args, no shell; path is built below
        ["gh", "api", path], cwd=ROOT, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gh api {path} failed: {proc.stderr.strip()[:200]}")
    return json.loads(proc.stdout)


def _open_prs() -> list[int]:
    data = _gh(f"repos/{REPO}/pulls?state=open&per_page=100")
    assert isinstance(data, list)
    return [int(pr["number"]) for pr in data]


def _author(pr: int) -> str | None:
    try:
        data = _gh(f"repos/{REPO}/pulls/{pr}")
    except RuntimeError:
        return None
    if isinstance(data, dict):
        user = data.get("user") or {}
        return user.get("login")
    return None


def _comments(pr: int) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for endpoint in (f"issues/{pr}/comments", f"pulls/{pr}/comments"):
        try:
            data = _gh(f"repos/{REPO}/{endpoint}?per_page=100")
        except RuntimeError:
            continue
        if isinstance(data, list):
            out += [(c["user"]["login"], c.get("body") or "") for c in data]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("prs", nargs="*", type=int, help="pull request numbers (default: all open)")
    ap.add_argument(
        "--expect",
        action="append",
        default=[],
        help="override the manifest: a reviewer coverage is judged against",
    )
    ap.add_argument(
        "--require",
        action="store_true",
        help="exit non-zero if any pull request has no trustworthy reviewer",
    )
    args = ap.parse_args()

    depends_on, _not_reviewers = load_manifest(ROOT / "config" / "immune" / "reviewers.yaml")
    expected = tuple(args.expect) if args.expect else depends_on
    if not expected:
        print(
            "[WARN] no reviewers declared in config/immune/reviewers.yaml and none "
            "passed with --expect, so coverage cannot be measured -- only observed."
        )

    numbers = args.prs or _open_prs()
    uncovered: list[str] = []
    blind_tally: dict[str, int] = {}

    for pr in numbers:
        coverage = assess(f"#{pr}", _comments(pr), expected=expected, author=_author(pr))
        print(coverage.summary)
        for verdict in coverage.unpublished:
            print(f"    {verdict.reviewer}: reviewed but could not publish a check")
        for verdict in coverage.blind:
            blind_tally[verdict.reviewer] = blind_tally.get(verdict.reviewer, 0) + 1
        if not coverage.covered:
            uncovered.append(f"#{pr}")

    print(
        f"\n{len(numbers)} pull request(s); {len(uncovered)} with no depended-on reviewer "
        f"that actually reviewed"
    )
    if uncovered:
        print(f"  uncovered: {', '.join(uncovered)}")
    if blind_tally:
        print("  reviewers that declared they could not review:")
        for name, count in sorted(blind_tally.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<28} on {count} pull request(s)")

    return 1 if (args.require and uncovered) else 0


if __name__ == "__main__":
    sys.exit(main())
