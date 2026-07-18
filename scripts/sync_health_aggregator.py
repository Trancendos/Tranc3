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

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.cmdb.health_sync import sync_from_health_aggregator_db  # noqa: E402
from src.cmdb.models import build_engine  # noqa: E402


def _marker_path(cmdb_db_path: str) -> str:
    return cmdb_db_path + ".health_sync_marker"


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
    """{"since_id": int, "cmdb_generation": str|None}. Missing or malformed
    (including a bare pre-generation-tracking integer) is treated as a
    first run — since_id=0, cmdb_generation=None so the rebuild check below
    is skipped rather than misfiring on a marker written by an older
    version of this script.

    A permission/IO error reading an *existing* marker is NOT treated as
    "start over": that would turn a persistent permissions misconfiguration
    into an expensive full health_checks scan on every scheduled run,
    forever. It's surfaced as a real failure instead.
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
        try:
            return {"since_id": int(raw), "cmdb_generation": None}
        except ValueError as exc:
            raise ValueError(f"Marker file {marker_path} is corrupt: {raw!r}") from exc


def _write_marker(marker_path: str, since_id: int, cmdb_generation: str | None) -> None:
    with open(marker_path, "w") as f:
        json.dump({"since_id": since_id, "cmdb_generation": cmdb_generation}, f)


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

    _write_marker(marker_path, stats["max_id"], cmdb_generation)
    print(f"Synced {args.health_db} -> {args.cmdb_db}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
