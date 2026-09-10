"""Memory: what this estate has already decided, and when to stop believing it.

WHY THIS EXISTS
---------------
Adaptive immunity is what separates a body that survives a second exposure from
one that fights every infection as if it were the first. Its mechanism is
memory: a record of what was met, what it turned out to be, and how it was
handled -- so the next encounter is fast and proportionate.

A CI estate needs the same thing and usually builds it badly. The common shape
is a suppression list: a rule id and a path, appended to forever, never
revisited. That is not memory, it is scar tissue. This repository has a live
example. `.security_learning/suppress.json` carries adjudications keyed on
paths like `/tmp/pytest-of-root/pytest-1/test_suppression_filtering0/...` --
directories that existed for the duration of one test run in May and can never
exist again. The store learned from its own test suite. Those entries will
match nothing forever, and nothing in the estate notices.

WHAT THIS DOES DIFFERENTLY
--------------------------
1. **Adjudications carry provenance and an expiry.** Who decided, when, why,
   and the date the decision must be looked at again. An expired adjudication
   is reported as expired -- it still suppresses, so nobody wakes to a wall of
   red, but it appears in the report every run until a human renews or drops
   it. A decision nobody will ever revisit is not a decision, it is a leak.

2. **Rot is a finding.** An adjudication whose file no longer exists, or whose
   rule no sensor emits any more, is reported. That is how the pytest-tmpdir
   entries above would have been caught the week after they were written.

3. **Autoimmunity is detected as a property of the rule, not the instance.**
   When one rule is adjudicated a false positive across many unrelated files,
   the rule is attacking healthy tissue. Suppressing each instance treats the
   symptom and hides the pattern; this reports the rule so the rule can be
   tuned or dropped. A guard that cries wolf on working code costs a gate its
   credibility as fast as a miss does -- and by then reviewers have learned to
   scroll past it, which is the same outcome as having no guard.

4. **Self is a baseline, not an allowlist.** The baseline records what the
   estate looked like at a known-good commit. Anything in it is "self" -- known,
   tolerated, on the backlog. Anything outside it is new, and new is what a
   pull request is answerable for. This is the mechanism the deleted AWS policy
   validator called CHECK_NO_NEW_ACCESS, generalised from IAM policies to every
   finding the estate can produce.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import yaml

from src.immune.sarif import Finding

ADJUDICATIONS = Path("config/immune/adjudications.yaml")
BASELINE = Path("config/immune/baseline.json")

# A rule adjudicated a false positive in at least this many distinct files is
# reported as autoimmune. Three is deliberately low: two could be coincidence
# in one subsystem, three across unrelated files is a property of the rule.
AUTOIMMUNE_THRESHOLD = 3


@dataclass
class Adjudication:
    """A written decision that a finding is not a defect here."""

    rule_id: str
    path: str = ""  # exact path, or "" for rule-wide
    reason: str = ""
    decided_by: str = ""
    decided_on: str = ""  # ISO date
    review_by: str = ""  # ISO date; blank means never reviewed = invalid
    verdict: str = "false-positive"  # false-positive | accepted-risk | by-design

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Adjudication":
        return cls(
            rule_id=str(data.get("rule_id") or ""),
            path=str(data.get("path") or ""),
            reason=str(data.get("reason") or ""),
            decided_by=str(data.get("decided_by") or ""),
            decided_on=str(data.get("decided_on") or ""),
            review_by=str(data.get("review_by") or ""),
            verdict=str(data.get("verdict") or "false-positive"),
        )

    def matches(self, finding: Finding) -> bool:
        if self.rule_id and self.rule_id != finding.rule_id:
            return False
        if self.path and self.path != finding.path:
            return False
        return bool(self.rule_id)

    def expired(self, today: date | None = None) -> bool:
        if not self.review_by:
            return True  # no review date is a decision that never expires
        try:
            return date.fromisoformat(self.review_by) < (today or date.today())
        except ValueError:
            return True  # an unparseable date cannot be trusted to be future

    def defects(self) -> list[str]:
        """Reasons this adjudication is not a usable decision."""
        problems = []
        if not self.rule_id:
            problems.append("no rule_id")
        if not self.reason.strip():
            problems.append("no written reason")
        if not self.decided_by.strip():
            problems.append("nobody named as deciding it")
        if not self.review_by.strip():
            problems.append("no review_by date -- suppresses forever")
        else:
            try:
                date.fromisoformat(self.review_by)
            except ValueError:
                problems.append(f"review_by {self.review_by!r} is not an ISO date")
        return problems


@dataclass
class MemoryReport:
    """What memory did to this run, and what memory itself needs looked at."""

    suppressed: list[tuple[Finding, Adjudication]] = field(default_factory=list)
    expired: list[Adjudication] = field(default_factory=list)
    rotted: list[tuple[Adjudication, str]] = field(default_factory=list)
    malformed: list[tuple[Adjudication, list[str]]] = field(default_factory=list)
    autoimmune: dict[str, list[str]] = field(default_factory=dict)

    @property
    def healthy(self) -> bool:
        return not (self.expired or self.rotted or self.malformed or self.autoimmune)


def load_adjudications(path: Path = ADJUDICATIONS) -> list[Adjudication]:
    if not path.exists():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    entries = raw.get("adjudications") or []
    return [Adjudication.from_mapping(entry) for entry in entries]


def apply_memory(
    findings: Iterable[Finding],
    adjudications: list[Adjudication],
    *,
    repo_root: Path = Path("."),
    today: date | None = None,
) -> tuple[list[Finding], MemoryReport]:
    """Filter findings through memory and audit memory at the same time.

    The audit runs on every invocation rather than on a schedule, because a
    suppression store is only ever examined when something forces it to be.
    """
    report = MemoryReport()
    remaining: list[Finding] = []
    used: set[int] = set()

    for finding in findings:
        hit = next((a for a in adjudications if a.matches(finding)), None)
        if hit is None:
            remaining.append(finding)
            continue
        used.add(id(hit))
        report.suppressed.append((finding, hit))

    for adj in adjudications:
        problems = adj.defects()
        if problems:
            report.malformed.append((adj, problems))
        if adj.expired(today):
            report.expired.append(adj)
        if adj.path and not (repo_root / adj.path).exists():
            report.rotted.append((adj, f"path {adj.path} no longer exists"))
        elif id(adj) not in used:
            report.rotted.append((adj, "matched nothing in this run"))

    # Autoimmunity: one rule, many unrelated files, all adjudicated false.
    by_rule: dict[str, set[str]] = {}
    for adj in adjudications:
        if adj.verdict != "false-positive" or not adj.path:
            continue
        by_rule.setdefault(adj.rule_id, set()).add(adj.path)
    for rule, paths in by_rule.items():
        if len(paths) >= AUTOIMMUNE_THRESHOLD:
            report.autoimmune[rule] = sorted(paths)

    return remaining, report


# ── baseline: the estate's notion of "self" ──────────────────────────


def write_baseline(
    findings: Iterable[Finding],
    path: Path = BASELINE,
    *,
    commit: str = "",
    sensors: Iterable[str] = (),
) -> int:
    """Record the estate's current findings as "self", and who saw them.

    `sensors` matters as much as the fingerprints. A baseline written on a
    machine with three sensors installed, then compared against a CI run with
    six, would report every finding from the three new sensors as a regression
    introduced by whichever pull request happened to run first. That is the
    freshness-gate failure again in a new costume: a gate reporting on a change
    in the measuring apparatus as if it were a change in the thing measured.
    """
    # Counted, not just listed. The fingerprint deliberately excludes the line
    # number so a finding survives code moving down the file -- but that also
    # collapses three instances of one rule in one file into a single entry,
    # and a fourth instance would then not read as new. Recording the count
    # keeps both properties: stable across edits, sensitive to multiplication.
    counted: dict[str, int] = {}
    for finding in findings:
        counted[finding.fingerprint] = counted.get(finding.fingerprint, 0) + 1
    entries = dict(sorted(counted.items()))
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "commit": commit,
        "count": len(entries),
        "occurrences": sum(entries.values()),
        "sensors": sorted(set(sensors)),
        "note": (
            "Fingerprints of findings present at a known-good commit. Anything "
            "not in this set is new, and new is what a pull request answers "
            "for. `sensors` records which sensors contributed; findings from a "
            "sensor NOT in that list are reported but not gated, because the "
            "estate has never measured them. Regenerate deliberately, in a "
            "commit that says why. Values are occurrence counts: a finding "
            "appearing more times than the baseline records is new."
        ),
        "fingerprints": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return len(entries)


def load_baseline(path: Path = BASELINE) -> dict[str, int]:
    """Fingerprint -> occurrence count. Empty means no baseline recorded.

    A list-shaped `fingerprints` from an older baseline is read as one
    occurrence each, so an existing file keeps working rather than reading as
    an empty baseline -- which would silently turn the gate off.
    """
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    entries = payload.get("fingerprints") or {}
    if isinstance(entries, list):
        return {str(fp): 1 for fp in entries}
    return {str(fp): int(count) for fp, count in entries.items()}


def baseline_sensors(path: Path = BASELINE) -> set[str]:
    """Which sensors the baseline was written from. Empty means unknown."""
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return set(payload.get("sensors") or [])


def split_unmeasured(
    findings: Iterable[Finding], baseline_sensor_names: set[str]
) -> tuple[list[Finding], list[Finding]]:
    """Separate findings the baseline could have contained from those it could not.

    Returns (measured, unmeasured). With no recorded sensor list -- an older
    baseline -- everything is treated as measured, because guessing the other
    way would gate on findings nobody has ever agreed a baseline for.
    """
    findings = list(findings)
    if not baseline_sensor_names:
        return findings, []
    def known(finding: Finding) -> bool:
        return (finding.sensor or finding.tool) in baseline_sensor_names

    return [f for f in findings if known(f)], [f for f in findings if not known(f)]


def split_by_baseline(
    findings: Iterable[Finding], baseline: dict[str, int]
) -> tuple[list[Finding], list[Finding]]:
    """Return (new, known). With no baseline, everything is known.

    An empty baseline must not make every pre-existing finding look like a
    regression introduced by whatever pull request happened to run first.

    Findings beyond a fingerprint's recorded occurrence count are new. Which
    specific instances get called new is arbitrary -- they are by definition
    indistinguishable -- so the excess is taken in the order given, which for a
    sorted report means the ones nearest the top of the file.
    """
    findings = list(findings)
    if not baseline:
        return [], findings
    budget = dict(baseline)
    new: list[Finding] = []
    known: list[Finding] = []
    for finding in findings:
        if budget.get(finding.fingerprint, 0) > 0:
            budget[finding.fingerprint] -= 1
            known.append(finding)
        else:
            new.append(finding)
    return new, known
