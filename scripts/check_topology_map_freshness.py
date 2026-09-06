#!/usr/bin/env python3
"""Fail CI if the topology map is stale vs. its generator.

`build_topology_map.py` derives `docs/architecture/topology-graph.json` and
`docs/architecture/topology-map.html` from live repo state — compose,
`api.py`'s actual mounts, `src/entities/platform.py`, the router-duplication
guard's classification tables, and the Matrix Suites registry. Nothing
enforces that the committed output still matches what the generator would
produce right now, so — same class of bug `check_master_matrix_freshness.py`
guards against for the EA workbook — it could silently drift from the code
it claims to describe. The generator has no `--output` flag, so this backs
up the committed files to a temp dir, runs the generator in place, diffs
the regenerated output against the backup (ignoring only the `generated_at`
timestamp, which legitimately differs on every run and carries no
information about staleness), then restores the committed bytes — in a
`finally`, so a crashed generator run can't leave the working tree holding
regenerated-not-committed content.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = ROOT / "scripts" / "build_topology_map.py"
COMMITTED_JSON = ROOT / "docs" / "architecture" / "topology-graph.json"
COMMITTED_HTML = ROOT / "docs" / "architecture" / "topology-map.html"

TIMESTAMP_RE = re.compile(r'"generated_at":\s*"[^"]*"')


def _normalized(text: str) -> str:
    return TIMESTAMP_RE.sub('"generated_at":"<normalized>"', text)


def main() -> int:
    if not COMMITTED_JSON.exists() or not COMMITTED_HTML.exists():
        print("MISSING: topology map output doesn't exist yet — run the generator first:")
        print(f"  python {GENERATOR.relative_to(ROOT)}")
        return 1

    committed_json = _normalized(COMMITTED_JSON.read_text(encoding="utf-8"))
    committed_html = _normalized(COMMITTED_HTML.read_text(encoding="utf-8"))

    with tempfile.TemporaryDirectory() as tmp:
        json_backup = Path(tmp) / "graph.json"
        html_backup = Path(tmp) / "map.html"
        shutil.copyfile(COMMITTED_JSON, json_backup)
        shutil.copyfile(COMMITTED_HTML, html_backup)

        # The generator has no --output flag; it writes straight to
        # COMMITTED_JSON/COMMITTED_HTML, so this necessarily mutates them
        # for the duration of this block. Restoration is in `finally` so a
        # crashed generator run (nonzero exit, or a read failure below if
        # it left a file missing/truncated) can't skip it and leave the
        # working tree holding regenerated-not-committed content.
        try:
            result = subprocess.run(
                [sys.executable, str(GENERATOR)], cwd=ROOT, capture_output=True, text=True
            )
            regenerated_json = _normalized(COMMITTED_JSON.read_text(encoding="utf-8"))
            regenerated_html = _normalized(COMMITTED_HTML.read_text(encoding="utf-8"))
        finally:
            shutil.copyfile(json_backup, COMMITTED_JSON)
            shutil.copyfile(html_backup, COMMITTED_HTML)

        if result.returncode != 0:
            print("FAILED to run the generator for comparison:")
            print(result.stdout)
            print(result.stderr)
            return 1

    stale = False
    if committed_json != regenerated_json:
        stale = True
        print("STALE: topology-graph.json differs from what the generator produces now.")
        try:
            c = json.loads(committed_json)
            r = json.loads(regenerated_json)
            if c.get("summary") != r.get("summary"):
                print(f"  committed summary:   {c.get('summary')}")
                print(f"  regenerated summary: {r.get('summary')}")
        except json.JSONDecodeError:
            pass

    if committed_html != regenerated_html:
        stale = True
        print("STALE: topology-map.html differs from what the generator produces now.")

    if stale:
        print(
            "\nRun `python scripts/build_topology_map.py` and commit the result — "
            "api.py, docker-compose.production.yml, src/entities/platform.py, "
            "scripts/check_duplicate_routers.py, or the Matrix Suites registry "
            "changed since this was last generated."
        )
        return 1

    print("OK: topology map matches its generator.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
