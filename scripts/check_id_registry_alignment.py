#!/usr/bin/env python3
"""Fail when the CI register and the entity register disagree about a Location.

Two registers, one truth
------------------------
`src/entities/platform.py` is the canonical entity register — CLAUDE.md says
so, and it is what the solution-pack generator, the flow contract and the
surface-ownership check all read. `src/config/id_registry.json` is the CMDB's
own record of the same 43 Locations, and nothing compared them.

They had parted on **22 of 43** — half the estate. Six Creativity Locations
(The Studio, Sashas Photo Studio, TranceFlow, TateKing, Fabulousa,
Imaginarium) all claimed `src/studio/`, a router CLAUDE.md records as
unmounted and removed. Worse were the pairs that named a *different live
service*: The Void pointed at `workers/config-service/`, Cryptex at
`workers/rate-limit-service/`, Section 7 at `workers/geo-service/`, DevOcity
at `workers/health-aggregator/`.

A CMDB whose configuration item points at another service's code is not a
stale record; it is a wrong one, and every dependency question asked of it
answers about the wrong thing.

What this checks
----------------
For every Location present in both registers, `worker_path` must match, and
the path must exist. `src/entities/platform.py` wins on disagreement — it is
the canonical register, and it is what the tooling reads.

Usage:
    python3 scripts/check_id_registry_alignment.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

REGISTRY = REPO / "src" / "config" / "id_registry.json"


def _registry_paths() -> dict[str, str]:
    """PID -> worker_path, from the CMDB register."""
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    found: dict[str, str] = {}

    def walk(node: object) -> None:
        if isinstance(node, dict):
            pid = node.get("pid")
            if isinstance(pid, str) and "worker_path" in node:
                found[pid] = node["worker_path"]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found


def _entity_paths() -> dict[str, str]:
    """PID -> worker_path, from the canonical entity register."""
    from src.entities.platform import PLATFORM_ENTITIES  # noqa: PLC0415

    return {
        entity.pid: entity.worker_path
        for entity in PLATFORM_ENTITIES.values()
        if getattr(entity, "pid", None)
    }


def drift() -> list[str]:
    registry = _registry_paths()
    entities = _entity_paths()
    failures: list[str] = []

    for pid, declared in sorted(registry.items()):
        canonical = entities.get(pid)
        if canonical is None:
            continue  # the registry carries records the entity table does not
        if declared != canonical:
            failures.append(
                f"{pid}: id_registry.json says {declared!r}, "
                f"src/entities/platform.py says {canonical!r}"
            )
        elif declared and not (REPO / declared).exists():
            failures.append(f"{pid}: both registers say {declared!r}, which is not on disk")

    return failures


def main() -> int:
    failures = drift()
    if failures:
        print("ID registry alignment: FAILED")
        for failure in failures:
            print(f"  - {failure}")
        print()
        print("  src/entities/platform.py is canonical (CLAUDE.md), and is what the")
        print("  pack generator, flow contract and ownership check read. A CMDB record")
        print("  pointing at another service's code answers every dependency question")
        print("  about the wrong thing.")
        return 1
    print(f"ID registry alignment: PASSED — {len(_registry_paths())} Location record(s) agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
