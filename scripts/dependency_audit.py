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
    try:
        out = subprocess.check_output(
            ["pip-audit", "-r", str(REQUIREMENTS), "--format", "json", "--desc", "on"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.STDOUT,
        )
        data = json.loads(out)
        vulns = data if isinstance(data, list) else data.get("dependencies", data)
        count = 0
        if isinstance(vulns, list):
            for dep in vulns:
                count += len(dep.get("vulns", []) or [])
        return count, {"tool": "pip-audit", "raw_count": count, "details": vulns}
    except FileNotFoundError:
        return -1, {"tool": "none", "message": "pip-audit not installed"}
    except subprocess.CalledProcessError as exc:
        return -1, {"tool": "pip-audit", "error": exc.stdout[:2000]}


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
        print(f"FAIL: {vuln_count} known vulnerabilities — see {out_path}")
        return 1

    print(f"dependency_audit OK (0 known vulns in pip-audit). Wrote {out_path}")
    return 0 if not unpinned else 1


if __name__ == "__main__":
    sys.exit(main())
