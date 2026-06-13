#!/usr/bin/env python3
"""N-1 Dependency Compliance Checker — Trancendos Platform.

Enforces the N-1 standard: every pinned dependency must be within one major
or minor version of the current stable release on PyPI.

Rules:
  - PATCH bumps: always allowed within same major.minor
  - MINOR behind by 1: allowed (e.g. using 1.9.x when 1.10 is latest)
  - MINOR behind by 2+: WARNING (action required within 30 days)
  - MAJOR behind by 1+: CRITICAL (upgrade immediately)
  - MAJOR 2+ behind: BLOCKER (breaks policy, must remediate before merge)

Usage:
    python scripts/n1_checker.py requirements.txt [requirements-test.txt ...]
    python scripts/n1_checker.py --all          # scan all requirements*.txt
    python scripts/n1_checker.py --json         # output JSON report
    python scripts/n1_checker.py --exit-code    # exit 1 if CRITICAL/BLOCKER found

Exit codes:
    0 — compliant
    1 — CRITICAL or BLOCKER violations found (use with --exit-code)
    2 — invocation error
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

PYPI_URL = "https://pypi.org/pypi/{package}/json"
CACHE: dict[str, tuple[str, ...]] = {}


class Status(str, Enum):
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"  # N-2 minor
    CRITICAL = "CRITICAL"  # N-1 major
    BLOCKER = "BLOCKER"  # N-2+ major
    UNPINNED = "UNPINNED"  # no exact pin
    UNKNOWN = "UNKNOWN"  # PyPI lookup failed


@dataclass
class Finding:
    package: str
    pinned: str
    latest: str
    status: Status
    message: str
    requirement_file: str


@dataclass
class Report:
    scanned_at: str
    files: list[str]
    findings: list[Finding] = field(default_factory=list)

    @property
    def blockers(self) -> list[Finding]:
        return [f for f in self.findings if f.status == Status.BLOCKER]

    @property
    def criticals(self) -> list[Finding]:
        return [f for f in self.findings if f.status == Status.CRITICAL]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.status == Status.WARNING]

    @property
    def passed(self) -> list[Finding]:
        return [f for f in self.findings if f.status == Status.COMPLIANT]

    def summary(self) -> str:
        return (
            f"Files: {len(self.files)} | "
            f"Packages: {len(self.findings)} | "
            f"BLOCKERS: {len(self.blockers)} | "
            f"CRITICAL: {len(self.criticals)} | "
            f"WARNING: {len(self.warnings)} | "
            f"COMPLIANT: {len(self.passed)}"
        )


def _parse_version(v: str) -> tuple[int, ...]:
    """Return numeric tuple from version string, ignoring pre/post/dev."""
    cleaned = re.split(r"[^0-9.]", v)[0]
    parts = cleaned.split(".")
    result = []
    for p in parts:
        try:
            result.append(int(p))
        except ValueError:
            break
    while len(result) < 3:
        result.append(0)
    return tuple(result)


def _get_latest_versions(package: str) -> tuple[str, ...]:
    """Fetch all non-yanked release versions from PyPI."""
    if package in CACHE:
        return CACHE[package]
    try:
        url = PYPI_URL.format(package=package.lower())
        req = urllib.request.Request(url, headers={"User-Agent": "tranc3-n1-checker/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())
        versions = [
            ver
            for ver, files in data.get("releases", {}).items()
            if files and not all(f.get("yanked", False) for f in files)
        ]
        CACHE[package] = tuple(versions)
        return CACHE[package]
    except Exception:
        return ()


def _latest_stable(versions: tuple[str, ...]) -> str | None:
    """Return the highest non-pre-release version string."""
    stable = [v for v in versions if not re.search(r"[a-zA-Z]", v)]
    if not stable:
        return None
    return max(stable, key=_parse_version)


def _check_n1(pinned_str: str, latest_str: str) -> Status:
    """Classify how far behind pinned is from latest."""
    p = _parse_version(pinned_str)
    lat = _parse_version(latest_str)
    if p >= lat:
        return Status.COMPLIANT
    major_diff = lat[0] - p[0]
    if major_diff >= 2:
        return Status.BLOCKER
    if major_diff == 1:
        return Status.CRITICAL
    minor_diff = lat[1] - p[1]
    if minor_diff >= 2:
        return Status.WARNING
    return Status.COMPLIANT


def _parse_requirements(path: Path) -> list[tuple[str, str | None]]:
    """Return list of (package_name, pinned_version_or_None)."""
    results = []
    with open(path) as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            if line.startswith("-") and not line.startswith("-r"):
                continue
            # Remove inline comments
            line = line.split(" #")[0].strip()
            # Exact pin: package==1.2.3
            exact = re.match(r"^([A-Za-z0-9_.\-]+)==([^\s,;]+)", line)
            if exact:
                results.append((exact.group(1), exact.group(2)))
                continue
            # Any other specifier — treat as unpinned for N-1 purposes
            name_only = re.match(r"^([A-Za-z0-9_.\-]+)", line)
            if name_only:
                results.append((name_only.group(1), None))
    return results


def check_file(req_file: Path, rate_limit_pause: float = 0.15) -> list[Finding]:
    """Run N-1 checks on a single requirements file."""
    findings: list[Finding] = []
    packages = _parse_requirements(req_file)

    for pkg, pinned in packages:
        time.sleep(rate_limit_pause)  # polite rate limiting

        if pinned is None:
            findings.append(
                Finding(
                    package=pkg,
                    pinned="(unpinned)",
                    latest="unknown",
                    status=Status.UNPINNED,
                    message="No exact version pin — N-1 cannot be verified. Pin to exact version.",
                    requirement_file=str(req_file),
                ),
            )
            continue

        versions = _get_latest_versions(pkg)
        if not versions:
            findings.append(
                Finding(
                    package=pkg,
                    pinned=pinned,
                    latest="unknown",
                    status=Status.UNKNOWN,
                    message="PyPI lookup failed — verify manually.",
                    requirement_file=str(req_file),
                ),
            )
            continue

        latest = _latest_stable(versions)
        if latest is None:
            findings.append(
                Finding(
                    package=pkg,
                    pinned=pinned,
                    latest="unknown",
                    status=Status.UNKNOWN,
                    message="No stable release found on PyPI.",
                    requirement_file=str(req_file),
                ),
            )
            continue

        status = _check_n1(pinned, latest)
        p_tuple = _parse_version(pinned)
        l_tuple = _parse_version(latest)
        major_diff = l_tuple[0] - p_tuple[0]
        minor_diff = l_tuple[1] - p_tuple[1] if major_diff == 0 else 0

        if status == Status.COMPLIANT:
            msg = f"✅ {pinned} (latest {latest}) — N-1 compliant"
        elif status == Status.WARNING:
            msg = f"⚠️  {pinned} (latest {latest}) — {minor_diff} minor version(s) behind (N-1 WARNING: update within 30 days)"
        elif status == Status.CRITICAL:
            msg = f"🚨 {pinned} (latest {latest}) — {major_diff} major version behind (N-1 CRITICAL: upgrade immediately)"
        else:  # BLOCKER
            msg = f"🔴 {pinned} (latest {latest}) — {major_diff} major versions behind (N-1 BLOCKER: must upgrade before merge)"

        findings.append(
            Finding(
                package=pkg,
                pinned=pinned,
                latest=latest,
                status=status,
                message=msg,
                requirement_file=str(req_file),
            ),
        )

    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="N-1 Dependency Compliance Checker")
    parser.add_argument("files", nargs="*", help="requirements*.txt files to check")
    parser.add_argument("--all", action="store_true", help="scan all requirements*.txt in cwd")
    parser.add_argument("--json", action="store_true", dest="as_json", help="output JSON report")
    parser.add_argument("--exit-code", action="store_true", help="exit 1 on CRITICAL/BLOCKER")
    parser.add_argument("--root", default=".", help="project root directory")
    args = parser.parse_args()

    root = Path(args.root)
    target_files: list[Path] = []

    if args.all:
        target_files = sorted(root.glob("requirements*.txt")) + sorted(
            root.glob("*/requirements*.txt"),
        )
    elif args.files:
        target_files = [Path(f) for f in args.files]
    else:
        default = root / "requirements.txt"
        if default.exists():
            target_files = [default]
        else:
            print("No requirements files specified. Use --all or pass file paths.", file=sys.stderr)
            return 2

    target_files = [f for f in target_files if f.exists()]
    if not target_files:
        print("No requirements files found.", file=sys.stderr)
        return 2

    import datetime

    report = Report(
        scanned_at=datetime.datetime.now(datetime.UTC).isoformat().replace("+00:00", "Z"),
        files=[str(f) for f in target_files],
    )

    for req_file in target_files:
        print(f"\n📦 Scanning {req_file} ...", file=sys.stderr)
        report.findings.extend(check_file(req_file))

    if args.as_json:
        output = {
            "scanned_at": report.scanned_at,
            "files": report.files,
            "summary": {
                "total": len(report.findings),
                "blockers": len(report.blockers),
                "critical": len(report.criticals),
                "warnings": len(report.warnings),
                "compliant": len(report.passed),
            },
            "findings": [
                {
                    "package": f.package,
                    "pinned": f.pinned,
                    "latest": f.latest,
                    "status": f.status.value,
                    "message": f.message,
                    "file": f.requirement_file,
                }
                for f in report.findings
            ],
        }
        print(json.dumps(output, indent=2))
    else:
        print(f"\n{'=' * 60}")
        print("N-1 DEPENDENCY COMPLIANCE REPORT")
        print(f"Scanned: {report.scanned_at}")
        print(f"{'=' * 60}")

        for status_group, label in [
            (report.blockers, "🔴 BLOCKERS"),
            (report.criticals, "🚨 CRITICAL"),
            (report.warnings, "⚠️  WARNINGS"),
            (report.passed, "✅ COMPLIANT"),
        ]:
            if status_group:
                print(f"\n{label} ({len(status_group)})")
                print("-" * 40)
                for f in status_group:
                    print(f"  [{f.requirement_file}] {f.message}")

        print(f"\n{'=' * 60}")
        print(f"SUMMARY: {report.summary()}")
        print(f"{'=' * 60}")

    violations = len(report.blockers) + len(report.criticals)
    if args.exit_code and violations > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
