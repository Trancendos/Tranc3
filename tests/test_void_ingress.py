"""Regression contracts for The Void's external Traefik route.

This does not replace a live Traefik smoke test; it protects compose wiring.
"""

from __future__ import annotations

import re
from pathlib import Path

COMPOSE = Path(__file__).resolve().parents[1] / "docker-compose.production.yml"


def _labels(service: str) -> dict[str, str]:
    """Read one Compose service's labels, without confusing another router."""
    text = COMPOSE.read_text(encoding="utf-8")
    match = re.search(
        rf"(?ms)^  {re.escape(service)}:\s*\n(.*?)(?=^  [\w-]+:\s*\n|\Z)",
        text,
    )
    assert match is not None, f"{service} service is missing"
    raw = re.findall(r'^\s+-\s+"(traefik\.[^"]+)"\s*$', match.group(1), re.MULTILINE)
    return dict(label.split("=", 1) for label in raw)


def test_void_router_strips_external_prefix_before_fastapi():
    labels = _labels("infinity-void")
    assert "PathPrefix(`/api/void`)" in labels["traefik.http.routers.infinity-void.rule"]
    assert labels["traefik.http.routers.infinity-void.middlewares"] == "strip-infinity-void"
    assert (
        labels["traefik.http.middlewares.strip-infinity-void.stripprefix.prefixes"] == "/api/void"
    )


def test_void_route_priority_exceeds_generic_api_gateway():
    void_labels = _labels("infinity-void")
    gateway_labels = _labels("api-gateway")
    assert int(void_labels["traefik.http.routers.infinity-void.priority"]) > int(
        gateway_labels["traefik.http.routers.api-gateway.priority"]
    )
