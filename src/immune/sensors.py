"""Sensors: the innate layer, and the honest reporting of what it could see.

WHY THIS EXISTS
---------------
Innate immunity is fast, generic and always on: it does not need to have met a
pathogen before. In this estate that is ruff, bandit, semgrep, gitleaks, trivy
and pip-audit -- generic sensors that fire on shapes, not on specific known
attacks.

Every commercial scanner this repository deleted had the same structural flaw,
and it is the flaw this module exists to fix: **a sensor that could not run
reports the same thing as a sensor that ran and found nothing.** `npm audit`
against a soft registry failure returns a well-formed report with an empty
vulnerability map. `pip-audit` behind a blocked proxy exits non-zero and a
`|| true` turns that into a pass. MSDO with no Azure onboarding uploads nothing
and the Security tab simply shows no new alerts.

In immunology the equivalent is not health, it is **anergy** -- a immune system
present but unresponsive. It looks identical to a body with nothing to fight.

SO EVERY SENSOR REPORTS AN OUTCOME, NOT JUST FINDINGS
-----------------------------------------------------
    ok          ran, produced a readable report (findings may be zero)
    absent      the tool is not installed here -- a known gap, not a clean bill
    failed      the tool ran and broke; its report cannot be trusted
    unreadable  the tool produced output that is not parseable as its format
    blind       the tool ran, reported clean, and FAILED ITS OWN PROBE

`blind` is the one that matters. A sensor may declare a probe: a small input
with a known defect planted in it that the sensor must flag. If the probe comes
back clean, the sensor is not working, whatever it says about the real tree.
This generalises the npm-registry canary in `scripts/vulnerability_census.py`
from one scanner to every sensor in the manifest, and it is a property no
commercial scanner in this estate's deleted set offered at any price.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Any, Sequence

import yaml

from src.immune.sarif import (
    Finding,
    SarifUnreadable,
    _relativise,
    findings_from_sarif,
    normalise_level,
)

DEFAULT_MANIFEST = Path("config/immune/sensors.yaml")
DEFAULT_TIMEOUT = 900


class Outcome(str, Enum):
    OK = "ok"
    ABSENT = "absent"
    FAILED = "failed"
    UNREADABLE = "unreadable"
    BLIND = "blind"

    @property
    def trustworthy(self) -> bool:
        """Can a clean result from this sensor be believed?"""
        return self is Outcome.OK


@dataclass
class SensorResult:
    name: str
    outcome: Outcome
    findings: list[Finding] = field(default_factory=list)
    detail: str = ""
    required: bool = False

    @property
    def blocking(self) -> bool:
        """A required sensor that could not see is a reason to stop.

        An optional one is a recorded gap. The difference is declared in the
        manifest, so 'we have no scanner for this' is a written decision rather
        than an accident of which tool happened to be on the runner.
        """
        return self.required and not self.outcome.trustworthy


@dataclass
class Sensor:
    name: str
    kind: str  # innate | adaptive
    senses: str  # one line: what class of harm this detects
    command: list[str] = field(default_factory=list)
    fmt: str = "sarif"
    output: str = ""  # file the tool writes; empty means stdout
    binary: str = ""  # executable that must exist
    required: bool = False
    accept_exit: list[int] = field(default_factory=lambda: [0, 1])
    probe: dict[str, Any] = field(default_factory=dict)
    location: str = ""  # owning Trancendos Location

    @classmethod
    def from_mapping(cls, name: str, data: dict[str, Any]) -> "Sensor":
        command = data.get("command") or []
        if isinstance(command, str):
            command = command.split()
        return cls(
            name=name,
            kind=str(data.get("kind") or "innate"),
            senses=str(data.get("senses") or ""),
            command=[str(part) for part in command],
            fmt=str(data.get("format") or "sarif"),
            output=str(data.get("output") or ""),
            binary=str(data.get("binary") or (command[0] if command else "")),
            required=bool(data.get("required", False)),
            accept_exit=[int(code) for code in (data.get("accept_exit") or [0, 1])],
            probe=dict(data.get("probe") or {}),
            location=str(data.get("location") or ""),
        )


def load_manifest(path: Path = DEFAULT_MANIFEST) -> list[Sensor]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sensors = raw.get("sensors") or {}
    return [Sensor.from_mapping(name, data) for name, data in sensors.items()]


# ── format converters ────────────────────────────────────────────────
# Each converter turns one tool's native JSON into normalised findings. They
# exist because the tool does not speak SARIF, not because SARIF is optional:
# everything downstream of here sees SARIF-shaped findings only.
#
# Every converter runs its path through `_relativise`, the same normaliser the
# SARIF reader uses. Tools disagree about how to name a file -- bandit reports
# "./src/x.py", trivy an absolute container path, CodeQL a file: URI -- and a
# finding whose path does not match `git ls-files` is a finding that attaches
# to no file. It still counts in the totals and never appears in the per-file
# grade, which is exactly how a repository with 13,712 findings can display a
# distribution of all-A. Measured, on the first real run of this scanner.


def _from_ruff(payload: Any, tool: str) -> list[Finding]:
    out: list[Finding] = []
    for item in payload if isinstance(payload, list) else []:
        location = item.get("location") or {}
        end = item.get("end_location") or {}
        out.append(
            Finding(
                tool=tool,
                rule_id=str(item.get("code") or "ruff/unknown"),
                level="warning",
                message=str(item.get("message") or "")[:500],
                path=_relativise(str(item.get("filename") or "")),
                start_line=int(location.get("row") or 0),
                end_line=int(end.get("row") or 0),
            )
        )
    return out


def _from_bandit(payload: Any, tool: str) -> list[Finding]:
    out: list[Finding] = []
    results = (payload or {}).get("results") or []
    for item in results:
        out.append(
            Finding(
                tool=tool,
                rule_id=str(item.get("test_id") or "bandit/unknown"),
                level=normalise_level(item.get("issue_severity")),
                message=str(item.get("issue_text") or "")[:500],
                path=_relativise(str(item.get("filename") or "")),
                start_line=int(item.get("line_number") or 0),
                snippet=str(item.get("code") or "").strip()[:200],
            )
        )
    return out


def _from_pip_audit(payload: Any, tool: str) -> list[Finding]:
    """pip-audit emits either a bare list or {"dependencies": [...]}."""
    deps = payload.get("dependencies") if isinstance(payload, dict) else payload
    out: list[Finding] = []
    for dep in deps or []:
        name = str(dep.get("name") or "")
        version = str(dep.get("version") or "")
        for vuln in dep.get("vulns") or []:
            fix = ", ".join(str(v) for v in (vuln.get("fix_versions") or []))
            out.append(
                Finding(
                    tool=tool,
                    rule_id=str(vuln.get("id") or "PYSEC-unknown"),
                    level="error" if fix else "warning",
                    message=(
                        f"{name} {version}: {vuln.get('description') or ''}"
                        + (f" (fixed in {fix})" if fix else " (no fix published)")
                    )[:500],
                    path=_relativise(str(dep.get("_source") or "requirements")),
                    start_line=0,
                )
            )
    return out


def _from_npm_audit(payload: Any, tool: str) -> list[Finding]:
    vulns = (payload or {}).get("vulnerabilities") or {}
    out: list[Finding] = []
    for name, entry in vulns.items():
        advisories = entry.get("via") or []
        titles = [
            a.get("title") for a in advisories if isinstance(a, dict) and a.get("title")
        ]
        out.append(
            Finding(
                tool=tool,
                rule_id=str(
                    next(
                        (
                            a.get("url", "").rsplit("/", 1)[-1]
                            for a in advisories
                            if isinstance(a, dict) and a.get("url")
                        ),
                        f"npm/{name}",
                    )
                ),
                level=normalise_level(entry.get("severity")),
                message=f"{name}: {'; '.join(titles) or 'vulnerable dependency'}"[:500],
                path="package-lock.json",
                start_line=0,
            )
        )
    return out


def _from_gitleaks(payload: Any, tool: str) -> list[Finding]:
    out: list[Finding] = []
    for item in payload if isinstance(payload, list) else []:
        out.append(
            Finding(
                tool=tool,
                # A leaked credential is always an error. gitleaks has no
                # severity field, and defaulting it to 'warning' would let a
                # live key sit below a grading threshold.
                rule_id=str(item.get("RuleID") or "gitleaks/unknown"),
                level="error",
                message=str(item.get("Description") or "secret detected")[:500],
                path=_relativise(str(item.get("File") or "")),
                start_line=int(item.get("StartLine") or 0),
            )
        )
    return out


_CONVERTERS = {
    "ruff-json": _from_ruff,
    "bandit-json": _from_bandit,
    "pip-audit-json": _from_pip_audit,
    "npm-audit-json": _from_npm_audit,
    "gitleaks-json": _from_gitleaks,
}


def _stamp(findings: list[Finding], sensor_name: str) -> list[Finding]:
    """Record which declared sensor produced each finding.

    `Finding.tool` is what the tool calls itself; `Finding.sensor` is which
    entry in config/immune/sensors.yaml produced it. The baseline matches on
    the second, so a vendor renaming its SARIF driver cannot make a whole
    sensor's findings look newly discovered.
    """
    return [replace(f, sensor=sensor_name) for f in findings]


def parse_output(text: str, fmt: str, tool: str) -> list[Finding]:
    """Turn a sensor's raw output into findings, or say it was unreadable."""
    if not text.strip():
        raise SarifUnreadable(f"{tool}: produced no output at all")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SarifUnreadable(f"{tool}: output is not JSON ({exc})") from exc
    if fmt == "sarif":
        if not isinstance(payload, dict) or "runs" not in payload:
            raise SarifUnreadable(f"{tool}: JSON without SARIF 'runs'")
        return findings_from_sarif(payload, tool_hint=tool)
    converter = _CONVERTERS.get(fmt)
    if converter is None:
        raise SarifUnreadable(f"{tool}: no converter for format {fmt!r}")
    return converter(payload, tool)


# ── execution ────────────────────────────────────────────────────────


def _run(
    command: Sequence[str], cwd: Path, timeout: int
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    # A scanner is not the place to discover that colour codes are not JSON.
    env.setdefault("NO_COLOR", "1")
    env.setdefault("FORCE_COLOR", "0")
    return subprocess.run(  # noqa: S603 - commands come from the checked-in manifest
        list(command),
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
        env=env,
        check=False,
    )


def _collect(sensor: Sensor, proc: subprocess.CompletedProcess[str], cwd: Path) -> str:
    if sensor.output:
        target = cwd / sensor.output
        try:
            return target.read_text(encoding="utf-8")
        except OSError as exc:
            raise SarifUnreadable(
                f"{sensor.name}: declared output {sensor.output} unreadable ({exc})"
            ) from exc
    return proc.stdout


def probe_sensor(sensor: Sensor, *, timeout: int = 120) -> tuple[bool, str]:
    """Plant a known defect and check the sensor actually flags it.

    Returns (saw_it, detail). A sensor with no declared probe returns
    (True, "no probe declared") -- unprobed is not the same as proven, and the
    report says which, so an estate can see how much of its own immunity has
    ever been demonstrated rather than assumed.
    """
    if not sensor.probe:
        return True, "no probe declared"
    filename = str(sensor.probe.get("file") or "probe.py")
    content = str(sensor.probe.get("content") or "")
    expect = str(sensor.probe.get("expect_rule") or "")
    command = sensor.probe.get("command") or sensor.command
    if isinstance(command, str):
        command = command.split()
    with tempfile.TemporaryDirectory(prefix="immune-probe-") as tmp:
        root = Path(tmp)
        target = root / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        try:
            proc = _run([str(part) for part in command], root, timeout)
        except (subprocess.SubprocessError, OSError) as exc:
            return False, f"probe could not run: {exc}"
        try:
            raw = _collect(sensor, proc, root)
            findings = parse_output(raw, sensor.fmt, sensor.name)
        except SarifUnreadable as exc:
            return False, f"probe output unreadable: {exc}"
    if not findings:
        return False, "probe planted a known defect and the sensor reported clean"
    if expect and not any(expect in f.rule_id for f in findings):
        rules = ", ".join(sorted({f.rule_id for f in findings})[:5])
        return False, f"probe flagged something, but not {expect} (saw: {rules})"
    return True, f"probe flagged {len(findings)} finding(s)"


def run_sensor(
    sensor: Sensor,
    *,
    cwd: Path = Path("."),
    timeout: int = DEFAULT_TIMEOUT,
    verify_probe: bool = True,
) -> SensorResult:
    """Run one sensor and classify honestly what came back."""
    if sensor.binary and shutil.which(sensor.binary) is None:
        return SensorResult(
            sensor.name,
            Outcome.ABSENT,
            detail=f"{sensor.binary} is not installed on this machine",
            required=sensor.required,
        )
    try:
        proc = _run(sensor.command, cwd, timeout)
    except subprocess.TimeoutExpired:
        return SensorResult(
            sensor.name,
            Outcome.FAILED,
            detail=f"timed out after {timeout}s",
            required=sensor.required,
        )
    except (subprocess.SubprocessError, OSError) as exc:
        return SensorResult(
            sensor.name, Outcome.FAILED, detail=str(exc), required=sensor.required
        )
    if proc.returncode not in sensor.accept_exit:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        return SensorResult(
            sensor.name,
            Outcome.FAILED,
            detail=f"exit {proc.returncode}: {' / '.join(tail)[:300]}",
            required=sensor.required,
        )
    try:
        findings = parse_output(_collect(sensor, proc, cwd), sensor.fmt, sensor.name)
    except SarifUnreadable as exc:
        return SensorResult(
            sensor.name, Outcome.UNREADABLE, detail=str(exc), required=sensor.required
        )
    if verify_probe and not findings:
        # Only a clean report needs proving. A sensor that found something has
        # already demonstrated it can see, and probing it would spend a
        # subprocess to learn nothing.
        saw, detail = probe_sensor(sensor)
        if not saw:
            return SensorResult(
                sensor.name, Outcome.BLIND, detail=detail, required=sensor.required
            )
        return SensorResult(
            sensor.name,
            Outcome.OK,
            _stamp(findings, sensor.name),
            detail=f"clean; {detail}",
            required=sensor.required,
        )
    return SensorResult(
        sensor.name,
        Outcome.OK,
        _stamp(findings, sensor.name),
        detail=f"{len(findings)} finding(s)",
        required=sensor.required,
    )
