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
  - Worker directories under workers/ that no docker-compose*.yml file
    actually builds (orphaned — dead code or a wiring gap)
  - Alt-language name collisions (e.g. foo-rs next to foo) suggesting two
    live implementations of the same logical service

The last two checks formalize what was previously a one-off manual sweep
(see docs/governance/DUPLICATE-WORKER-FINDINGS.md) into something that runs
on every CI pass instead of only when someone happens to look. Known,
already-documented findings are read from
config/estate/duplication_baseline.yaml so they report as tracked, not as
fresh CI-blocking warnings — only a *new*, previously unseen instance
should surprise anyone.

Usage:
    python scripts/estate_lint.py [--strict]
"""

from __future__ import annotations

import re
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
DUPLICATION_BASELINE_PATH = ROOT / "config" / "estate" / "duplication_baseline.yaml"
WORKERS_DIR = ROOT / "workers"

CONTAINER_PREFIX = "tranc3-"

# Suffixes stripped when looking for an alt-language rewrite of the same
# logical service (foo-rs / foo-go / foo-node next to a Python `foo`).
_ALT_LANGUAGE_SUFFIXES = ("-go", "-rs", "-node", "-js", "-ts", "-py", "-v2", "-legacy", "-old")

# Directories under workers/ that are not themselves a worker (support files,
# not a case the orphan check should ever flag).
_NON_WORKER_DIR_NAMES = {"__pycache__", ".pytest_cache"}


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH) as f:
        data = yaml.safe_load(f)
    return data.get("components", [])


def load_compose() -> dict:
    with open(COMPOSE_PATH) as f:
        return yaml.safe_load(f)


def load_duplication_baseline() -> dict:
    if not DUPLICATION_BASELINE_PATH.exists():
        return {"orphaned_worker_dirs": [], "alt_language_duplicates": []}
    with open(DUPLICATION_BASELINE_PATH) as f:
        data = yaml.safe_load(f) or {}
    return {
        "orphaned_worker_dirs": set(data.get("orphaned_worker_dirs") or []),
        "alt_language_duplicates": set(data.get("alt_language_duplicates") or []),
    }


def _worker_dirs_referenced_by_compose(compose_path: Path) -> set[str]:
    """Return the workers/<name> directory names a compose file's services
    actually build from, via their `build.context` / `build.dockerfile`."""
    try:
        with open(compose_path) as f:
            data = yaml.safe_load(f) or {}
    except yaml.YAMLError:
        return set()
    refs: set[str] = set()
    for svc_cfg in (data.get("services") or {}).values():
        if not isinstance(svc_cfg, dict):
            continue
        build = svc_cfg.get("build")
        candidates: list[str] = []
        if isinstance(build, dict):
            candidates.append(str(build.get("context") or ""))
            candidates.append(str(build.get("dockerfile") or ""))
        elif isinstance(build, str):
            candidates.append(build)
        for candidate in candidates:
            match = re.search(r"workers/([A-Za-z0-9_-]+)", candidate)
            if match:
                refs.add(match.group(1))
    return refs


def check_orphaned_worker_dirs(baseline: set[str]) -> tuple[list[str], list[str]]:
    """Returns (warnings, tracked): workers/<name> directories that no
    docker-compose*.yml file (production, optional-services, self-hosted,
    planned-entities, ...) builds from at all. Scans every docker-compose*.yml
    in the repo root, not just docker-compose.production.yml, since a worker
    can legitimately live in a non-production compose file only.
    """
    if not WORKERS_DIR.is_dir():
        return [], []
    actual_dirs = {
        p.name for p in WORKERS_DIR.iterdir() if p.is_dir() and p.name not in _NON_WORKER_DIR_NAMES
    }
    referenced: set[str] = set()
    for compose_path in ROOT.glob("docker-compose*.yml"):
        referenced |= _worker_dirs_referenced_by_compose(compose_path)

    orphaned = sorted(actual_dirs - referenced)
    warnings = []
    tracked = []
    for name in orphaned:
        msg = (
            f"ORPHANED WORKER DIR: workers/{name}/ exists but no docker-compose*.yml "
            f"builds it — dead code, or a wiring gap"
        )
        if name in baseline:
            tracked.append(f"{msg} (tracked in duplication_baseline.yaml)")
        else:
            warnings.append(msg)
    return warnings, tracked


def _normalize_alt_language_name(name: str) -> str:
    for suffix in _ALT_LANGUAGE_SUFFIXES:
        if name.endswith(suffix) and len(name) > len(suffix):
            return name[: -len(suffix)]
    return name


def check_alt_language_duplicates(compose: dict, baseline: set[str]) -> tuple[list[str], list[str]]:
    """Returns (warnings, tracked): live docker-compose services whose name
    normalizes (stripping -go/-rs/-node/... suffixes) to the same base as
    another live service — a likely alt-language rewrite running alongside
    its original rather than replacing it. Candidates, not certainties: a
    human still decides whether it's genuine duplication or two
    coincidentally-similarly-named, complementary services — that's what the
    baseline file and docs/governance/DUPLICATE-WORKER-FINDINGS.md are for.
    """
    live_services = set(compose.get("services", {}).keys())
    groups: dict[str, list[str]] = {}
    for svc in live_services:
        base = _normalize_alt_language_name(svc)
        if base != svc:
            groups.setdefault(base, []).append(svc)

    warnings = []
    tracked = []
    for base, variants in sorted(groups.items()):
        for variant in sorted(variants):
            msg = (
                f"ALT-LANGUAGE NAME COLLISION: '{variant}' normalizes to '{base}' — "
                f"check whether it's a live duplicate of a same-purpose service"
            )
            if variant in baseline:
                tracked.append(f"{msg} (tracked in duplication_baseline.yaml)")
            else:
                warnings.append(msg)
    return warnings, tracked


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
        "traefik",
        "vault",
        "prometheus",
        "grafana",
        "loki",
        "promtail",
        "ipfs",
        "redis",
        # Third-party tools with their own compose entries (not platform entities)
        "ollama",
        "qdrant",
        "valkey",
        "nats",
        "victoriametrics",
        "tempo",
        "langfuse",
        "signoz-frontend",
        "signoz-query-service",
        "signoz-otel-collector",
        "signoz-clickhouse",
        "woodpecker-server",
        "woodpecker-agent",
        "watchtower",
        "falco",
        "outline",
        "outline-db",
        "outline-redis",
        "calcom",
        "calcom-db",
        "penpot-frontend",
        "penpot-backend",
        "penpot-db",
        "penpot-exporter",
        "zot",
        "krakend",
        "openbao",
        "dependency-track-apiserver",
        "dependency-track-frontend",
        "blender-worker",
        "triposr-worker",
        # Volume-only entries (not actual services)
        "langfuse-db",
        # Legacy CF Workers still referenced in docker-compose during migration
        "tranc3-ai",
        "infinity-void",
    }
    for svc in compose_services:
        if svc not in registry_services and svc not in skip_infra:
            warnings.append(
                f"UNREGISTERED SERVICE: '{svc}' in docker-compose but not in registry.yaml"
            )

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
    duplication_baseline = load_duplication_baseline()

    all_errors: list[str] = []
    all_warnings: list[str] = []
    all_tracked: list[str] = []

    # Run checks
    all_errors += check_duplicate_refs(components)
    all_errors += check_port_conflicts(components)
    all_errors += check_container_names(components)
    all_errors += check_missing_short_ids(components)

    compose_errors, compose_warnings = check_compose_vs_registry(components, compose)
    all_errors += compose_errors
    all_warnings += compose_warnings

    all_warnings += check_compose_container_names(compose)

    orphan_warnings, orphan_tracked = check_orphaned_worker_dirs(
        duplication_baseline["orphaned_worker_dirs"]
    )
    all_warnings += orphan_warnings
    all_tracked += orphan_tracked

    dup_warnings, dup_tracked = check_alt_language_duplicates(
        compose, duplication_baseline["alt_language_duplicates"]
    )
    all_warnings += dup_warnings
    all_tracked += dup_tracked

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

    if all_tracked:
        print(f"TRACKED, KNOWN FINDINGS ({len(all_tracked)}) — see duplication_baseline.yaml:")
        for t in all_tracked:
            print(f"  ○ {t}")
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
