"""Vaccination: prove, on a clock, that the estate's sensors can still see.

WHY THIS EXISTS
---------------
Every sensor in `config/immune/sensors.yaml` can declare a probe — a known
defect planted in a temporary directory that the sensor must flag. A sensor
that reports clean while failing its own probe is recorded `blind`, because an
immune system present but unresponsive looks exactly like a healthy one. That
mechanism already runs on pull requests, in `scripts/immune_scan.py`.

Running it only on pull requests answers a narrower question than it appears
to. It says "this sensor could see at the moment somebody pushed". It cannot
say when a sensor STOPPED being able to see, because going blind is not an
event in the repository:

  * a scanner release changes a rule's default, or drops it
  * a pinned tool falls out of the runner image
  * a config edit widens an `ignore` until `--select` no longer wins
  * a wrapper script's output format shifts and the parser silently yields none

None of those produce a commit. A repository with no pushes for three weeks has
a three-week-old claim about its own immunity, and nothing anywhere says so.
`.github/workflows/supply-chain-watch.yml` already makes exactly this argument
for dependency abandonment and CVE disclosure — "events in the world, not events
in the repository" — and anergy belongs in the same category, which is why this
runs as a job in that same schedule rather than as a new workflow.

WHAT IT MEASURES THAT A SCAN DOES NOT
-------------------------------------
**Sight, not cleanliness.** A scan answers "what is wrong with the code". This
answers "is the estate still capable of noticing". Those are different
questions and they fail independently: the worst state is a clean scan from
sensors that stopped looking, and it is indistinguishable from health unless
something asks this question separately.

**Regression, not absolute state.** A sensor that could see yesterday and
cannot today is a failure even when it is optional, because something changed
underneath it. A sensor that has never had a probe is a recorded coverage gap,
not a failure — the difference between "we checked and it broke" and "we have
never checked" is the whole point, and collapsing them would make the number
comfortable and useless.

**Time since proof.** Each sensor carries the date it last demonstrated sight.
A sensor blind for twelve days reads as twelve days, not as a boolean — which
is the closest thing to mean-time-to-detect available without a metrics store,
and enough to tell a slow rot from this morning's breakage.

WHAT IT DELIBERATELY DOES NOT DO
--------------------------------
It does not fix anything, and it does not gate pull requests. A probe needs the
real toolchain installed; a runner without `bandit` on it would redden a pull
request that touched nothing, which is the "gate measures state, not change"
defect this estate has already been bitten by. Absent is reported as absent.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence

from src.immune.sensors import Outcome, Sensor, probe_sensor

DEFAULT_RECORD = Path("config/immune/immunity.json")

RECORD_NOTE = (
    "What each sensor last PROVED about its own sight, and when. Written by "
    "`python scripts/vaccinate.py --record`. `outcome` is the probe verdict, "
    "not a scan result: `ok` means the sensor flagged a defect deliberately "
    "planted for it. `last_proven` is the date it last managed that, and it is "
    "NOT updated when a sensor fails -- so a blind sensor's age is readable. "
    "`probed: false` is a coverage gap, not a failure: the sensor has never "
    "been asked to demonstrate anything. Driving that count to zero is the "
    "point of the exercise; see docs/governance/IMMUNE-SYSTEM.md."
)


@dataclass
class Immunity:
    """One sensor's demonstrated ability to see."""

    sensor: str
    probed: bool
    outcome: str
    required: bool = False
    detail: str = ""
    last_proven: str = ""

    @property
    def proven(self) -> bool:
        return self.probed and self.outcome == Outcome.OK.value

    def days_since_proven(self, today: date | None = None) -> int | None:
        """How long since this sensor demonstrated sight. None if it never has."""
        if not self.last_proven:
            return None
        try:
            then = date.fromisoformat(self.last_proven)
        except ValueError:
            return None
        return ((today or date.today()) - then).days


@dataclass
class VaccinationReport:
    records: list[Immunity] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    recoveries: list[str] = field(default_factory=list)

    @property
    def required(self) -> list[Immunity]:
        return [r for r in self.records if r.required]

    @property
    def unprobed(self) -> list[Immunity]:
        return [r for r in self.records if not r.probed]

    @property
    def sight(self) -> float:
        """Fraction of REQUIRED sensors that proved they can see.

        The SLO. Required-only on purpose: an optional sensor with no probe is
        a gap the estate has chosen and written down, and folding it into the
        headline number would let a deliberate choice look like a failure --
        and, worse, let adding optional sensors dilute a real blindness.
        """
        required = self.required
        if not required:
            return 0.0
        return sum(1 for r in required if r.proven) / len(required)

    @property
    def coverage(self) -> float:
        """Fraction of ALL sensors that have a probe at all.

        Separate from `sight` because it answers a different question: not
        "did the immune system work today" but "how much of it has ever been
        tested". A high sight score over low coverage is a confident number
        about a small corner.
        """
        if not self.records:
            return 0.0
        return sum(1 for r in self.records if r.probed) / len(self.records)

    @property
    def blind_required(self) -> list[Immunity]:
        return [r for r in self.required if r.probed and not r.proven]

    def failing(self) -> list[str]:
        """Reasons this run should fail, in the order a reader needs them."""
        reasons = []
        for record in self.blind_required:
            reasons.append(
                f"required sensor '{record.sensor}' could not prove it can see: {record.detail}"
            )
        for name in self.regressions:
            reasons.append(f"'{name}' proved sight before and cannot now")
        return reasons


def load_record(path: Path = DEFAULT_RECORD) -> dict[str, Immunity]:
    """Previously demonstrated immunity, by sensor name.

    A missing or unreadable record is an empty one rather than an error: the
    first run of a new estate has nothing to compare against, and crashing
    there would make the control impossible to adopt.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    sensors = raw.get("sensors")
    if not isinstance(sensors, dict):
        return {}
    out: dict[str, Immunity] = {}
    for name, entry in sensors.items():
        if not isinstance(entry, dict):
            continue
        out[name] = Immunity(
            sensor=name,
            probed=bool(entry.get("probed")),
            outcome=str(entry.get("outcome") or ""),
            required=bool(entry.get("required")),
            detail=str(entry.get("detail") or ""),
            last_proven=str(entry.get("last_proven") or ""),
        )
    return out


def write_record(
    report: VaccinationReport,
    *,
    path: Path = DEFAULT_RECORD,
    commit: str = "",
) -> None:
    payload = {
        "note": RECORD_NOTE,
        "recorded_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "commit": commit,
        "sight": round(report.sight, 4),
        "coverage": round(report.coverage, 4),
        "sensors": {
            record.sensor: {key: value for key, value in asdict(record).items() if key != "sensor"}
            for record in sorted(report.records, key=lambda r: r.sensor)
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def vaccinate(
    sensors: Sequence[Sensor],
    *,
    previous: dict[str, Immunity] | None = None,
    today: date | None = None,
    timeout: int = 180,
) -> VaccinationReport:
    """Ask every sensor to demonstrate that it can still see."""
    previous = previous or {}
    stamp = (today or date.today()).isoformat()
    report = VaccinationReport()

    for sensor in sensors:
        was = previous.get(sensor.name)
        if not sensor.probe:
            # Never asked, so nothing to regress. Carried forward rather than
            # invented, so a sensor that once had a probe and lost it keeps the
            # date it last proved anything -- which is exactly the case worth
            # noticing.
            report.records.append(
                Immunity(
                    sensor=sensor.name,
                    probed=False,
                    outcome="unprobed",
                    required=sensor.required,
                    detail="no probe declared — this sensor has never demonstrated sight",
                    last_proven=was.last_proven if was else "",
                )
            )
            continue

        saw, detail = probe_sensor(sensor, timeout=timeout)
        record = Immunity(
            sensor=sensor.name,
            probed=True,
            outcome=Outcome.OK.value if saw else Outcome.BLIND.value,
            required=sensor.required,
            detail=detail,
            # Only a pass moves the date. A failure leaves it where it was, so
            # the gap between then and now IS the age of the blindness.
            last_proven=stamp if saw else (was.last_proven if was else ""),
        )
        report.records.append(record)

        if was and was.proven and not record.proven:
            report.regressions.append(sensor.name)
        elif was and was.probed and not was.proven and record.proven:
            report.recoveries.append(sensor.name)

    report.records.sort(key=lambda r: r.sensor)
    return report


def render(report: VaccinationReport, *, today: date | None = None) -> str:
    """The report a reader can act on, not a score."""
    lines = ["── immunity ────────────────────────────────────────────────"]
    for record in report.records:
        if not record.probed:
            mark, state = "  ", "unprobed"
        elif record.proven:
            mark, state = "ok", "sees"
        else:
            mark, state = "!!", "BLIND"
        tag = "(required)" if record.required else ""
        age = record.days_since_proven(today)
        when = "never proven" if age is None else f"proved {age}d ago"
        lines.append(f"  {mark:<4}{record.sensor:<12} {state:<9} {tag:<11}{when}")

    lines.append("")
    lines.append("── vitals ──────────────────────────────────────────────────")
    lines.append(f"  sight         {report.sight:.0%} of required sensors proved they can see")
    lines.append(f"  coverage      {report.coverage:.0%} of all sensors have a probe at all")
    if report.unprobed:
        lines.append("  never asked   " + ", ".join(sorted(r.sensor for r in report.unprobed)))
    if report.recoveries:
        lines.append("  recovered     " + ", ".join(sorted(report.recoveries)))
    return "\n".join(lines)


def stale_sensors(
    records: Iterable[Immunity], *, max_age_days: int, today: date | None = None
) -> list[Immunity]:
    """Sensors whose last proof of sight is older than the estate allows.

    Distinct from blindness: a sensor can be `ok` today and still have a stale
    record if nothing has run the probe for a month. This is what catches the
    schedule itself having quietly stopped -- the control that watches the
    watcher, which is the failure this whole module was built around.
    """
    out = []
    for record in records:
        age = record.days_since_proven(today)
        if age is None or age > max_age_days:
            out.append(record)
    return out
