#!/usr/bin/env python3
"""Phase 0: capture security baseline artifacts for SECURITY_ALERT_REGISTER closure tracking."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"
REGISTER = ROOT / "SECURITY_ALERT_REGISTER.md"


def _run(cmd: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        cmd,
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _bandit_summary() -> dict:
    paths = [
        "src/",
        "api.py",
        "workers/infinity-auth",
        "workers/infinity-ws",
        "workers/api-gateway",
    ]
    proc = _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            *paths,
            "-f",
            "json",
            "--severity-level",
            "medium",
            "--confidence-level",
            "medium",
        ]
    )
    high = medium = low = 0
    if proc.returncode in (0, 1) and proc.stdout.strip():
        try:
            data = json.loads(proc.stdout)
            for r in data.get("results", []):
                sev = r.get("issue_severity", "")
                if sev == "HIGH":
                    high += 1
                elif sev == "MEDIUM":
                    medium += 1
                elif sev == "LOW":
                    low += 1
        except json.JSONDecodeError:
            pass
    return {
        "returncode": proc.returncode,
        "high": high,
        "medium": medium,
        "low": low,
        "available": proc.returncode not in (127, 2) or bool(proc.stdout or proc.stderr),
    }


def _register_status() -> dict:
    text = REGISTER.read_text(encoding="utf-8") if REGISTER.is_file() else ""
    return {
        "exists": REGISTER.is_file(),
        "has_fix_fp_accept_suppress": all(
            token in text for token in ("FIX", "FP", "ACCEPT", "SUPPRESS")
        ),
        "hostipc_documented": (ROOT / "docs" / "HOSTIPC_RISK_ACCEPTANCE.md").is_file(),
    }


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    baseline = {
        "phase": 0,
        "timestamp": time.time(),
        "register": _register_status(),
        "bandit": _bandit_summary(),
        "trivyignore_lines": sum(
            1
            for line in (ROOT / ".trivyignore").read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.strip().startswith("#")
        )
        if (ROOT / ".trivyignore").is_file()
        else 0,
        "honest_note": "Local snapshot; Forgejo live alerts may differ until CI sync.",
    }
    out = LOGS / "phase0_baseline.json"
    out.write_text(json.dumps(baseline, indent=2), encoding="utf-8")
    print(json.dumps(baseline, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
