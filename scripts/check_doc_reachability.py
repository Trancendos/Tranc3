#!/usr/bin/env python3
"""Fail when a document becomes unreachable, and when one is fixed unrecorded.

The failure this exists for
---------------------------
On 2026-09-05, 52 of 321 markdown documents were named by nothing anywhere in
the repository — no markdown link, no backtick path mention, no reference from
code or configuration, and not swept into the action backlog. About 530 KB of
correct, carefully written material that no reader and no tool could arrive at.

Twenty-eight were `wiki-content/Historical-*` and `wiki-content/Strategy-*`:
phase reports, mind maps, SCAMPER analyses, zero-cost assessments. Five of
them were SWOT or forensic assessments — so when the platform owner asked for
a SWOT and a forensic assessment, the honest first answer was that five
already existed and none could be found.

This is the estate's characteristic defect in a different medium. A guard that
runs and never blocks, a control that reports and never acts, and a register
that is accurate and unread are the same failure: something correct, present,
and never invoked.

What "reachable" means here
---------------------------
A document is reachable when any OTHER tracked file names it — by repository
path or by bare filename — in any syntax. That is deliberately generous:
markdown links, backticked paths in prose (the estate's dominant style), a
path in a workflow, a template loaded by `src/townhall`, a register swept by
the backlog generator. The question is not "is it linked" but "can anything at
all lead a reader here". A document nothing names fails even that.

It is generous in the other direction too: a bare filename match can be
coincidental. That errs toward reporting a document as reachable, which is the
right direction for a gate whose job is to catch the clear cases.

Why a ratchet rather than a rule
--------------------------------
Failing all 46 today would put the build red for work nobody can do today,
which teaches people to wave the gate through — the outcome this repository
has already paid for once. So the current set is recorded, and this fails on:

  * a NEW document that nothing names, and
  * a recorded one that has become reachable without refreshing the baseline.

The second direction matters as much as the first: an improvement nobody
records lets the next regression slip in under the old count.

Usage:
    python3 scripts/check_doc_reachability.py
    python3 scripts/check_doc_reachability.py --write-baseline
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "config" / "estate" / "doc_reachability_baseline.json"

#: Submodules are checked in their own repositories.
_SKIP = ("compliance/magna-carta", "workers/cranbania", "node_modules")

#: Documents that are entry points by nature: a reader arrives at them
#: directly, so nothing needs to name them. Each is a real front door, not a
#: convenience exemption — adding to this list means claiming a reader lands
#: here without being sent.
_ENTRY_POINTS = {
    "README.md",
    "CLAUDE.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CHANGELOG.md",
    "LICENSE.md",
}


def _tracked(*patterns: str) -> list[str]:
    """Tracked paths, split on NULs so a path with a space stays one path."""
    listed = subprocess.run(
        ["git", "ls-files", "-z", *patterns],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split("\0")
    return [p for p in listed if p and not any(s in p for s in _SKIP) and (REPO / p).is_file()]


def unreachable() -> list[str]:
    """Documents no other tracked file names, by path or by filename."""
    documents = _tracked("*.md")
    corpus: dict[str, str] = {}
    for path in _tracked():
        try:
            corpus[path] = (REPO / path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    dark: list[str] = []
    for document in documents:
        if Path(document).name in _ENTRY_POINTS:
            continue
        name = Path(document).name
        if any(
            source != document and (document in text or name in text)
            for source, text in corpus.items()
        ):
            continue
        dark.append(document)
    return sorted(dark)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write-baseline", action="store_true", help="record the current set as the baseline"
    )
    args = parser.parse_args(argv)

    current = unreachable()

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        print(f"baseline written: {len(current)} unreachable document(s)")
        return 0

    if not BASELINE.exists():
        print(f"Document reachability: FAILED — {BASELINE} is missing", file=sys.stderr)
        return 1

    baseline = set(json.loads(BASELINE.read_text(encoding="utf-8")))
    added = sorted(set(current) - baseline)
    fixed = sorted(baseline - set(current))

    if added or fixed:
        print("Document reachability: FAILED")
        for entry in added:
            print(f"  [NEW] {entry}")
            print("        Nothing in the repository names this document, so no reader and")
            print("        no tool can arrive at it. Link it from a document that is itself")
            print("        reachable, or name it where the work it describes is tracked.")
        for entry in fixed:
            print(f"  [REACHABLE NOW, UNRECORDED] {entry}")
            print("        Refresh with: python3 scripts/check_doc_reachability.py")
            print("        --write-baseline — an improvement nobody records lets the next")
            print("        regression slip in under the old count.")
        return 1

    print(f"Document reachability: PASSED — {len(current)} recorded, none added or fixed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
