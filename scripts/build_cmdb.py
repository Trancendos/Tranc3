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


def _write_generation_token(generation_path: str, token: str) -> None:
    # Atomic (temp file + os.replace, unique temp path per call): a crash
    # mid-write must never leave a torn/partial token on disk, and two
    # overlapping invocations must never clobber each other's temp file.
    tmp_path = f"{generation_path}.{uuid.uuid4().hex}.tmp"
    with open(tmp_path, "w") as f:
        f.write(token)
    os.replace(tmp_path, generation_path)


if __name__ == "__main__":
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    db_path = os.path.join(repo_root, "data", "cmdb.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    generation_path = db_path + ".generation"

    # A fresh token identifies this rebuild to scripts/sync_health_aggregator.py,
    # which resets its incremental marker whenever the token it sees differs
    # from the one it last recorded — that's how it tells "the CMDB was
    # rebuilt, HealthObservation is now empty" apart from "something wrote to
    # the db since I last looked" (true on every normal sync run too).
    #
    # A crash between load_all() finishing (which drops and recreates every
    # table, including HealthObservation) and the token being written would
    # otherwise leave the OLD token on disk paired with a freshly-emptied
    # table — exactly the state the token exists to distinguish. Written
    # here, before load_all(), a sentinel that can never coincidentally match
    # a real UUID4 token closes that window: any crash from this point until
    # the real token replaces it leaves a value on disk that's guaranteed to
    # differ from whatever the marker last recorded, forcing a safe (if
    # unnecessary) resync next time rather than silently trusting a stale
    # generation against a table that may already have been wiped.
    _write_generation_token(generation_path, "REBUILDING")

    stats = load_all(db_path)

    _write_generation_token(generation_path, uuid.uuid4().hex)

    print(f"Built {db_path}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
