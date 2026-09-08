#!/usr/bin/env python3
"""Verify production Compose contracts that Docker cannot infer safely.

The checks are intentionally narrow: they fail only on deterministic deployment
or control-plane risks. Broader observations, such as an image tag without a
digest, are reported as warnings so existing services can be migrated in
reviewable slices rather than making every pull request permanently red.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_FILE = ROOT / "docker-compose.production.yml"
CONTROL_PLANE_SERVICES = frozenset(
    {
        "alertmanager",
        "grafana",
        "loki",
        "minio",
        "nats",
        "otel-collector",
        "prometheus",
        "tempo",
        "traefik",
        "valkey",
        "vault",
        "victoriametrics",
        "zot",
    }
)
PUBLIC_CONTROL_PLANE_PORTS = {("traefik", "80"), ("traefik", "443")}
SECRET_NAME_PATTERN = re.compile(r"(?:PASSWORD|SECRET|TOKEN|PRIVATE_KEY|JWT|API_KEY)$")
INTERPOLATION_PATTERN = re.compile(r"^\$\{(?P<name>[A-Z0-9_]+):-(?P<fallback>[^}]*)\}$")
CRITICAL_REQUIRED_VARIABLES = frozenset({"INTERNAL_SECRET", "JWT_SECRET", "MINIO_ROOT_USER"})


@dataclass(frozen=True)
class PublishedPort:
    service: str
    host_ip: str | None
    published: str
    target: str
    protocol: str

    @property
    def is_public(self) -> bool:
        return self.host_ip in (None, "", "0.0.0.0", "::", "[::]")

    @property
    def binding(self) -> str:
        prefix = f"{self.host_ip}:" if self.host_ip else ""
        return f"{prefix}{self.published}/{self.protocol}"


def load_compose(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as compose_file:
        data = yaml.safe_load(compose_file)
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        raise ValueError(f"{path} does not contain a Compose services mapping")
    return data


def parse_port(service: str, value: Any) -> PublishedPort | None:
    if isinstance(value, dict):
        published = value.get("published")
        target = value.get("target")
        if published is None or target is None:
            return None
        return PublishedPort(
            service=service,
            host_ip=str(value.get("host_ip") or ""),
            published=str(published),
            target=str(target),
            protocol=str(value.get("protocol") or "tcp"),
        )
    if not isinstance(value, (str, int)):
        return None
    text = str(value)
    match = re.fullmatch(
        r"(?:(?P<host_ip>\[[^]]+]|[^:]+):)?(?P<published>\d+):(?P<target>\d+)(?:/(?P<protocol>\w+))?",
        text,
    )
    if match is None:
        return None
    return PublishedPort(
        service=service,
        host_ip=match.group("host_ip"),
        published=match.group("published"),
        target=match.group("target"),
        protocol=match.group("protocol") or "tcp",
    )


def published_ports(services: dict[str, Any]) -> list[PublishedPort]:
    ports: list[PublishedPort] = []
    for service, config in services.items():
        if not isinstance(config, dict):
            continue
        for value in config.get("ports", []):
            parsed = parse_port(service, value)
            if parsed is not None:
                ports.append(parsed)
    return ports


def _bindings_overlap(left: PublishedPort, right: PublishedPort) -> bool:
    if left.published != right.published or left.protocol != right.protocol:
        return False
    if left.host_ip == right.host_ip:
        return True
    return left.is_public or right.is_public


def duplicate_bindings(ports: Iterable[PublishedPort]) -> list[str]:
    results: list[str] = []
    port_list = list(ports)
    for index, left in enumerate(port_list):
        for right in port_list[index + 1 :]:
            if _bindings_overlap(left, right):
                results.append(
                    f"host port {left.published}/{left.protocol} is published by both "
                    f"{left.service} ({left.binding}) and {right.service} ({right.binding})"
                )
    return results


def control_plane_exposure(ports: Iterable[PublishedPort]) -> list[str]:
    results: list[str] = []
    for port in ports:
        if port.service not in CONTROL_PLANE_SERVICES or not port.is_public:
            continue
        if (port.service, port.published) in PUBLIC_CONTROL_PLANE_PORTS:
            continue
        results.append(
            f"control-plane service {port.service} publishes {port.binding} to all interfaces; "
            "bind it to 127.0.0.1 or route it through an authenticated proxy"
        )
    return results


def environment_items(config: dict[str, Any]) -> Iterable[tuple[str, str]]:
    environment = config.get("environment", {})
    if isinstance(environment, dict):
        for name, value in environment.items():
            yield str(name), str(value)
    elif isinstance(environment, list):
        for value in environment:
            if not isinstance(value, str) or "=" not in value:
                continue
            name, setting = value.split("=", 1)
            yield name, setting


def unsafe_secret_fallbacks(services: dict[str, Any]) -> list[str]:
    results: list[str] = []
    for service, config in services.items():
        if not isinstance(config, dict):
            continue
        for name, value in environment_items(config):
            match = INTERPOLATION_PATTERN.fullmatch(value)
            if match is None:
                continue
            fallback = match.group("fallback")
            is_secret = bool(SECRET_NAME_PATTERN.search(name))
            requires_value = is_secret or name in CRITICAL_REQUIRED_VARIABLES
            if requires_value and fallback:
                results.append(
                    f"{service} supplies insecure fallback for {name}; use ${{{match.group('name')}:?required}}"
                )
            if name in CRITICAL_REQUIRED_VARIABLES and not fallback:
                results.append(
                    f"{service} permits an empty {name}; use ${{{match.group('name')}:?required}}"
                )
    return results


def image_warnings(services: dict[str, Any]) -> list[str]:
    results: list[str] = []
    for service, config in services.items():
        if not isinstance(config, dict):
            continue
        image = config.get("image")
        if isinstance(image, str) and "@sha256:" not in image:
            results.append(f"{service} image is not digest-pinned: {image}")
    return results


def audit(path: Path) -> dict[str, Any]:
    compose = load_compose(path)
    services = compose["services"]
    ports = published_ports(services)
    errors = [
        *duplicate_bindings(ports),
        *control_plane_exposure(ports),
        *unsafe_secret_fallbacks(services),
    ]
    return {
        "compose_file": str(path.relative_to(ROOT) if path.is_relative_to(ROOT) else path),
        "services": len(services),
        "published_ports": len(ports),
        "errors": errors,
        "warnings": image_warnings(services),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_COMPOSE_FILE)
    parser.add_argument("--check", action="store_true", help="return non-zero on contract errors")
    parser.add_argument("--json", action="store_true", help="emit the full machine-readable report")
    args = parser.parse_args()
    report = audit(args.file)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(
            f"Compose contract audit: {report['services']} services, "
            f"{report['published_ports']} published ports, {len(report['errors'])} error(s), "
            f"{len(report['warnings'])} advisory warning(s)"
        )
        for finding in report["errors"]:
            print(f"ERROR: {finding}")
        for finding in report["warnings"]:
            print(f"WARNING: {finding}")
    return 1 if args.check and report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
