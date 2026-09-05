#!/usr/bin/env python3
"""Every dependency surface the census scans must have somebody who answers for it.

WHY THIS EXISTS

`src/dvms/surface_owner.py` joins a manifest path to the Location that owns it,
so a Cryptex finding can be handed to The Lab as a Request or a Change against a
named Location rather than as a path nobody is accountable for. A join is only
worth having while it is complete: one worker added under a new directory and
the census starts reporting findings that route nowhere, silently, because an
unrouted finding looks exactly like no finding at all in a summary.

So this fails on three things, and each is a different way the join rots:

  1. A scanned surface no ladder resolves. Somebody added a tree and did not
     say who owns it.
  2. A `DECLARED_OWNERS` prefix that matches nothing on disk. The tree moved
     and the mapping was left behind, so it is now a claim about a path that
     does not exist.
  3. A `DECLARED_OWNERS` entry naming a Location that is not one of the 43.
     A typo here routes findings to a Location that cannot receive them.

It deliberately does NOT fail on a `shared` surface. Cross-cutting
infrastructure genuinely belongs to no single Location -- the API gateway, the
rate limiter, the AI-framework bridges -- and `src/cmdb/identity.py` takes the
same position for the same reason. A shared surface still names a steward, so
it is routed; it is just not owned.

Usage:
    python scripts/check_surface_ownership.py           # exit 1 on a gap
    python scripts/check_surface_ownership.py --json    # machine-readable
"""

from __future__ import annotations

import argparse
import collections
import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.dvms.surface_owner import (  # noqa: E402
    DECLARED_OWNERS,
    resolve_surface,
)
from src.entities.platform import PLATFORM_ENTITIES  # noqa: E402


def _census():
    """Load the census by path; it is a script, not an importable module."""
    path = os.path.join(REPO_ROOT, "scripts", "vulnerability_census.py")
    spec = importlib.util.spec_from_file_location("_census_for_ownership", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit("vulnerability_census.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_census_for_ownership"] = module
    spec.loader.exec_module(module)
    return module


def scanned_surfaces() -> list[str]:
    """Every surface the census actually scans, all four ecosystems.

    Read from the census's own discovery rather than re-globbed here, so the
    two cannot disagree about what the estate contains. A second walk would be
    a second answer, and the whole point is that there is one.

    Go and Rust joined the census on 2026-09-04 and are included from the same
    day. A surface the census scans but this gate does not check is a surface
    that can lose its owner without anything failing -- which is precisely the
    rot this script exists to catch, so widening the census without widening
    this would have rebuilt the gap one layer up.
    """
    census = _census()
    pip = {m for group in census.PY_MANIFEST_GROUPS.values() for m in group}
    return sorted(pip | set(census.NPM_DIRS) | set(census.GO_MODULES) | set(census.RUST_CRATES))


def stale_declarations() -> list[str]:
    """DECLARED_OWNERS prefixes that no longer exist on disk."""
    problems = []
    for prefix in DECLARED_OWNERS:
        if prefix == ".":
            continue
        if not os.path.exists(os.path.join(REPO_ROOT, prefix)):
            problems.append(
                f"DECLARED_OWNERS names {prefix!r}, which does not exist — the tree "
                "moved and the mapping was left behind"
            )
    return problems


def bad_locations() -> list[str]:
    """DECLARED_OWNERS entries naming something that is not one of the 43."""
    problems = []
    for prefix, (location, _reason) in DECLARED_OWNERS.items():
        if location is not None and location not in PLATFORM_ENTITIES:
            problems.append(
                f"DECLARED_OWNERS maps {prefix!r} to {location!r}, which is not one of "
                "the 43 Locations — findings routed there cannot be received"
            )
    return problems


def missing_reasons() -> list[str]:
    """An entry with no written reason is indistinguishable from a guess."""
    return [
        f"DECLARED_OWNERS entry {prefix!r} has no reason recorded"
        for prefix, (_location, reason) in DECLARED_OWNERS.items()
        if not (reason or "").strip()
    ]


def _print_rollup(surfaces: list[str], kinds, by_location) -> None:
    """The human-readable coverage summary."""
    print(f"Dependency surfaces scanned: {len(surfaces)}")
    print(f"  owned by a Location: {kinds['location']} across {len(by_location)} Locations")
    print(f"  cross-cutting (shared, stewarded): {kinds['shared']}")
    print(f"  unowned: {kinds['unmapped']}")
    if by_location:
        print("\nSurfaces per Location:")
        for location, count in sorted(by_location.items()):
            print(f"  {location:28} {count}")


def main(argv: list[str] | None = None) -> int:
    # `argv` explicit rather than implicit sys.argv: a test importing this
    # module and calling main() would otherwise be handed pytest's own
    # arguments and exit 2 on them, which looks like a failing gate and is not.
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit the roll-up as JSON")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    surfaces = scanned_surfaces()
    owners = [resolve_surface(s) for s in surfaces]
    kinds = collections.Counter(owner.kind for owner in owners)
    by_location = collections.Counter(
        owner.location for owner in owners if owner.kind == "location"
    )

    problems = stale_declarations() + bad_locations() + missing_reasons()
    problems += [
        f"{owner.surface} has no owner — {owner.reason}"
        for owner in owners
        if owner.kind == "unmapped"
    ]

    if args.json:
        print(
            json.dumps(
                {
                    "surfaces": len(surfaces),
                    "owned": kinds["location"],
                    "shared": kinds["shared"],
                    "unmapped": kinds["unmapped"],
                    "locations_covered": len(by_location),
                    "by_location": dict(sorted(by_location.items())),
                    "problems": problems,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 1 if problems else 0

    _print_rollup(surfaces, kinds, by_location)
    if problems:
        print()
        for problem in problems:
            print(f"FAIL {problem}", file=sys.stderr)
        print(
            "\nSurface ownership: FAILED — a finding on an unowned surface has "
            "nobody to route to, and in a summary it is indistinguishable from no "
            "finding at all. Add the path to DECLARED_OWNERS in "
            "src/dvms/surface_owner.py with the reason it belongs there.",
            file=sys.stderr,
        )
        return 1
    print("\nSurface ownership: PASSED — every scanned surface routes to a Location")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
