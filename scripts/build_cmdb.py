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
    with open(db_path + ".generation", "w") as f:
        f.write(uuid.uuid4().hex)

    print(f"Built {db_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
