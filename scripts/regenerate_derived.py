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

Five variants were hit in a single afternoon (#1369, #1370, #1361 SBOMs; #1289,
#1288 CI register; #1246 action backlog), each needing the same two minutes of
archaeology to identify and one command to fix. This is that command.

What it does NOT do: it never touches the `check_*` / `*_conformance` scripts in
that job. Those are assertions, not generators, and a failure from one of them is
a real finding about the change rather than a stale artefact. `check_doc_reachability.py`
is the clearest case -- #1252 failed it by adding a document nothing linked to,
and the right fix was to link the document, not to regenerate anything.

Generator output is NOT captured. `scripts/ai_bom.py` exits 0 while printing its
non-permissive-licence findings, so a runner that captured output and showed it
only on failure would swallow a governance finding to keep its own log tidy --
the same trade this whole class of defect is about. The generators talk straight
to the caller; this script only summarises afterwards.

Run with no arguments to regenerate and report. `--check` reports what would
change and undoes it, so CI can use it too.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Generators only, in dependency order. Two edges are real and both were found by
# review rather than by design:
#   * the SBOMs feed the CI register, which the service review reads;
#   * `build_action_backlog.py` reads `docs/solution-packs/<slug>.md` and renders
#     `_no pack_` when one is absent, so it MUST run after `build_solution_packs.py`
#     -- otherwise a missing pack gets baked into the backlog, the pack is written
#     a moment later, and the backlog this script just regenerated is already stale.
# A generator absent from the tree is skipped rather than failing, so this stays
# usable on a branch that predates one of them.
GENERATORS = (
    "build_container_sboms.py",
    "build_ci_register.py",
    "build_topology_3d.py",
    "build_taxonomy_tree.py",
    "build_service_review.py",
    "build_solution_packs.py",
    "build_action_backlog.py",
    "build_matrix_index.py",
    "ai_bom.py",
    "generate_gate_engine_doc.py",
    "generate_plm_docs.py",
)

# Generated files that `.gitignore` covers, so `git status` cannot see them and
# `git checkout` cannot restore them. `--check` promises to leave the tree as it
# found it; without an explicit snapshot that promise is false for these, which
# would make this script an instance of the defect it exists to prevent.
IGNORED_OUTPUTS = ("logs/ai-bom.cyclonedx.json",)


def _status() -> dict[str, str]:
    """Working-tree state as {path: porcelain status}, including untracked files.

    `-z` is used so paths arrive verbatim rather than shell-quoted.
    """
    out = subprocess.run(
        ["git", "status", "--porcelain", "-z"], cwd=ROOT, capture_output=True, text=True
    ).stdout
    fields = [f for f in out.split("\0") if f]
    state: dict[str, str] = {}
    i = 0
    while i < len(fields):
        entry = fields[i]
        code, path = entry[:2], entry[3:]
        if code[0] in ("R", "C"):
            # A rename/copy spends a second field on the original path.
            i += 1
        state[path] = code
        i += 1
    return state


def _restore(paths: dict[str, str]) -> None:
    """Undo exactly what this run did, and nothing else.

    `git checkout -- .` would restore every tracked file from the index, which
    destroys an edit another process made while the generators ran, and still
    leaves behind any file a generator newly created. So tracked paths are
    restored one by one and new untracked paths are removed.
    """
    modified = [p for p, code in paths.items() if code != "??"]
    created = [p for p, code in paths.items() if code == "??"]
    if modified:
        subprocess.run(  # nosec B603 — list args, no shell; paths come from git status
            ["git", "checkout", "--", *modified], cwd=ROOT, capture_output=True
        )
    for path in created:
        target = ROOT / path
        if target.is_file():
            target.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="report what would change and fail if anything would, without keeping it",
    )
    args = parser.parse_args()

    before = _status()
    if before and args.check:
        print(
            "[ERROR] the working tree already has changes, so --check cannot tell "
            "a stale register from your own edit. Commit or stash first."
        )
        return 1

    snapshots: dict[Path, bytes | None] = {}
    if args.check:
        for rel in IGNORED_OUTPUTS:
            path = ROOT / rel
            snapshots[path] = path.read_bytes() if path.is_file() else None

    failed: list[str] = []
    for name in GENERATORS:
        script = ROOT / "scripts" / name
        if not script.is_file():
            continue
        result = subprocess.run(  # nosec B603 — list args, no shell; names are the literals above
            [sys.executable, str(script)], cwd=ROOT
        )
        if result.returncode != 0:
            failed.append(name)
            print(f"  [ERROR] {name} exited {result.returncode}")

    after = {p: code for p, code in _status().items() if p not in before}
    if args.check:
        _restore(after)
        for path, content in snapshots.items():
            if content is None:
                if path.is_file():
                    path.unlink()
            else:
                path.write_bytes(content)

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
