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


def _load_security_dimension():
    """Import compute_security_dimension without requiring scripts/ as a package."""
    import importlib.util

    path = ROOT / "scripts" / "security_score.py"
    spec = importlib.util.spec_from_file_location("security_score", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.compute_security_dimension


def _security_score_percent() -> tuple[float, list[str], list[str]]:
    """Repo-weighted security dimension from scripts/security_score.py."""
    try:
        compute = _load_security_dimension()
        dim = compute()
        pct = float(dim["score_percent"])
        blockers = [] if pct >= 90.0 else [f"Security score {pct}% < 90% target"]
        actions = [
            "Run: python scripts/security_score.py",
            "Resolve SECURITY_ALERT_REGISTER.md open items",
        ]
        if pct < 90.0:
            checks = dim.get("checks", {})
            failed = [k for k, v in checks.items() if v is False]
            if failed:
                actions.insert(0, f"Fix security checks: {', '.join(failed)}")
        return pct, blockers, actions if pct < 90.0 else ["Keep Forgejo security-scan green"]
    except Exception as exc:
        return 0.0, [f"security_score.py failed: {exc}"], ["Fix scripts/security_score.py"]


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
        "tests/test_url_validation.py",
        "tests/test_p0_health_syntax.py",
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
        text = compose.read_text(encoding="utf-8")
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


def _cloud_only_readiness() -> tuple[float, list[str], list[str]]:
    """Measured readiness of the cloud-only surface — Fly + Cloudflare + Pages.

    Every other dimension here scores the Citadel path, which is blocked on hardware
    funding. That made "are we ready to go live?" unanswerable for the path the
    platform can actually take today: a cloud-only deploy needs no owned hardware and
    is the mode CLAUDE.md names as the current default for every Location.

    This is a real measurement, not a constant: it shells out to cloud_preflight.py,
    which validates Fly app-name agreement, per-worker wrangler/lockfile presence and
    the frontend source, and scores from that result plus the runbook's existence.
    """
    blockers: list[str] = []
    actions: list[str] = []

    preflight = ROOT / "scripts" / "cloud_preflight.py"
    if not preflight.is_file():
        return 0.0, ["scripts/cloud_preflight.py missing"], ["Add the cloud preflight"]

    try:
        proc = subprocess.run(
            [sys.executable, str(preflight), "--json"],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=ROOT,
        )
        report = json.loads(proc.stdout or "{}")
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError) as exc:
        return 0.0, [f"cloud_preflight.py did not produce a report: {exc}"], []

    failures = report.get("failures") or []
    warnings = report.get("warnings") or []
    checks = report.get("checks") or []

    if failures:
        # Artifacts are broken — the deploy cannot start regardless of credentials.
        pct = max(20.0, 60.0 - 10.0 * len(failures))
        blockers.extend(failures)
    else:
        # Deployable. Withhold the last 15 points because nothing here proves a deploy
        # has actually been executed — same honesty the Citadel dimension applies.
        pct = 85.0 - 2.0 * len(warnings)
        actions.extend(warnings)

    if not (ROOT / "deploy" / "CLOUD_GO_LIVE.md").is_file():
        pct -= 10.0
        actions.append("Add deploy/CLOUD_GO_LIVE.md — the cloud-only runbook")

    if not checks:
        blockers.append("cloud_preflight.py reported no passing checks")

    actions.append("Execute the deploy: see deploy/CLOUD_GO_LIVE.md")
    return round(max(0.0, min(pct, 100.0)), 1), blockers, actions


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
    stub_count = total_workers - implemented

    tests_ok = _pytest_gate_passed()
    compose_pct, compose_blockers, compose_actions = _compose_checks()
    security_pct, security_blockers, security_actions = _security_score_percent()
    cloud_pct, cloud_blockers, cloud_actions = _cloud_only_readiness()

    env_prod = (ROOT / ".env.production").exists()
    # Honest live ops: scripts alone ≠ deployed stack (see forensic assessment).
    if env_prod:
        ops_pct = 35.0
        ops_status = "amber"
        ops_blockers = ["deploy-live success not verified in CI"]
    elif live_scripts:
        ops_pct = 12.0
        ops_status = "red"
        ops_blockers = [".env.production missing — run make generate-prod-env"]
    else:
        ops_pct = 5.0
        ops_status = "red"
        ops_blockers = ["Missing deploy_live.sh / generate_production_env.sh"]

    return [
        Dimension(
            name="CI & automated tests",
            weight=0.20,
            percent=92.0 if tests_ok else 40.0,
            status="green" if tests_ok else "red",
            blockers=[] if tests_ok else ["Production gate pytest failed"],
            next_actions=["Run full make test nightly on Workshop"]
            if tests_ok
            else ["Fix failing gate tests"],
        ),
        Dimension(
            name="P0 core platform (API, Spark, auth, gateway)",
            weight=0.18,
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
            weight=0.13,
            percent=worker_pct,
            status="green" if worker_pct >= 70 else "amber",
            blockers=[f"{stub_count} worker.py files marked stub/TODO"] if stub_count > 0 else [],
            next_actions=["Replace P3 stubs per business priority"],
        ),
        Dimension(
            name="Production infrastructure (Citadel)",
            weight=0.13,
            percent=compose_pct,
            status="green" if compose_pct >= 80 else "amber",
            blockers=compose_blockers,
            next_actions=compose_actions
            + ([] if env_prod else ["Create .env.production from .env.production.example + Vault"]),
        ),
        Dimension(
            name="Security & dependencies",
            weight=0.10,
            percent=security_pct,
            status="green" if security_pct >= 90 else ("amber" if security_pct >= 75 else "red"),
            blockers=security_blockers,
            next_actions=security_actions,
        ),
        Dimension(
            name="Observability (The Observatory)",
            weight=0.08,
            percent=88.0 if tests_ok else 72.0,
            status="green" if tests_ok else "amber",
            blockers=[],
            next_actions=[
                "Scrape all P0 /health in Prometheus",
                "Set AUDIT_SIGNING_KEY in production",
            ],
        ),
        # SELF-ASSESSED, not measured. The number below is a standing judgement, not
        # evidence — no E2E run feeds it. Named as such so the headline percentage is
        # not read as a measurement it isn't. Replace with the Playwright pass rate
        # (.forgejo/workflows/e2e-playwright.yml) to make it real.
        Dimension(
            name="UX / Infinity Admin OS (self-assessed)",
            weight=0.06,
            percent=78.0,
            status="amber",
            blockers=[],
            next_actions=["E2E browser pass on dashboard + Admin OS", "Arcadia web app parity"],
        ),
        # SELF-ASSESSED, not measured — see the note above. scripts/zero_cost_audit.py
        # exists and could supply a real figure here.
        Dimension(
            name="Zero-cost policy & vendor lock-in (self-assessed)",
            weight=0.04,
            percent=90.0,
            status="green",
            blockers=[],
            next_actions=["Keep optional cloud AI keys off until caps accepted"],
        ),
        # Measured, and the only dimension that scores the surface the platform can
        # actually deploy to today. See _cloud_only_readiness().
        Dimension(
            name="Cloud-only go-live readiness",
            weight=0.05,
            percent=cloud_pct,
            status=(
                "green" if cloud_pct >= 80 else "amber" if cloud_pct >= 50 else "red"
            ),
            blockers=cloud_blockers,
            next_actions=cloud_actions,
        ),
        # Weight reduced from 5% to 2%: during the cloud-only phase the Cloudflare
        # workers *are* the production platform, so scoring their continued existence
        # as a liability misreports the current architecture. This measures progress
        # toward the hybrid/local end state, which is deliberately deferred.
        Dimension(
            name="Legacy decommission (Cloudflare) — hybrid/local phase only",
            weight=0.01,
            percent=55.0 if live_scripts else 35.0,
            status="amber" if live_scripts else "red",
            blockers=[] if live_scripts else ["api.trancendos.com still may route to CF workers"],
            next_actions=["Point DNS to Citadel Traefik — see deploy/LIVE_DEPLOY.md"],
        ),
        # Weight reduced from 5% to 3% for the same reason: this is gated on hardware
        # funding, not engineering, and it is not on the cloud-only critical path.
        Dimension(
            name="Ops executed on Citadel (live)",
            weight=0.02,
            percent=ops_pct,
            status=ops_status,
            blockers=ops_blockers,
            next_actions=["make deploy-live", "vault operator init/unseal"]
            if live_scripts
            else ["make deploy-citadel on production host"],
        ),
    ]


def overall_percent(dimensions: list[Dimension]) -> float:
    # A weight table that no longer sums to 1 silently rescales the headline number,
    # which is the one figure people quote. Catch it here rather than in a meeting.
    total_weight = sum(d.weight for d in dimensions)
    if abs(total_weight - 1.0) > 0.001:
        raise ValueError(
            f"Dimension weights must sum to 1.0, got {total_weight:.3f}. "
            "Adjust the table in build_dimensions()."
        )
    return round(sum(d.percent * d.weight for d in dimensions), 1)


def main() -> int:
    LOGS.mkdir(parents=True, exist_ok=True)
    dimensions = build_dimensions()
    overall = overall_percent(dimensions)
    live_dim = next(d for d in dimensions if "Ops executed" in d.name)
    # Re-normalise over the weight that remains once the live dimension is excluded,
    # read from the table rather than hardcoded — the previous `1.0 - 0.05` silently
    # went wrong the moment that weight changed.
    code_weight = sum(d.weight for d in dimensions if d is not live_dim)
    p0_code = round(
        sum(d.percent * d.weight for d in dimensions if d is not live_dim)
        / max(0.01, code_weight),
        1,
    )
    # B score = live verification dimension (not blended with repo artifacts).
    honest_p0_live = live_dim.percent
    payload = {
        "overall_percent": overall,
        "honest_p0_code_percent": p0_code,
        "honest_p0_live_percent": honest_p0_live,
        "honest_full_platform_percent": 52.0,
        "note": (
            "See docs/GO_LIVE_GAP_ANALYSIS.md — overall_percent is repo-weighted and "
            "optimistic; Citadel live requires deploy-live on owned hardware, while "
            "cloud-only go-live does not (deploy/CLOUD_GO_LIVE.md)."
        ),
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
        f"**Repo-weighted score: {overall}%** (compose + scripts; optimistic)",
        f"**Honest P0 code: {p0_code}%** | **Honest P0 live: {honest_p0_live}%** (until deploy-live succeeds)",
        "**Honest full platform: ~52%**",
        "",
        "Gap detail: `docs/GO_LIVE_GAP_ANALYSIS.md` | Cloud-only runbook: `deploy/CLOUD_GO_LIVE.md`",
        "",
        "- P0 go-live target: **85%**",
        "- Full 43-entity platform: **95%**",
        "",
        "| Dimension | Weight | % | Status |",
        "|-----------|--------|---|--------|",
    ]
    for d in dimensions:
        lines.append(f"| {d.name} | {int(d.weight * 100)}% | {d.percent}% | {d.status} |")
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
