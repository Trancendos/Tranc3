#!/usr/bin/env python3
"""Hand The Lab the priority order of Requests and Changes a census implies.

This is the step that was missing between assessment and remediation. The
census says what is wrong and, since `src/dvms/surface_owner.py`, whose it is.
This turns that into ITSM records against the Location that answers for each
surface: a Change where a patch exists and is reachable, an Incident where one
does not, and an Incident at the top of the queue for a surface that could not
be scanned at all.

DRY RUN IS THE DEFAULT, and deliberately. `--apply` writes into The Town Hall's
ITSM store, which is shared state other people work from; filing a queue's
worth of tickets is not something to do as a side effect of asking what the
queue looks like.

Usage:
    python scripts/dvms_dispatch.py                     # plan from a fresh census
    python scripts/dvms_dispatch.py --census run.json   # plan from a saved one
    python scripts/dvms_dispatch.py --json              # the plan, machine-readable
    python scripts/dvms_dispatch.py --apply             # write the records
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

from src.dvms import plan, summarise  # noqa: E402


def _fresh_census(scope: str) -> dict:
    """Run the census in-process rather than shelling out to it."""
    path = os.path.join(REPO_ROOT, "scripts", "vulnerability_census.py")
    spec = importlib.util.spec_from_file_location("_census_for_dispatch", path)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise SystemExit("vulnerability_census.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_census_for_dispatch"] = module
    spec.loader.exec_module(module)
    return module.build_census(scope)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--census", help="read a saved census JSON instead of running one")
    # Restricted, not free text: a typo silently ran the CORE subset and
    # presented the reduced plan as the whole estate's.
    parser.add_argument(
        "--scope",
        choices=("core", "all"),
        default="core",
        help="census scope when running one",
    )
    parser.add_argument("--json", action="store_true", help="emit the plan as JSON")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the records into The Town Hall's ITSM store (default is a dry run)",
    )
    args = parser.parse_args(argv if argv is not None else sys.argv[1:])

    if args.census:
        try:
            with open(args.census, encoding="utf-8") as handle:
                census = json.load(handle)
        except (OSError, ValueError) as exc:
            print(f"FAIL could not read {args.census}: {exc}", file=sys.stderr)
            return 1
    else:
        census = _fresh_census(args.scope)

    # Valid JSON is not a valid census. A list, a scalar, or an object with no
    # `surfaces` key produces an EMPTY plan, which reads exactly like "nothing
    # to raise" — a malformed file would silently suppress every dispatch.
    if (
        not isinstance(census, dict)
        or not isinstance(census.get("surfaces"), list)
        or not census["surfaces"]
        or not all(
            isinstance(surface, dict)
            and bool(surface.get("surface"))
            and isinstance(surface.get("errored"), bool)
            and isinstance(surface.get("findings"), list)
            and all(isinstance(finding, dict) for finding in surface["findings"])
            for surface in census["surfaces"]
        )
    ):
        print(
            "FAIL the census must be a JSON object containing a `surfaces` list; "
            "an empty plan from a malformed file is indistinguishable from a clean estate",
            file=sys.stderr,
        )
        return 1

    items = plan(census)
    summary = summarise(items)

    # In JSON mode stdout carries the document and nothing else, so it can be
    # piped. Status text goes to stderr.
    status = sys.stderr if args.json else sys.stdout

    if args.json:
        print(json.dumps({"summary": summary, "items": [i.to_dict() for i in items]}, indent=2))
    else:
        print(
            f"Dispatch plan: {summary['total']} records "
            f"({summary['changes']} changes, {summary['incidents']} incidents)"
        )
        if not items:
            print("Nothing to raise — no fixable, blocked or unscannable surface.")
        for item in items:
            who = item.responsible or "UNROUTED"
            print(f"  {item.priority.upper()} {item.kind:8} {who:26} {item.title}")
        if summary["unroutable"]:
            print(
                f"\n{summary['unroutable']} record(s) have no Location to route to and "
                "will be SKIPPED rather than filed against a placeholder. Run "
                "scripts/check_surface_ownership.py to see which.",
                file=sys.stderr,
            )

    if not args.apply:
        print("\n(dry run — pass --apply to write these into the ITSM store)", file=status)
        return 0

    from src.dvms import apply as apply_plan

    written = apply_plan(items)
    filed = [w for w in written if "skipped" not in w]
    print(
        f"\nFiled {len(filed)} record(s); skipped {len(written) - len(filed)} "
        "(unroutable, or already filed).",
        file=status,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
