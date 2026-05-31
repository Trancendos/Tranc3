"""Contract tests for live-deploy automation (no Docker required)."""

from __future__ import annotations

from pathlib import Path

import yaml

from tests._repo_io import read_repo_text

ROOT = Path(__file__).resolve().parents[1]


def test_live_deploy_scripts_exist():
    for path in (
        "scripts/deploy_live.sh",
        "scripts/generate_production_env.sh",
        "scripts/wait_for_healthy.py",
        "scripts/citadel_compose_validate.py",
        "deploy/LIVE_DEPLOY.md",
        "deploy/vault/init-citadel.sh",
        "deploy/traefik/DNS_CUTOVER.md",
    ):
        assert (ROOT / path).is_file(), path


def test_p0_worker_dockerfiles_use_repo_root_context():
    compose = yaml.safe_load(read_repo_text(ROOT / "docker-compose.production.yml"))
    for svc in (
        "infinity-ws",
        "infinity-auth",
        "api-gateway",
        "users-service",
    ):
        build = compose["services"][svc]["build"]
        assert build["context"] == ".", svc
        assert build["dockerfile"].startswith("workers/"), svc


def test_compose_has_ollama_valkey_and_backend():
    compose = yaml.safe_load(read_repo_text(ROOT / "docker-compose.production.yml"))
    services = compose["services"]
    assert "ollama" in services
    assert "valkey" in services
    assert "tranc3-backend" in services
    backend = services["tranc3-backend"]
    dep = backend.get("depends_on", {})
    assert "valkey" in dep or "valkey" in str(dep)


def test_prometheus_scrapes_backend():
    prom = read_repo_text(ROOT / "monitoring" / "prometheus.yml")
    assert "tranc3-backend" in prom
    assert "tranc3-core.yml" in prom


def test_generate_production_env_template_keys():
    script = read_repo_text(ROOT / "scripts" / "generate_production_env.sh")
    for key in (
        "SECRET_KEY=",
        "JWT_SECRET=",
        "DATABASE_URL=sqlite",
        "REDIS_URL=redis://valkey",
        "AUDIT_SIGNING_KEY=",
        "VAULT_MASTER_KEY=",
        "AUTH_SERVICE_URL=",
    ):
        assert key in script
