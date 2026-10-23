"""`make regen` must not promise more than it measures.

Two properties are pinned here because both were wrong in the first version of
`scripts/regenerate_derived.py` and both were caught in review rather than by a
test.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

_spec = importlib.util.spec_from_file_location(
    "regenerate_derived", ROOT / "scripts" / "regenerate_derived.py"
)
assert _spec and _spec.loader
rd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rd)


def _git_ignores(path: str) -> bool:
    return (
        subprocess.run(
            ["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True
        ).returncode
        == 0
    )


def test_no_generator_known_to_write_an_ignored_path_is_in_the_list():
    """`--check` can only undo what `git status` can see.

    `ai_bom.py` writes only `logs/ai-bom.cyclonedx.json`, which `.gitignore`
    covers, so including it made `--check` mutate a file it could neither detect
    nor restore -- while reporting "already current". Measured 2026-10-05: it was
    the only one of the eleven doing so.
    """
    for name in rd.IGNORED_WRITERS:
        assert name not in rd.GENERATORS, (
            f"{name} writes a path git ignores, so --check cannot honour its "
            "promise to leave the tree as it found it"
        )


def test_the_ignored_writer_really_does_write_an_ignored_path():
    """Otherwise the exclusion above is folklore rather than a measurement."""
    assert _git_ignores("logs/ai-bom.cyclonedx.json"), (
        "logs/ai-bom.cyclonedx.json is no longer gitignored, so ai_bom.py may "
        "belong in GENERATORS after all -- re-measure before changing either"
    )


def test_solution_packs_are_generated_before_the_action_backlog():
    """`build_action_backlog.py` renders `_no pack_` from a pack's absence.

    Running it first baked that into the backlog, the pack was written moments
    later, and the backlog was stale again -- the exact failure this script
    exists to clear.
    """
    gens = list(rd.GENERATORS)
    assert gens.index("build_solution_packs.py") < gens.index("build_action_backlog.py")


def test_every_declared_generator_is_a_generator_not_a_checker():
    """A `check_*` failure is a finding about the change, not a stale artefact.

    Regenerating cannot fix one, and conflating the two would turn real findings
    into "run the script again".
    """
    for name in rd.GENERATORS:
        assert name.startswith(("build_", "generate_")), name
        assert "check" not in name and "conformance" not in name, name
