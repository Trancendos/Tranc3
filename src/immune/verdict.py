"""Verdicts: a pass is a claim about a moment, and moments end.

WHY THIS EXISTS
---------------
`memory.py` gave adjudications an expiry because a decision nobody revisits is
a leak. The same argument applies with more force one layer up, to the
*verdicts* this estate gates merges on -- and there it had never been made.

The Production merge gate runs `scripts/vulnerability_census.py`, which reads a
LIVE advisory feed. Its answer is therefore a statement about the feed at the
moment it ran. GitHub records that answer as a check-run conclusion on a commit
and a required check is satisfied by any green on the head commit, however old.
When the head stops moving, the green stops being re-earned -- and nothing
anywhere notices that it has aged out of being true.

Measured on 2026-10-13, nine open pull requests were in exactly that state:

    main        Production merge gate  success  2026-10-05T18:59:40Z
    #1372       Production merge gate  success  2026-10-05T19:10:37Z
    #1370       Production merge gate  success  2026-10-05T18:45:16Z
    #1369  ..   Production merge gate  success  2026-10-05T18:35:51Z
    #1365       Production merge gate  success  2026-10-05T18:27:19Z
    #1364       Production merge gate  success  2026-10-05T18:24:53Z
    #1288       Production merge gate  success  2026-10-05T18:40:31Z
    #1271       Production merge gate  success  2026-10-05T18:30:52Z
    #1208       Production merge gate  success  2026-10-05T18:27:11Z

Every one inside a forty-five-minute window on a single day, eight days before
they were read, and all of them predating the seventeen advisories that landed
afterwards. Seven of those pull requests also reported `mergeable_state: clean`.
For that queue, "clean, with a green required check" was a statement about
2026-10-05 and nothing else, and anything merged on it would have been merged
on last week's measurement.

WHY A VERDICT EXPIRES HARDER THAN AN ADJUDICATION
-------------------------------------------------
`memory.py` makes an expired adjudication keep suppressing, so that nobody
wakes to a wall of red, and reports it every run until a human renews it. That
is right for a suppression and wrong for a pass, and the asymmetry is the whole
design:

  * An expired SUPPRESSION, left in force, delays a fix.
  * An expired PASS, left in force, authorises a merge.

One costs time; the other ships. So a stale verdict does not stay a pass here.
It degrades to `unknown` -- which `grade.py` already treats as "the estate did
not look", distinct from "the estate looked and it was fine". That distinction
is the immune system's founding rule, and this module is that rule applied to
the gate itself rather than only to the scanners underneath it.

WHY TWENTY-FOUR HOURS
---------------------
The default TTL is not invented here. `.github/workflows/supply-chain-watch.yml`
already states the estate's own interval and its reason: under CRA Art. 14(1)
an actively exploited vulnerability must be notified within 24 hours of
becoming aware of it, so the intake that feeds it runs daily. A census answer
older than the interval the estate committed to re-measuring on is, by the
estate's own standard, no longer current. Callers may pass a shorter TTL; a
longer one is a decision that should be written down where it is made.

WHAT FAILS CLOSED
-----------------
A verdict with no timestamp, an unparseable timestamp, or a timestamp in the
future is `unknown`, never `live`. `memory.py` reached the same conclusion for
adjudication dates -- "an unparseable date cannot be trusted to be future" --
and the reasoning carries: a verdict that cannot say when it was measured has
not established that it was measured recently, and guessing in its favour is
the defect this module exists to remove.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

#: The estate's own re-measurement interval, from supply-chain-watch.yml and
#: MC-045 in the Magna Carta register. See WHY TWENTY-FOUR HOURS above.
DEFAULT_TTL_HOURS = 24

#: Freshness states. Deliberately three, not two: "I could not tell" is not
#: "it is fine", which is the same split `sensors.Outcome` draws.
LIVE = "live"
STALE = "stale"
UNKNOWN = "unknown"


def _usable_ttl(hours: float) -> bool:
    """Whether a TTL can be compared against an age at all.

    Positive and finite. Separated out because three places need the same
    answer -- `freshness`, `defects` and the report -- and they disagreed
    before: `defects()` reported a non-positive TTL while `freshness()` still
    returned LIVE for a zero TTL at age zero, so the gate held on a verdict the
    module had already called unusable.
    """
    return math.isfinite(hours) and hours > 0


def _is_count(value: Any) -> bool:
    """A non-negative integer, with `bool` excluded deliberately.

    `isinstance(True, int)` is True in Python, so `fixable_count: false` would
    otherwise read as zero findings -- a clean scan conjured from a malformed
    field.
    """
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _parse_instant(text: str) -> datetime | None:
    """An ISO-8601 instant, or None when it cannot be read as one.

    Accepts the trailing `Z` that `vulnerability_census.py` writes, which
    `datetime.fromisoformat` rejects before Python 3.11.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    if raw.endswith(("Z", "z")):
        raw = raw[:-1] + "+00:00"
    # A date with no time is not an instant. `fromisoformat("2026-10-13")`
    # succeeds and yields midnight, so a census carrying a bare date would read
    # as measured at 00:00 -- up to a day earlier or later than the truth, and
    # silently. Freshness is the whole subject here, so an underspecified
    # timestamp must not be guessed into one.
    if not any(sep in raw for sep in ("T", "t", " ")):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    # A naive timestamp is read as UTC rather than rejected: every producer in
    # this estate writes UTC, and rejecting it would fail closed on a verdict
    # that is merely underspecified rather than untrustworthy.
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class Verdict:
    """A gate's answer, with the moment it was true and how long that lasts."""

    name: str
    outcome: str = UNKNOWN  # pass | fail | unknown
    measured_at: str = ""  # ISO-8601 instant
    ttl_hours: float = DEFAULT_TTL_HOURS
    subject: str = ""  # what it was measured against, e.g. a commit sha
    source: str = ""  # where the answer came from, for the report

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Verdict":
        return cls(
            name=str(data.get("name") or ""),
            outcome=str(data.get("outcome") or UNKNOWN),
            measured_at=str(data.get("measured_at") or ""),
            # `or` would turn an explicit 0 into 24: `0 or 24 == 24`. Zero is
            # the one TTL this module promises to fail closed on, and it is the
            # likeliest malformed value since an empty numeric field coerces to
            # it. Default only when the key is absent or null.
            ttl_hours=float(
                DEFAULT_TTL_HOURS if data.get("ttl_hours") is None else data["ttl_hours"]
            ),
            subject=str(data.get("subject") or ""),
            source=str(data.get("source") or ""),
        )

    @classmethod
    def from_census(
        cls, census: dict[str, Any], *, ttl_hours: float = DEFAULT_TTL_HOURS
    ) -> "Verdict":
        """Read `logs/vulnerability_census.json` as a verdict.

        `scanned_ok` false means the census could not complete its scan, which
        is `unknown` and not `fail`: a registry outage is not a vulnerability,
        and conflating the two is how a transient network error would come to
        read as a security finding.
        """
        # `int(fixable)` accepted anything int() accepts, and three of those
        # produced a PASS that no clean scan had earned: `False` (int 0), the
        # string `"0"`, and `0.5` (truncated to 0). A count that is not a
        # non-negative integer is not a count, and a verdict derived from one
        # must be `unknown` rather than a guess in either direction.
        # `scanned_ok` is tested for identity with True, not truthiness, for
        # exactly the reason `_is_count` exists below: the string "false" is
        # truthy, so a census recording `"scanned_ok": "false"` with zero
        # fixable findings read as a clean scan. Two clauses of one predicate,
        # and only one of them had been tightened. Raised by coderabbit on #1403.
        fixable = census.get("fixable_count")
        if census.get("scanned_ok") is not True or not _is_count(fixable):
            outcome = UNKNOWN
        else:
            outcome = "pass" if int(fixable) == 0 else "fail"
        return cls(
            name="vulnerability-census",
            outcome=outcome,
            measured_at=str(census.get("generated_at") or ""),
            ttl_hours=ttl_hours,
            subject=str(census.get("commit") or ""),
            source="logs/vulnerability_census.json",
        )

    def age(self, now: datetime | None = None) -> timedelta | None:
        """How long ago this was measured, or None when that is unknowable."""
        measured = _parse_instant(self.measured_at)
        if measured is None:
            return None
        return (now or datetime.now(timezone.utc)) - measured

    def freshness(self, now: datetime | None = None) -> str:
        """`LIVE`, `STALE`, or `UNKNOWN` -- never a guess in its own favour."""
        age = self.age(now)
        if age is None:
            return UNKNOWN
        if age < timedelta(0):
            # Measured in the future: a clock disagreement somewhere, and a
            # verdict resting on a clock nobody can reconcile is not live.
            return UNKNOWN
        if not _usable_ttl(self.ttl_hours):
            # A non-positive TTL means nothing is ever live, and a non-finite
            # one makes `timedelta` RAISE -- ValueError for nan, OverflowError
            # for inf. A freshness check that throws is worse than one that
            # fails: it takes the whole step down instead of reporting. Both
            # are UNKNOWN, which is what "cannot establish" means here.
            return UNKNOWN
        return LIVE if age <= timedelta(hours=self.ttl_hours) else STALE

    def counts_as_pass(self, now: datetime | None = None) -> bool:
        """The only question a gate should ask of a verdict.

        Both halves are required. A pass that has aged out is not a pass, which
        is the entire point of this module -- see WHY A VERDICT EXPIRES HARDER
        THAN AN ADJUDICATION.
        """
        return self.outcome == "pass" and self.freshness(now) == LIVE

    def defects(self) -> list[str]:
        """Reasons this verdict is not a usable answer."""
        problems: list[str] = []
        if not self.name.strip():
            problems.append("no name -- nothing says which gate this answers for")
        if self.outcome not in ("pass", "fail", UNKNOWN):
            problems.append(f"outcome {self.outcome!r} is not pass, fail or unknown")
        if not self.measured_at.strip():
            problems.append("no measured_at -- cannot establish it was measured recently")
        elif _parse_instant(self.measured_at) is None:
            problems.append(f"measured_at {self.measured_at!r} is not an ISO-8601 instant")
        if not _usable_ttl(self.ttl_hours):
            problems.append(
                f"ttl_hours {self.ttl_hours!r} is not a positive finite number -- "
                "nothing could ever be live"
            )
        return problems

    def explain(self, now: datetime | None = None) -> str:
        """One line a reader can act on, with the number behind it."""
        state = self.freshness(now)
        age = self.age(now)
        if age is None:
            when = "age unknown"
        else:
            hours = age.total_seconds() / 3600
            when = f"{hours:.1f}h old" if hours < 48 else f"{hours / 24:.1f} days old"
        verdict = "counts as a pass" if self.counts_as_pass(now) else "does NOT count as a pass"
        subject = f" on {self.subject[:8]}" if self.subject else ""
        return (
            f"{self.name}{subject}: outcome={self.outcome} {state} "
            f"({when}, ttl {self.ttl_hours:g}h) -- {verdict}"
        )


@dataclass
class VerdictReport:
    """Every verdict a gate relied on, and which of them still hold."""

    verdicts: list[Verdict] = field(default_factory=list)
    checked_at: datetime | None = None

    @property
    def stale(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.freshness(self.checked_at) == STALE]

    @property
    def unknown(self) -> list[Verdict]:
        return [v for v in self.verdicts if v.freshness(self.checked_at) == UNKNOWN]

    @property
    def malformed(self) -> list[tuple[Verdict, list[str]]]:
        return [(v, d) for v in self.verdicts if (d := v.defects())]

    @property
    def holds(self) -> bool:
        """True only when every verdict is a live pass.

        A report with no verdicts in it does NOT hold. An empty gate is not a
        passing gate -- that is the `supply-chain-watch` failure in miniature,
        where a run that skipped the census reported success for the workflow.
        """
        return bool(self.verdicts) and all(
            not v.defects() and v.counts_as_pass(self.checked_at) for v in self.verdicts
        )

    def explain(self) -> str:
        if not self.verdicts:
            return "no verdicts were presented, so nothing has been established"
        return "\n".join(v.explain(self.checked_at) for v in self.verdicts)


def load_verdict(path: Path, *, ttl_hours: float = DEFAULT_TTL_HOURS) -> Verdict:
    """A verdict from a census output file.

    An absent or unreadable file is `unknown`, not a failure and not a pass.
    The census output is generated in CI and is not committed, so "absent" is
    an ordinary state locally and must not be read as either answer.
    """
    try:
        census = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Verdict(
            name="vulnerability-census",
            outcome=UNKNOWN,
            measured_at="",
            ttl_hours=ttl_hours,
            source=str(path),
        )
    if not isinstance(census, dict):
        return Verdict(
            name="vulnerability-census",
            outcome=UNKNOWN,
            ttl_hours=ttl_hours,
            source=str(path),
        )
    return Verdict.from_census(census, ttl_hours=ttl_hours)
