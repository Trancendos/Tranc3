from __future__ import annotations

import importlib.util
from pathlib import Path
from uuid import uuid4

import pytest
import yaml


ROOT = Path(__file__).resolve().parent.parent


def _load_compose() -> dict:
    return yaml.safe_load((ROOT / "docker-compose.production.yml").read_text())


def _environment(service: dict) -> dict[str, str]:
    env = service.get("environment") or {}
    if isinstance(env, dict):
        return {str(key): str(value) for key, value in env.items()}

    parsed: dict[str, str] = {}
    for item in env:
        key, _, value = str(item).partition("=")
        parsed[key] = value
    return parsed


def test_production_compose_runs_vault_with_file_storage_not_dev_mode():
    compose = _load_compose()
    vault = compose["services"]["vault"]

    assert "server -dev" not in str(vault.get("command", ""))
    assert "VAULT_DEV_ROOT_TOKEN_ID" not in _environment(vault)
    assert "IPC_LOCK" in vault.get("cap_add", [])
    assert any("./deploy/vault/vault.hcl" in volume for volume in vault.get("volumes", []))
    assert (ROOT / "deploy" / "vault" / "vault.hcl").exists()


def test_production_compose_includes_main_backend_service():
    compose = _load_compose()
    backend = compose["services"]["tranc3-backend"]

    assert backend["build"]["context"] == "."
    assert backend["build"]["dockerfile"] == "Dockerfile"
    assert "8000:8000" in backend["ports"]
    assert "SECRET_KEY=${SECRET_KEY}" in backend["environment"]
    assert "JWT_SECRET=${JWT_SECRET}" in backend["environment"]
    assert "DATABASE_URL=${DATABASE_URL}" in backend["environment"]
    assert "REDIS_URL=${REDIS_URL}" in backend["environment"]


def test_production_compose_wires_api_gateway_upstreams():
    compose = _load_compose()
    gateway = compose["services"]["api-gateway"]
    env = _environment(gateway)

    assert env["AUTH_SERVICE_URL"] == "http://infinity-auth:8005"
    assert env["USERS_SERVICE_URL"] == "http://users-service:8006"
    assert env["PRODUCTS_SERVICE_URL"] == "http://products-service:8011"
    assert env["ORDERS_SERVICE_URL"] == "http://orders-service:8012"
    assert env["PAYMENTS_SERVICE_URL"] == "http://payments-service:8013"
    assert env["TRANC3_AI_SERVICE_URL"] == "http://tranc3-ai:8001"
    assert env["INTERNAL_SECRET"] == "${INTERNAL_SECRET}"

    depends_on = set(gateway.get("depends_on", []))
    assert {
        "tranc3-ai",
        "infinity-auth",
        "users-service",
        "products-service",
        "orders-service",
        "payments-service",
    } <= depends_on


def test_api_gateway_refuses_production_startup_with_missing_upstream(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "x" * 32)
    monkeypatch.delenv("AUTH_SERVICE_URL", raising=False)
    monkeypatch.delenv("USERS_SERVICE_URL", raising=False)
    monkeypatch.delenv("PRODUCTS_SERVICE_URL", raising=False)
    monkeypatch.delenv("ORDERS_SERVICE_URL", raising=False)
    monkeypatch.delenv("PAYMENTS_SERVICE_URL", raising=False)

    spec = importlib.util.spec_from_file_location(
        f"api_gateway_worker_{uuid4().hex}",
        ROOT / "workers" / "api-gateway" / "worker.py",
    )
    module = importlib.util.module_from_spec(spec)

    with pytest.raises(RuntimeError, match="USERS_SERVICE_URL"):
        assert spec.loader is not None
        spec.loader.exec_module(module)
