"""The guard that catches an unwired guard.

`scripts/check_lab_languages.py` was merged with a docstring and a commit
message both asserting it ran in CI, and it did not. These tests protect the
check that now makes that impossible — and, on the live tree, that the check
is telling the truth about this repository rather than passing vacuously.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


def _load():
    path = REPO / "scripts" / "check_guards_are_wired.py"
    spec = importlib.util.spec_from_file_location("check_guards_are_wired", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def guard():
    return _load()


_REASON = (
    "A reason long enough to be a sentence about this specific script and why "
    "continuous integration is the wrong place for it to run at all."
)


class TestTheDecision:
    def test_an_unwired_guard_with_no_reason_fails(self, guard):
        """Calibrated: returning no failures for a missing entry fails this."""
        failures = guard.evaluate(["check_thing.py"], set(), {})
        assert len(failures) == 1
        assert "no workflow runs it" in failures[0]

    def test_a_wired_guard_passes(self, guard):
        assert guard.evaluate(["check_thing.py"], {"check_thing.py"}, {}) == []

    def test_an_unwired_guard_with_a_written_reason_passes(self, guard):
        assert guard.evaluate(["check_thing.py"], set(), {"check_thing.py": _REASON}) == []

    def test_a_reason_too_short_to_say_anything_fails(self, guard):
        """Calibrated: dropping the length floor fails this.

        Without it the allowlist accepts "n/a", which converts the check from
        a decision that shows up in review into a formality.
        """
        failures = guard.evaluate(["check_thing.py"], set(), {"check_thing.py": "not needed"})
        assert len(failures) == 1
        assert "characters" in failures[0]

    def test_a_reason_that_outlived_its_fact_fails(self, guard):
        """Calibrated: checking the allowlist in one direction only fails this.

        A guard listed as deliberately unwired, which somebody has since
        wired, leaves a written reason describing the opposite of the truth.
        Nothing else in the estate would notice.
        """
        failures = guard.evaluate(
            ["check_thing.py"], {"check_thing.py"}, {"check_thing.py": _REASON}
        )
        assert len(failures) == 1
        assert "must not outlive" in failures[0]

    def test_a_reason_for_a_deleted_guard_fails(self, guard):
        failures = guard.evaluate([], set(), {"check_gone.py": _REASON})
        assert len(failures) == 1
        assert "no such guard exists" in failures[0]


class TestThisRepository:
    def test_the_guards_it_finds_include_both_shapes(self, guard):
        """A discovery that missed the generators would pass vacuously.

        `check_*.py` is the obvious half; the drift generators are guards too —
        `--check` is what makes them fail rather than quietly rewrite.
        """
        guards = guard.discover_guards()
        assert "check_creative_routes.py" in guards
        assert "generate_plm_docs.py" in guards
        assert "build_solution_packs.py" in guards

    def test_the_lab_language_checker_is_actually_wired(self, guard):
        """The specific defect that prompted this check, asserted directly."""
        assert "check_lab_languages.py" in guard.wired_guards()

    def test_the_repository_passes_its_own_check(self, guard):
        assert (
            guard.evaluate(guard.discover_guards(), guard.wired_guards(), guard.UNWIRED_BY_DESIGN)
            == []
        )
