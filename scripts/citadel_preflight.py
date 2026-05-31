#!/usr/bin/env python3
"""Citadel production preflight — validates env, compose, and entity DB wiring.

Run before deploy: python3 scripts/citadel_preflight.py
Exit 0 = ready; 1 = blocking issues (printed to stderr).
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env.production"
COMPOSE = ROOT / "docker-compose.production.yml"
VAULT_HCL = ROOT / "deploy" / "vault" / "vault.hcl"

REQUIRED_KEYS = ("SECRET_KEY", "JWT_SECRET", "DATABASE_URL", "REDIS_URL")
RECOMMENDED_KEYS = (
    "INTERNAL_SECRET",
    "MASTER_KEY_SEED",
    "ENTITY_OVERRIDES_DB",
    "INFINITY_ADMIN_DB_PATH",
)
PLACEHOLDER = re.compile(r"LOAD_FROM_VAULT|change-me|your[-_]", re.I)


def _load_env_file() -> dict[str, str]:
    if not ENV_FILE.exists():
        return {}
    values: dict[str, str] = {}
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip()
    return values


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    if not COMPOSE.exists():
        errors.append(f"Missing {COMPOSE}")
    if not VAULT_HCL.exists():
        errors.append(f"Missing {VAULT_HCL} — production Vault uses file storage")
    compose_text = COMPOSE.read_text() if COMPOSE.exists() else ""
    if "server -dev" in compose_text:
        errors.append("docker-compose.production.yml still uses Vault dev mode")
    if "tranc3-backend:" not in compose_text:
        errors.append("docker-compose.production.yml missing tranc3-backend service")
    if "AUTH_SERVICE_URL=http://infinity-auth:8005" not in compose_text:
        warnings.append("api-gateway may not route /api/auth to infinity-auth")

    env = _load_env_file()
    for key in REQUIRED_KEYS:
        if os.getenv(key):
            env[key] = os.getenv(key, "")

    ci_mode = os.getenv("ENVIRONMENT", "").lower() in ("test", "ci")
    if not env and not ci_mode:
        errors.append(".env.production missing — copy from .env.production.example")
    else:
        for key in REQUIRED_KEYS:
            val = env.get(key, "")
            if not val and not ci_mode:
                errors.append(f"{key} is not set in .env.production")
            elif val and PLACEHOLDER.search(val):
                warnings.append(f"{key} still has Vault/placeholder value")
        for key in RECOMMENDED_KEYS:
            if not env.get(key) and not ci_mode:
                warnings.append(f"{key} not set (recommended for full platform)")

    if errors:
        print("Citadel preflight FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        for w in warnings:
            print(f"  ⚠ {w}", file=sys.stderr)
        return 1

    print("Citadel preflight OK")
    for w in warnings:
        print(f"  ⚠ {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
