#!/usr/bin/env python3
"""Fail when two documents claim to be the same thing.

What duplication actually cost here
-----------------------------------
Two pairs of documents shared a title across 320 files:

  * `SECURITY_ALERT_REGISTER.md` (289 lines, read by
    `scripts/security_score.py`) and
    `wiki-content/Security-SECURITY_ALERT_REGISTER.md` (102 lines, read by
    people).
  * `docs/API_REFERENCE.md` (750 lines, 47 endpoints) and
    `wiki-content/Strategy-DOC-03-API-Reference.md` (238 lines, 9).

The security pair is the argument for this check. The wiki copy carried two
advisories the canonical register had never heard of, and asserted their
remedy was applied across all seven Cloudflare packages. It was in one. Six
surfaces stood unremediated behind a record that said otherwise, in a
document no scanner read — and the register the scanner *did* read had no
entry at all. Neither copy was wrong about the other; each was simply blind
to it.

What this checks
----------------
No two documents may share a normalised H1 title. A page may point at the
canonical document — that is the resolution, not a violation — so a document
whose body is a pointer (it names the canonical path and is short) is
exempt: it holds no second copy of anything.

Alternatives considered
-----------------------
Content hashing finds only byte-identical files, and there were none: the
copies had drifted, which is exactly what makes them dangerous. Similarity
scoring would need a threshold nobody can defend. A shared title is the
claim itself — "this document is the X" — and two of them is the defect.

Usage:
    python3 scripts/check_doc_duplication.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

_SKIP = ("compliance/magna-carta", "workers/cranbania", "node_modules")

#: A pointer page: short, and it names where the real document is.
_POINTER_MAX_LINES = 60
_POINTER_MARKERS = ("This page is a pointer", "canonical document is", "lives at")

#: Titles that are generic by nature — a per-service README is not a duplicate
#: of another service's README.
_GENERIC = {"readme", "index", "overview", "contents"}


def _normalise(title: str) -> str:
    """Reduce a title to the claim it makes.

    Punctuation and spacing are presentation. "Security Alert Register",
    "Security  ALERT  register!" and "Security-Alert-Register" all assert the
    same thing, and a comparison that told them apart would let a second copy
    in on a typographic difference.
    """
    stripped = re.sub(r"[^a-z0-9 ]", " ", title.strip().lower())
    return " ".join(stripped.split())


def _title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:]
    return ""


def _is_pointer(text: str) -> bool:
    if len(text.splitlines()) > _POINTER_MAX_LINES:
        return False
    return any(marker in text for marker in _POINTER_MARKERS)


def duplicates() -> dict[str, list[str]]:
    listed = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    by_title: dict[str, list[str]] = defaultdict(list)
    for rel in listed:
        if any(skip in rel for skip in _SKIP):
            continue
        text = (REPO / rel).read_text(encoding="utf-8", errors="replace")
        title = _normalise(_title(text))
        if not title or title in _GENERIC or _is_pointer(text):
            continue
        by_title[title].append(rel)
    return {title: paths for title, paths in by_title.items() if len(paths) > 1}


def main() -> int:
    found = duplicates()
    if found:
        print("Documentation duplication check: FAILED")
        for title, paths in sorted(found.items()):
            print(f"  '{title}' is claimed by {len(paths)} documents:")
            for path in paths:
                print(f"      {path}")
        print()
        print("  Two documents claiming to be the same thing drift, and each stays")
        print("  blind to the other's contents. Keep one, and make the other a")
        print("  pointer to it — a short page naming where the real document lives.")
        return 1
    print("Documentation duplication check: PASSED — no title is claimed twice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
