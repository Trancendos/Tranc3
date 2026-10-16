#!/usr/bin/env python3
"""Installed GitHub Apps are a control class, and they had no register.

This estate counts three registers of its controls and fails CI when any of
them drifts: `.github/workflows/` (28 files), `.forgejo/workflows/` (33), and
`.pre-commit-config.yaml` (22 hooks). Each works because a file on disk can be
counted.

An App leaves no file. It is installed in a GitHub settings page and appears in
this repository only as comments and check-runs. So nothing here could be
counted, and nothing was -- which is how four Apps that PUBLISH COMMIT CHECKS
came to be running while named in no document in the tree:

    debricked                       software composition analysis
    gitguardian                     secret scanning
    codefactor-io                   static analysis, gates pull requests
    mermaid-diagram-sync-assistant  diagram sync

Two are security scanners. `docs/governance/IMMUNE-SYSTEM.md` says to read it
before adding any scanner to this estate, and CLAUDE.md records the identical
lesson about workflows: the instruction "only binds if adding one is visible".
For Apps it was not visible. Measured 2026-10-16: 22 distinct Apps act here,
and `ecc-tools` alone posted 134 comments across five pull requests -- more
than any human or agent wrote in the same span.

TWO MODES, AND WHY THEY ARE SEPARATE
------------------------------------
`--validate` (default) reads `config/estate/github_apps.yaml` and checks the
register is a usable document: every row named, with a written `does`, a
`decision` from the fixed set, a non-restating `reason`, and an ISO
`reviewed_on`. This needs no network and runs in CI on every pull request.

`--measure` asks GitHub which Apps actually acted recently and fails on any
that the register does not name. It needs a token.

Without a token `--measure` reports UNKNOWN and exits non-zero rather than
reporting that the register is complete. That is the whole point of this file:
a register validated offline proves only that it is well-formed, never that it
is complete, and claiming otherwise would make this script the thing it exists
to catch. `grade.py` already separates "did not look" from "looked and it was
fine"; so does this.

UNDECIDED IS NOT A FAILURE
--------------------------
A row may say `decision: undecided`. The count is reported every run and never
fails the check. This follows the Backlog Routing Register, where items with no
decision stay `_unrouted_` because that count "is a queue the Town Hall owes an
answer to rather than a number assigned away by judgement". A register that
demanded a verdict on every row the day it was written would record one
author's guesses as the estate's decisions.
"""

from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parents[1]
REGISTER = REPO / "config/estate/github_apps.yaml"

#: The only decisions a row may record. `undecided` is deliberate -- see the
#: module docstring.
DECISIONS = ("keep", "declined", "undecided")

#: A `reason` must say something the slug does not. These are the words that
#: appear in a row that restates its own name instead of justifying it.
_EMPTY_REASONS = ("", "n/a", "none", "tbd", "todo", "see above", "as above")

GITHUB_API = "https://api.github.com"


def _shown(path: Path) -> str:
    """A path for a message, repo-relative where it can be.

    `Path.relative_to` RAISES for a path outside the repository, so using it
    unguarded here crashed the error-reporting branch on any register passed
    from a temporary directory -- a check that could not report its own
    failure. Caught by its own tests.
    """
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return str(path)


def _load_register(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """Rows and any reason the file itself is unusable."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError:
        return [], [f"{_shown(path)} is missing"]
    except yaml.YAMLError as exc:
        return [], [f"{_shown(path)} is not valid YAML: {exc}"]
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        return [], [f"{_shown(path)} has no top-level `apps:` list"]
    return [r for r in data["apps"] if isinstance(r, dict)], []


def row_defects(row: dict[str, Any]) -> list[str]:
    """Reasons one row is not a usable entry."""
    problems: list[str] = []
    slug = str(row.get("slug") or "").strip()
    if not slug:
        problems.append("no slug")
    if not str(row.get("does") or "").strip():
        problems.append("no `does` -- nothing says what it does here")
    decision = str(row.get("decision") or "").strip()
    if decision not in DECISIONS:
        problems.append(f"decision {decision!r} is not one of {', '.join(DECISIONS)}")
    reason = str(row.get("reason") or "").strip()
    if reason.lower().rstrip(".") in _EMPTY_REASONS:
        problems.append("no written reason")
    elif slug and reason.lower().rstrip(".") == slug.lower():
        problems.append("the reason restates the slug")
    reviewed = str(row.get("reviewed_on") or "").strip()
    if not reviewed:
        problems.append("no reviewed_on date")
    else:
        from datetime import date

        try:
            date.fromisoformat(reviewed)
        except ValueError:
            problems.append(f"reviewed_on {reviewed!r} is not an ISO date")
    for flag in ("publishes_checks", "opens_prs"):
        if not isinstance(row.get(flag), bool):
            problems.append(f"{flag} must be true or false, not {row.get(flag)!r}")
    return problems


def _api(path: str, token: str) -> Any:
    request = urllib.request.Request(
        f"{GITHUB_API}{path}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "tranc3-app-inventory",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310 - fixed host
        return json.loads(response.read().decode("utf-8"))


def observed_apps(repo: str, token: str, *, pulls: int = 10) -> set[str]:
    """Apps seen publishing checks, commenting, or opening pull requests."""
    seen: set[str] = set()
    prs = _api(f"/repos/{repo}/pulls?state=all&per_page={pulls}", token)
    for pr in prs if isinstance(prs, list) else []:
        number, head = pr.get("number"), (pr.get("head") or {}).get("sha")
        author = (pr.get("user") or {}).get("login") or ""
        if author.endswith("[bot]"):
            seen.add(author[: -len("[bot]")])
        for endpoint in (f"/repos/{repo}/issues/{number}/comments?per_page=100",):
            try:
                for comment in _api(endpoint, token) or []:
                    login = (comment.get("user") or {}).get("login") or ""
                    if login.endswith("[bot]"):
                        seen.add(login[: -len("[bot]")])
            except (urllib.error.URLError, json.JSONDecodeError):
                continue
        if head:
            try:
                runs = _api(f"/repos/{repo}/commits/{head}/check-runs?per_page=100", token)
                for run in (runs or {}).get("check_runs", []):
                    slug = ((run.get("app") or {}).get("slug")) or ""
                    if slug:
                        seen.add(slug)
            except (urllib.error.URLError, json.JSONDecodeError):
                continue
    return seen


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--register", type=Path, default=REGISTER)
    parser.add_argument(
        "--measure",
        action="store_true",
        help="also ask GitHub which Apps acted recently (needs a token)",
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Trancendos/Tranc3"))
    parser.add_argument("--list", action="store_true", help="print the register and exit")
    args = parser.parse_args(argv)

    rows, fatal = _load_register(args.register)
    if fatal:
        for problem in fatal:
            print(f"App register: FAILED — {problem}")
        return 1

    if args.list:
        for row in sorted(rows, key=lambda r: str(r.get("slug"))):
            caps = []
            if row.get("publishes_checks"):
                caps.append("checks")
            if row.get("opens_prs"):
                caps.append("prs")
            print(f"  {str(row.get('slug')):34s} {str(row.get('decision')):10s} {','.join(caps)}")
        print(f"\n{len(rows)} apps registered")
        return 0

    failures: list[str] = []
    seen_slugs: dict[str, int] = {}
    for row in rows:
        slug = str(row.get("slug") or "?")
        seen_slugs[slug] = seen_slugs.get(slug, 0) + 1
        for problem in row_defects(row):
            failures.append(f"{slug}: {problem}")
    for slug, count in seen_slugs.items():
        if count > 1:
            failures.append(f"{slug}: listed {count} times")

    gating = [r for r in rows if r.get("publishes_checks")]
    merging = [r for r in rows if str(r.get("slug")) == "mergify"]
    undecided = [r for r in rows if str(r.get("decision")) == "undecided"]

    print(f"App register: {len(rows)} apps")
    print(f"  publish commit checks (can gate a merge): {len(gating)}")
    print(f"  can merge without a human:                {len(merging)}")
    print(f"  undecided (a queue, not a failure):       {len(undecided)}")
    if undecided:
        for row in undecided:
            print(f"      - {row.get('slug')}")

    unknown_measure = False
    if args.measure:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
        if not token:
            unknown_measure = True
            print(
                "\nMeasurement: UNKNOWN — no GITHUB_TOKEN, so the register was not "
                "compared against reality. A register validated offline is well-formed, "
                "never complete; reporting it as complete here would make this script "
                "the defect it exists to catch."
            )
        else:
            try:
                observed = observed_apps(args.repo, token)
            except (urllib.error.URLError, json.JSONDecodeError) as exc:
                unknown_measure = True
                print(f"\nMeasurement: UNKNOWN — could not reach GitHub ({exc}).")
            else:
                registered = {str(r.get("slug")) for r in rows}
                unregistered = sorted(observed - registered)
                print(f"\nMeasurement: {len(observed)} apps observed acting on {args.repo}")
                for slug in unregistered:
                    failures.append(
                        f"{slug}: acting on this repository but named nowhere in the register"
                    )
                stale = sorted(registered - observed)
                if stale:
                    print("  registered but not seen in the sampled window (not a failure):")
                    for slug in stale:
                        print(f"      - {slug}")

    if failures:
        print("\nApp register: FAILED")
        for problem in failures:
            print(f"  - {problem}")
        return 1
    if unknown_measure:
        return 1
    print("\nApp register: PASSED — every row is a usable entry")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
