"""Dimensional is one shared service; Dimensionals is several.

The owner set this on 2026-09-12. It is an ordinary English plural, and it
carries information: the form tells a reader whether a sentence is about one
shared service or the collection of them.

The 2026-09-11 rename swept `Dimensional` -> `Dimensionals` across 8,319
references. That was right for the directory and every import path, and wrong
for prose, where it produced "operating under a Dimensionals" -- a grammatical
error the sweep could not tell apart from a path. These tests fail on that
shape, so the next sweep cannot reintroduce it silently.

They deliberately do NOT ban the singular. `Dimensional` is not a legacy
spelling; banning it is the mistake that caused this.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent

#: A singular determiner immediately in front of the plural noun. "a
#: Dimensionals" is wrong under any reading, so this needs no exceptions.
SINGULAR_BEFORE_PLURAL = re.compile(r"\b(?:a|an|each|every|one|another|single)\s+Dimensionals\b")

#: Files that quote the error on purpose: the migration script's comments and
#: the convention's own documentation both need to show the wrong form.
ALLOWED_TO_QUOTE_THE_ERROR = {
    "scripts/migrate_to_dimensionals.py",
    "config/estate/naming_conventions.md",
    "tests/test_dimensionals_naming.py",
    "docs/governance/PR-QUEUE-TRIAGE.md",
}

TEXTUAL_SUFFIXES = {".py", ".md", ".ts", ".tsx", ".yml", ".yaml", ".txt", ".json", ".toml"}


def tracked_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split("\n")
    return [
        REPO / rel
        for rel in out
        if rel
        and Path(rel).suffix in TEXTUAL_SUFFIXES
        and rel not in ALLOWED_TO_QUOTE_THE_ERROR
        and not rel.startswith(("node_modules/", "compliance/magna-carta/", "workers/cranbania/"))
    ]


def test_no_singular_determiner_in_front_of_the_plural() -> None:
    """ "a Dimensionals" is the shape the rename produced. It must not come back."""
    offences: list[str] = []
    for path in tracked_files():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if SINGULAR_BEFORE_PLURAL.search(line):
                offences.append(f"{path.relative_to(REPO)}:{n}: {line.strip()}")
    assert not offences, (
        "Dimensional is one shared service, Dimensionals is several. "
        "These read as a singular article in front of the plural:\n  " + "\n  ".join(offences)
    )


def test_the_probe_itself_detects_the_error() -> None:
    """A guard that cannot see reports what a clean estate reports.

    The scan above passes on a clean tree, which is indistinguishable from a
    scan that matches nothing at all. Plant the defect and require a hit.
    """
    planted = "domain-specific microservice operating under a Dimensionals."
    assert SINGULAR_BEFORE_PLURAL.search(planted), "the pattern must flag the real defect"


@pytest.mark.parametrize(
    "line",
    [
        "each Underverse module operates under a Dimensional.",
        "from Dimensionals.middleware import cors",
        "the Dimensionals package holds every shared service",
        "Dimensional Nexus — multi-dimensional data routing",
        "DIMENSIONALS_DIR = REPO / 'Dimensionals'",
    ],
)
def test_correct_usage_is_not_flagged(line: str) -> None:
    """The other half of the probe: legitimate usage of both forms stays green.

    Including `Dimensional Nexus`, where "dimensional" is the English adjective
    and nothing to do with shared services.
    """
    assert not SINGULAR_BEFORE_PLURAL.search(line)


def test_the_legacy_fallback_is_not_the_canonical_path() -> None:
    """src/taxonomy/build.py promises to fall back to the pre-rename directory.

    The rename rewrote that constant too, so both pointed at `Dimensionals` and
    the fallback could not fall back: mid-migration the taxonomy would report
    the entire shared core as missing, which is exactly what the fallback was
    written to prevent.
    """
    from src.taxonomy.build import DIMENSIONALS_DIR, LEGACY_DIMENSIONAL_DIR

    assert LEGACY_DIMENSIONAL_DIR != DIMENSIONALS_DIR, (
        "the legacy fallback must name the pre-rename directory, not the current one"
    )
    assert LEGACY_DIMENSIONAL_DIR.name == "Dimensional", (
        "the pre-rename directory was the singular form -- one shared-core tree"
    )
    assert DIMENSIONALS_DIR.name == "Dimensionals"
