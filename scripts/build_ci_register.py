#!/usr/bin/env python3
"""Register every datastore and container in the estate as a Configuration Item.

The owner's requirement: records captured in the CMDB and registered as CIs, with
containers marked as containers, their contents logged, and a shared jurisdiction
between the Location/AI inside the container and The Ice Box as custodian.

The register is *derived*, for the reason a CMDB usually fails: hand-maintained
CI records describe the estate on the day someone last typed them. Adding a
`sqlite3.connect("data/new.db")` or a compose service is a routine change nobody
thinks to mirror into a register, and those are precisely the changes that must
not go missing. Everything here is read from the repository on each run.

Two CI classes, and one deliberate asymmetry between them:

  Datastore  jurisdiction = owning Location, or `_unrouted_`
  Container  jurisdiction = owning Location, or `_unrouted_`
             custodian    = The Ice Box, ALWAYS

A container's jurisdiction can be unknown -- 86 of them are third-party images
that run nobody's code here. Its custodian cannot be, because containment,
isolation and stability are answerable regardless of whose software is inside.
Splitting the two is what lets the register say "we do not know whose this is"
without also saying "nobody is responsible for it".

Usage:
    python3 scripts/build_ci_register.py           # write the register
    python3 scripts/build_ci_register.py --check   # fail if stale
    python3 scripts/build_ci_register.py --gaps    # unrouted and un-SBOM'd only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.cmdb.containers import CUSTODIAN  # noqa: E402
from src.cmdb.containers import CannotEnumerateContainers  # noqa: E402
from src.cmdb.containers import discover as discover_containers  # noqa: E402
from src.cmdb.datastores import discover as discover_datastores  # noqa: E402

OUTPUT = REPO / "docs" / "architecture" / "ci-register.json"


def build_register() -> dict:
    datastores = discover_datastores()
    # Not wrapped in a try/except that degrades to an empty list. With PyYAML
    # absent this function used to write a register saying "containers with no
    # SBOM: 0" and exit 0 -- a report of perfect coverage produced by a run that
    # enumerated nothing. Letting the exception out is what makes "could not
    # measure" distinguishable from "measured, and it is fine".
    containers = discover_containers()

    # Test-fixture databases are excluded from the register and counted, not
    # dropped silently: they are real SQLite usage, and a reader who sees 143
    # stores here and 212 in the discovery output should be able to account for
    # the difference without reading the code.
    live_stores = [d for d in datastores if not d.test_only]

    return {
        "generated_from": "repository scan (src/cmdb/datastores.py, src/cmdb/containers.py)",
        "custodian_of_all_containers": CUSTODIAN,
        "counts": {
            "datastores_registered": len(live_stores),
            "datastores_excluded_as_test_fixtures": len(datastores) - len(live_stores),
            "containers_registered": len(containers),
            "containers_built_here": sum(1 for c in containers if c.provenance == "built"),
            "containers_pulled": sum(1 for c in containers if c.provenance == "pulled"),
            "containers_with_sbom": sum(1 for c in containers if c.has_sbom),
            "datastores_unrouted": sum(1 for d in live_stores if not d.location),
            "containers_unrouted": sum(1 for c in containers if not c.jurisdiction),
        },
        "configuration_items": ([d.as_ci() for d in live_stores] + [c.as_ci() for c in containers]),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--gaps", action="store_true")
    args = parser.parse_args(argv)

    try:
        register = build_register()
    except CannotEnumerateContainers as exc:
        print(f"cannot build the CI register: {exc}", file=sys.stderr)
        print(
            "Refusing to write a register that would report zero containers, "
            "which is indistinguishable from an estate with none.",
            file=sys.stderr,
        )
        return 1

    if args.gaps:
        counts = register["counts"]
        print(f"datastores with no owning Location: {counts['datastores_unrouted']}")
        print(f"containers with no owning Location: {counts['containers_unrouted']}")
        print(
            f"containers with no SBOM:            "
            f"{counts['containers_registered'] - counts['containers_with_sbom']}"
        )
        print(
            f"\nEvery container has a custodian ({CUSTODIAN}) regardless. "
            "Unrouted means jurisdiction is undecided, not unmanaged."
        )
        return 0

    payload = json.dumps(register, indent=2, ensure_ascii=False) + "\n"

    if args.check:
        if not OUTPUT.is_file() or OUTPUT.read_text(encoding="utf-8") != payload:
            print(f"STALE: {OUTPUT.relative_to(REPO)}", file=sys.stderr)
            print("Run: python3 scripts/build_ci_register.py", file=sys.stderr)
            return 1
        print("CI register is current")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(payload, encoding="utf-8")
    counts = register["counts"]
    print(f"wrote {OUTPUT.relative_to(REPO)}")
    print(
        f"  {counts['datastores_registered']} datastore CIs, "
        f"{counts['containers_registered']} container CIs"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
