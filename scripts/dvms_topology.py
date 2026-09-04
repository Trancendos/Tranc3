#!/usr/bin/env python3
"""Navigate the dependency ↔ Location graph in both directions.

The platform owner's ask, verbatim: open a Location's record, go to its
dependencies, pick one, and see every other service associated with it. That is
two queries and this answers both, plus the one they imply — which packages are
shared widely enough that upgrading one is an estate-wide change rather than a
worker's.

Usage:
    python scripts/dvms_topology.py --shared              # widest blast radius first
    python scripts/dvms_topology.py --package starlette   # who depends on it
    python scripts/dvms_topology.py --location "The Studio"
    python scripts/dvms_topology.py --duplication         # advisories x blast radius
    python scripts/dvms_topology.py --json                # any of the above, machine-readable
"""

from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.dvms import dependency_graph as graph  # noqa: E402


def _shared(args) -> dict:
    entries = graph.shared_packages(args.minimum)
    if not args.json:
        print(f"Packages declared by {args.minimum}+ Locations: {len(entries)}")
        print("Widest blast radius first — this is the order an upgrade queue should take.\n")
        for entry in entries[: args.limit]:
            print(
                f"  {entry.ecosystem}:{entry.package:<28} "
                f"{len(entry.locations):>2} Locations  {len(entry.manifests):>3} manifests"
            )
    return {"shared": [e.to_dict() for e in entries[: args.limit]]}


def _package(args) -> dict:
    result = graph.blast_radius(args.package, args.ecosystem)
    if not args.json:
        if not result.get("known"):
            print(f"{args.ecosystem}:{args.package} — {result['reason']}")
        else:
            print(
                f"{args.ecosystem}:{args.package} is declared by {len(result['locations'])} Location(s):"
            )
            for location in result["locations"]:
                print(f"  {location}")
            if result["unrouted_manifests"]:
                print(
                    f"\n{len(result['unrouted_manifests'])} manifest(s) could not be routed to a "
                    "Location and are NOT counted above:"
                )
                for manifest in result["unrouted_manifests"]:
                    print(f"  {manifest}")
            print(f"\n{result['note']}")
    return result


def _location(args) -> dict:
    declared = graph.dependencies_of(args.location)
    if not args.json:
        if not declared:
            print(f"{args.location!r} declares nothing, or is not a Location name.")
        for ecosystem, names in declared.items():
            print(f"{args.location} — {ecosystem} ({len(names)}):")
            for name in names:
                shared = graph.usage(name, ecosystem)
                others = [
                    loc for loc in (shared.locations if shared else []) if loc != args.location
                ]
                suffix = f"  → also in {len(others)} other Location(s)" if others else ""
                print(f"  {name}{suffix}")
    return {"location": args.location, "declares": declared}


def _duplication(args) -> dict:
    """How much of a findings list is distinct, and how much is blast radius.

    A vulnerability scanner that reports per-manifest counts one advisory in a
    35-Location package as 35 findings. Both numbers are true and they answer
    different questions: how much work there is, and how much exposure. Reading
    the second as the first makes a queue look thirty times longer than it is.
    """
    entries = list(graph.build_graph().values())
    reach = sum(max(len(e.locations), 1) for e in entries)
    widest = sorted(entries, key=lambda e: -len(e.locations))[:5]
    summary = {
        "distinct_packages": len(entries),
        "package_location_pairs": reach,
        "amplification": round(reach / len(entries), 1) if entries else 0,
        "widest": [{"package": e.package, "locations": len(e.locations)} for e in widest],
    }
    if not args.json:
        print(f"Distinct packages declared:      {summary['distinct_packages']}")
        print(f"Package x Location pairs:        {summary['package_location_pairs']}")
        print(f"Mean amplification per package:  {summary['amplification']}x")
        print(
            "\nOne advisory in a widely shared package becomes that many findings in a\n"
            "per-manifest report. The count is exposure, not workload."
        )
        for item in summary["widest"]:
            print(f"  {item['package']:<28} {item['locations']:>2} Locations")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--shared", action="store_true", help="packages several Locations declare")
    mode.add_argument("--package", help="which Locations depend on this package")
    mode.add_argument("--location", help="what this Location declares")
    mode.add_argument("--duplication", action="store_true", help="distinct packages vs total reach")
    parser.add_argument("--ecosystem", choices=("pip", "npm"), default="pip")
    parser.add_argument("--minimum", type=int, default=2, help="with --shared: Location threshold")
    parser.add_argument("--limit", type=int, default=40, help="with --shared: rows to print")
    parser.add_argument("--json", action="store_true", help="emit the result as JSON")
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.shared:
        result = _shared(args)
    elif args.package:
        result = _package(args)
    elif args.location:
        result = _location(args)
    else:
        result = _duplication(args)

    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
