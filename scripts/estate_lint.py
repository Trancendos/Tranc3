#!/usr/bin/env python3
"""
estate_lint.py — Trancendos Platform Estate Validator

Checks the estate against registry.yaml and docker-compose.production.yml:
  - Port conflicts
  - Container name convention (must be tranc3-{short-id})
  - docker-compose services not in registry
  - Registry active/building entries with no docker-compose service
  - Duplicate PLM references
  - Missing short_ids

Usage:
    python scripts/estate_lint.py [--strict]
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERROR: PyYAML not installed. Run: pip install pyyaml")
    sys.exit(1)

ROOT = Path(__file__).parent.parent
REGISTRY_PATH = ROOT / "config" / "estate" / "registry.yaml"
COMPOSE_PATH = ROOT / "docker-compose.production.yml"

CONTAINER_PREFIX = "tranc3-"


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("components", [])


def load_compose() -> dict:
    with open(COMPOSE_PATH) as f:
        return yaml.safe_load(f)


def check_duplicate_refs(components: list[dict]) -> list[str]:
    seen: dict[str, str] = {}
    errors = []
    for c in components:
        ref = c.get("ref", "")
        name = c.get("name", "")
        if ref in seen:
            errors.append(f"DUPLICATE REF: {ref} used by both '{seen[ref]}' and '{name}'")
        else:
            seen[ref] = name
    return errors


def check_port_conflicts(components: list[dict]) -> list[str]:
    port_map: dict[int, list[str]] = {}
    for c in components:
        port = c.get("port")
        if port and isinstance(port, int):
            port_map.setdefault(port, []).append(c.get("ref", "?") + " " + c.get("name", "?"))
    errors = []
    for port, owners in port_map.items():
        if len(owners) > 1:
            errors.append(f"PORT CONFLICT {port}: {owners}")
    return errors


def check_container_names(components: list[dict]) -> list[str]:
    errors = []
    for c in components:
        container = c.get("docker_container")
        if not container:
            continue
        if not container.startswith(CONTAINER_PREFIX):
            errors.append(
                f"BAD CONTAINER NAME [{c.get('ref')}] {c.get('name')}: "
                f"'{container}' must start with '{CONTAINER_PREFIX}'"
            )
    return errors


def check_missing_short_ids(components: list[dict]) -> list[str]:
    errors = []
    for c in components:
        if not c.get("short_id"):
            errors.append(f"MISSING short_id: [{c.get('ref')}] {c.get('name')}")
    return errors


def check_compose_vs_registry(components: list[dict], compose: dict) -> tuple[list[str], list[str]]:
    """
    Returns (errors, warnings):
    - errors: active/building registry entries with no docker-compose service
    - warnings: docker-compose services not in registry
    """
    compose_services = set(compose.get("services", {}).keys())
    registry_services = {c["docker_service"] for c in components if c.get("docker_service")}

    errors = []
    warnings = []

    # Registry active/building entries that have docker_service set but are absent from compose
    # Services that live in a separate compose file or external deployment
    external_services = {"forgejo"}

    for c in components:
        ds = c.get("docker_service")
        status = c.get("status", "")
        if ds and ds in external_services:
            continue
        if ds and status == "active" and ds not in compose_services:
            errors.append(
                f"MISSING IN COMPOSE [{c.get('ref')}] {c.get('name')}: "
                f"docker_service='{ds}' not found in docker-compose.production.yml "
                f"(status={status})"
            )
        elif ds and status == "building" and ds not in compose_services:
            warnings.append(
                f"NOT YET IN COMPOSE [{c.get('ref')}] {c.get('name')}: "
                f"docker_service='{ds}' (status=building — add to docker-compose when ready)"
            )

    # Compose services not tracked in registry
    # Services in separate compose files or external deployments
    skip_infra = {
        "traefik", "vault", "prometheus", "grafana", "loki", "promtail", "ipfs", "redis",
        # Third-party tools with their own compose entries (not platform entities)
        "ollama", "qdrant", "valkey", "nats", "victoriametrics", "tempo", "langfuse",
        "signoz-frontend", "signoz-query-service", "signoz-otel-collector", "signoz-clickhouse",
        "woodpecker-server", "woodpecker-agent", "watchtower", "falco",
        "outline", "outline-db", "outline-redis",
        "calcom", "calcom-db",
        "penpot-frontend", "penpot-backend", "penpot-db", "penpot-exporter",
        "zot", "krakend", "openbao",
        "dependency-track-apiserver", "dependency-track-frontend",
        "blender-worker", "triposr-worker",
        # Volume-only entries (not actual services)
        "langfuse-db",
        # Legacy CF Workers still referenced in docker-compose during migration
        "tranc3-ai", "infinity-void",
    }
    for svc in compose_services:
        if svc not in registry_services and svc not in skip_infra:
            warnings.append(f"UNREGISTERED SERVICE: '{svc}' in docker-compose but not in registry.yaml")

    return errors, warnings


def check_compose_container_names(compose: dict) -> list[str]:
    errors = []
    for svc_name, svc_cfg in compose.get("services", {}).items():
        if not isinstance(svc_cfg, dict):
            continue
        container_name = svc_cfg.get("container_name")
        if container_name and not container_name.startswith(CONTAINER_PREFIX):
            errors.append(
                f"BAD COMPOSE CONTAINER_NAME: service '{svc_name}' "
                f"has container_name='{container_name}' (must start with '{CONTAINER_PREFIX}')"
            )
    return errors


def main(strict: bool = False) -> int:
    print("=" * 60)
    print("Trancendos Estate Linter")
    print("=" * 60)

    if not REGISTRY_PATH.exists():
        print(f"ERROR: Registry not found at {REGISTRY_PATH}")
        return 1
    if not COMPOSE_PATH.exists():
        print(f"ERROR: docker-compose.production.yml not found at {COMPOSE_PATH}")
        return 1

    components = load_registry()
    compose = load_compose()

    all_errors: list[str] = []
    all_warnings: list[str] = []

    # Run checks
    all_errors += check_duplicate_refs(components)
    all_errors += check_port_conflicts(components)
    all_errors += check_container_names(components)
    all_errors += check_missing_short_ids(components)

    compose_errors, compose_warnings = check_compose_vs_registry(components, compose)
    all_errors += compose_errors
    all_warnings += compose_warnings

    all_warnings += check_compose_container_names(compose)

    # Report
    print(f"\nRegistry: {len(components)} components loaded")
    print(f"Compose:  {len(compose.get('services', {}))} services loaded")
    print()

    if all_errors:
        print(f"ERRORS ({len(all_errors)}):")
        for e in all_errors:
            print(f"  ✗ {e}")
        print()

    if all_warnings:
        print(f"WARNINGS ({len(all_warnings)}):")
        for w in all_warnings:
            print(f"  ⚠ {w}")
        print()

    if not all_errors and not all_warnings:
        print("✓ All checks passed — estate is clean")
        return 0

    if not all_errors:
        print(f"✓ No errors. {len(all_warnings)} warning(s).")
        return 0 if not strict else 1

    print(f"✗ {len(all_errors)} error(s), {len(all_warnings)} warning(s).")
    return 1


if __name__ == "__main__":
    strict = "--strict" in sys.argv
    sys.exit(main(strict=strict))
