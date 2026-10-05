#!/usr/bin/env python3
"""Regenerate every derived register the Service Topology job checks for currency.

The problem this exists for, measured on 2026-10-05 across the open pull request
queue: `ci.yml`'s Service Topology job runs roughly a dozen `--check` steps, each
asserting that a committed, generated file still matches the tree it was derived
from. Nothing regenerates them automatically, and neither dependabot nor renovate
knows they exist. So a pull request that edits one worker requirement arrives red
at `Container SBOMs are current`; one that bumps a compose digest arrives red at
`CI register is current`; and one that merely *adds lines to a file the backlog
cites* arrives red at `Action backlog is current`, because that register cites
items by `file:line`.

Four variants were hit in a single afternoon (#1369, #1370 SBOMs; #1289, #1288 CI
register; #1246 action backlog), each needing the same two minutes of archaeology
to identify and one command to fix. This is that command.

What it does NOT do: it never touches the `check_*` / `*_conformance` scripts in
that job. Those are assertions, not generators, and a failure from one of them is
a real finding about the change rather than a stale artefact. `check_doc_reachability.py`
is the clearest case — #1252 failed it by adding a document nothing linked to,
and the right fix was to link the document, not to regenerate anything.

Run with no arguments to regenerate and report. `--check` reports what would
change without writing, so CI can use it too.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Generators only, in dependency order: the SBOMs feed the CI register, which the
# service review reads. A generator absent from the tree is skipped rather than
# failing, so this stays usable on a branch that predates one of them.
GENERATORS = (
    "build_container_sboms.py",
    "build_ci_register.py",
    "build_action_backlog.py",
    "build_topology_3d.py",
    "build_taxonomy_tree.py",
    "build_service_review.py",
    "build_solution_packs.py",
    "build_matrix_index.py",
    "ai_bom.py",
    "generate_gate_engine_doc.py",
    "generate_plm_docs.py",
)


def _tracked_changes() -> list[str]:
    out = subprocess.run(
        ["git", "status", "--porcelain"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    return [line[3:] for line in out.splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would change and fail if anything would, without keeping it",
    )
    args = parser.parse_args()

    before = set(_tracked_changes())
    if before and args.check:
        print(
            "[ERROR] the working tree already has changes, so --check cannot tell "
            "a stale register from your own edit. Commit or stash first."
        )
        return 1

    failed: list[str] = []
    for name in GENERATORS:
        script = ROOT / "scripts" / name
        if not script.is_file():
            continue
        result = subprocess.run(
            [sys.executable, str(script)], cwd=ROOT, capture_output=True, text=True
        )
        if result.returncode != 0:
            failed.append(name)
            print(f"  [ERROR] {name} exited {result.returncode}")
            tail = (result.stderr or result.stdout).strip().splitlines()[-3:]
            for line in tail:
                print(f"          {line}")

    after = set(_tracked_changes()) - before
    if args.check:
        subprocess.run(["git", "checkout", "--", "."], cwd=ROOT, capture_output=True)

    if failed:
        print(f"\n{len(failed)} generator(s) failed: {', '.join(failed)}")
        return 1

    if not after:
        print(f"Derived registers: already current ({len(GENERATORS)} generators ran)")
        return 0

    verb = "would change" if args.check else "regenerated"
    print(f"Derived registers: {len(after)} file(s) {verb}")
    for path in sorted(after)[:20]:
        print(f"  {path}")
    if len(after) > 20:
        print(f"  … and {len(after) - 20} more")
    return 1 if args.check else 0


if __name__ == "__main__":
    sys.exit(main())
