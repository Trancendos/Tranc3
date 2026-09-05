#!/usr/bin/env python3
"""Fail when a documentation link points at a file that is not there.

Why this needs a script rather than a reader
--------------------------------------------
320 markdown documents carry roughly 2,000 internal links, and the
wiki-content migration moved 62 of them at once. Eight links pointed at
files that had not existed for weeks — including four in `README.md`, the
first document anybody reads. Nothing noticed, because nothing reads a link
until a person clicks it and finds nothing there.

Two link conventions, one checker
---------------------------------
The estate writes links two ways, and both are correct in their own context:

  * Repository style — `[x](docs/THING.md)`, resolved from the linking file.
  * GitHub Wiki style — `[x](Architecture-THING)`, no extension, because the
    published wiki flattens `wiki-content/` into one namespace. Every such
    link lives inside `wiki-content/` already, so it resolves against the
    linking file's own directory once the elided `.md` is restored.

A checker that understood only the first reported 137 failures, 128 of them
wiki links that resolve perfectly well once published. A gate that is wrong
128 times out of 137 is one nobody will keep. Both forms are accepted here,
and a wiki-style target has to exist as a real file in `wiki-content/`.

External links are not fetched: a gate whose verdict depends on a third
party's uptime fails for reasons unrelated to the tree, which is the same
reason the OSV freshness check is opt-in.

Usage:
    python3 scripts/check_doc_links.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: Submodules are checked in their own repositories.
_SKIP = ("compliance/magna-carta", "workers/cranbania", "node_modules")

_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)")
_EXTERNAL = ("http://", "https://", "mailto:", "tel:", "#")

#: A fenced block opener or closer: ``` or ~~~ (three or more), optionally
#: indented, capturing the FULL run — a four-backtick fence is not closed by
#: three, and storing only three resumed scanning inside the block.
_FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})(.*)$")

#: Inline code spans. The delimiter runs must match in length AND be complete
#: — the lookarounds stop the pattern backtracking into part of a longer run,
#: which would end a span in the middle of one and leave real links on the far
#: side unmasked. `re.DOTALL` because a span may cross a line break.
_INLINE_CODE = re.compile(
    r"(?<!`)(?P<ticks>`+)(?!`)(?:(?!(?P=ticks)).)*?(?P=ticks)(?!`)", re.DOTALL
)

#: Links into a submodule's tree: the file is real, it just is not checked out
#: here. Reporting them would make the gate depend on submodule state.
_SUBMODULE_PREFIXES = ("compliance/magna-carta/", "workers/cranbania/")


def documents() -> list[Path]:
    # -z and a NUL split: whitespace splitting turns one path containing a
    # space into two names that resolve to nothing, dropping the document.
    """Tracked markdown files this gate is responsible for, submodules excluded."""
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
    return [REPO / p for p in listed if not any(skip in p for skip in _SKIP)]


def prose(text: str) -> str:
    """The document with its code removed, so links inside code are not links.

    Documentation about linking has to show a link that does not resolve —
    `[label](docs/example.md)` in a fenced block explaining the syntax, an
    inline `[x](path)` in a checker's own docstring. Those are illustrations,
    not references, and failing on them makes the gate punish the documents
    most likely to explain it. Removing code rather than skipping the whole
    line keeps a real link that shares a line with a code span checkable.

    Code is replaced with blank lines and spaces rather than deleted, so the
    surviving text keeps its original line numbers for the report.
    """
    # Fences first, on whole lines. An inline-code pass cannot be trusted to
    # run before this: a stray ``` in prose would otherwise open a span that
    # swallows the rest of the document.
    kept: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        match = _FENCE.match(line)
        marker = match.group(1) if match else ""
        trailing = match.group(2) if match else ""
        if fence is None:
            if marker:
                fence = marker
                kept.append("")
                continue
            kept.append(line)
            continue
        # Inside a block. Only a run at least as long as the opener, of the
        # same character, with nothing but whitespace after it, closes it —
        # a marker followed by text is code content, and treating it as a
        # close resumed scanning for links inside the block.
        closes = (
            marker and marker[0] == fence[0] and len(marker) >= len(fence) and not trailing.strip()
        )
        if closes:
            fence = None
        kept.append("")

    # Then inline spans, over the whole remaining text rather than line by
    # line, so a span that crosses a newline masks its continuation too.
    # Replacing each character with a space (newlines excepted) keeps every
    # line number exactly where it was, which is what the report prints.
    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if c == "\n" else " " for c in match.group(0))

    return _INLINE_CODE.sub(blank, "\n".join(kept))


def resolve(source: Path, target: str) -> bool:
    """Does this link land on something that exists?"""
    path = target.split("#")[0].strip()
    if not path:
        return True  # a pure anchor into the same document
    if any(part in path for part in _SUBMODULE_PREFIXES):
        return True
    # Both conventions resolve against the linking file's own directory. A
    # wiki-style link only ever appears inside `wiki-content/`, which is the
    # directory the published wiki flattens — so the extension-elided
    # candidate is what carries it, and a separate `wiki-content/` search
    # path resolved nothing the first two did not. It was written, measured
    # against every link in the estate, found to be dead, and removed rather
    # than left in looking load-bearing.
    candidates = [
        source.parent / path,  # repository style
        source.parent / f"{path}.md",  # extension elided; the wiki's form too
    ]
    return any(candidate.exists() for candidate in candidates)


def broken() -> list[str]:
    """Internal links that resolve to nothing, as `path:line: -> target`.

    Code is stripped before extraction, so a link inside a fence or a code
    span is read as the illustration it is rather than a reference.
    """
    found: list[str] = []
    for document in documents():
        if not document.is_file():
            continue  # `git ls-files` lists staged paths, deletions included
        text = prose(document.read_text(encoding="utf-8", errors="replace"))
        for number, line in enumerate(text.splitlines(), 1):
            for target in _LINK.findall(line):
                if target.startswith(_EXTERNAL):
                    continue
                if not resolve(document, target):
                    rel = document.relative_to(REPO).as_posix()
                    found.append(f"{rel}:{number}: -> {target}")
    return found


def main() -> int:
    """Report every unresolved internal link. Returns a process exit code."""
    found = broken()
    if found:
        print("Documentation link check: FAILED")
        for entry in found:
            print(f"  - {entry}")
        print()
        print("  A link to a file that is not there is a document quietly rotting.")
        print("  Point it at where the file went, or remove the reference.")
        return 1
    total = len(documents())
    print(f"Documentation link check: PASSED — every internal link in {total} documents resolves")
    return 0


if __name__ == "__main__":
    sys.exit(main())
