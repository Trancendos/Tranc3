"""A verdict must not outlive the moment it was measured.

Every case here is drawn from the state this estate was actually in on
2026-10-13, when nine open pull requests reported a green Production merge
gate dated inside one forty-five-minute window on 2026-10-05 -- eight days
earlier, and before the seventeen advisories that landed in between. Seven of
them also reported `mergeable_state: clean`.

Nothing was wrong with those check-runs. They were true when they ran. The
defect was that nothing in the estate could tell the difference between a pass
earned an hour ago and one earned eight days ago, so the tests below pin that
difference rather than the arithmetic.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from src.immune.verdict import (
    DEFAULT_TTL_HOURS,
    LIVE,
    STALE,
    UNKNOWN,
    Verdict,
    VerdictReport,
    load_verdict,
)

NOW = datetime(2026, 10, 13, 12, 0, 0, tzinfo=timezone.utc)

#: The real timestamp of main's own Production merge gate green, and the real
#: moment it was read. Eight days is not a hypothetical in this test file.
MAIN_GATE_GREEN = "2026-10-05T18:59:40Z"


def _verdict(**kw) -> Verdict:
    base = dict(name="vulnerability-census", outcome="pass", measured_at=MAIN_GATE_GREEN)
    base.update(kw)
    return Verdict(**base)


# ---------------------------------------------------------------------------
# The measurement this module exists for.
# ---------------------------------------------------------------------------


def test_mains_own_eight_day_old_green_does_not_count_as_a_pass():
    """REGRESSION: the exact state nine pull requests were in.

    `outcome` is a genuine `pass` and the check-run really was green. The
    verdict still must not authorise anything, because it answers for a feed
    read eight days earlier.
    """
    v = _verdict()
    assert v.outcome == "pass"
    assert v.freshness(NOW) == STALE
    assert v.counts_as_pass(NOW) is False
    age = v.age(NOW)
    assert age is not None and age > timedelta(days=7), age


def test_a_green_measured_an_hour_ago_does_count():
    """The other half: freshness must not become a way to refuse everything."""
    recent = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    v = _verdict(measured_at=recent)
    assert v.freshness(NOW) == LIVE
    assert v.counts_as_pass(NOW) is True


def test_the_ttl_boundary_is_inclusive_and_defaults_to_the_estates_own_interval():
    """24h is not invented here -- supply-chain-watch.yml already states it."""
    assert DEFAULT_TTL_HOURS == 24
    exactly = (NOW - timedelta(hours=24)).isoformat().replace("+00:00", "Z")
    just_over = (NOW - timedelta(hours=24, seconds=1)).isoformat().replace("+00:00", "Z")
    assert _verdict(measured_at=exactly).freshness(NOW) == LIVE
    assert _verdict(measured_at=just_over).freshness(NOW) == STALE


# ---------------------------------------------------------------------------
# Failing closed. Each of these would be a way to smuggle a pass through.
# ---------------------------------------------------------------------------


def test_a_verdict_with_no_timestamp_is_unknown_not_live():
    v = _verdict(measured_at="")
    assert v.freshness(NOW) == UNKNOWN
    assert v.counts_as_pass(NOW) is False
    assert any("measured_at" in d for d in v.defects())


def test_an_unparseable_timestamp_is_unknown_not_live():
    """`memory.py`: an unparseable date cannot be trusted to be future."""
    for bad in ("yesterday", "2026-13-45T99:99:99Z", "1760000000", "2026/10/05 18:59"):
        v = _verdict(measured_at=bad)
        assert v.freshness(NOW) == UNKNOWN, bad
        assert v.counts_as_pass(NOW) is False, bad


def test_a_timestamp_in_the_future_is_unknown_not_live():
    """A verdict resting on a clock nobody can reconcile is not live.

    This is the one case where the naive reading -- "newer than the TTL, so
    fresh" -- is actively wrong, and it is reachable: a runner with a skewed
    clock produces exactly this.
    """
    ahead = (NOW + timedelta(hours=6)).isoformat().replace("+00:00", "Z")
    v = _verdict(measured_at=ahead)
    assert v.freshness(NOW) == UNKNOWN
    assert v.counts_as_pass(NOW) is False


def test_a_non_positive_ttl_is_reported_as_a_defect():
    """Otherwise nothing is ever live and the gate silently refuses everything."""
    assert any("ttl_hours" in d for d in _verdict(ttl_hours=0).defects())
    assert any("ttl_hours" in d for d in _verdict(ttl_hours=-1).defects())


def test_a_fail_never_counts_as_a_pass_however_fresh():
    recent = (NOW - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
    v = _verdict(outcome="fail", measured_at=recent)
    assert v.freshness(NOW) == LIVE
    assert v.counts_as_pass(NOW) is False


def test_naive_timestamps_are_read_as_utc_rather_than_refused():
    """Every producer here writes UTC; refusing it would fail closed on a
    verdict that is underspecified rather than untrustworthy."""
    naive = (NOW - timedelta(hours=2)).replace(tzinfo=None).isoformat()
    assert _verdict(measured_at=naive).freshness(NOW) == LIVE


# ---------------------------------------------------------------------------
# Reading a real census output.
# ---------------------------------------------------------------------------


def test_a_census_that_could_not_scan_is_unknown_not_fail():
    """A registry outage is not a vulnerability.

    Conflating them is how a transient network error comes to read as a
    security finding -- and `supply-chain-watch.yml` notes the inverse risk,
    that an outage would redden a pull request touching no dependency at all.
    """
    v = Verdict.from_census(
        {"scanned_ok": False, "fixable_count": 0, "generated_at": MAIN_GATE_GREEN}
    )
    assert v.outcome == UNKNOWN
    assert v.counts_as_pass(NOW) is False


def test_a_census_with_fixable_findings_is_a_fail():
    v = Verdict.from_census(
        {"scanned_ok": True, "fixable_count": 17, "generated_at": MAIN_GATE_GREEN}
    )
    assert v.outcome == "fail"


def test_a_clean_census_is_a_pass_and_carries_its_commit():
    v = Verdict.from_census(
        {
            "scanned_ok": True,
            "fixable_count": 0,
            "generated_at": MAIN_GATE_GREEN,
            "commit": "2c8549e7b8424f74aeeee047753aef7de312b50b",
        }
    )
    assert v.outcome == "pass"
    # The WHOLE sha. `startswith` would still pass if `subject` were
    # truncated to eight characters, and a caller publishing a commit
    # status needs the full value.
    assert v.subject == "2c8549e7b8424f74aeeee047753aef7de312b50b"


def test_an_absent_census_file_is_unknown(tmp_path):
    """The census output is generated in CI and not committed, so absent is an
    ordinary local state and must read as neither answer."""
    v = load_verdict(tmp_path / "nope.json")
    assert v.outcome == UNKNOWN
    assert v.counts_as_pass(NOW) is False


def test_an_unreadable_census_file_is_unknown(tmp_path):
    p = tmp_path / "census.json"
    p.write_text("{not json", encoding="utf-8")
    assert load_verdict(p).outcome == UNKNOWN
    p.write_text(json.dumps(["a", "list"]), encoding="utf-8")
    assert load_verdict(p).outcome == UNKNOWN


# ---------------------------------------------------------------------------
# The report, and the empty-gate case.
# ---------------------------------------------------------------------------


def test_an_empty_report_does_not_hold():
    """REGRESSION for the `supply-chain-watch` shape.

    That workflow reported `success` for a Monday run that skipped the
    vulnerability census entirely -- a green meaning "the job did not run".
    A report with no verdicts in it is the same claim, so it must not hold.
    """
    assert VerdictReport(verdicts=[], checked_at=NOW).holds is False


def test_a_report_holds_only_when_every_verdict_is_a_live_pass():
    recent = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    live = _verdict(measured_at=recent)
    stale = _verdict()
    assert VerdictReport(verdicts=[live], checked_at=NOW).holds is True
    assert VerdictReport(verdicts=[live, stale], checked_at=NOW).holds is False


def test_the_report_separates_stale_from_unknown():
    """`grade.py` already distinguishes "did not look" from "looked and fine";
    the report must not collapse them back together."""
    report = VerdictReport(
        verdicts=[_verdict(), _verdict(measured_at="")],
        checked_at=NOW,
    )
    assert len(report.stale) == 1
    assert len(report.unknown) == 1


def test_explain_states_the_age_a_reader_needs():
    line = _verdict().explain(NOW)
    assert "does NOT count as a pass" in line
    assert "stale" in line
    assert "days old" in line


# ---------------------------------------------------------------------------
# Fail-closed gaps found in review. Five independent reviewers converged on
# most of these, and every one of them was a path to a pass nothing earned.
# ---------------------------------------------------------------------------


def test_a_date_with_no_time_is_not_an_instant():
    """`fromisoformat("2026-10-13")` succeeds and yields midnight, so a bare
    date would read as measured at 00:00 -- up to a day from the truth, and
    silently. Freshness is the whole subject, so it must not be guessed."""
    v = _verdict(measured_at="2026-10-13")
    assert v.freshness(NOW) == UNKNOWN
    assert v.counts_as_pass(NOW) is False
    assert any("measured_at" in d for d in v.defects())


def test_an_explicit_zero_ttl_survives_to_be_reported():
    """REGRESSION: `float(data.get("ttl_hours") or DEFAULT)` turned an explicit
    0 into 24, because `0 or 24 == 24`. Zero is the one TTL this module
    promises to fail closed on, and the likeliest malformed value."""
    v = Verdict.from_mapping({"name": "x", "outcome": "pass", "ttl_hours": 0})
    assert v.ttl_hours == 0
    assert any("ttl_hours" in d for d in v.defects())
    assert Verdict.from_mapping({"name": "x"}).ttl_hours == DEFAULT_TTL_HOURS
    assert Verdict.from_mapping({"name": "x", "ttl_hours": None}).ttl_hours == DEFAULT_TTL_HOURS


def test_a_zero_ttl_is_not_live_even_at_age_zero():
    """REGRESSION: `age <= timedelta(hours=0)` is True at age exactly zero, so
    a verdict `defects()` already called unusable still counted as a pass."""
    exactly_now = NOW.isoformat().replace("+00:00", "Z")
    v = _verdict(measured_at=exactly_now, ttl_hours=0)
    assert v.freshness(NOW) == UNKNOWN
    assert v.counts_as_pass(NOW) is False


@pytest.mark.parametrize("ttl", [float("nan"), float("inf"), float("-inf")])
def test_a_non_finite_ttl_is_unknown_rather_than_an_exception(ttl):
    """`timedelta(hours=nan)` raises ValueError and `inf` raises OverflowError.
    A freshness check that throws takes the gate step down instead of
    answering it, which is strictly worse than reporting it cannot tell."""
    v = _verdict(ttl_hours=ttl)
    assert v.freshness(NOW) == UNKNOWN
    assert v.counts_as_pass(NOW) is False
    assert any("ttl_hours" in d for d in v.defects())


@pytest.mark.parametrize("bad", [False, True, "0", "3", 0.5, -1, None, [], {}])
def test_a_fixable_count_that_is_not_a_count_is_unknown(bad):
    """REGRESSION: `int(fixable)` accepted three values that became a PASS no
    clean scan had earned -- `False` (int 0), `"0"`, and `0.5` (truncated).
    `isinstance(True, int)` is True in Python, which is why bool is excluded
    explicitly rather than assumed away."""
    v = Verdict.from_census(
        {"scanned_ok": True, "fixable_count": bad, "generated_at": MAIN_GATE_GREEN}
    )
    assert v.outcome == UNKNOWN, f"{bad!r} must not produce a pass or a fail"


def test_a_real_integer_count_still_works():
    """The other half: this must not refuse every valid census."""
    base = {"scanned_ok": True, "generated_at": MAIN_GATE_GREEN}
    assert Verdict.from_census({**base, "fixable_count": 0}).outcome == "pass"
    assert Verdict.from_census({**base, "fixable_count": 17}).outcome == "fail"


def test_a_report_does_not_hold_on_a_verdict_with_defects():
    """A fresh pass with no name passed `counts_as_pass` while `defects()`
    called it unusable, so a caller could report success for a gate nothing
    could identify."""
    recent = (NOW - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    nameless = Verdict(name="", outcome="pass", measured_at=recent)
    assert nameless.counts_as_pass(NOW) is True, "the old predicate still passes it"
    assert nameless.defects(), "but it is unusable"
    assert VerdictReport(verdicts=[nameless], checked_at=NOW).holds is False


def test_the_census_producer_writes_the_commit_the_verdict_reads():
    """REGRESSION: `from_census` read a `commit` key `build_census()` never
    wrote, so `subject` was always empty in every real run and the test
    covering it fabricated the key -- pinning an interface nothing produced.
    This asserts the two ends agree, by reading the producer."""
    import importlib.util
    import sys as _sys
    from pathlib import Path as _Path

    spec = importlib.util.spec_from_file_location(
        "_census_for_test", _Path(__file__).resolve().parents[1] / "scripts/vulnerability_census.py"
    )
    assert spec and spec.loader
    census = importlib.util.module_from_spec(spec)
    _sys.modules[spec.name] = census
    spec.loader.exec_module(census)

    head = census._scanned_head()
    assert head, "the census must record the head it scanned"
    v = Verdict.from_census(
        {"scanned_ok": True, "fixable_count": 0, "generated_at": MAIN_GATE_GREEN, "commit": head}
    )
    assert v.subject == head, "the full sha, not a prefix -- callers need the whole thing"
