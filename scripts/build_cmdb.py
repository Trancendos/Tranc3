#!/usr/bin/env python3
"""Build data/cmdb.db from docs/architecture/ea-workbook/*.csv.

Regenerate after the CSVs change — this is a derived build artifact
(data/cmdb.db is gitignored, same as every other *.db in this repo), not a
second place to hand-edit CMDB data. The CSVs stay the source of truth.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.cmdb.loader import load_all  # noqa: E402

if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(repo_root, "data", "cmdb.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    stats = load_all(db_path)
    print(f"Built {db_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
