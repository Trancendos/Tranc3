#!/usr/bin/env python3
"""Pre-deploy quality gate — fails only on CRITICAL issues (not all IDE warnings).

The IDE problem panel (~800+) mixes mypy stubs, bandit LOW, and ruff style.
Production deploy is blocked only when this script exits non-zero.

Usage:
  python scripts/pre_deploy_quality_gate.py
  python scripts/pre_deploy_quality_gate.py --cloud-only   # skip Citadel compose (Fly/CLOUD_ONLY)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kwargs)


def _module_ok(module: str) -> bool:
    r = _run([sys.executable, "-c", f"import {module}"], check=False)
    return r.returncode == 0


def _cloud_only_mode() -> bool:
    if os.environ.get("PRE_DEPLOY_CLOUD_ONLY", "").lower() in ("1", "true", "yes"):
        return True
    try:
        sys.path.insert(0, str(ROOT))
        from src.platform.infrastructure_mode import is_cloud_only

        return is_cloud_only()
    except Exception:
        return os.environ.get("PLATFORM_INFRA_MODE", "CLOUD_ONLY").upper() == "CLOUD_ONLY"


def _tail(text: str, lines: int = 25) -> str:
    parts = (text or "").strip().splitlines()
    if not parts:
        return "(no output)"
    return "\n".join(parts[-lines:])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--cloud-only",
        action="store_true",
        help="CLOUD_ONLY / Fly deploy: skip docker-compose validation",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print tool output when checks fail",
    )
    args = parser.parse_args()
    cloud_only = args.cloud_only or _cloud_only_mode()

    failures: list[str] = []

    for mod, label in (("pytest", "pytest"), ("ruff", "ruff")):
        if not _module_ok(mod):
            failures.append(
                f"Missing {label} — run: {sys.executable} -m pip install {label} pytest ruff bandit pip-audit"
            )

    if failures:
        print("Pre-deploy quality gate")
        print("=" * 40)
        print("BLOCKED — fix before deploy:")
        for f in failures:
            print(f)
        return 1

    env = {
        **dict(os.environ),
        "SECRET_KEY": "a" * 32,
        "JWT_SECRET": "b" * 32,
        "DATABASE_URL": "sqlite:///./test.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "ENVIRONMENT": "test",
    }
    tests = _run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/test_smoke.py",
            "tests/test_api_startup_readiness.py",
            "tests/test_production_readiness_stack.py",
            "tests/test_p0_health_syntax.py",
            "tests/test_p0_metrics_mount.py",
            "tests/test_live_deploy_contract.py",
            "tests/test_infrastructure_mode.py",
            "tests/test_adaptive_rotator.py",
            "-q",
            "--tb=short",
        ],
        env=env,
    )
    if tests.returncode != 0:
        failures.append("Production gate pytest failed")
        failures.append("--- pytest (last lines) ---")
        failures.append(_tail(tests.stdout + "\n" + tests.stderr))

    ruff = _run(
        [
            sys.executable,
            "-m",
            "ruff",
            "check",
            "src/",
            "api.py",
            "workers/infinity-auth",
            "workers/infinity-ws",
            "workers/api-gateway",
            "workers/tranc3-ai",
            "workers/infinity-void",
            "workers/users-service",
            "workers/products-service",
            "workers/orders-service",
            "workers/payments-service",
            "workers/notifications",
            "workers/infinity-ai",
            "workers/monitoring",
        ],
    )
    if ruff.returncode != 0:
        detail = ruff.stdout.strip() or ruff.stderr.strip() or "ruff check failed (no output)"
        failures.append(f"Ruff errors on P0 paths: {detail[:500]}")

    bandit = _run(
        [
            sys.executable,
            "-m",
            "bandit",
            "-r",
            "src/",
            "api.py",
            "workers/infinity-auth",
            "workers/infinity-ws",
            "workers/api-gateway",
            "workers/tranc3-ai",
            "workers/infinity-void",
            "workers/users-service",
            "workers/products-service",
            "workers/orders-service",
            "workers/payments-service",
            "workers/notifications",
            "workers/infinity-ai",
            "workers/monitoring",
            "-f",
            "json",
            "-ll",
        ],
        check=False,
    )
    high: list[dict] = []
    if bandit.returncode in (0, 1) and bandit.stdout.strip():
        try:
            data = json.loads(bandit.stdout)
            high = [
                r
                for r in data.get("results", [])
                if r.get("issue_severity") == "HIGH"
                and r.get("issue_confidence") in ("HIGH", "MEDIUM")
            ]
        except json.JSONDecodeError:
            pass
    elif bandit.returncode not in (0, 1):
        failures.append("bandit not available (optional)")

    if high:
        failures.append(f"Bandit HIGH: {len(high)} issue(s)")
        for r in high[:10]:
            failures.append(
                f"  - {r.get('test_id')} {r.get('filename')}:{r.get('line_number')} "
                f"{r.get('issue_text', '')[:60]}"
            )

    audit = _run(
        [sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "--format", "json"],
        check=False,
    )
    if audit.returncode == 0 and audit.stdout.strip():
        try:
            deps = json.loads(audit.stdout)
            vuln_count = sum(len(d.get("vulns", [])) for d in deps if isinstance(d, dict))
            if vuln_count:
                failures.append(f"pip-audit: {vuln_count} known CVE(s) in requirements.txt")
        except json.JSONDecodeError:
            pass

    if not cloud_only:
        compose = _run([sys.executable, "scripts/citadel_compose_validate.py"])
        if compose.returncode != 0:
            failures.append("citadel_compose_validate failed")
            failures.append(_tail(compose.stdout + "\n" + compose.stderr))
    else:
        print("(cloud-only: skipping docker-compose validation)", file=sys.stderr)

    print("Pre-deploy quality gate")
    print("=" * 40)
    if failures:
        print("BLOCKED — fix before deploy:")
        for f in failures:
            print(f)
        print()
        print("Tip: CLOUD_ONLY deploy — scripts/deploy_cloud.py --skip-gate is not recommended.")
        print(f"Re-run with details: {sys.executable} scripts/pre_deploy_quality_gate.py --cloud-only -v")
        return 1

    mode = "CLOUD_ONLY" if cloud_only else "full"
    print(f"PASS — no critical blockers for P0 deploy ({mode})")
    print("(Remaining IDE warnings may be stub routes / style — not deploy blockers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
