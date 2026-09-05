#!/usr/bin/env python3
"""Emit the platform's measured topology as JSON for the 3D map.

Everything here is read, never asserted: the 43 Locations and their pillars
from `src/entities/platform.py`, ports and Traefik rules from
`docker-compose.production.yml`, in-process mounts from `api.py`, flow edges
from `config/estate/flow_contract.yaml` with their measured verdicts from
`config/estate/flow_baseline.json`, and creative routing status from
`src/creative/routing.py`.

The map's value is in what it shows as *missing*: a Location with no compose
service, a declared flow nothing routes to, a capability whose Location
answers nothing. A diagram drawn from intent shows a tidy platform. This one
shows the platform.

Usage:
    python3 scripts/build_topology_3d.py            # writes the JSON
    python3 scripts/build_topology_3d.py --check    # fails if it is stale
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

COMPOSE = REPO / "docker-compose.production.yml"
FLOW_CONTRACT = REPO / "config" / "estate" / "flow_contract.yaml"
FLOW_BASELINE = REPO / "config" / "estate" / "flow_baseline.json"
API = REPO / "api.py"
OUTPUT = REPO / "docs" / "architecture" / "topology-3d.json"

_SERVICE = re.compile(r"^  ([a-z0-9][a-z0-9_-]*):\s*$")
_PORT_MAP = re.compile(r'^\s+- "(\d+):(\d+)"')
_PORT_ENV = re.compile(r"^\s+- [A-Z_]*PORT=(\d+)")
_PREFIX = re.compile(r"PathPrefix\(`([^`]+)`\)")


def compose_services() -> dict[str, dict]:
    """Every compose service, with its published port and route prefix."""
    services: dict[str, dict] = {}
    current: str | None = None
    for line in COMPOSE.read_text(encoding="utf-8").splitlines():
        match = _SERVICE.match(line)
        if match:
            current = match.group(1)
            services[current] = {"port": None, "prefix": "", "image": ""}
            continue
        if current is None:
            continue
        port = _PORT_MAP.match(line) or _PORT_ENV.match(line)
        if port and services[current]["port"] is None:
            services[current]["port"] = int(port.group(1))
        if "rule=" in line:
            prefix = _PREFIX.search(line)
            if prefix:
                services[current]["prefix"] = prefix.group(1)
        image = re.match(r"^\s+image:\s*(\S+)", line)
        if image:
            services[current]["image"] = image.group(1)
    return services


def mounted_in_api() -> set[str]:
    """Every module `api.py` actually mounts as a router.

    This used to match one import spelling — `from src.X.routes import` — and
    so could see 25 of the 39 routers `api.py` mounts. The 14 it could not see
    were the ones that do not call their module `routes`: The Spark's is
    `src.mcp.server`, Turing's Hub's is `src.personality.turingshub.routes`,
    billing's is `src.monetisation.router`. The map therefore reported The
    Spark — the MCP server, reachable at `/mcp/*` on the backend since
    `api.py:798` — as a Location with nowhere to receive traffic, and I
    reported that to the owner as a finding. It was a defect in the detector.

    A regex that recognises one naming convention is a detector with a
    documented blind spot. This resolves it the way the interpreter does:
    find every `include_router(<name>)` call, then resolve `<name>` back
    through the file's `from ... import ... as ...` bindings to the module it
    came from. A router mounted under any name, from any module, is seen.
    """
    tree = ast.parse(API.read_text(encoding="utf-8"))

    bindings: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                bindings[alias.asname or alias.name] = node.module

    mounted: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if getattr(node.func, "attr", None) != "include_router" or not node.args:
            continue
        argument = node.args[0]
        name = getattr(argument, "id", None) or getattr(argument, "attr", None)
        if name and name in bindings:
            mounted.add(bindings[name])
    return mounted


def _is_mounted(module: str, mounts: set[str]) -> bool:
    """Is this Location's package mounted, under any module inside it?

    `entity.worker_path` names a package (`src/mcp/`); the mount names the
    module within it (`src.mcp.server`). Comparing them for equality found
    neither, so the prefix is what is compared — with the dot required, so
    `src.lab` does not match `src.laboratory`.
    """
    if not module:
        return False
    return any(m == module or m.startswith(module + ".") for m in mounts)


def flow_edges() -> list[dict]:
    """Declared Location-to-Location flows, with their measured verdict."""
    import yaml  # noqa: PLC0415

    contract = yaml.safe_load(FLOW_CONTRACT.read_text(encoding="utf-8")) or {}
    baseline = json.loads(FLOW_BASELINE.read_text(encoding="utf-8"))
    edges: list[dict] = []
    for rule in contract.get("flows", contract.get("rules", [])) or []:
        rule_id = rule.get("id")
        edges.append(
            {
                "id": rule_id,
                "hub": rule.get("hub", ""),
                "claim": rule.get("claim", ""),
                "verdict": baseline.get(rule_id, "unknown"),
            }
        )
    return edges


def creative_capabilities() -> list[dict]:
    """The creative routing table's capabilities and their measured status.

    Read from `src.creative.routing` rather than restated here, so the map
    cannot claim a capability the router does not declare.
    """
    from src.creative.routing import CAPABILITIES  # noqa: PLC0415

    return [
        {
            "id": c.id,
            "location": c.location,
            "delivers": c.delivers,
            "status": c.status.value,
        }
        for c in CAPABILITIES
    ]


def build() -> dict:
    """The estate's shape, derived from four sources that can each be re-checked.

    Locations come from the canonical entity register; ports, Traefik rules and
    build contexts from `docker-compose.production.yml`; in-process mounts from
    `api.py`; flow verdicts from the measured baseline. Nothing here is
    asserted by hand, which is the point — a hand-maintained topology is a
    drawing, not a map.
    """
    from src.entities.platform import PLATFORM_ENTITIES  # noqa: PLC0415

    services = compose_services()
    mounts = mounted_in_api()

    nodes = []
    for name, entity in PLATFORM_ENTITIES.items():
        directory = Path(entity.worker_path.rstrip("/")).name if entity.worker_path else ""
        service = next(
            (s for s in (directory, name.lower().replace(" ", "-")) if s in services), ""
        )
        module = ""
        if entity.worker_path.startswith("src/"):
            module = entity.worker_path.rstrip("/").replace("/", ".")
        nodes.append(
            {
                "pid": entity.pid,
                "name": name,
                "pillar": entity.pillar.value,
                "lead_ai": entity.lead_ai,
                "worker_path": entity.worker_path,
                "on_disk": bool(entity.worker_path) and (REPO / entity.worker_path).exists(),
                "compose_service": service,
                "port": services.get(service, {}).get("port") or entity.worker_port,
                "route_prefix": services.get(service, {}).get("prefix", ""),
                "in_process": _is_mounted(module, mounts),
                "agents": list(getattr(entity, "agent_teams", None) or []),
                "abilities": len(getattr(entity, "abilities", []) or []),
            }
        )

    return {
        "generated_by": "scripts/build_topology_3d.py",
        "counts": {
            "locations": len(nodes),
            "deployed": sum(1 for n in nodes if n["compose_service"]),
            "routed": sum(1 for n in nodes if n["route_prefix"]),
            "in_process": sum(1 for n in nodes if n["in_process"]),
            "undeployed": sum(1 for n in nodes if not n["compose_service"] and not n["in_process"]),
            "compose_services": len(services),
            "infrastructure": sum(1 for v in services.values() if v["image"]),
        },
        "locations": sorted(nodes, key=lambda n: (n["pillar"], n["name"])),
        "flows": flow_edges(),
        "creative": creative_capabilities(),
    }


def main(argv: list[str] | None = None) -> int:
    """Write the topology, or verify the committed copy. Returns an exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    rendered = json.dumps(build(), indent=2, sort_keys=True) + "\n"

    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding="utf-8") != rendered:
            print("Topology map data: FAILED — stale or missing")
            print("Run: python3 scripts/build_topology_3d.py")
            return 1
        print("Topology map data: PASSED — matches the registers")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    data = json.loads(rendered)
    print(f"Wrote {OUTPUT.relative_to(REPO)}")
    for key, value in data["counts"].items():
        print(f"  {key:18} {value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
