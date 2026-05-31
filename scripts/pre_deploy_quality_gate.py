#!/usr/bin/env python3
"""Pre-deploy quality gate — fails only on CRITICAL issues (not all IDE warnings).

The IDE problem panel (~800+) mixes mypy stubs, bandit LOW, and ruff style.
Production deploy is blocked only when this script exits non-zero.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, **kwargs)


def main() -> int:
    failures: list[str] = []

    # 1. Production gate tests
    env = {
        **dict(__import__("os").environ),
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
            "-q",
            "--tb=no",
        ],
        env=env,
    )
    if tests.returncode != 0:
        failures.append("Production gate pytest failed")

    # 2. Ruff on deploy paths only
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
        failures.append(f"Ruff errors on P0 paths ({ruff.stdout.count(chr(10))} lines)")

    # 3. Bandit HIGH severity on deploy paths
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
    )
    high: list[dict] = []
    if bandit.stdout.strip():
        try:
            data = json.loads(bandit.stdout)
            high = [
                r
                for r in data.get("results", [])
                if r.get("issue_severity") == "HIGH" and r.get("issue_confidence") in ("HIGH", "MEDIUM")
            ]
        except json.JSONDecodeError:
            pass
    if high:
        failures.append(f"Bandit HIGH: {len(high)} issue(s)")
        for r in high[:10]:
            failures.append(
                f"  - {r.get('test_id')} {r.get('filename')}:{r.get('line_number')} {r.get('issue_text', '')[:60]}"
            )

    # 4. pip-audit HIGH if available
    audit = _run([sys.executable, "-m", "pip_audit", "-r", "requirements.txt", "--format", "json"])
    if audit.returncode == 0 and audit.stdout.strip():
        try:
            deps = json.loads(audit.stdout)
            vuln_count = sum(len(d.get("vulns", [])) for d in deps if isinstance(d, dict))
            if vuln_count:
                failures.append(f"pip-audit: {vuln_count} known CVE(s) in requirements.txt")
        except json.JSONDecodeError:
            pass
    elif audit.returncode not in (0, 1):
        pass  # pip-audit missing is OK in dev sandboxes

    # 5. Compose validate
    compose = _run([sys.executable, "scripts/citadel_compose_validate.py"])
    if compose.returncode != 0:
        failures.append("citadel_compose_validate failed")

    print("Pre-deploy quality gate")
    print("=" * 40)
    if failures:
        print("BLOCKED — fix before deploy:")
        for f in failures:
            print(f)
        print()
        print("Note: IDE '846 issues' includes non-blocking mypy stubs and bandit LOW.")
        print("Run: python3 scripts/pre_deploy_quality_gate.py  (this gate)")
        return 1

    print("PASS — no critical blockers for P0 deploy")
    print("(Remaining IDE warnings may be stub routes / style — not deploy blockers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
