"""One reading of the accepted-risk register, for every control that consults it.

WHY THIS EXISTS

Two gates asked the same question — "is this advisory a knowingly carried
risk?" — and answered it two different ways.

`scripts/vulnerability_census.py` scoped it properly: split
`SECURITY_ALERT_REGISTER.md` per `### SEC-NNN` entry, take that entry's ids
ONLY when its own Disposition row says ACCEPT or SUPPRESS, and read
`SECURITY.md` only inside its accepted-risk table.

`scripts/check_trivyignore_governance.py` grepped both files whole. Any id
mentioned anywhere counted as registered — including ids in FIX entries, which
record a vulnerability that WAS remediated. A `.trivyignore` suppression naming
one of those passed governance on a decision nobody had made about it. The
register itself carries such ids today, so this was reachable, not theoretical.

Two parsers for one question drift, and the weaker one is the one an attacker
or an accident meets. There is now one.

WHAT COUNTS, AND WHAT DOES NOT

The register records four dispositions and only two of them mean the risk is
knowingly carried:

  ACCEPT / SUPPRESS  the risk is carried on purpose — registered.
  FIX                it was remediated. If the same id resurfaces as unfixable
                     later, matching it against that historical note would
                     silence a live finding using a decision about a different
                     situation.
  FP                 the scanner was wrong once. That says nothing about the
                     next time the same id is raised somewhere else.

`blocked` is narrower still and is deliberately NOT inferred from membership:
it means a patched release exists and something upstream puts it out of reach,
which has to be written down as a `Blocked-by` row. Inferring it from the
register was a real defect once — an entry suppressed for want of any patch
would have flipped to `blocked` the day upstream shipped one, so the gate
would start passing at the exact moment it should start failing.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, Set

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REGISTER = "SECURITY_ALERT_REGISTER.md"
SECURITY = "SECURITY.md"

#: Advisory id shapes. Broader than the census's original CVE/GHSA/PYSEC set
#: because the census now scans Go and Rust, whose advisories arrive as `GO-`
#: and `RUSTSEC-` ids: an entry dispositioned under one of those would
#: otherwise read as undocumented and fail the gate over a decision that had
#: been made. `TEMP-` is this estate's own placeholder for an advisory with no
#: upstream id yet.
ID_PATTERN = re.compile(
    r"\b(?:CVE-\d{4}-\d+|GHSA-[\w-]+|PYSEC-\d{4}-\d+|GO-\d{4}-\d+|RUSTSEC-\d{4}-\d+"
    r"|OSV-\d{4}-\d+|TEMP-\d{4}-\d+)\b",
    re.IGNORECASE,
)

#: Only these mean "knowingly carried".
ACCEPTING_DISPOSITIONS = ("ACCEPT", "SUPPRESS")

#: The header row of SECURITY.md's accepted-risk table. Rows beneath it are
#: accepted by construction; ids elsewhere in that file are prose.
ACCEPTED_TABLE_HEADER = re.compile(r"^\|\s*Package\s*\|\s*Finding\s*\|", re.I)

_DISPOSITION_ROW = re.compile(r"\|\s*\*\*Disposition\*\*\s*\|\s*\*?\*?(\w+)")
_BLOCKED_BY_ROW = re.compile(r"\|\s*\*\*Blocked-by\*\*\s*\|")
_SUPPRESSED_IN_ROW = re.compile(r"\|\s*\*\*Suppressed-in\*\*\s*\|")


def _read(path: str) -> str:
    try:
        with open(os.path.join(REPO_ROOT, path), encoding="utf-8", errors="replace") as handle:
            return handle.read()
    except OSError:
        return ""


def _entries(text: str) -> Iterable[str]:
    """Each `### SEC-NNN` block, so a disposition cannot leak across entries."""
    return re.split(r"^### ", text, flags=re.M)[1:]


def registered_ids(register: str = REGISTER, security: str = SECURITY) -> Set[str]:
    """Advisory ids carrying an explicit ACCEPT or SUPPRESS decision, uppercased.

    Deliberately not "every id mentioned in the security docs" — see the module
    docstring for what that let through.
    """
    ids: Set[str] = set()

    for block in _entries(_read(register)):
        disposition = _DISPOSITION_ROW.search(block)
        if disposition and disposition.group(1).upper() in ACCEPTING_DISPOSITIONS:
            ids.update(match.upper() for match in ID_PATTERN.findall(block))

    in_table = False
    for line in _read(security).splitlines():
        if ACCEPTED_TABLE_HEADER.match(line):
            in_table = True
            continue
        if not in_table:
            continue
        if not line.lstrip().startswith("|"):
            in_table = False
            continue
        if set(line.replace("|", "").strip()) <= {"-", " ", ":"}:
            continue  # separator row
        ids.update(match.upper() for match in ID_PATTERN.findall(line))

    return ids


def suppression_licensed_ids(register: str = REGISTER, security: str = SECURITY) -> Set[str]:
    """Ids a `.trivyignore` line may legitimately silence.

    Wider than `registered_ids` by exactly one written-down case, and the case
    is real: SEC-001 pins `sentencepiece==0.2.1`, which IS the patched release,
    and Trivy keeps reporting the advisory because its database has not
    recorded 0.2.1 as the fix. The vulnerability is remediated — `FIX` is the
    honest disposition — while a residual SCANNER finding still has to be
    silenced.

    Those are two different facts about two different things, and collapsing
    them either way loses one. Forcing the entry to `SUPPRESS` would claim the
    vulnerability is carried when it is fixed; letting any `FIX` id license a
    suppression would put every remediated advisory back in scope, which is the
    fail-open this whole module exists to close.

    So it is written down, per entry, as a `Suppressed-in` row naming where the
    suppression lives — the same shape as `Blocked-by`, and for the same
    reason: a state that changes a gate's verdict has to be stated, not
    inferred.
    """
    ids = registered_ids(register, security)
    for block in _entries(_read(register)):
        if _SUPPRESSED_IN_ROW.search(block):
            ids.update(match.upper() for match in ID_PATTERN.findall(block))
    return ids


def blocked_ids(register: str = REGISTER) -> Set[str]:
    """Ids an entry explicitly marks unreachable behind an upstream pin.

    Strictly narrower than `registered_ids`, and written down rather than
    inferred — the module docstring records why inferring it inverted a gate.
    """
    ids: Set[str] = set()
    for block in _entries(_read(register)):
        if _BLOCKED_BY_ROW.search(block):
            ids.update(match.upper() for match in ID_PATTERN.findall(block))
    return ids
