#!/usr/bin/env python3
"""Validate deploy_live CORE_SERVICES exist in docker-compose.production.yml."""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

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


def _undeclared_volume_refs() -> list[str]:
    """Named volumes a service mounts that the top-level `volumes:` never declares.

    Compose rejects the whole project on the first one of these ("refers to
    undefined volume ..."), so a single missed declaration means the stack cannot
    start at all. Five had accumulated (`shards-data`, four `stirling-pdf-*`)
    without anything noticing: `docker compose config` is the only check that
    catches it, that step is skipped when docker is absent, and on a hosted runner
    it aborted earlier still on an unset required variable. This makes the failure
    visible from a plain YAML parse, with no docker and no secrets needed.

    Bind mounts and paths built from variables are skipped — only named volumes
    have to be declared.
    """
    doc = yaml.safe_load(COMPOSE.read_text()) or {}
    declared = set((doc.get("volumes") or {}).keys())
    problems: list[str] = []
    for svc, cfg in (doc.get("services") or {}).items():
        for mount in (cfg or {}).get("volumes") or []:
            if isinstance(mount, str):
                source = mount.split(":")[0]
            elif isinstance(mount, dict) and mount.get("type") == "volume":
                source = mount.get("source")
            else:
                continue
            if not source or source.startswith((".", "/", "$", "~")):
                continue
            if source not in declared:
                problems.append(
                    f"service '{svc}' mounts named volume '{source}', "
                    f"which is not declared under the top-level `volumes:`"
                )
    return problems


def main() -> int:
    errors: list[str] = []
    errors.extend(_undeclared_volume_refs())
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
