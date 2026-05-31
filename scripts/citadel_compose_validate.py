#!/usr/bin/env python3
"""Validate deploy_live CORE_SERVICES exist in docker-compose.production.yml."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"
DEPLOY_SCRIPT = ROOT / "scripts" / "deploy_live.sh"


def _core_services_from_deploy() -> list[str]:
    text = DEPLOY_SCRIPT.read_text()
    match = re.search(r"CORE_SERVICES=\(\s*([\s\S]*?)\)", text)
    if not match:
        return []
    block = match.group(1)
    services: list[str] = []
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        for part in line.split():
            part = part.strip("\r")
            if part:
                services.append(part)
    return services


def _compose_service_names() -> set[str]:
    names: set[str] = set()
    for line in COMPOSE.read_text().splitlines():
        m = re.match(r"^  ([a-z0-9][a-z0-9-]*):\s*$", line)
        if m and not line.startswith("    "):
            names.add(m.group(1))
    return names


def main() -> int:
    errors: list[str] = []
    core = _core_services_from_deploy()
    compose_names = _compose_service_names()
    for svc in core:
        if svc not in compose_names:
            errors.append(f"CORE_SERVICES lists '{svc}' but it is not in {COMPOSE.name}")

    gateway = "api-gateway"
    if gateway in compose_names:
        compose_text = COMPOSE.read_text()
        gateway_block = compose_text.split(f"  {gateway}:")[1].split("\n  ")[0:40]
        gateway_section = "\n".join(gateway_block)
        for dep in ("products-service", "orders-service", "payments-service"):
            if dep not in gateway_section:
                errors.append(f"api-gateway should depend_on {dep} in compose")

    if errors:
        print("citadel_compose_validate FAILED:", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1

    print(f"citadel_compose_validate OK ({len(core)} core services)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
