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
import urllib.parse
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

#: Checked in `_api` before every fetch. See its docstring for why a
#: constant base URL is not on its own a guarantee.
_ALLOWED_SCHEMES = frozenset({"https"})
_API_HOST = "api.github.com"


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
    """One GitHub read, with the scheme checked rather than asserted.

    `urlopen` will follow `file://`, `data:` and any other scheme the opener
    knows, so a URL assembled from a variable is a real finding and not a
    style complaint -- `GITHUB_API` is a constant today, but `--repo` and
    `$GITHUB_REPOSITORY` both reach `path`. The suppression below is honest
    only because the two lines above it make it true: an allowlisted scheme
    and the one host this script is for. A comment claiming "fixed host" and
    nothing enforcing it is the defect this estate keeps finding in its own
    controls.
    """
    url = f"{GITHUB_API}{path}"
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme not in _ALLOWED_SCHEMES or parsed.netloc != _API_HOST:
        raise ValueError(
            f"refusing to fetch {parsed.scheme}://{parsed.netloc} -- not the GitHub API"
        )
    request = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "tranc3-app-inventory",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # nosec B310 - scheme+host checked above
        return json.loads(response.read().decode("utf-8"))


def _bot_slug(login: str) -> str:
    """The App slug behind a login, or "" if the login is not a bot.

    GitHub reports the same App two ways: `coderabbitai[bot]` as a comment
    author, `coderabbitai` as a check-run app slug. Normalising here is what
    lets the register hold one row per App rather than one per surface.
    """
    return login[: -len("[bot]")] if login.endswith("[bot]") else ""


def _apps_in_comments(repo: str, number: Any, token: str) -> set[str]:
    try:
        comments = _api(f"/repos/{repo}/issues/{number}/comments?per_page=100", token) or []
    except (urllib.error.URLError, json.JSONDecodeError):
        return set()
    logins = ((c.get("user") or {}).get("login") or "" for c in comments)
    return {slug for slug in map(_bot_slug, logins) if slug}


def _apps_in_checks(repo: str, head: str, token: str) -> set[str]:
    try:
        runs = _api(f"/repos/{repo}/commits/{head}/check-runs?per_page=100", token)
    except (urllib.error.URLError, json.JSONDecodeError):
        return set()
    slugs = (((r.get("app") or {}).get("slug")) or "" for r in (runs or {}).get("check_runs", []))
    return {slug for slug in slugs if slug}


def observed_apps(repo: str, token: str, *, pulls: int = 10) -> set[str]:
    """Apps seen publishing checks, commenting, or opening pull requests.

    Three surfaces, because an App is only visible on the ones it uses: a
    scanner appears solely as a check-run, a review bot solely as comments,
    and a dependency bot as the author of its own pull requests. Sampling one
    surface would under-count the register's subject.
    """
    seen: set[str] = set()
    prs = _api(f"/repos/{repo}/pulls?state=all&per_page={pulls}", token)
    for pr in prs if isinstance(prs, list) else []:
        author = _bot_slug((pr.get("user") or {}).get("login") or "")
        if author:
            seen.add(author)
        seen |= _apps_in_comments(repo, pr.get("number"), token)
        head = (pr.get("head") or {}).get("sha")
        if head:
            seen |= _apps_in_checks(repo, head, token)
    return seen


def register_defects(rows: list[dict[str, Any]]) -> list[str]:
    """Every reason the register as a whole is not usable.

    Per-row problems come from `row_defects`; this adds the one defect a row
    cannot see on its own, a slug listed twice. Two rows for one App mean two
    decisions for one grant of authority, and nothing says which holds.
    """
    failures: list[str] = []
    counts: dict[str, int] = {}
    for row in rows:
        slug = str(row.get("slug") or "?")
        counts[slug] = counts.get(slug, 0) + 1
        failures.extend(f"{slug}: {problem}" for problem in row_defects(row))
    failures.extend(f"{slug}: listed {count} times" for slug, count in counts.items() if count > 1)
    return failures


def _print_listing(rows: list[dict[str, Any]]) -> None:
    for row in sorted(rows, key=lambda r: str(r.get("slug"))):
        caps = [
            name
            for flag, name in (("publishes_checks", "checks"), ("opens_prs", "prs"))
            if row.get(flag)
        ]
        print(f"  {str(row.get('slug')):34s} {str(row.get('decision')):10s} {','.join(caps)}")
    print(f"\n{len(rows)} apps registered")


def _print_shape(rows: list[dict[str, Any]]) -> None:
    """What the register says about this estate, by authority held."""
    gating = [r for r in rows if r.get("publishes_checks")]
    merging = [r for r in rows if str(r.get("slug")) == "mergify"]
    undecided = [r for r in rows if str(r.get("decision")) == "undecided"]
    print(f"App register: {len(rows)} apps")
    print(f"  publish commit checks (can gate a merge): {len(gating)}")
    print(f"  can merge without a human:                {len(merging)}")
    print(f"  undecided (a queue, not a failure):       {len(undecided)}")
    for row in undecided:
        print(f"      - {row.get('slug')}")


def _measure_against_github(repo: str, rows: list[dict[str, Any]]) -> tuple[list[str], bool]:
    """Compare the register with what GitHub says acted here.

    Returns the failures found and whether the comparison is UNKNOWN. The
    two are deliberately separate: an unreachable GitHub is not a register
    defect, and must not be reported as one -- nor as a clean comparison.
    """
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN") or ""
    if not token:
        print(
            "\nMeasurement: UNKNOWN — no GITHUB_TOKEN, so the register was not "
            "compared against reality. A register validated offline is well-formed, "
            "never complete; reporting it as complete here would make this script "
            "the defect it exists to catch."
        )
        return [], True
    try:
        observed = observed_apps(repo, token)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        print(f"\nMeasurement: UNKNOWN — could not reach GitHub ({exc}).")
        return [], True

    registered = {str(r.get("slug")) for r in rows}
    print(f"\nMeasurement: {len(observed)} apps observed acting on {repo}")
    failures = [
        f"{slug}: acting on this repository but named nowhere in the register"
        for slug in sorted(observed - registered)
    ]
    stale = sorted(registered - observed)
    if stale:
        print("  registered but not seen in the sampled window (not a failure):")
        for slug in stale:
            print(f"      - {slug}")
    return failures, False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--register", type=Path, default=REGISTER)
    parser.add_argument(
        "--measure",
        action="store_true",
        help="also ask GitHub which Apps acted recently (needs a token)",
    )
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "Trancendos/Tranc3"))
    parser.add_argument("--list", action="store_true", help="print the register and exit")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    rows, fatal = _load_register(args.register)
    if fatal:
        for problem in fatal:
            print(f"App register: FAILED — {problem}")
        return 1

    if args.list:
        _print_listing(rows)
        return 0

    failures = register_defects(rows)
    _print_shape(rows)

    unknown_measure = False
    if args.measure:
        measured_failures, unknown_measure = _measure_against_github(args.repo, rows)
        failures.extend(measured_failures)

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
