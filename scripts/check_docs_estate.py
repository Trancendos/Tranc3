#!/usr/bin/env python3
"""Report which of the declared documentation estate actually exists.

Why this rather than writing the documents
------------------------------------------
A forward-planning pass proposed a documentation estate of roughly fifty
artefacts. The repository already holds 210 markdown documents, 47 of them
under `docs/governance/` alone, and most of the proposal was among them.
Generating the set again would have produced duplicates of things that exist
— against a standing instruction to consolidate rather than duplicate — and
would have buried the handful of genuine gaps in a pile of new files.

So `config/estate/documentation_estate.yaml` declares the estate as a
contract and this script measures it. An entry nobody can point at is
reported as missing. An entry pointing at a file that exists is reported
with its status: `live` when the artefact is wired to something that runs,
`descriptive` when it only describes.

`--check` fails when a `live` entry's file has disappeared. It deliberately
does not fail on a `missing` entry: those are the backlog, and a gate that is
red on day one for reasons nobody can fix that day teaches people to wave it
through — the same reasoning `scripts/flow_conformance.py` records for the
flow baseline.
"""

from __future__ import annotations

import argparse
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ESTATE = REPO / "config" / "estate" / "documentation_estate.yaml"

_STATUS_ORDER = ("live", "descriptive", "missing")


def _resolve(patterns: list[str]) -> Path | None:
    """The first declared path or glob that matches something."""
    for pattern in patterns:
        if any(ch in pattern for ch in "*?["):
            matches = sorted(REPO.glob(pattern))
            if matches:
                return matches[0]
        else:
            candidate = REPO / pattern
            if candidate.exists():
                return candidate
    return None


def audit() -> tuple[list[dict], list[str]]:
    """Return (entries, broken) — broken being live entries whose file is gone."""
    import yaml  # noqa: PLC0415

    estate = yaml.safe_load(ESTATE.read_text())
    entries: list[dict] = []
    broken: list[str] = []

    for section, items in estate["sections"].items():
        for item in items:
            declared = item.get("satisfied_by") or []
            found = _resolve(declared) if declared else None
            status = item.get("status", "missing")
            entries.append(
                {
                    "section": section,
                    "id": item["id"],
                    "title": item["title"],
                    "status": status,
                    "found": str(found.relative_to(REPO)) if found else None,
                    "note": item.get("note", ""),
                }
            )
            if status in ("live", "descriptive") and found is None:
                broken.append(
                    f"{item['id']} is declared {status} but none of its paths exist: "
                    f"{', '.join(declared) or '(none declared)'}"
                )
    return entries, broken


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit non-zero when a live or descriptive entry's file has gone.",
    )
    parser.add_argument("--missing", action="store_true", help="List only the gaps.")
    args = parser.parse_args(argv)

    entries, broken = audit()
    counts = {status: sum(1 for e in entries if e["status"] == status) for status in _STATUS_ORDER}

    if args.check:
        if broken:
            print("Documentation estate: FAILED")
            for problem in broken:
                print(f"  [ERROR] {problem}")
            print()
            print(
                "A declared artefact whose file has gone leaves the estate claiming "
                "coverage it no longer has. Restore the file, or move the entry to "
                "status: missing so the gap is visible."
            )
            return 1
        print(
            f"Documentation estate: PASSED — {counts['live']} live, "
            f"{counts['descriptive']} descriptive, {counts['missing']} missing"
        )
        return 0

    if args.missing:
        gaps = [e for e in entries if e["status"] == "missing"]
        print(f"Documentation estate — {len(gaps)} gap(s)\n")
        for entry in gaps:
            print(f"  {entry['id']:<24} {entry['title']}")
            if entry["note"]:
                print(f"    {' '.join(entry['note'].split())}")
        return 0

    print(f"Documentation estate — {len(entries)} declared artefact(s)")
    print("=" * 70)
    for status in _STATUS_ORDER:
        print(f"{status:<12} {counts[status]:>3}")
    print()
    for section in dict.fromkeys(e["section"] for e in entries):
        print(f"{section}")
        for entry in (e for e in entries if e["section"] == section):
            mark = {"live": "*", "descriptive": "-", "missing": "!"}[entry["status"]]
            where = entry["found"] or "nothing satisfies this"
            print(f"  {mark} {entry['id']:<24} {where}")
        print()
    print("* live   - descriptive   ! missing")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
