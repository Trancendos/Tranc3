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

#: Words that, sitting between the determiner and the noun, make the plural
#: legitimate: "one **of the** Dimensionals" is correct English and must stay
#: green. Without this the guard would flag every sentence that counts them.
_PLURAL_IS_LEGITIMATE = r"(?:of|the|these|those|all|many|several|both|its|their|our)"

#: A singular determiner in front of the plural noun, tolerating up to two
#: intervening adjectives.
#:
#: The first version required the determiner to sit *immediately* before the
#: noun, and cubic then found three sites it could not see -- "a **parent**
#: Dimensionals" and "a **specific** Dimensionals" twice -- in the very file
#: whose other singular this guard had just fixed. One adjective defeated it.
#: A guard that only catches the simplest spelling of a defect reports a clean
#: estate while the defect is still there, which is the failure
#: docs/governance/IMMUNE-SYSTEM.md names.
SINGULAR_BEFORE_PLURAL = re.compile(
    r"\b(?:a|an|each|every|one|another|single)\s+"
    r"(?:(?!" + _PLURAL_IS_LEGITIMATE + r"\b)[A-Za-z,-]+\s+){0,2}"
    r"Dimensionals\b"
)

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


@pytest.mark.parametrize(
    "line",
    [
        "operates under the governance of a parent Dimensionals.",
        "Get all Underverse modules belonging to a specific Dimensionals.",
        "one shared Dimensionals",
        "a lightweight, domain-specific Dimensionals",
    ],
)
def test_an_adjective_does_not_hide_the_error(line: str) -> None:
    """cubic found three of these in a file this guard had already passed.

    The original pattern required the determiner to sit immediately before the
    noun, so "a **parent** Dimensionals" slipped through. The first two cases
    here are verbatim from `Dimensionals/dimensionals/underverse.py` before the
    fix.
    """
    assert SINGULAR_BEFORE_PLURAL.search(line)


@pytest.mark.parametrize(
    "line",
    [
        "one of the Dimensionals",
        "each of the Dimensionals",
        "every one of their Dimensionals",
        "all the Dimensionals are registered as CIs",
    ],
)
def test_counting_them_is_legitimate_and_stays_green(line: str) -> None:
    """The cost of widening the pattern.

    "one of the Dimensionals" is correct English about several shared services.
    A guard that flagged it would be wrong on the sentences most likely to be
    written about a collection, and would be switched off.
    """
    assert not SINGULAR_BEFORE_PLURAL.search(line)


def test_the_migration_script_excludes_this_file() -> None:
    """A rewriter that edits every text file must exclude its own regression test.

    `scripts/migrate_to_dimensionals.py` already excludes itself, and says why:
    its first `--apply` run rewrote its own `OLD_DIR`/`NEW_DIR` constants and
    produced `git mv Dimensionals Dimensionals`. The same hazard reaches this
    file, and the exclusion did not.

    Found by re-running the migration on a clean checkout -- which the script's
    own docstring says will happen ("a rename you can only do once is a rename
    you cannot verify"). The run rewrote the singular string inside this file's
    assertions, turning a test that pins the old name into one that asserts the
    new name against itself: green, and measuring nothing.

    Two defences, because one of them is this file's own text and a text
    rewriter is what we are defending against:
      * the script skips this path, next to where it skips itself;
      * every singular literal here is joined at runtime (`"Dimension" + "al"`),
        so no textual substitution can find it in the source at all.
    """
    script = (REPO / "scripts" / "migrate_to_dimensionals.py").read_text(encoding="utf-8")
    assert "test_dimensionals_naming.py" in script, (
        "the migration script does not exclude this file, so re-running it "
        "rewrites the assertions that are supposed to catch it"
    )


def test_the_singular_form_is_never_a_bare_literal_here() -> None:
    """The defence above only holds while no plain singular literal creeps back."""
    source = (REPO / "tests" / "test_dimensionals_naming.py").read_text(encoding="utf-8")
    singular = '"' + "Dimension" + 'al"'
    assert singular not in source, (
        f"a bare {singular} literal is rewritable by the migration script; "
        'build it at runtime instead, as `"Dimension" + "al"`'
    )


#: Documents that record a past assessment. Rewriting them would put a name in
#: the record that did not exist when the assessment was made, so the sweep
#: below exempts them rather than the rename touching them.
HISTORICAL_RECORDS = {
    "wiki-content/Historical-PHASE25_REPO_REVIEW.md",
}

#: Path-like shapes for the singular form. Prose is excluded deliberately --
#: "a Dimensional" is the correct singular concept noun, and a bare-word rule
#: was tried and reverted for over-applying to it.
_SINGULAR_PATH = re.compile(r"(?:\.\./|\./|/|=|context[ =])" + "Dimension" + r"al(?!s)")


def test_no_path_reference_to_the_singular_form_survives() -> None:
    """The rename reported itself complete while 69 references remained.

    `scripts/migrate_to_dimensionals.py` printed "0 references across 0 files"
    on its second run -- correctly, by its own rules -- and the tree still held:

      * 66 Dockerfiles whose build instructions read
        `--build-context sharedcore=../../Dimension` + `al`, a command that
        fails as printed, because the path rules needed a trailing slash or a
        bare `./` after whitespace;
      * `scripts/apply_shared_core_contexts.py`, which GENERATES those build
        contexts and still pointed its source at the old directory -- quoted,
        so the lookbehind did not apply;
      * `--cov=` naming the old package in `.github/workflows/test.yml`, a live
        coverage flag measuring a directory that no longer exists.

    A rename that reports complete while incomplete is the defect this estate
    keeps finding. The script's rules were widened; this sweep is what stops
    the next narrow rule from reporting the same false clean.
    """
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.split()
    suffixes = {".py", ".yml", ".yaml", ".toml", ".md", ".sh", ".cfg", ".ini", ".txt"}
    offenders = []
    for rel in tracked:
        if rel in HISTORICAL_RECORDS or rel == "scripts/migrate_to_dimensionals.py":
            continue
        if rel == "tests/test_dimensionals_naming.py":
            continue
        path = REPO / rel
        if not path.is_file():
            continue  # a submodule pointer, or a path the checkout does not hold
        if path.suffix not in suffixes and not path.name.startswith("Dockerfile"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if _SINGULAR_PATH.search(line):
                offenders.append(f"{rel}:{number}: {line.strip()[:100]}")
    assert not offenders, (
        "path references to the pre-rename directory survive the migration:\n  "
        + "\n  ".join(offenders[:20])
    )
