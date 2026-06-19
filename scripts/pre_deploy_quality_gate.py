#!/usr/bin/env python3
"""Pre-deploy quality gate — fails only on CRITICAL issues (not all IDE warnings).

The IDE problem panel (~800+) mixes mypy stubs, bandit LOW, and ruff style.
Production deploy is blocked only when this script exits non-zero.

Usage:
  python scripts/pre_deploy_quality_gate.py
  python scripts/pre_deploy_quality_gate.py --cloud-only   # skip Citadel compose (Fly/CLOUD_ONLY)
  python scripts/pre_deploy_quality_gate.py --security-only  # bandit + ruff + security pytest (no smoke/stack)
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
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
        "--security-only",
        action="store_true",
        help="Security phase gate: skip smoke/stack pytest; run SSRF + zero-cost tests only",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print tool output when checks fail",
    )
    args = parser.parse_args()
    cloud_only = args.cloud_only or _cloud_only_mode()
    security_only = args.security_only

    failures: list[str] = []

    gate_tools = "pytest pytest-asyncio ruff bandit pip-audit"
    for mod, label in (
        ("pytest", "pytest"),
        ("pytest_asyncio", "pytest-asyncio"),
        ("ruff", "ruff"),
    ):
        if not _module_ok(mod):
            failures.append(
                f"Missing {label} — run: {sys.executable} -m pip install {gate_tools}"
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
        # Windows: docker-compose.production.yml uses UTF-8 (em-dash); avoid cp1252 decode errors
        "PYTHONUTF8": "1",
    }
    if security_only:
        pytest_targets = [
            "tests/test_url_validation.py",
            "tests/test_zero_cost_registry.py",
            "tests/test_adaptive_rotator.py",
            "tests/test_p0_health_syntax.py",
            "tests/test_infrastructure_mode.py",
        ]
    else:
        pytest_targets = [
            "tests/test_smoke.py",
            "tests/test_api_startup_readiness.py",
            "tests/test_production_readiness_stack.py",
            "tests/test_p0_health_syntax.py",
            "tests/test_p0_metrics_mount.py",
            "tests/test_live_deploy_contract.py",
            "tests/test_infrastructure_mode.py",
            "tests/test_adaptive_rotator.py",
            "tests/test_url_validation.py",
            "tests/test_zero_cost_registry.py",
        ]
    tests = _run(
        [sys.executable, "-m", "pytest", *pytest_targets, "-q", "--tb=short"],
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
            "--select",
            "E,F,W",
            "--ignore",
            "E501",
            "--exit-zero",
        ],
        check=False,
    )
    if ruff.stdout.strip():
        print("Ruff findings (CI: warn-only):", file=sys.stderr)
        if args.verbose:
            print(ruff.stdout[:2000])

    bandit_paths = [
        "src/",
        "api.py",
        "workers/infinity-auth",
        "workers/infinity-ws",
        "workers/api-gateway",
    ]
    bandit_report = ROOT / "logs" / "bandit-results.json"
    bandit_report.parent.mkdir(parents=True, exist_ok=True)
    # Match .forgejo/workflows/security-scan.yml (no -ll; medium+ severity and confidence)
    bandit_args = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        *bandit_paths,
        "-f",
        "json",
        "-o",
        str(bandit_report),
        "--severity-level",
        "medium",
        "--confidence-level",
        "medium",
    ]
    _run([*bandit_args, "--exit-zero"], check=False)
    bandit = _run(bandit_args, check=False)
    high: list[dict] = []
    medium_plus: list[dict] = []

    def _bandit_results_from_payload(data: dict) -> None:
        for r in data.get("results", []):
            sev = r.get("issue_severity")
            conf = r.get("issue_confidence")
            if sev in ("HIGH", "MEDIUM") and conf in ("HIGH", "MEDIUM"):
                medium_plus.append(r)
            if sev == "HIGH" and conf in ("HIGH", "MEDIUM"):
                high.append(r)

    bandit_data: dict | None = None
    if bandit_report.is_file():
        try:
            bandit_data = json.loads(bandit_report.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            bandit_data = None
    if bandit_data is None and bandit.stdout.strip():
        try:
            bandit_data = json.loads(bandit.stdout)
        except json.JSONDecodeError:
            bandit_data = None
    if bandit_data is not None:
        _bandit_results_from_payload(bandit_data)
    elif bandit.returncode not in (0, 1):
        failures.append("bandit not available (optional)")

    if bandit.returncode != 0 or medium_plus:
        failures.append(
            f"Bandit CI scope: {len(medium_plus)} medium+ issue(s) (exit {bandit.returncode})"
        )
        for r in medium_plus[:10]:
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
                print(
                    f"pip-audit: {vuln_count} known CVE(s) (CI: warn-only)",
                    file=sys.stderr,
                )
                if args.verbose and audit.stdout:
                    print(audit.stdout[:1500])
        except json.JSONDecodeError:
            pass

    if not cloud_only and not security_only:
        compose = _run([sys.executable, "scripts/citadel_compose_validate.py"])
        if compose.returncode != 0:
            failures.append("citadel_compose_validate failed")
            failures.append(_tail(compose.stdout + "\n" + compose.stderr))
    elif cloud_only:
        print("(cloud-only: skipping docker-compose validation)", file=sys.stderr)
    elif security_only:
        print("(security-only: skipping docker-compose validation)", file=sys.stderr)

    print("Pre-deploy quality gate")
    print("=" * 40)
    LOGS = ROOT / "logs"
    LOGS.mkdir(parents=True, exist_ok=True)
    gate_payload = {
        "passed": len(failures) == 0,
        "pytest_ok": tests.returncode == 0,
        "bandit_high": len(high),
        "bandit_issues": [
            {
                "test_id": r.get("test_id"),
                "filename": r.get("filename"),
                "line_number": r.get("line_number"),
            }
            for r in high[:20]
        ],
        "cloud_only": cloud_only,
        "security_only": security_only,
        "timestamp": time.time(),
    }
    (LOGS / "pre_deploy_gate.json").write_text(
        json.dumps(gate_payload, indent=2),
        encoding="utf-8",
    )
    if failures:
        print("BLOCKED — fix before deploy:")
        for f in failures:
            print(f)
        print()
        print("Tip: CLOUD_ONLY deploy — scripts/deploy_cloud.py --skip-gate is not recommended.")
        print(f"Re-run with details: {sys.executable} scripts/pre_deploy_quality_gate.py --cloud-only -v")
        return 1

    mode_parts = []
    if security_only:
        mode_parts.append("security-only")
    if cloud_only:
        mode_parts.append("CLOUD_ONLY")
    mode = ", ".join(mode_parts) if mode_parts else "full"
    print(f"PASS — no critical blockers for P0 deploy ({mode})")
    print("(Remaining IDE warnings may be stub routes / style — not deploy blockers)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
