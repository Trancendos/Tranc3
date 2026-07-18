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

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy.orm import sessionmaker  # noqa: E402

from src.cmdb.health_sync import sync_from_health_aggregator_db  # noqa: E402
from src.cmdb.models import HealthObservation, build_engine  # noqa: E402


def _marker_path(cmdb_db_path: str) -> str:
    return cmdb_db_path + ".health_sync_marker"


def _read_since_id(marker_path: str) -> int:
    if not os.path.exists(marker_path):
        return 0
    try:
        with open(marker_path) as f:
            return int(f.read().strip() or 0)
    except (ValueError, OSError) as exc:
        print(f"Marker file {marker_path} unreadable ({exc}) — resyncing from id 0.")
        return 0


def _write_since_id(marker_path: str, value: int) -> None:
    with open(marker_path, "w") as f:
        f.write(str(value))


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--health-db",
        default=os.environ.get("HEALTH_AGGREGATOR_DB_PATH", "/data/health_aggregator.db"),
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
    since_id = _read_since_id(marker_path)

    engine = build_engine(args.cmdb_db)
    session = sessionmaker(bind=engine)()
    try:
        # scripts/build_cmdb.py drops and recreates every table (including
        # HealthObservation) on every rebuild, but the marker file survives
        # on disk untouched — without this check, a rebuilt-but-empty CMDB
        # would resume from the old since_id and never backfill the history
        # that was just wiped out.
        if since_id > 0 and session.query(HealthObservation).first() is None:
            print(f"HealthObservation is empty but marker was at id {since_id} — resyncing from 0.")
            since_id = 0
        stats = sync_from_health_aggregator_db(session, args.health_db, since_id=since_id)
    finally:
        session.close()

    _write_since_id(marker_path, stats["max_id"])
    print(f"Synced {args.health_db} -> {args.cmdb_db}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
