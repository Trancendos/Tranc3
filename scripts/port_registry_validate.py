#!/usr/bin/env python3
"""Validate CLAUDE.md's worker port table against docker-compose.production.yml.

Prevents the class of drift that caused issue #188: CLAUDE.md's port column is
documentation, hand-maintained, and had silently diverged from the deployment
truth (compose). This script is the regression guard — it does not touch
PLATFORM_ENTITIES.md (a separate, richer registry) or auto-fix anything; it only
fails CI when CLAUDE.md disagrees with compose for a worker that appears in both.

Compose port precedence per worker (first found wins), matching the convention
documented in CLAUDE.md's "Port source of truth" note:
  1. `PORT` env var set in the service's `environment:` block
  2. Traefik `loadbalancer.server.port` label
  3. published `ports:` host mapping

Workers that read a *custom* port env (e.g. HIVE_PORT, CACHE_PORT) are out of
scope here — this only checks the documented/compose port pairing, not each
worker's code bind (see docs/services/ and issue #188 for the 4 known code-bind
routing defects, which this script deliberately does not attempt to detect).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE = ROOT / "docker-compose.production.yml"
CLAUDE_MD = ROOT / "CLAUDE.md"

# Workers with a *documented, deliberate* CLAUDE.md/compose port mismatch —
# each is a known #188 routing defect (code binds a different port than compose
# routes to) where CLAUDE.md intentionally states the app's actual bind port
# rather than the (unreachable) compose-routed port. Do not add to this list
# without a corresponding note in CLAUDE.md's "known routing defects" table.
KNOWN_EXCEPTIONS = {
    "infinity-void",  # code/CLAUDE.md 8082 vs compose 8002 — see docs/services/the-void/
}


def _compose_ports() -> dict[str, str]:
    services = yaml.safe_load(COMPOSE.read_text()).get("services") or {}
    ports: dict[str, str] = {}
    for name, svc in services.items():
        env = svc.get("environment")
        port_env = None
        if isinstance(env, dict) and env.get("PORT") is not None:
            port_env = str(env["PORT"])
        elif isinstance(env, list):
            for e in env:
                if str(e).startswith("PORT="):
                    port_env = str(e).split("=", 1)[1]
                    break
        if port_env:
            ports[name] = port_env
            continue

        labels = svc.get("labels") or []
        label_text = " ".join(labels) if isinstance(labels, list) else str(labels)
        m = re.search(r"loadbalancer\.server\.port=(\d+)", label_text)
        if m:
            ports[name] = m.group(1)
            continue

        for p in svc.get("ports") or []:
            m = re.match(r'^"?(\d+):', str(p))
            if m:
                ports[name] = m.group(1)
                break
    return ports


def _claude_md_ports() -> dict[str, str]:
    """Parse worker rows from CLAUDE.md's `| Service | Port | ... |` tables."""
    text = CLAUDE_MD.read_text()
    ports: dict[str, str] = {}
    for line in text.splitlines():
        m = re.match(r"^\|\s*([a-z0-9][a-z0-9-]*)\s*\|\s*(\d{4})\s*\|", line)
        if m:
            # first occurrence wins; CLAUDE.md documents each worker once
            ports.setdefault(m.group(1), m.group(2))
    return ports


def main() -> int:
    compose = _compose_ports()
    claude = _claude_md_ports()

    shared = sorted(set(compose) & set(claude))
    mismatches = [
        (w, claude[w], compose[w])
        for w in shared
        if claude[w] != compose[w] and w not in KNOWN_EXCEPTIONS
    ]

    if mismatches:
        print("port_registry_validate FAILED — CLAUDE.md disagrees with compose:", file=sys.stderr)
        for worker, claude_port, compose_port in mismatches:
            print(f"  ✗ {worker}: CLAUDE.md={claude_port} compose={compose_port}", file=sys.stderr)
        print(
            "\nUpdate CLAUDE.md's port column to match compose (the deployment truth), "
            "or fix compose if CLAUDE.md is right. See issue #188.",
            file=sys.stderr,
        )
        return 1

    print(f"port_registry_validate OK ({len(shared)} workers checked, CLAUDE.md == compose)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
