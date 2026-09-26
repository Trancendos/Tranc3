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

import json
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


def test_a_reintroduced_directory_merges_rather_than_nesting(tmp_path, monkeypatch) -> None:
    """The documented rerun case is the one `git mv` gets wrong.

    The script exists to be re-run "on a merge that reintroduces the old name".
    In exactly that case the renamed directory is already present, and
    `git mv Dimensional Dimensionals` does not merge -- it moves the source
    INSIDE the destination, giving `Dimensionals/Dimensional/`. The text pass
    then rewrites imports to `Dimensionals.foo` for modules that now live a
    level deeper, so the tree imports nothing and the run reports success.

    Found by `chatgpt-codex-connector` on PR #1244.
    """
    import importlib.util

    repo = tmp_path / "repo"
    (repo / "Dimensionals" / "sub").mkdir(parents=True)
    old = repo / ("Dimension" + "al")
    (old / "sub").mkdir(parents=True)
    (repo / "Dimensionals" / "kept.py").write_text("# already renamed\n", encoding="utf-8")
    (old / "reintroduced.py").write_text("# came back in a merge\n", encoding="utf-8")
    (old / "sub" / "deep.py").write_text("# nested\n", encoding="utf-8")
    (old / "kept.py").write_text("# a second copy\n", encoding="utf-8")
    for args in (["init", "-q"], ["add", "-A"]):
        subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "seed"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    spec = importlib.util.spec_from_file_location(
        "_mig", REPO / "scripts" / "migrate_to_dimensionals.py"
    )
    assert spec and spec.loader
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    monkeypatch.setattr(mig, "REPO", repo)

    moved, clashes = mig._merge_into(old, repo / "Dimensionals")

    assert not (repo / "Dimensionals" / ("Dimension" + "al")).exists(), (
        "the reintroduced directory was nested inside the destination instead "
        "of merged into it -- every import rewritten afterwards points one "
        "level too shallow"
    )
    assert (repo / "Dimensionals" / "reintroduced.py").is_file()
    assert (repo / "Dimensionals" / "sub" / "deep.py").is_file(), "nesting was not preserved"
    assert moved == 2, moved
    assert clashes == [f"{'Dimension' + 'al'}/kept.py"], clashes
    assert (repo / "Dimensionals" / "kept.py").read_text() == "# already renamed\n", (
        "an existing destination file was overwritten; which of two copies is "
        "correct is a merge decision, not a rename's to make"
    )


def test_the_shared_core_detector_sees_the_renamed_import(tmp_path, monkeypatch) -> None:
    """`\\b` after the singular name does not match the plural.

    `scripts/apply_shared_core_contexts.py` decides which workers need the
    shared core copied in, and REMOVES the COPY block and the compose
    `additional_contexts` entry for a context it thinks is unused. After the
    rename its detector still matched the old name, so every worker importing
    the renamed package read as not needing it -- running the script would have
    stripped working build config out of roughly forty workers.

    The second half of that same line already named the new directory, because
    the rename rewrote the quoted string and could not rewrite the regex. The
    line was detecting one name and checking for the other. Found by
    `chatgpt-codex-connector` on PR #1244.
    """
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "_ctx", REPO / "scripts" / "apply_shared_core_contexts.py"
    )
    assert spec and spec.loader
    ctx = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ctx)
    monkeypatch.setattr(ctx, "ROOT", tmp_path)

    worker = tmp_path / "workers" / "an-example"
    worker.mkdir(parents=True)
    (worker / "worker.py").write_text(
        "from Dimensionals.service_auth_fastapi import guard_internal_secret\n",
        encoding="utf-8",
    )
    assert "sharedcore" in ctx.needed_contexts("an-example"), (
        "a worker importing the renamed shared core reads as not needing it, so "
        "this script would delete its build context rather than supply it"
    )

    bare = tmp_path / "workers" / "no-shared-core"
    bare.mkdir(parents=True)
    (bare / "worker.py").write_text("import os\n", encoding="utf-8")
    assert "sharedcore" not in ctx.needed_contexts("no-shared-core"), (
        "a worker that does not import it must not be granted the context"
    )


def test_the_secret_baseline_is_keyed_to_paths_that_exist() -> None:
    """detect-secrets matches an accepted finding by filename.

    `.secrets.baseline` is not swept by the text pass -- `.baseline` is not a
    recognised text suffix -- so after the rename its `results` keys still named
    the old directory. Eight accepted findings across five files stopped being
    recognised, and the next commit touching any of them would have reported
    long-accepted values as new secrets, on a pull request with nothing to do
    with them. Found by `chatgpt-codex-connector` on PR #1244.
    """
    baseline = REPO / ".secrets.baseline"
    if not baseline.is_file():  # pragma: no cover - the repo ships one
        pytest.skip("no baseline in this checkout")
    data = json.loads(baseline.read_text(encoding="utf-8"))
    singular = "Dimension" + "al"
    stale = [
        key
        for key in data.get("results", {})
        if key.startswith(singular + "/") or f"/{singular}/" in key
    ]
    assert not stale, f"baseline entries keyed to the pre-rename directory: {stale}"

    inner = [
        finding["filename"]
        for findings in data.get("results", {}).values()
        for finding in findings
        if isinstance(finding, dict)
        and isinstance(finding.get("filename"), str)
        and (
            finding["filename"].startswith(singular + "/") or f"/{singular}/" in finding["filename"]
        )
    ]
    assert not inner, f"findings whose filename names the pre-rename directory: {inner[:5]}"
