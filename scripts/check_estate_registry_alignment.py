#!/usr/bin/env python3
"""The estate registry must name the containers the estate actually runs.

`config/estate/registry.yaml` is the CMDB: the record an operator reads to
find a service's port, its compose service and the container to exec into.
None of those three were checked against `docker-compose.production.yml`,
and all three had drifted — 45 records named a container that does not
exist, and 15 recorded a live, Traefik-routed Location as having no
deployment at all. A CMDB that names a container you cannot attach to is
worse than no CMDB, because it is consulted during an incident.

The derivation is deliberately narrow. A port is claimed only where compose
states it unambiguously: an env var whose name ends in `PORT` with a numeric
value, or a single symmetric `host:container` mapping. Forgejo publishes
`2222:22` (SSH) and serves HTTP on a port compose never names; Prometheus
maps `9091:9090`; IPFS publishes three. Guessing for those would replace a
stale number with a confident wrong one, so they are left to the record.
"""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "config" / "estate" / "registry.yaml"
COMPOSE = REPO / "docker-compose.production.yml"

#: Single fields that legitimately disagree with compose, each with the
#: reason. Keyed `(ref, field)` rather than by record: exempting a whole
#: record would silently exempt the fields nobody argued about, which is how
#: a stale container name rides along behind a defensible port.
ACCEPTED_DIVERGENCES: dict[tuple[str, str], str] = {
    ("TRC-P0-001", "port"): (
        "The Spark is mounted in-process under api.py, so it shares "
        "tranc3-backend's container and has no port of its own. Recording "
        "8000 would imply a separately addressable service."
    ),
    ("TRC-P1-003", "worker_path"): (
        "Infinity Gate is embedded in the Infinity Portal worker and has no "
        "worker directory of its own; recording the portal's would claim a "
        "second service builds from it."
    ),
    ("TRC-P1-003", "port"): (
        "Infinity Gate is embedded in the Infinity Portal worker rather "
        "than being a service of its own, so it has no port of its own; "
        "its container is the portal's, and is checked as such."
    ),
}


def records(node: Any) -> list[dict]:
    """Every registry record, wherever the file nests them."""
    found: list[dict] = []
    if isinstance(node, dict):
        if "short_id" in node and "entity_type" in node:
            found.append(node)
        for value in node.values():
            found.extend(records(value))
    elif isinstance(node, list):
        for value in node:
            found.extend(records(value))
    return found


def derived_worker_path(service: dict) -> str | None:
    """The worker directory compose builds this service from, or None.

    Only a build context under `workers/` is claimed. A service built from
    the repo root, or pulled as a third-party image, has no worker directory
    of its own and inventing one would point a reader at nothing.
    """
    build = service.get("build")
    context = build.get("context") if isinstance(build, dict) else build
    if isinstance(context, str):
        trimmed = context.lstrip("./").rstrip("/")
        if trimmed.startswith("workers/"):
            return f"{trimmed}/"
    # A root-context build still names its worker, in the Dockerfile path.
    # Several services build from `.` so their image can COPY `src/`, and
    # reading only the context left every one of them unchecked — the
    # registry could say anything about their worker_path and this agreed.
    dockerfile = build.get("dockerfile") if isinstance(build, dict) else None
    if isinstance(dockerfile, str):
        trimmed = dockerfile.lstrip("./")
        if trimmed.startswith("workers/"):
            return f"{PurePosixPath(trimmed).parent}/"
    return None


def derived_port(service: dict) -> str | None:
    """The container port compose states outright, or None.

    Two shapes are unambiguous: a `*PORT=<digits>` environment entry, and a
    single `X:X` published mapping — the convention every worker in this
    estate follows. An asymmetric or multiple mapping is not: `2222:22`
    publishes SSH while the service answers HTTP elsewhere, and claiming the
    container side of it would put `22` in the CMDB.
    """
    environment = service.get("environment") or []
    if isinstance(environment, list):
        for entry in environment:
            if not isinstance(entry, str) or "=" not in entry:
                continue
            name, _, value = entry.partition("=")
            if name.upper().endswith("PORT") and value.isdigit():
                return value
    ports = [str(p) for p in (service.get("ports") or [])]
    if len(ports) == 1:
        parts = ports[0].split(":")
        if len(parts) == 2 and parts[0] == parts[1]:
            return parts[1]
    return None


def check_compose_banners() -> list[str]:
    """The `# ── Name (Port N) ──` banners must name the port below them.

    Thirteen of them did not, and several named a port belonging to a
    different service — Swarm Coordinator's banner said 8053, which is
    Cryptex's. These banners are what a reader scrolling a 4,000-line
    compose file actually reads, and the registry's own wrong numbers match
    them, so the drift had already propagated into the CMDB once.
    """
    text = COMPOSE.read_text(encoding="utf-8")
    lines = text.splitlines()
    services = yaml.safe_load(text).get("services", {})
    failures: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^  ([a-z0-9][a-z0-9._-]*):\s*$", line)
        if not match or match.group(1) not in services:
            continue
        # Scan every consecutive comment above the key, not just the
        # nearest one. Stopping at the first comment meant a service with a
        # stacked header — a note above its banner — had its banner never
        # checked, which is the drift this exists to catch hiding behind an
        # unrelated line of prose.
        #
        # The scan runs to the first non-comment line rather than stopping
        # after a fixed six. "Every consecutive comment" was what the
        # comment claimed and a six-line window is not that: a service whose
        # banner sits under a seven-line block of explanation — several do
        # in this file — had its banner silently skipped, and the check
        # reported clean for a service it never looked at. A bounded window
        # in a guard is a bound on what the guard can see.
        for above in range(index - 1, -1, -1):
            comment = lines[above].strip()
            if not comment.startswith("#"):
                break
            stated = re.search(r"Port\s+(\d+)", comment)
            if not stated:
                continue
            actual = derived_port(services[match.group(1)])
            if actual and stated.group(1) != actual:
                failures.append(
                    f"docker-compose.production.yml:{above + 1}: the banner for "
                    f"`{match.group(1)}` says Port {stated.group(1)}, the service "
                    f"serves {actual}"
                )
            break
    return failures


def check() -> list[str]:
    registry = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    services = yaml.safe_load(COMPOSE.read_text(encoding="utf-8")).get("services", {})
    failures: list[str] = []

    for record in records(registry):
        ref = record.get("ref", record.get("short_id", "?"))
        name = record.get("name", ref)
        declared = record.get("docker_service")
        if declared is not None and declared not in services:
            # Reported, never silently re-pointed at `short_id`. Falling
            # back would accept a record naming a service that does not
            # exist as long as its short_id happened to name one that does,
            # which is a wrong deployment mapping validated as correct.
            failures.append(
                f"{ref} {name}: docker_service `{declared}` is not a service in "
                "docker-compose.production.yml"
            )
            continue
        key = declared if declared in services else None
        if key is None and record["short_id"] in services:
            # A record saying it has no deployment while compose builds,
            # publishes and routes a container of that exact name. This is
            # how The Chaos Party read as an unowned test-suite platform
            # while its worker answered on 8079 behind its own Traefik host.
            if declared is None:
                failures.append(
                    f"{ref} {name}: recorded with no deployment, but compose runs service "
                    f"`{record['short_id']}` (container "
                    f"`{services[record['short_id']].get('container_name')}`)"
                )
                continue
            key = record["short_id"]
        if key is None:
            continue

        service = services[key]
        container = service.get("container_name")
        if (
            container
            and record.get("docker_container") != container
            and (ref, "docker_container") not in ACCEPTED_DIVERGENCES
        ):
            failures.append(
                f"{ref} {name}: docker_container is "
                f"`{record.get('docker_container')}`, compose names `{container}`"
            )
        worker_path = derived_worker_path(service)
        if (
            worker_path is not None
            and record.get("worker_path") != worker_path
            and (ref, "worker_path") not in ACCEPTED_DIVERGENCES
        ):
            failures.append(
                f"{ref} {name}: worker_path is {record.get('worker_path')}, compose "
                f"builds service `{key}` from {worker_path}"
            )
        port = derived_port(service)
        if (
            port is not None
            and str(record.get("port")) != port
            and (ref, "port") not in ACCEPTED_DIVERGENCES
        ):
            failures.append(
                f"{ref} {name}: port is {record.get('port')}, compose service `{key}` serves {port}"
            )
    return failures


def main() -> int:
    failures = check() + check_compose_banners()
    if not failures:
        print(
            "PASSED — every estate record and compose banner agrees with "
            "docker-compose.production.yml"
        )
        return 0
    print(f"FAILED — {len(failures)} disagreement(s) with the deployment:")
    for failure in failures:
        print(f"  - {failure}")
    print(
        "\nCompose is the deployment truth. Correct config/estate/registry.yaml, or "
        "record the divergence with a written reason in ACCEPTED_DIVERGENCES."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
