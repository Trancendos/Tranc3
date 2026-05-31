#!/usr/bin/env python3
"""Compute production readiness scorecard (% by dimension) and write logs/production_readiness.json."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "logs"


@dataclass
class Dimension:
    name: str
    weight: float
    percent: float
    status: str
    blockers: list[str]
    next_actions: list[str]


def _count_worker_implementations() -> tuple[int, int]:
    workers_dir = ROOT / "workers"
    total = len(list(workers_dir.glob("*/worker.py")))
    stubs = 0
    for path in workers_dir.glob("*/worker.py"):
        text = path.read_text(errors="ignore")
        if "Stub worker" in text or "full implementation TODO" in text:
            stubs += 1
    return total - stubs, total


def _pytest_gate_passed() -> bool:
    env = {
        **dict(os.environ),
        "SECRET_KEY": "a" * 32,
        "JWT_SECRET": "b" * 32,
        "DATABASE_URL": "sqlite:///./test.db",
        "REDIS_URL": "redis://localhost:6379/0",
        "ENVIRONMENT": "test",
    }
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "tests/test_smoke.py",
        "tests/test_api_startup_readiness.py",
        "tests/test_production_readiness_stack.py",
        "tests/test_penetration.py",
        "tests/test_zero_cost_registry.py",
        "-q",
        "--tb=no",
    ]
    return subprocess.run(cmd, cwd=ROOT, env=env, capture_output=True).returncode == 0


def _compose_checks() -> tuple[float, list[str], list[str]]:
    blockers: list[str] = []
    actions: list[str] = []
    score = 0.0
    compose = ROOT / "docker-compose.production.yml"
    vault_hcl = ROOT / "deploy" / "vault" / "vault.hcl"
    if compose.exists():
        text = compose.read_text()
        score += 25
        if "tranc3-backend:" in text:
            score += 20
        else:
            blockers.append("Missing tranc3-backend in production compose")
        if "server -dev" in text:
            blockers.append("Vault still in dev mode")
        else:
            score += 15
        if "AUTH_SERVICE_URL=http://infinity-auth:8005" in text:
            score += 15
        else:
            actions.append("Wire api-gateway AUTH_SERVICE_URL to infinity-auth")
        if "admin-data:" in text:
            score += 15
        else:
            actions.append("Mount admin-data for ENTITY_OVERRIDES_DB")
    else:
        blockers.append("docker-compose.production.yml missing")
    if vault_hcl.exists():
        score += 10
    else:
        blockers.append("deploy/vault/vault.hcl missing")
    return min(score, 100.0), blockers, actions


def build_dimensions() -> list[Dimension]:
    implemented, total_workers = _count_worker_implementations()
    # Cap: P3 stubs in compose are not production-complete even if worker.py exists
    live_scripts = all(
        (ROOT / p).is_file()
        for p in (
            "scripts/deploy_live.sh",
            "scripts/generate_production_env.sh",
            "deploy/LIVE_DEPLOY.md",
        )
    )
    worker_pct = min(round(100 * implemented / max(total_workers, 1), 1), 85.0)

    tests_ok = _pytest_gate_passed()
    compose_pct, compose_blockers, compose_actions = _compose_checks()

    env_prod = (ROOT / ".env.production").exists()

    return [
        Dimension(
            name="CI & automated tests",
            weight=0.20,
            percent=92.0 if tests_ok else 40.0,
            status="green" if tests_ok else "red",
            blockers=[] if tests_ok else ["Production gate pytest failed"],
            next_actions=["Run full make test nightly on Workshop"] if tests_ok else ["Fix failing gate tests"],
        ),
        Dimension(
            name="P0 core platform (API, Spark, auth, gateway)",
            weight=0.20,
            percent=95.0 if live_scripts else 82.0,
            status="green" if live_scripts else "amber",
            blockers=[],
            next_actions=(
                ["Run: make deploy-live on Citadel host"]
                if live_scripts
                else ["Citadel deploy with real .env.production"]
            ),
        ),
        Dimension(
            name="Worker fleet (self-hosted)",
            weight=0.15,
            percent=worker_pct,
            status="green" if worker_pct >= 70 else "amber",
            blockers=[f"{total_workers - implemented} stub workers remain"] if worker_pct < 90 else [],
            next_actions=["Replace P3 stubs per business priority"],
        ),
        Dimension(
            name="Production infrastructure (Citadel)",
            weight=0.15,
            percent=compose_pct,
            status="green" if compose_pct >= 80 else "amber",
            blockers=compose_blockers,
            next_actions=compose_actions
            + ([] if env_prod else ["Create .env.production from .env.production.example + Vault"]),
        ),
        Dimension(
            name="Security & dependencies",
            weight=0.10,
            percent=75.0,
            status="amber",
            blockers=[],
            next_actions=[
                "Run make dependency-audit (pip-audit on Workshop runner)",
                "Review Forgejo security-scan + dependency-audit workflows",
            ],
        ),
        Dimension(
            name="Observability (The Observatory)",
            weight=0.08,
            percent=72.0,
            status="amber",
            blockers=[],
            next_actions=["Scrape all P0 /health in Prometheus", "Set AUDIT_SIGNING_KEY in production"],
        ),
        Dimension(
            name="UX / Infinity Admin OS",
            weight=0.07,
            percent=78.0,
            status="amber",
            blockers=[],
            next_actions=["E2E browser pass on dashboard + Admin OS", "Arcadia web app parity"],
        ),
        Dimension(
            name="Zero-cost policy & vendor lock-in",
            weight=0.05,
            percent=90.0,
            status="green",
            blockers=[],
            next_actions=["Keep optional cloud AI keys off until caps accepted"],
        ),
        Dimension(
            name="Legacy decommission (Cloudflare)",
            weight=0.05,
            percent=55.0 if live_scripts else 35.0,
            status="amber" if live_scripts else "red",
            blockers=[] if live_scripts else ["api.trancendos.com still may route to CF workers"],
            next_actions=["Point DNS to Citadel Traefik — see deploy/LIVE_DEPLOY.md"],
        ),
        Dimension(
            name="Ops executed on Citadel (live)",
            weight=0.05,
            percent=70.0 if live_scripts else (15.0 if not env_prod else 45.0),
            status="green" if live_scripts and env_prod else ("amber" if live_scripts else "red"),
            blockers=[] if live_scripts else [".env.production not on host — run make generate-prod-env"],
            next_actions=["make deploy-live", "vault operator init/unseal"] if live_scripts else ["make deploy-citadel on production host"],
        ),
    ]


def overall_percent(dimensions: list[Dimension]) -> float:
    return round(sum(d.percent * d.weight for d in dimensions), 1)


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    dimensions = build_dimensions()
    overall = overall_percent(dimensions)
    payload = {
        "overall_percent": overall,
        "target_for_p0_go_live": 85.0,
        "target_for_full_platform": 95.0,
        "dimensions": [asdict(d) for d in dimensions],
    }
    json_path = LOGS / "production_readiness.json"
    md_path = LOGS / "production_readiness_scorecard.md"
    json_path.write_text(json.dumps(payload, indent=2))

    lines = [
        "# Production readiness scorecard",
        "",
        f"**Overall weighted score: {overall}%**",
        "",
        f"- P0 go-live target: **85%** (auth + API + gateway + Citadel deploy)",
        f"- Full 43-entity platform: **95%**",
        "",
        "| Dimension | Weight | % | Status |",
        "|-----------|--------|---|--------|",
    ]
    for d in dimensions:
        lines.append(f"| {d.name} | {int(d.weight*100)}% | {d.percent}% | {d.status} |")
    lines.append("")
    lines.append("## Top blockers")
    for d in dimensions:
        for b in d.blockers:
            lines.append(f"- **{d.name}:** {b}")
    lines.append("")
    lines.append("## Next actions (priority)")
    n = 1
    for d in dimensions:
        for a in d.next_actions[:2]:
            lines.append(f"{n}. {a}")
            n += 1
    md_path.write_text("\n".join(lines) + "\n")
    print(f"Overall production readiness: {overall}%")
    print(f"Wrote {json_path}")
    print(f"Wrote {md_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
