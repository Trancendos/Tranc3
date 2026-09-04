#!/usr/bin/env python3
"""A Trivy suppression must say why, and stay true.

WHY THIS EXISTS

`.trivyignore` silences findings in three scanners' worth of output. Today's
four entries are exemplary -- each carries the affected package, why it is not
exploitable here, and what would make it exploitable again. Nothing enforces
any of that. One line holding a bare `CVE-2025-12345` is valid Trivy syntax and
suppresses a real vulnerability with no record of who decided, or why.

That is this estate's recurring defect in its most consequential form: a
control that exists, runs, reports, and does not act. A suppression file is the
one place where NOT acting is the whole point, so the discipline has to live
somewhere else -- here.

WHAT IT REQUIRES

  1. A justification. Every id must be preceded by a contiguous comment block,
     and that block must say something: a bare `# CVE-2025-12345` repeated
     above the entry is not a reason.
  2. A re-check trigger. Three of the four current entries are suppressed
     because "no fixed version exists" -- a claim about upstream that stops
     being true the day upstream ships one. An entry has to say what would
     make somebody look again, whether that is an event ("a patched release
     ships") or a date (`Review-By: 2026-12-01`).
  3. Registration. A vulnerability id must also appear in SECURITY.md or
     SECURITY_ALERT_REGISTER.md, so the suppression and the accepted-risk
     register cannot disagree about what the platform has accepted. This
     mirrors the census's rule exactly: an unrecorded accepted risk is an
     ignored one. Non-vulnerability ids -- Trivy's own misconfiguration checks
     like `KSV118` -- are exempt, because the register is for vulnerabilities.
  4. A live review date. `Review-By:` in the past is a lapsed suppression, and
     a lapsed suppression is an undated one.

WHAT IT DOES NOT DO

It does not ask upstream whether a fix has shipped. `--check-upstream` does
that against the OSV API, and it is opt-in rather than part of the gate,
because a gate whose verdict depends on a third party's uptime fails for
reasons that have nothing to do with the tree. Run it on a schedule, not on
every pull request.

Usage:
    python scripts/check_trivyignore_governance.py                  # the gate
    python scripts/check_trivyignore_governance.py --check-upstream # ask OSV
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import urllib.error
import urllib.request

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TRIVYIGNORE = os.path.join(REPO_ROOT, ".trivyignore")
REGISTERS = ("SECURITY.md", "SECURITY_ALERT_REGISTER.md")

# Ids that name a VULNERABILITY, as opposed to one of Trivy's own
# misconfiguration or secret checks (KSV118, AVD-AWS-0107, ...). Only the
# former belong in the accepted-risk register.
VULN_ID = re.compile(r"^(?:CVE|GHSA|PYSEC|OSV|GO|RUSTSEC|TEMP)[-:]", re.IGNORECASE)

# The strict form of an advisory id, used before one is interpolated into a
# URL. VULN_ID above only checks the PREFIX, which `CVE-../../x` also satisfies.
SAFE_ID = re.compile(r"^[A-Za-z]+-[A-Za-z0-9._-]+$")

# The LABEL, whatever follows it. Used to catch a Review-By whose value is not
# a date at all; REVIEW_BY below only matches a well-formed one.
REVIEW_BY_LABEL = re.compile(r"Review-By:", re.IGNORECASE)

REVIEW_BY = re.compile(r"Review-By:\s*(\d{4}-\d{2}-\d{2})", re.IGNORECASE)

# Words that make a comment block a re-check trigger rather than a description.
# Deliberately broad: the point is that somebody wrote down what would make
# them look again, not that they used a particular phrase.
TRIGGER_WORDS = (
    "re-check",
    "recheck",
    "re-evaluate",
    "reevaluate",
    "review-by",
    "review periodically",
    "revisit",
    "drop this ignore",
    "until",
)

OSV_API = "https://api.osv.dev/v1/vulns/"


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def parse_entries(text: str) -> list[tuple[int, str, list[str]]]:
    """[(line number, id, the comment block directly above it)].

    The block is the run of contiguous comment lines immediately preceding the
    entry, which is how a reader attributes a justification to an id and how
    the existing file is already written.
    """
    entries: list[tuple[int, str, list[str]]] = []
    block: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            block = []
            continue
        if line.startswith("#"):
            block.append(line.lstrip("#").strip())
            continue
        entries.append((number, line, list(block)))
        block = []
    return entries


def _registered_ids() -> set[str]:
    """Every id named anywhere in the accepted-risk registers, uppercased."""
    found: set[str] = set()
    for name in REGISTERS:
        path = os.path.join(REPO_ROOT, name)
        try:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
        except OSError:
            continue
        found.update(
            match.upper()
            # Same prefixes as VULN_ID. They were two lists and drifted: VULN_ID
            # required a TEMP- id to be registered and this could never find one,
            # so every valid TEMP suppression would have been rejected.
            for match in re.findall(r"\b(?:CVE|GHSA|PYSEC|OSV|GO|RUSTSEC|TEMP)[-:][\w.-]+", text)
        )
    return found


def _justification_problems(number: int, entry: str, block: list[str]) -> list[str]:
    prose = " ".join(block)
    problems: list[str] = []

    # A block that only repeats the id says nothing. Strip the id out and see
    # whether any words are left.
    without_id = prose.replace(entry, " ")
    if len(without_id.split()) < 8:
        problems.append(
            f".trivyignore:{number} suppresses {entry} with no justification — a bare "
            "id silences a real finding in three scanners with no record of who "
            "decided or why"
        )
        return problems

    lowered = prose.lower()
    if not any(word in lowered for word in TRIGGER_WORDS):
        problems.append(
            f".trivyignore:{number} suppresses {entry} with no re-check trigger — say "
            "what would make somebody look again (an event, or `Review-By: YYYY-MM-DD`); "
            "'no fixed version exists' stops being true the day one ships"
        )

    # A malformed value satisfies the trigger check (the words "Review-By" are
    # present) and then never reaches the date check, so `Review-By: soon` and
    # `Review-By:` both read as a dated suppression that is not one.
    if REVIEW_BY_LABEL.search(prose) and not REVIEW_BY.search(prose):
        problems.append(
            f".trivyignore:{number} has a Review-By for {entry} that is not an ISO date "
            "(YYYY-MM-DD) — a date nothing can compare is not a review date"
        )
    match = REVIEW_BY.search(prose)
    if match:
        try:
            due = dt.date.fromisoformat(match.group(1))
        except ValueError:
            problems.append(f".trivyignore:{number} has an unparseable Review-By date for {entry}")
        else:
            if due < dt.date.today():
                problems.append(
                    f".trivyignore:{number} suppresses {entry} past its Review-By date "
                    f"({due.isoformat()}) — a lapsed suppression is an undated one"
                )
    return problems


def check(text: str, registered: set[str]) -> list[str]:
    problems: list[str] = []
    seen: dict[str, int] = {}
    for number, entry, block in parse_entries(text):
        if entry in seen:
            problems.append(
                f".trivyignore:{number} repeats {entry}, already suppressed at line "
                f"{seen[entry]} — two justifications for one id means one of them is "
                "not the reason it is suppressed"
            )
        seen[entry] = number

        problems.extend(_justification_problems(number, entry, block))

        if VULN_ID.match(entry) and entry.upper() not in registered:
            problems.append(
                f".trivyignore:{number} suppresses {entry}, which is not named in "
                f"{' or '.join(REGISTERS)} — the suppression file and the accepted-risk "
                "register would then disagree about what the platform has accepted, and "
                "an unrecorded accepted risk is an ignored one"
            )
    return problems


def upstream_fixed(entry: str, timeout: int = 15) -> tuple[bool, str]:
    """Has a fixed version shipped for this id since it was suppressed?

    Returns (fixed, note). An unreachable API returns `(False, why)` rather
    than raising: this runs on a schedule against somebody else's service, and
    a network blip is not a finding.
    """
    if not VULN_ID.match(entry):
        return False, "not a vulnerability id"
    # The id is interpolated into a URL, so its SHAPE is checked here rather
    # than trusted from VULN_ID's prefix match alone: `CVE-../../something`
    # satisfies that prefix and would walk the path. Anything but the strict
    # form is refused, and the built URL is re-checked against the API prefix
    # so no entry can redirect the request somewhere else entirely.
    if not SAFE_ID.match(entry):
        return False, "id is not in a form safe to query"
    url = OSV_API + entry
    if not url.startswith(OSV_API):  # pragma: no cover - defensive
        return False, "constructed URL left the OSV API prefix"
    try:
        # The rule fires on any non-literal URL because urllib honours
        # `file://`. It cannot be one here: the constant prefix is
        # `https://api.osv.dev/v1/vulns/`, the only variable part is an id that
        # SAFE_ID has already restricted to `[A-Za-z]+-[A-Za-z0-9._-]+`, and the
        # assembled string is re-checked against that prefix above. There is no
        # input that reaches this line able to change the scheme.
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, ValueError, OSError) as exc:
        return False, f"OSV unreachable ({type(exc).__name__})"
    # Valid JSON is not the expected JSON. OSV returning an object where a list
    # belongs would raise here, and a scheduled job that crashes on somebody
    # else's response shape reports nothing about our suppressions.
    if not isinstance(data, dict):
        return False, "OSV returned a payload that is not an object"
    for affected in data.get("affected") or []:
        if not isinstance(affected, dict):
            continue
        for entry_range in affected.get("ranges") or []:
            if not isinstance(entry_range, dict):
                continue
            # GIT ranges name a COMMIT, not a release. A fix that exists only
            # as a commit is not a version anybody can pin, and reporting it as
            # "FIX AVAILABLE" sends a reader looking for a release that has not
            # shipped. Both of this tree's suppressions that claim "no fixed
            # version exists" have a GIT-range fix in OSV and are still correct.
            if str(entry_range.get("type", "")).upper() == "GIT":
                continue
            for event in entry_range.get("events") or []:
                if isinstance(event, dict) and event.get("fixed"):
                    package_info = affected.get("package")
                    package_info = package_info if isinstance(package_info, dict) else {}
                    package = package_info.get("name", "?")
                    ecosystem = package_info.get("ecosystem", "?")
                    return True, f"{ecosystem}/{package} fixed in {event['fixed']}"
    return False, "no fixed RELEASE published (a commit-only fix does not count)"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-upstream",
        action="store_true",
        help="ask OSV whether a fix has shipped (network; not part of the gate)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    try:
        with open(TRIVYIGNORE, encoding="utf-8") as handle:
            text = handle.read()
    except OSError as exc:
        _fail(f".trivyignore could not be read ({exc.__class__.__name__})")
        return 1

    entries = parse_entries(text)
    problems = check(text, _registered_ids())

    print(f"Trivy suppressions: {len(entries)}")
    for number, entry, _block in entries:
        print(f"  .trivyignore:{number:<3} {entry}")

    expired: list[str] = []
    if args.check_upstream:
        print("\nUpstream check (OSV):")
        for _number, entry, _block in entries:
            fixed, note = upstream_fixed(entry)
            marker = "FIX AVAILABLE" if fixed else "still suppressed"
            print(f"  {entry:<20} {marker:<15} {note}")
            if fixed:
                expired.append(
                    f"{entry} is suppressed but a fixed release has shipped ({note}) — "
                    "take the fix, or rewrite the entry to say why the published fix "
                    "does not apply here"
                )

    # An expired suppression FAILS. Printing it to a scheduled job's stdout and
    # exiting 0 is the pattern this whole checker exists to reject: the job's
    # sole purpose is surfacing suppressions whose reason has expired, and a
    # green run surfaces nothing. An unreachable OSV is deliberately NOT a
    # failure -- `upstream_fixed` distinguishes the two -- because a job whose
    # verdict depends on somebody else's uptime goes red for reasons unrelated
    # to this repository.
    problems += expired

    if problems:
        print()
        for problem in problems:
            _fail(problem)
        print(
            "\nTrivy suppression governance: FAILED — a suppression without a written "
            "reason and a re-check trigger is a vulnerability the platform has stopped "
            "looking at rather than one it has accepted.",
            file=sys.stderr,
        )
        return 1
    print("\nTrivy suppression governance: PASSED — every entry is justified and registered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
