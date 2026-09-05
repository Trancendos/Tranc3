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
#:
#: The markers used to be loose prose — "canonical document is", "lives at" —
#: matched anywhere in the body. Both are ordinary English. A 40-line duplicate
#: register that happened to say "the canonical document is the one in the
#: repository root" earned the exemption without pointing anywhere, which is
#: the opposite of what the exemption is for. A pointer now has to do two
#: things: use one of the explicit forms below, AND name a markdown path that
#: exists.
_POINTER_MAX_LINES = 60
#: Every marker is a declaration a page makes ABOUT ITSELF. "The canonical
#: document is" was tried and dropped: it is ordinary prose, and a second copy
#: writing "the canonical document is important" earned the exemption while
#: pointing at nothing — the same looseness, one phrase over.
_POINTER_MARKERS = (
    "This page is a pointer",
    "This document is a pointer",
    "The canonical version lives at",
)

#: A markdown path named inside a pointer page, whether bare or in a link.
_POINTER_PATH = re.compile(r"[\w./-]+\.md")

#: A GitHub blob URL into this repository, which is how the wiki pages point
#: home. Resolving only bare paths worked by accident — both pointer pages
#: happen to use the bare filename as the link TEXT — and would have broken
#: the moment someone wrote a link with a prose label instead.
_BLOB_URL = re.compile(r"github\.com/[^/\s]+/[^/\s]+/blob/[^/\s]+/([\w./-]+\.md)")

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
    """The document's H1, in either markdown spelling.

    ATX (`# Title`) is what this repository writes, but setext — a title
    followed by a line of `=` — is equally valid markdown and renders
    identically on GitHub. Reading only ATX meant a setext copy of a document
    carried no title at all here and was skipped, so the one spelling the
    checker could not see was the one that got past it.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line.startswith("# "):
            return line[2:]
        following = lines[index + 1] if index + 1 < len(lines) else ""
        if line.strip() and set(following.strip()) == {"="} and len(following.strip()) >= 2:
            return line
    return ""


def _is_pointer(text: str) -> bool:
    """Short, explicitly a pointer, and pointing at a document that exists.

    All three are required. Length alone lets a short second copy through;
    a phrase alone lets incidental prose claim the exemption; and a phrase
    naming a path that does not resolve is a pointer to nowhere, which leaves
    the reader exactly where a duplicate would.
    """
    if len(text.splitlines()) > _POINTER_MAX_LINES:
        return False
    if not any(marker in text for marker in _POINTER_MARKERS):
        return False
    named = set(_POINTER_PATH.findall(text)) | set(_BLOB_URL.findall(text))
    return any(candidate and (REPO / candidate).is_file() for candidate in named)


def duplicates() -> dict[str, list[str]]:
    # -z and a NUL split, not .split(): a path containing a space is one path,
    # and whitespace splitting turns it into two names that resolve to nothing,
    # so the document silently drops out of the comparison.
    listed = [
        entry
        for entry in subprocess.run(
            ["git", "ls-files", "-z", "*.md"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split("\0")
        if entry
    ]
    by_title: dict[str, list[str]] = defaultdict(list)
    for rel in listed:
        if any(skip in rel for skip in _SKIP):
            continue
        source = REPO / rel
        if not source.is_file():
            # `git ls-files` lists staged paths, including ones deleted from
            # the working tree. Reading one raised FileNotFoundError and took
            # the whole check down with a traceback, which is a fail with no
            # usable message rather than a finding.
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        title = _normalise(_title(text))
        if not title or title in _GENERIC or _is_pointer(text):
            continue
        by_title[title].append(rel)
    return {title: paths for title, paths in by_title.items() if len(paths) > 1}


#: `### SEC-001 — …` in the security alert register. The register is the only
#: document in the estate that numbers its entries, so the check is scoped to
#: it rather than pattern-matching headings everywhere.
_REGISTER = "SECURITY_ALERT_REGISTER.md"
_ENTRY_ID = re.compile(r"^#{2,4}\s+(SEC-\d+)\b", re.MULTILINE)


def repeated_entry_ids() -> dict[str, int]:
    """Entry IDs the register uses more than once.

    Two open entries filed as SEC-006 is the title problem one level down: a
    disposition recorded "against SEC-006" lands on whichever entry the reader
    reaches first, and the other finding keeps the status of a decision that
    was never about it. It happened — the esbuild/ws entry was filed under the
    nltk entry's number and stood that way until a review caught it.
    """
    source = REPO / _REGISTER
    if not source.is_file():
        return {}
    counts: dict[str, int] = defaultdict(int)
    for entry_id in _ENTRY_ID.findall(source.read_text(encoding="utf-8", errors="replace")):
        counts[entry_id] += 1
    return {entry_id: count for entry_id, count in counts.items() if count > 1}


def main() -> int:
    repeated = repeated_entry_ids()
    if repeated:
        print("Documentation duplication check: FAILED")
        for entry_id, count in sorted(repeated.items()):
            print(f"  {_REGISTER} files {count} entries as {entry_id}")
        print()
        print("  An entry ID is how a disposition, a suppression comment and a")
        print("  scanner exclusion all refer back to one finding. Two entries")
        print("  sharing one means a decision recorded against it applies to")
        print("  whichever the reader found first. Give the newer one the next")
        print("  free number.")
        return 1

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
