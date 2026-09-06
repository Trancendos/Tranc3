#!/usr/bin/env python3
"""Give every CMDB service a PID, and name the ones that cannot have one yet.

WHY THIS EXISTS

`src/cmdb/` and `docs/architecture/ea-workbook/` describe the estate's
infrastructure. `src/entities/platform.py` describes its identity -- 43
Locations, each with a PID. Until now the two had no key in common: the EA
service inventory carried `Tier3AI` and `Tier2Prime` as free text and no PID
column at all, so nothing could join a running service to the Location that
owns it, and nothing could tell you which Locations had no service behind them.

Two consequences, both measured on 2026-08-22:

  * The inventory had drifted from the registry without anything noticing.
    SRV-SPARK-001 named Norman Hawkins as The Spark's Tier-3 AI (he is its
    Tier-2 Prime; Imfy is the Lead AI), and six rows still used
    "The Guardian (Anchor: Orb of Orisis)", a combined title CLAUDE.md
    retired. Free text cannot be checked. A PID can.

  * Thirteen services named no Location at all. Those are not errors to be
    hidden -- they are the discovery list. A service nobody owns is exactly
    what a CMDB is for finding.

WHAT IT WILL NOT DO

It will not guess. Every PID it assigns records the BASIS on which it was
assigned, and a service that no basis resolves is left blank and reported
rather than attached to whichever Location looked closest. A wrong owner is
worse than a missing one: a blank prompts a question, a wrong value ends it.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
INVENTORY = REPO / "docs" / "architecture" / "ea-workbook" / "02_service_inventory.csv"
ENTITIES_MD = REPO / "PLATFORM_ENTITIES.md"

sys.path.insert(0, str(REPO))

# Services deliberately reviewed by hand, because no automatic basis is sound.
# Each records why. Absence from this map is not a decision -- it is the
# discovery list, and stays visible as one.
REVIEWED: dict[str, tuple[str, str]] = {
    "SRV-STUDIOWORKER-001": ("PID-STD", "ServiceName names The Studio explicitly"),
    "SRV-LABSVC-001": ("PID-LAB", "'The Lab Extended Service' is The Lab's second worker"),
    "SRV-WS-001": ("PID-NXS", "the Nexus WebSocket worker; workers/infinity-ws is PID-NXS"),
    "SRV-FFMPEG-001": ("PID-TKG", "video encode for TateKing, its only consumer"),
    "SRV-REMOTION-001": ("PID-TKG", "video render for TateKing, its only consumer"),
    "SRV-APIGW-001": ("PID-INF", "self-hosted API gateway fronting Infinity's auth surface"),
}

# Free-text AI names in the CSV that the registry no longer uses.
RETIRED_AI_NAMES = {
    "The Guardian (Anchor: Orb of Orisis)": "The Guardian (Marcus Magnolia)",
}


def _norm(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (value or "").lower())


def _worker_table() -> dict[str, str]:
    """worker directory -> PID, from PLATFORM_ENTITIES.md's port table.

    Covers 26 of the estate's ~89 workers (ports 8004-8029 only). That partial
    coverage is itself worth knowing and is reported, not silently absorbed.
    """
    if not ENTITIES_MD.is_file():
        return {}
    pattern = (
        r"^\|\s*(\d{4})\s*\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|"
        r"\s*([^|]*?)\s*\|\s*(PID-[A-Z0-9]+)\s*\|"
    )
    return {m[1]: m[4] for m in re.findall(pattern, ENTITIES_MD.read_text(encoding="utf-8"), re.M)}


def _registry_indexes() -> tuple[dict[str, str], dict[str, list[str]]]:
    from src.entities.platform import PLATFORM_ENTITIES

    by_location = {_norm(name): entity.pid for name, entity in PLATFORM_ENTITIES.items()}
    by_lead: dict[str, list[str]] = defaultdict(list)
    for entity in PLATFORM_ENTITIES.values():
        leads = getattr(entity, "lead_ais", None) or ([entity.lead_ai] if entity.lead_ai else [])
        for ai in leads:
            if entity.pid not in by_lead[_norm(ai)]:
                by_lead[_norm(ai)].append(entity.pid)
    return by_location, dict(by_lead)


def _leads_by_pid() -> dict[str, list[str]]:
    """PID -> the Lead AI names the registry says that Location actually has."""
    from src.entities.platform import PLATFORM_ENTITIES

    return {
        entity.pid: (
            getattr(entity, "lead_ais", None) or ([entity.lead_ai] if entity.lead_ai else [])
        )
        for entity in PLATFORM_ENTITIES.values()
    }


def _location_from_stem(service_id: str, by_location: dict[str, str]) -> str:
    """SRV-SPARK-001 -> PID-SPK, tolerating the leading "The" in Location names.

    This has to outrank `lead-ai-unique`, and the reason is the whole point of
    the exercise. SRV-SPARK-001's recorded Tier3AI was "Norman Hawkins", who
    resolves uniquely to The Observatory -- so ranking the free-text AI name
    higher attached The Spark's own service to a different Location, and left
    PID-SPK looking like it had no service at all. The ID stem is stable; the
    free-text name is the field that drifted.
    """
    stem = _norm(service_id.rsplit("-", 1)[0].removeprefix("SRV-"))
    if not stem:
        return ""
    for key, pid in by_location.items():
        if key == stem or key == f"the{stem}":
            return pid
    return ""


def _resolve_pid(sid: str, service_name: str, lead: str, idx: dict) -> tuple[str, str]:
    """(PID, basis) for one service, trying each basis strongest-first.

    Ordering is load-bearing, not stylistic. SRV-SPARK-001's recorded Tier3AI
    was "Norman Hawkins", who resolves uniquely to The Observatory -- so
    ranking the free-text AI name above the ID stem attached The Spark's own
    service to a different Location. The stem is stable; the free text is the
    field that drifted, which is the whole reason a key was needed.
    """
    if sid in REVIEWED:
        return REVIEWED[sid][0], "reviewed"

    by_location = idx["by_location"]
    if _norm(service_name) in by_location:
        return by_location[_norm(service_name)], "location-name"

    from_stem = _location_from_stem(sid, by_location)
    if from_stem:
        return from_stem, "service-id-stem"

    stem = _norm(sid.rsplit("-", 1)[0].removeprefix("SRV-"))
    hits = {
        pid
        for worker, pid in idx["workers"].items()
        if _norm(worker) == stem or _norm(worker).replace("service", "") == stem
    }
    if len(hits) == 1:
        return hits.pop(), "worker-table"

    by_lead = idx["by_lead"].get(_norm(lead), [])
    if len(by_lead) == 1:
        return by_lead[0], "lead-ai-unique"

    return "", ""


def _corrected_lead(pid: str, lead: str, leads_by_pid: dict) -> str:
    """The Lead AI the registry says this Location has, when the CSV disagrees.

    With a PID in hand the free text becomes checkable rather than
    authoritative. Ambiguity is left uncorrected: a Location with several Lead
    AIs cannot say which one a given service belongs to, and guessing there
    would replace a visible disagreement with an invisible wrong answer.
    """
    if not pid or not lead:
        return ""
    leads = leads_by_pid.get(pid, [])
    if not leads or lead in leads:
        return ""
    return leads[0] if len(leads) == 1 else ""


def resolve() -> list[dict[str, str]]:
    """One record per service: its PID, the basis, and any drift found."""
    by_location, by_lead = _registry_indexes()
    idx = {"by_location": by_location, "by_lead": by_lead, "workers": _worker_table()}
    leads_by_pid = _leads_by_pid()

    out: list[dict[str, str]] = []
    for row in csv.DictReader(INVENTORY.open(encoding="utf-8")):
        sid = row["ServiceID"]
        lead_raw = (row.get("Tier3AI") or "").strip()
        # A retired name is drift to report, not a lookup to fail on.
        drift = RETIRED_AI_NAMES.get(lead_raw, "")
        lead = drift or lead_raw

        pid, basis = _resolve_pid(sid, row["ServiceName"], lead, idx)
        out.append(
            {
                "ServiceID": sid,
                "ServiceName": row["ServiceName"],
                "PID": pid,
                "Basis": basis or "unresolved",
                "RecordedTier3AI": lead_raw,
                "RetiredNameShouldBe": drift,
                "Tier3AIShouldBe": _corrected_lead(pid, lead, leads_by_pid),
            }
        )
    return out


def _block(heading: str, rows: list[str]) -> list[str]:
    """A named group of report lines, or nothing when the group is empty.

    Printing an empty heading would read as a category with no members, which
    is a different claim from the category not applying.
    """
    return [f"\n  {heading}", *rows] if rows else []


def report(records: list[dict[str, str]]) -> str:
    resolved = [r for r in records if r["PID"]]
    retired = [r for r in records if r["RetiredNameShouldBe"]]
    wrong = [r for r in records if r.get("Tier3AIShouldBe")]
    unresolved = [r for r in records if not r["PID"]]
    bases = Counter(r["Basis"] for r in resolved)

    lines = [
        f"PID coverage: {len(resolved)}/{len(records)} services carry a PID",
        "  by basis: " + ", ".join(f"{k}={v}" for k, v in sorted(bases.items())),
    ]
    lines += _block(
        f"{len(retired)} rows use a retired AI name (drift, not a gap):",
        [
            f"    {r['ServiceID']:22} {r['RecordedTier3AI']} -> {r['RetiredNameShouldBe']}"
            for r in retired
        ],
    )
    lines += _block(
        f"{len(wrong)} rows name an AI the registry says does not lead that Location:",
        [
            f"    {r['ServiceID']:22} {r['PID']:10} "
            f"{r['RecordedTier3AI']} -> {r['Tier3AIShouldBe']}"
            for r in wrong
        ],
    )
    lines += _block(
        f"{len(unresolved)} services own no Location -- the discovery list:",
        [
            f"    {r['ServiceID']:22} {r['ServiceName'][:40]:40} "
            f"Tier3AI={r['RecordedTier3AI'] or '(blank)'}"
            for r in unresolved
        ],
    )
    return "\n".join(lines)


def unrepresented_locations(records: list[dict[str, str]]) -> list[tuple[str, str]]:
    """Locations with no service behind them -- the other half of the question."""
    from src.entities.platform import PLATFORM_ENTITIES

    claimed = {r["PID"] for r in records if r["PID"]}
    return [
        (entity.pid, name)
        for name, entity in PLATFORM_ENTITIES.items()
        if entity.pid not in claimed
    ]


def write_inventory(records: list[dict[str, str]]) -> dict[str, int]:
    """Add the PID column and replace retired AI names, preserving every other field.

    The PID is written even when blank, because an empty cell in a column that
    exists is a visible question, while a missing column is not a question at
    all -- which is how the join stayed absent for as long as it did.
    """
    by_id = {r["ServiceID"]: r for r in records}
    rows = list(csv.DictReader(INVENTORY.open(encoding="utf-8")))
    fields = list(rows[0].keys())
    if "PID" not in fields:
        fields.insert(fields.index("Tier3AI"), "PID")

    counts = {"pid": 0, "names": 0}
    for row in rows:
        record = by_id.get(row["ServiceID"])
        if record is None:
            row.setdefault("PID", "")
            continue
        row["PID"] = record["PID"]
        if record["PID"]:
            counts["pid"] += 1
        if record["RetiredNameShouldBe"]:
            row["Tier3AI"] = record["RetiredNameShouldBe"]
            counts["names"] += 1
        if record.get("Tier3AIShouldBe"):
            row["Tier3AI"] = record["Tier3AIShouldBe"]
            counts["names"] += 1
        if row.get("Tier2Prime") in RETIRED_AI_NAMES:
            row["Tier2Prime"] = RETIRED_AI_NAMES[row["Tier2Prime"]]
            counts["names"] += 1

    with INVENTORY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit non-zero if PID coverage has fallen below the recorded floor",
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the PID column and correct retired AI names in the inventory CSV",
    )
    parser.add_argument(
        "--floor",
        type=int,
        default=77,
        help="minimum services that must carry a PID (default: the 2026-08-22 measurement of 77)",
    )
    args = parser.parse_args()

    records = resolve()
    if args.write:
        changed = write_inventory(records)
        print(
            f"inventory: wrote PID for {changed['pid']} services, "
            f"corrected {changed['names']} retired AI names"
        )
        records = resolve()
    print(report(records))

    missing = unrepresented_locations(records)
    print(f"\nLocations with no service in the CMDB: {len(missing)}")
    for pid, name in sorted(missing):
        print(f"    {pid:10} {name}")

    resolved = sum(1 for r in records if r["PID"])
    if args.check and resolved < args.floor:
        print(
            f"\nPID coverage: FAILED -- {resolved} services carry a PID, floor is {args.floor}",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print(f"\nPID coverage: PASSED ({resolved} >= floor {args.floor})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
