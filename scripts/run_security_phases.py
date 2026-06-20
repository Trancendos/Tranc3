#!/usr/bin/env python3
"""Run security phases 0–6 locally (register → gates → scorecard).

Usage:
  python scripts/run_security_phases.py
  python scripts/run_security_phases.py --cloud-only
  python scripts/run_security_phases.py --min-security-percent 90
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(label: str, cmd: list[str], *, env: dict | None = None) -> int:
    print(f"\n=== {label} ===", flush=True)
    proc = subprocess.run(cmd, cwd=ROOT, env=env)  # nosec B603 — list args, no shell=True
    if proc.returncode != 0:
        print(f"FAILED: {label} (exit {proc.returncode})", file=sys.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Orchestrate security phases 0–6")
    parser.add_argument(
        "--cloud-only",
        action="store_true",
        help="Pass --cloud-only to pre_deploy_quality_gate (skip compose)",
    )
    parser.add_argument(
        "--min-security-percent",
        type=float,
        default=90.0,
        help="Fail if Security dimension score is below this (default 90)",
    )
    parser.add_argument(
        "--skip-zero-cost-audit",
        action="store_true",
        help="Skip zero_cost_audit.py (optional smoke)",
    )
    args = parser.parse_args()

    py = sys.executable
    failures = 0

    # Phase 0 — baseline artifacts
    failures += _run("Phase 0: security baseline", [py, "scripts/phase0_security_baseline.py"])

    # Phase 2 — SSRF / zero-cost / rotator tests
    failures += _run(
        "Phase 2: security pytest suite",
        [
            py,
            "-m",
            "pytest",
            "tests/test_url_validation.py",
            "tests/test_zero_cost_registry.py",
            "tests/test_adaptive_rotator.py",
            "-q",
            "--tb=short",
        ],
    )

    # Phase 6 — pre-deploy gate (bandit HIGH blocks)
    gate_cmd = [py, "scripts/pre_deploy_quality_gate.py", "--security-only"]
    if args.cloud_only:
        gate_cmd.append("--cloud-only")
    failures += _run("Phase 6: pre-deploy quality gate", gate_cmd)

    # Phase 4 — security dimension
    failures += _run(
        "Phase 4: security dimension score",
        [py, "scripts/security_score.py", "--min-percent", str(args.min_security_percent)],
    )

    # Production readiness (includes security dimension wiring)
    failures += _run(
        "Phase 4: production readiness scorecard",
        [py, "scripts/production_readiness_score.py"],
    )

    if not args.skip_zero_cost_audit:
        failures += _run("Phase 5: zero-cost audit", [py, "scripts/zero_cost_audit.py"])

    print("\n=== Summary ===")
    if failures:
        print(f"BLOCKED: {failures} step(s) failed", file=sys.stderr)
        return 1
    print("PASS — all security phase steps completed")
    print(
        f"Artifacts: {ROOT / 'logs'}/security_score.json, pre_deploy_gate.json, phase0_baseline.json"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
