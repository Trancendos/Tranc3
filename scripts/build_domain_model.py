#!/usr/bin/env python3
"""Emit the domain model, its PostgreSQL DDL, and the conformance report.

Three outputs from one model:

  docs/architecture/domain-model.json   entities, attributes, associations, routes
  docs/architecture/domain-model.sql    schemas, tables, foreign keys, RLS policies
  docs/architecture/conformance.json    per Location: CMDB, docs, registry, env,
                                        dependencies, domain model

The model is Mendix-shaped -- module, entity, attribute, association, access rule
constrained per role -- because that shape makes one description generate the
schema, the permissions and the routing instead of maintaining three that drift.

Usage:
    python3 scripts/build_domain_model.py            # write all three
    python3 scripts/build_domain_model.py --check    # fail if stale
    python3 scripts/build_domain_model.py --report   # conformance summary only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.domain.build import build_model  # noqa: E402
from src.domain.conformance import assess, summary  # noqa: E402
from src.domain.ddl import generate  # noqa: E402

JSON_OUT = REPO / "docs" / "architecture" / "domain-model.json"
SQL_OUT = REPO / "docs" / "architecture" / "domain-model.sql"
CONFORMANCE_OUT = REPO / "docs" / "architecture" / "conformance.json"


def _payloads() -> dict[Path, str]:
    model = build_model()
    rows = assess()
    return {
        JSON_OUT: json.dumps(model.to_dict(), indent=2, ensure_ascii=False) + "\n",
        SQL_OUT: generate(model),
        CONFORMANCE_OUT: json.dumps(
            {"summary": summary(), "locations": [r.as_row() for r in rows]},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args(argv)

    if args.report:
        counts = summary()
        width = max(len(k) for k in counts)
        for key, value in counts.items():
            print(f"{key.replace('_', ' '):<{width}}  {value}")
        print(
            "\n'not checked' is reported as not checked, never as passing. A property "
            "this script could not evaluate is not a property that passed."
        )
        return 0

    payloads = _payloads()

    if args.check:
        stale = [p for p, text in payloads.items() if not p.is_file() or p.read_text() != text]
        if stale:
            for path in stale:
                print(f"STALE: {path.relative_to(REPO)}", file=sys.stderr)
            print("\nRun: python3 scripts/build_domain_model.py", file=sys.stderr)
            return 1
        print("domain model, DDL and conformance report are current")
        return 0

    for path, text in payloads.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"wrote {path.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
