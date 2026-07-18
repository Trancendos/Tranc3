#!/usr/bin/env python3
"""Build data/cmdb.db from docs/architecture/ea-workbook/*.csv.

Regenerate after the CSVs change — this is a derived build artifact
(data/cmdb.db is gitignored, same as every other *.db in this repo), not a
second place to hand-edit CMDB data. The CSVs stay the source of truth.
"""

import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cmdb.loader import load_all  # noqa: E402

if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(repo_root, "data", "cmdb.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    stats = load_all(db_path)

    # A fresh token on every rebuild, independent of db_path's own mtime
    # (which also changes on every downstream write to the db, e.g.
    # scripts/sync_health_aggregator.py's own syncs) — that's the signal
    # sync_health_aggregator.py uses to tell "this CMDB was rebuilt, reset
    # my incremental marker" apart from "something wrote to the db since
    # I last looked, which happens on every normal sync run too."
    #
    # Written atomically (temp file + os.replace): a crash mid-write must
    # never leave a torn/partial token on disk — that could coincidentally
    # collide with the *next* real generation and silently disable rebuild
    # detection, permanently losing a backfill window with no visible error.
    generation_path = db_path + ".generation"
    generation_token = uuid.uuid4().hex
    # Unique per invocation (not a fixed ".tmp" suffix) — two overlapping
    # rebuilds sharing one temp path could have the second's write clobber
    # the first's temp file out from under it, or delete-then-replace race
    # so one process's os.replace raises FileNotFoundError after it already
    # rebuilt the db, leaving that rebuild's generation token never written.
    tmp_generation_path = f"{generation_path}.{generation_token}.tmp"
    with open(tmp_generation_path, "w") as f:
        f.write(generation_token)
    os.replace(tmp_generation_path, generation_path)

    print(f"Built {db_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
