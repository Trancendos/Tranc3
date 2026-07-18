#!/usr/bin/env python3
"""Sync workers/health-aggregator's SQLite DB into data/cmdb.db's
HealthObservation table.

Usage:
    python scripts/sync_health_aggregator.py [--health-db PATH] [--cmdb-db PATH]

Defaults: --health-db /data/health_aggregator.db (health-aggregator's own
default, per its DB_PATH env var), --cmdb-db data/cmdb.db (this repo's
default, per scripts/build_cmdb.py). Neither exists in this sandbox —
this script is meant to run where health-aggregator's volume is mounted.

Not a daemon: run this on a schedule (cron, ChronosSphere) to pull new
rows incrementally. Tracks the last-synced health_checks.id in a small
marker file next to the CMDB db so repeated runs are incremental, not
full re-scans.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.cmdb.health_sync import sync_from_health_aggregator_db  # noqa: E402
from src.cmdb.models import build_engine  # noqa: E402

# scripts/build_cmdb.py finishes a rebuild (19 CSVs, ~92 rows) in well
# under a second in practice. This is a generous multiple of that, not a
# tight timeout — it exists only to eventually recover from a build_cmdb.py
# that crashed or was killed while the REBUILDING sentinel was in place,
# which would otherwise leave every future sync run silently skipping
# forever (see _generation_is_stale).
_REBUILDING_STALE_SECONDS = 600


def _marker_path(cmdb_db_path: str) -> str:
    return cmdb_db_path + ".health_sync_marker"


def _generation_is_stale(cmdb_db_path: str) -> bool:
    """A pure elapsed-time check alone can't tell "abandoned" apart from
    "legitimately still running, just past the timeout" — a rebuild that's
    unusually slow (much larger CSVs someday, a loaded disk) but still
    actively writing would otherwise get preempted by a sync reading a
    half-rebuilt CMDB. Cross-checked against the db file's own mtime: if
    load_all() has written to db_path more recently than the REBUILDING
    sentinel itself, that's direct evidence the rebuild is still live
    right now, regardless of how long it's been running — only silence on
    *both* signals (no sentinel activity AND no db activity, for the full
    timeout) counts as abandoned.
    """
    generation_path = cmdb_db_path + ".generation"
    try:
        generation_mtime = os.path.getmtime(generation_path)
    except OSError:
        return False

    try:
        db_mtime = os.path.getmtime(cmdb_db_path)
    except OSError:
        db_mtime = generation_mtime  # db missing/unreadable — fall back to time-only

    most_recent_activity = max(generation_mtime, db_mtime)
    return (time.time() - most_recent_activity) > _REBUILDING_STALE_SECONDS


def _read_generation(cmdb_db_path: str) -> str | None:
    """A fresh random token written by scripts/build_cmdb.py on every
    rebuild — NOT the CMDB db file's own mtime, which also changes on
    every ordinary sync run (this script writes to that same file) and so
    can't distinguish "rebuilt" from "synced normally" that way. Missing
    (e.g. a cmdb.db built before this file existed) is treated as unknown,
    not as "just rebuilt" — see _read_marker.
    """
    generation_path = cmdb_db_path + ".generation"
    if not os.path.exists(generation_path):
        return None
    with open(generation_path) as f:
        return f.read().strip() or None


def _read_marker(marker_path: str) -> dict:
    """{"since_id": int, "cmdb_generation": str|None}. Missing, empty,
    genuinely corrupt, or a bare pre-generation-tracking integer (from an
    older version of this script) all resolve to a safe first run —
    since_id=0, cmdb_generation=None — rather than either crashing the
    scheduled sync or silently resuming from a since_id with no generation
    to detect a concurrent rebuild against. The dedupe check in
    health_sync.py means a spurious full rescan can never create
    duplicate HealthObservation rows, so "when in doubt, rescan" is safe.
    """
    if not os.path.exists(marker_path):
        return {"since_id": 0, "cmdb_generation": None}
    with open(marker_path) as f:
        raw = f.read().strip()
    if not raw:
        return {"since_id": 0, "cmdb_generation": None}
    try:
        data = json.loads(raw)
        return {"since_id": int(data["since_id"]), "cmdb_generation": data.get("cmdb_generation")}
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        # Includes a bare pre-generation-tracking integer marker (e.g. "17"),
        # which int(raw) would happily parse — but resuming from that id
        # without a generation to compare against means a rebuild that
        # happened around the same time as this upgrade would never be
        # detected, permanently skipping backfill for ids <= 17. Any
        # marker this script can't fully understand — legacy format or
        # genuinely corrupt — is treated the same way: a safe first run.
        # A one-time full rescan is the cost; the dedupe check in
        # health_sync.py means it can never create duplicate rows.
        print(f"Marker file {marker_path} is legacy/malformed ({raw!r}) — resyncing from id 0.")
        return {"since_id": 0, "cmdb_generation": None}


def _write_marker(marker_path: str, since_id: int, cmdb_generation: str | None) -> None:
    # Atomic (write-temp-then-rename) so a crash mid-write can never leave
    # a torn/partial JSON file for the next run's _read_marker to choke on.
    tmp_path = marker_path + ".tmp"
    with open(tmp_path, "w") as f:
        json.dump({"since_id": since_id, "cmdb_generation": cmdb_generation}, f)
    os.replace(tmp_path, marker_path)


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health-db",
        # DB_PATH matches workers/health-aggregator/worker.py's own env var
        # name — if the worker is deployed with a non-default DB_PATH, this
        # must follow it or it silently syncs from (or 404s against) the
        # wrong file. HEALTH_AGGREGATOR_DB_PATH is kept as a higher-priority
        # override for pointing this script somewhere different from the
        # worker itself (e.g. a read replica).
        default=os.environ.get(
            "HEALTH_AGGREGATOR_DB_PATH",
            os.environ.get("DB_PATH", "/data/health_aggregator.db"),
        ),
    )
    parser.add_argument(
        "--cmdb-db",
        default=os.path.join(repo_root, "data", "cmdb.db"),
    )
    args = parser.parse_args()

    if not os.path.exists(args.health_db):
        print(f"health-aggregator DB not found at {args.health_db} — nothing to sync.")
        return 1
    if not os.path.exists(args.cmdb_db):
        print(f"CMDB DB not found at {args.cmdb_db} — run scripts/build_cmdb.py first.")
        return 1

    marker_path = _marker_path(args.cmdb_db)
    marker = _read_marker(marker_path)
    since_id = marker["since_id"]
    cmdb_generation = _read_generation(args.cmdb_db)

    # scripts/build_cmdb.py writes this sentinel before load_all() runs
    # (which drops and recreates every table) and replaces it with a real
    # token only once the rebuild succeeds. Treating it as a real changed
    # generation would trigger a resync while tables are actively being
    # dropped/recreated underneath this query — defer instead, UNLESS the
    # sentinel is stale enough to mean the rebuild that wrote it crashed or
    # was killed rather than being merely slow. Without this staleness
    # check, an abandoned REBUILDING sentinel would make every future run
    # exit "successfully" through this branch forever, silently never
    # syncing again.
    if cmdb_generation == "REBUILDING":
        if not _generation_is_stale(args.cmdb_db):
            print(
                f"{args.cmdb_db} is mid-rebuild (generation sidecar shows REBUILDING) — skipping this run."
            )
            return 0
        print(
            f"{args.cmdb_db}'s generation sidecar has shown REBUILDING for over "
            f"{_REBUILDING_STALE_SECONDS}s — treating as an abandoned/crashed rebuild, not "
            "an in-progress one, and proceeding rather than deferring forever."
        )

    # scripts/build_cmdb.py drops and recreates every table (including
    # HealthObservation) on every rebuild, but the marker file survives on
    # disk untouched — without this check, a rebuilt CMDB would resume from
    # the old since_id and never backfill the history the rebuild wiped
    # out. Detected via build_cmdb.py's generation token changing, not via
    # HealthObservation being empty — a legitimately-empty result (every
    # fetched check currently unmapped) must NOT trigger this, or every
    # run would re-trigger a full rescan forever.
    if (
        marker["cmdb_generation"] is not None
        and cmdb_generation is not None
        and cmdb_generation != marker["cmdb_generation"]
    ):
        print(
            f"{args.cmdb_db} was rebuilt since the last sync (generation changed) — resyncing from 0."
        )
        since_id = 0

    engine = build_engine(args.cmdb_db)
    session = sessionmaker(bind=engine)()
    try:
        stats = sync_from_health_aggregator_db(session, args.health_db, since_id=since_id)
    finally:
        session.close()

    # If the generation sidecar is transiently unreadable this run (mid
    # deployment, a restore in progress), don't let that overwrite a real,
    # previously-recorded generation with None — that would silently
    # disable rebuild detection forever, since a future real rebuild's
    # token would then always look "different from None" the same as a
    # transient-miss cycle does, and there'd be no way to tell them apart.
    generation_to_write = (
        cmdb_generation if cmdb_generation is not None else marker["cmdb_generation"]
    )
    _write_marker(marker_path, stats["max_id"], generation_to_write)
    print(f"Synced {args.health_db} -> {args.cmdb_db}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
