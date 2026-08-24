#!/usr/bin/env python3
"""Zero-cost dependency audit — pip-audit when available, else requirements sanity check."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ROOT / "requirements.txt"
LOGS = ROOT / "logs"
PIN_PATTERN = re.compile(r"^([A-Za-z0-9_.-]+)==([0-9.]+)")


def _unpinned_packages() -> list[str]:
    unpinned: list[str] = []
    for line in REQUIREMENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("-") or "://" in line:
            continue
        if "==" not in line and ">=" not in line and "~=" not in line:
            name = line.split("[")[0].strip()
            if name:
                unpinned.append(name)
    return unpinned


def _run_pip_audit() -> tuple[int, dict]:
    """Audit the root requirements, treating "found something" as a result.

    Two things were wrong here, and only the second one mattered.

    `pip-audit` was invoked as a bare binary name resolved through PATH; it is now
    `sys.executable -m pip_audit`, tying the audit to the interpreter that resolved
    the install, the way vulnerability_census.py already does.

    The real defect: **pip-audit exits non-zero when it finds a vulnerability.**
    That is success, not failure -- it is the whole point of running it. The old
    code used `check_output`, so any finding raised `CalledProcessError`, and the
    handler threw away the complete JSON report sitting in `exc.stdout` and
    returned -1. The script therefore only produced data when there was nothing to
    report, and degraded to "unavailable" the moment it had something to say. In
    the production gate, where the step is wrapped in `|| true`, that meant a green
    check writing an empty audit on every run.

    stdout and stderr are captured separately now. They used to be merged, which
    put pip-audit's human summary line ("Found 1 known vulnerability...") in front
    of the JSON and would have broken the parse even once the exit code was handled.
    """
    try:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip_audit",
                "-r",
                str(REQUIREMENTS),
                "--format",
                "json",
                "--desc",
                "on",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return -1, {"tool": "none", "message": f"pip_audit could not be run: {exc}"}

    # 0 = clean, 1 = vulnerabilities found. Both carry a full report on stdout.
    # Anything else is a real failure (bad arguments, unreadable manifest, network).
    if proc.returncode not in (0, 1):
        return -1, {
            "tool": "pip-audit",
            "error": (proc.stderr or proc.stdout)[:2000],
            "returncode": proc.returncode,
        }
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        return -1, {"tool": "pip-audit", "error": f"unparseable report: {exc}"}

    vulns = data if isinstance(data, list) else data.get("dependencies", data)
    count = 0
    if isinstance(vulns, list):
        for dep in vulns:
            count += len(dep.get("vulns", []) or [])
    return count, {"tool": "pip-audit", "raw_count": count, "details": vulns}


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    unpinned = _unpinned_packages()
    vuln_count, audit_payload = _run_pip_audit()

    report = {
        "requirements": str(REQUIREMENTS),
        "unpinned_packages": unpinned,
        "vulnerability_count": vuln_count,
        "audit": audit_payload,
    }
    out_path = LOGS / "dependency_audit.json"
    out_path.write_text(json.dumps(report, indent=2))

    if unpinned:
        print(f"WARN: {len(unpinned)} unpinned packages (pin with == for reproducible builds)")
        for pkg in unpinned[:15]:
            print(f"  - {pkg}")

    if vuln_count < 0:
        print("dependency_audit: pip-audit unavailable — install with: pip install pip-audit")
        print(f"Wrote {out_path}")
        return 0 if not unpinned else 1

    if vuln_count > 0:
        # Reported, not judged. This is a raw pip-audit count over one manifest with
        # no notion of disposition: the single finding today is `ecdsa`
        # PYSEC-2026-1325, which has no patched release and is accepted in
        # SECURITY_ALERT_REGISTER.md. Failing on it would mean a permanently red
        # check for a risk somebody already reviewed and signed off -- and a check
        # that is always red is a check nobody reads.
        #
        # scripts/vulnerability_census.py is the authority for the verdict: it
        # classifies fixable / accepted / blocked against the register, covers the
        # whole estate rather than one file, and is what the production gate calls
        # with --check. This script's job is the artefact and the unpinned-package
        # check, which is something it *can* evaluate on its own.
        print(f"{vuln_count} known vulnerabilities recorded — see {out_path}")
        print("Verdict comes from scripts/vulnerability_census.py --check, not this count.")
        return 0 if not unpinned else 1

    print(f"dependency_audit OK (0 known vulns in pip-audit). Wrote {out_path}")
    return 0 if not unpinned else 1


if __name__ == "__main__":
    sys.exit(main())
