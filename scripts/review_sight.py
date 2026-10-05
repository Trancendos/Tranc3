#!/usr/bin/env python3
"""Report which pull requests were actually reviewed, and which only looked it.

Nine review bots post on this repository. Three of them were out of credits,
out of quota or unsubscribed on 2026-10-05, and said so in a comment nobody
reads -- while the pull request page showed what a clean review shows. See
`src/immune/reviewers.py` for the measurement and the design, and
`docs/governance/IMMUNE-SYSTEM.md` for the rule it extends.

    python scripts/review_sight.py                  # open pull requests
    python scripts/review_sight.py 1372 1371        # named ones
    python scripts/review_sight.py --require        # exit non-zero if uncovered

Collection is all-or-nothing per pull request. If any endpoint fails -- a 403,
a rate limit, a transient error -- that pull request reports UNKNOWN rather than
a verdict built from partial evidence, because a reduced evidence set presented
as a measurement is the defect this whole subsystem exists to prevent.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.immune.reviewers import Remark, assess, load_manifest  # noqa: E402

REPO = "Trancendos/Tranc3"


class Unavailable(RuntimeError):
    """Evidence could not be collected. Never silently downgraded to silence."""


def _gh(path: str, paginate: bool = True) -> object:
    cmd = ["gh", "api"]
    if paginate:
        cmd.append("--paginate")
    cmd.append(path)
    proc = subprocess.run(  # nosec B603 — list args, no shell; path is built below
        cmd, cwd=ROOT, capture_output=True, text=True
    )
    if proc.returncode != 0:
        raise Unavailable(f"gh api {path}: {proc.stderr.strip()[:160]}")
    text = proc.stdout.strip()
    if not text:
        return []
    # `--paginate` concatenates one JSON document per page; join the arrays.
    out: list[object] = []
    decoder = json.JSONDecoder()
    idx = 0
    while idx < len(text):
        try:
            doc, end = decoder.raw_decode(text, idx)
        except json.JSONDecodeError as exc:
            raise Unavailable(f"gh api {path}: unparseable response") from exc
        if isinstance(doc, list):
            out.extend(doc)
        else:
            return doc
        idx = end
        while idx < len(text) and text[idx] in " \t\r\n":
            idx += 1
    return out


def _login(record: dict) -> str | None:
    """A comment's author, which GitHub may report as null for a deleted user."""
    user = record.get("user")
    if not isinstance(user, dict):
        return None
    login = user.get("login")
    return login if isinstance(login, str) else None


def _remarks(pr: int) -> tuple[list[Remark], str | None, str | None]:
    """Every remark on a pull request, its head sha and its author.

    Raises Unavailable if any part could not be read, so the caller reports
    UNKNOWN rather than assembling a verdict from what happened to arrive.
    """
    meta = _gh(f"repos/{REPO}/pulls/{pr}", paginate=False)
    if not isinstance(meta, dict):
        raise Unavailable(f"pull {pr}: unexpected payload")
    head = ((meta.get("head") or {}) if isinstance(meta.get("head"), dict) else {}).get("sha")
    author = _login(meta)

    out: list[Remark] = []
    for record in _gh(f"repos/{REPO}/issues/{pr}/comments?per_page=100") or []:
        if isinstance(record, dict) and (who := _login(record)):
            out.append(Remark(who, record.get("body") or "", "issue_comment"))
    for record in _gh(f"repos/{REPO}/pulls/{pr}/comments?per_page=100") or []:
        if isinstance(record, dict) and (who := _login(record)):
            out.append(
                Remark(
                    who,
                    record.get("body") or "",
                    "review_comment",
                    record.get("commit_id") or record.get("original_commit_id"),
                )
            )
    # Submitted reviews: a reviewer can approve or summarise with no comment at
    # all, which the first version recorded as SILENT.
    for record in _gh(f"repos/{REPO}/pulls/{pr}/reviews?per_page=100") or []:
        if isinstance(record, dict) and (who := _login(record)):
            out.append(
                Remark(
                    who,
                    record.get("body") or "",
                    "review",
                    record.get("commit_id"),
                    record.get("state"),
                )
            )
    return out, head, author


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

    depends_on, not_a_reviewer = load_manifest()
    expected = tuple(args.expect) if args.expect else depends_on
    if not expected:
        print(
            "[WARN] no reviewers declared in config/immune/reviewers.yaml and none "
            "passed with --expect, so coverage cannot be measured -- only observed."
        )

    if args.prs:
        numbers = args.prs
    else:
        try:
            listing = _gh(f"repos/{REPO}/pulls?state=open&per_page=100")
        except Unavailable as exc:
            print(f"[ERROR] could not list open pull requests: {exc}")
            return 1
        numbers = [int(p["number"]) for p in listing if isinstance(p, dict)]

    uncovered: list[str] = []
    unknown: list[str] = []
    blind_tally: dict[str, int] = {}

    for pr in numbers:
        try:
            remarks, head, author = _remarks(pr)
        except Unavailable as exc:
            coverage = assess(f"#{pr}", [], expected=expected, collected=False)
            print(f"{coverage.summary}\n    {exc}")
            unknown.append(f"#{pr}")
            continue

        coverage = assess(
            f"#{pr}",
            remarks,
            expected=expected,
            author=author,
            head=head,
            not_a_reviewer=not_a_reviewer,
        )
        print(coverage.summary)
        for verdict in coverage.unpublished:
            print(f"    {verdict.reviewer}: reviewed but could not publish a check")
        for verdict in coverage.stale:
            print(f"    {verdict.reviewer}: {verdict.evidence}, not the current head")
        for verdict in coverage.silent:
            if verdict.reviewer in expected:
                print(f"    {verdict.reviewer}: said nothing at all")
        for verdict in coverage.unproven:
            if verdict.reviewer in expected:
                print(f"    {verdict.reviewer}: commented, but nothing shows it read the diff")
        for verdict in coverage.blind:
            blind_tally[verdict.reviewer] = blind_tally.get(verdict.reviewer, 0) + 1
        if not coverage.covered:
            uncovered.append(f"#{pr}")

    print(
        f"\n{len(numbers)} pull request(s); {len(uncovered)} with no depended-on reviewer "
        f"that reviewed the current head; {len(unknown)} not measurable"
    )
    if uncovered:
        print(f"  uncovered: {', '.join(uncovered)}")
    if unknown:
        print(f"  UNKNOWN (evidence unavailable): {', '.join(unknown)}")
    if blind_tally:
        print("  reviewers that declared they could not review:")
        for name, count in sorted(blind_tally.items(), key=lambda kv: -kv[1]):
            print(f"    {name:<28} on {count} pull request(s)")

    return 1 if (args.require and (uncovered or unknown)) else 0


if __name__ == "__main__":
    sys.exit(main())
