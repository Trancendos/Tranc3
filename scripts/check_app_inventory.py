#!/usr/bin/env python3
"""Installed GitHub Apps are a control class, and they had no register.

This estate counts three registers of its controls and fails CI when any of
them drifts: `.github/workflows/`, `.forgejo/workflows/`, and `.pre-commit-config.yaml`. Each
works because a file on disk can be counted. (Counts are not restated here;
`check_workflow_inventory.py` validates them only where they are first written.)

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
The default invocation (no flag; there is no `--validate` option) reads
`config/estate/github_apps.yaml` and checks the
register is a usable document: every row named, with a written `does`, a
`decision` from the fixed set, a non-restating `reason`, and an ISO
`reviewed_on`. This needs no network and runs in CI on every pull request.

`--measure` samples the ten most recent pull requests and asks which Apps acted
on them -- as authors, in either comment surface, or as check-runs -- failing on
any the register does not name. It needs a token. It is a SAMPLE: it cannot
enumerate installed Apps, only observe recent activity, and it reports UNKNOWN
if any request in the sample fails.

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


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader that refuses duplicate mapping keys.

    PyYAML keeps the LAST value for a repeated key, so a row with two
    `publishes_checks:` entries validated against whichever came second while
    the other -- possibly the true one -- vanished. `publishes_checks` decides
    whether an App can gate a merge, so a silently discarded value is the most
    consequential field in the register going missing without a message.
    """


def _no_duplicate_keys(loader: yaml.SafeLoader, node: Any, deep: bool = False) -> dict:
    mapping: dict = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r} — one row, two answers, and YAML keeps only the last",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_StrictLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _no_duplicate_keys)

#: Fields that must be written prose, not a YAML scalar that merely stringifies.
#: `does: true` passed as a non-empty description before this existed.
_TEXT_FIELDS = ("slug", "does", "reason")

#: A `reason` must say something the slug does not. These are the words that
#: appear in a row that restates its own name instead of justifying it.
_EMPTY_REASONS = ("", "n/a", "none", "tbd", "todo", "see above", "as above")

GITHUB_API = "https://api.github.com"


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    """Refuse redirects rather than forward a bearer token to a new host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ARG002
        raise urllib.error.HTTPError(
            newurl, code, f"refusing to follow a redirect to {newurl}", headers, fp
        )


#: Built once. Every GitHub read goes through it so the no-redirect rule cannot
#: be bypassed by a caller reaching for `urlopen` directly.
_OPENER = urllib.request.build_opener(_NoRedirects)

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
        # B506 flags any `yaml.load` whose Loader is not literally SafeLoader.
        # `_StrictLoader` SUBCLASSES yaml.SafeLoader and adds only a duplicate-key
        # constructor, so no arbitrary object can be instantiated -- the property
        # B506 protects is intact, and `safe_load` is what we had to leave to get
        # duplicate-key detection at all. Verified: issubclass(_StrictLoader,
        # yaml.SafeLoader) is True, asserted in tests.
        data = yaml.load(  # nosec B506 - _StrictLoader subclasses yaml.SafeLoader
            path.read_text(encoding="utf-8"), Loader=_StrictLoader
        )
    except OSError:
        return [], [f"{_shown(path)} is missing"]
    except yaml.YAMLError as exc:
        return [], [f"{_shown(path)} is not valid YAML: {exc}"]
    if not isinstance(data, dict) or not isinstance(data.get("apps"), list):
        return [], [f"{_shown(path)} has no top-level `apps:` list"]
    # A non-mapping entry is REPORTED, not filtered. Dropping it silently meant
    # a bare `- gitguardian` disappeared from validation entirely while the
    # checker printed PASSED -- and `--measure` then called that App
    # unregistered. A row this file cannot read is a defect in this file.
    rows = [r for r in data["apps"] if isinstance(r, dict)]
    malformed = [
        f"{_shown(path)}: entry {i} is {type(r).__name__}, not a mapping — a row that "
        "cannot be read is not a row that passed"
        for i, r in enumerate(data["apps"])
        if not isinstance(r, dict)
    ]
    return rows, malformed


def row_defects(row: dict[str, Any]) -> list[str]:
    """Reasons one row is not a usable entry."""
    problems: list[str] = []
    for field in _TEXT_FIELDS:
        value = row.get(field)
        if value is not None and not isinstance(value, str):
            problems.append(
                f"{field} is {type(value).__name__}, not text — `{field}: true` "
                "stringifies to a non-empty value and would pass as prose"
            )
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
    # The scheme and host check above covers the URL WE build. `urlopen`
    # follows redirects by default and carries the Authorization header to
    # wherever it is sent, so a 302 would hand this token to a host nothing
    # validated -- the check would have been true of the first request and
    # irrelevant to the one that carried the credential. `_NoRedirects`
    # refuses instead, so the guarantee covers every request actually made.
    with _OPENER.open(request, timeout=30) as response:  # nosec B310 - scheme+host checked, redirects refused
        return json.loads(response.read().decode("utf-8"))


def _bot_slug(login: str) -> str:
    """The App slug behind a login, or "" if the login is not a bot.

    GitHub reports the same App two ways: `coderabbitai[bot]` as a comment
    author, `coderabbitai` as a check-run app slug. Normalising here is what
    lets the register hold one row per App rather than one per surface.
    """
    return login[: -len("[bot]")] if login.endswith("[bot]") else ""


def _apps_in_comments(repo: str, number: Any, token: str) -> set[str]:
    """Apps that commented, across BOTH comment surfaces.

    GitHub stores conversation comments and inline review comments as separate
    resources. Sampling only `/issues/{n}/comments` missed every App that
    posts solely inline review comments -- which is most of the review bots
    this register exists to inventory, so the one omission fell exactly on the
    subject.

    Raises rather than returning a partial set: see `observed_apps`.
    """
    seen: set[str] = set()
    for endpoint in (
        f"/repos/{repo}/issues/{number}/comments?per_page=100",
        f"/repos/{repo}/pulls/{number}/comments?per_page=100",
    ):
        for comment in _api(endpoint, token) or []:
            slug = _bot_slug((comment.get("user") or {}).get("login") or "")
            if slug:
                seen.add(slug)
    return seen


def _apps_in_checks(repo: str, head: str, token: str) -> set[str]:
    """Apps that published a check-run on this head. Raises on failure."""
    runs = _api(f"/repos/{repo}/commits/{head}/check-runs?per_page=100", token)
    slugs = (((r.get("app") or {}).get("slug")) or "" for r in (runs or {}).get("check_runs", []))
    return {slug for slug in slugs if slug}


def observed_apps(repo: str, token: str, *, pulls: int = 10) -> set[str] | None:
    """Apps seen publishing checks, commenting, or opening pull requests.

    `None` when ANY request failed, so the caller reports UNKNOWN instead of a
    completeness claim built on partial sight.

    REGRESSION, and the defect this whole script was written to prevent. Every
    per-PR fetch used to swallow `URLError` and continue. `HTTPError` is a
    SUBCLASS of `URLError`, so a 403 or a 429 -- the likeliest failures when
    walking ten pull requests' comments and check-runs -- silently dropped that
    PR's Apps, `unregistered` came back empty, and `main` printed
    `App register: PASSED`. A sensor that could not see, reporting clean. Five
    independent reviewers found it; the module docstring already forbade it for
    the no-token case and the same obligation always applied here.

    Three surfaces, because an App is only visible on the ones it uses: a
    scanner appears solely as a check-run, a review bot solely as comments, and
    a dependency bot as the author of its own pull requests.
    """
    seen: set[str] = set()
    try:
        prs = _api(f"/repos/{repo}/pulls?state=all&per_page={pulls}", token)
        for pr in prs if isinstance(prs, list) else []:
            author = _bot_slug((pr.get("user") or {}).get("login") or "")
            if author:
                seen.add(author)
            seen |= _apps_in_comments(repo, pr.get("number"), token)
            head = (pr.get("head") or {}).get("sha")
            if head:
                seen |= _apps_in_checks(repo, head, token)
    except (urllib.error.URLError, json.JSONDecodeError, ValueError):
        return None
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
    observed = observed_apps(repo, token)
    if observed is None:
        print(
            "\nMeasurement: UNKNOWN — at least one GitHub request failed, so the "
            "sample is\nincomplete. A partial observation cannot show the register "
            "is complete, and\nreporting it as though it could is the defect this "
            "script exists to catch."
        )
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
