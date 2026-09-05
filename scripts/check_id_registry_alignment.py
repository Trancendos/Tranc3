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
from pathlib import Path, PurePosixPath

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

REGISTRY = REPO / "src" / "config" / "id_registry.json"


def _registry_paths() -> tuple[dict[str, str], dict[str, list[str]]]:
    """PID -> worker_path from the CMDB, and any PID recorded twice differently."""
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    duplicates: dict[str, list[str]] = {}

    def walk(node: object) -> None:
        """Collect every record carrying both a `pid` and a `worker_path`.

        The registry nests records at varying depths, so this recurses rather
        than assuming a shape — a record moved one level down would otherwise
        drop silently out of the comparison, which is the opposite of what an
        alignment check is for.
        """
        if isinstance(node, dict):
            pid = node.get("pid")
            if isinstance(pid, str) and "worker_path" in node:
                if pid in found and found[pid] != node["worker_path"]:
                    # Last-write-wins would hide the conflict: a second record
                    # for the same PID carrying a different path is exactly
                    # the kind of drift this check exists to surface, and
                    # silently overwriting it makes the register look aligned.
                    duplicates.setdefault(pid, [found[pid]]).append(node["worker_path"])
                found[pid] = node["worker_path"]
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(data)
    return found, duplicates


def _entity_paths() -> dict[str, str]:
    """PID -> worker_path, from the canonical entity register."""
    from src.entities.platform import PLATFORM_ENTITIES  # noqa: PLC0415

    return {
        entity.pid: entity.worker_path
        for entity in PLATFORM_ENTITIES.values()
        if getattr(entity, "pid", None)
    }


def drift() -> list[str]:
    """Disagreements between the CMDB and the canonical entity register.

    Reports two kinds: a PID whose `worker_path` differs between the two, and
    a path both agree on that is not on disk — the second is how six records
    kept pointing at `src/studio/` after that router was removed.
    """
    registry, duplicates = _registry_paths()
    entities = _entity_paths()
    failures: list[str] = []

    for pid, paths in sorted(duplicates.items()):
        failures.append(
            f"{pid}: id_registry.json records this PID more than once with "
            f"different paths ({', '.join(repr(p) for p in paths)}). One PID, one record."
        )

    for pid, declared in sorted(registry.items()):
        canonical = entities.get(pid)
        if canonical is None:
            continue  # the registry carries records the entity table does not
        if declared != canonical:
            failures.append(
                f"{pid}: id_registry.json says {declared!r}, "
                f"src/entities/platform.py says {canonical!r}"
            )
        elif declared:
            failures.extend(_path_failures(pid, declared))

    # A PID the canonical register holds and the CMDB does not is drift in the
    # direction the loop above cannot see: it iterates the CMDB, so a record
    # deleted or renamed there simply stops being visited and the check passes.
    for pid in sorted(set(entities) - set(registry)):
        failures.append(
            f"{pid}: src/entities/platform.py holds this Location and "
            "id_registry.json has no record for it"
        )

    return failures


def _path_failures(pid: str, declared: str) -> list[str]:
    """Reasons an agreed-upon path is still not a usable repository path.

    Agreement between the two registers is necessary and not sufficient. Both
    can agree on an absolute path, or one containing `..`, and
    `(REPO / declared).exists()` would then test something outside the
    repository entirely — reporting a pass because a directory happens to
    exist on the machine running the check.
    """
    path = PurePosixPath(declared)
    if path.is_absolute():
        return [f"{pid}: {declared!r} is absolute; worker paths are repository-relative"]
    if ".." in path.parts:
        return [f"{pid}: {declared!r} escapes the repository with '..'"]
    if not (REPO / declared).exists():
        return [f"{pid}: both registers say {declared!r}, which is not on disk"]
    return []


def main() -> int:
    """Report every registry disagreement. Returns a process exit code."""
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
    print(f"ID registry alignment: PASSED — {len(_registry_paths()[0])} Location record(s) agree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
