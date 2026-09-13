"""The premise guard must read a Disposition row the way the census does.

`scripts/check_disposition_premises.py` decides whether to enforce an entry's
premises by reading its Disposition row. An earlier version restated
`ACCEPTING_DISPOSITIONS` and hand-rolled a parser beside the canonical one,
with a comment claiming the two "cannot disagree" -- and the parser was wrong
in the one way that matters:

    cells[1].strip("* ").split()[0]

`str.strip` removes the listed characters from BOTH ends, so it ate the leading
`**` and left the trailing one glued to whatever came next:

    "**SUPPRESS** - no patched release exists"        -> "SUPPRESS**"
    "**ACCEPT** - **RETIRED** (upstream fix landed)"  -> "ACCEPT**"

Neither is in ACCEPTING_DISPOSITIONS, so a live SUPPRESS carrying its reason on
the same row would have read as closed, its premise checks would have been
skipped, and the gate would have printed PASSED. The second line is the exact
row shape behind the SEC-005 defect -- read the wrong way round by the guard
written to prevent it. Both raised by cubic.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

import check_disposition_premises as guard  # noqa: E402

from src.security import accepted_risk_register  # noqa: E402


def _register(tmp_path: Path, disposition: str) -> Path:
    path = tmp_path / "REG.md"
    path.write_text(
        f"### SEC-007 — a finding\n\n"
        f"| Field | Value |\n|---|---|\n"
        f"| **Disposition** | {disposition} |\n"
        f"| **ID** | GHSA-px8p-9vwx-vf98 |\n",
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    "row, expected",
    [
        ("**ACCEPT**", "ACCEPT"),
        ("**SUPPRESS**", "SUPPRESS"),
        ("**RESOLVED**", "RESOLVED"),
        # The two shapes the hand-rolled parser got wrong.
        ("**SUPPRESS** — no patched release exists", "SUPPRESS"),
        ("**ACCEPT** — **RETIRED** (upstream fix landed)", "ACCEPT"),
        # Shapes the live register actually uses.
        ("**FIX** ×2 — one reported, one found by reading around it", "FIX"),
        ("**FP (scanner limitation)**, plus one real correction", "FP"),
    ],
)
def test_the_first_word_is_read_whatever_follows_it(tmp_path, row, expected):
    assert guard.disposition_of("SEC-007", _register(tmp_path, row)) == expected


def test_the_guard_and_the_census_share_one_disposition_vocabulary():
    """Not two tuples that agree today -- literally the same object."""
    assert guard._ACCEPTING is accepted_risk_register.ACCEPTING_DISPOSITIONS


def test_every_disposition_in_the_live_register_is_recognised():
    """An unknown word disables an entry's premise checks, so none may exist."""
    text = (REPO / "SECURITY_ALERT_REGISTER.md").read_text(encoding="utf-8")
    known = (*guard._ACCEPTING, *guard._CLOSING)

    unknown = []
    for entry in accepted_risk_register._entries(text):
        match = accepted_risk_register._DISPOSITION_ROW.search(entry)
        if match and match.group(1).upper() not in known:
            unknown.append((entry.splitlines()[0].strip()[:40], match.group(1)))

    assert not unknown, f"unrecognised dispositions {unknown}; known: {known}"


def test_a_suppress_carrying_its_reason_is_still_enforced(tmp_path, monkeypatch):
    """The regression itself: prose after the word must not close the entry."""
    register = _register(tmp_path, "**SUPPRESS** — no patched release exists")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "REGISTER", register.name)

    enforce, failures = guard.still_accepting("SEC-007")
    assert enforce, "a live SUPPRESS with a reason must still be enforced"
    assert failures == []


def test_an_unrecognised_disposition_fails_rather_than_reading_as_closed(tmp_path, monkeypatch):
    """Fail closed: a typo must not silently disable a premise check."""
    register = _register(tmp_path, "**RESOLVEDD**")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "REGISTER", register.name)

    enforce, failures = guard.still_accepting("SEC-007")
    assert not enforce
    assert failures and "unrecognised Disposition" in failures[0]


def test_a_closed_entry_is_not_enforced(tmp_path, monkeypatch):
    """The other half: a genuinely closed entry must stop being enforced."""
    register = _register(tmp_path, "**RESOLVED**")
    monkeypatch.setattr(guard, "ROOT", tmp_path)
    monkeypatch.setattr(guard, "REGISTER", register.name)

    enforce, failures = guard.still_accepting("SEC-007")
    assert not enforce
    assert failures == []
