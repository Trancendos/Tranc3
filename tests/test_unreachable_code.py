"""The unreachable-code gate — found by a CodeQL alert nothing was acting on.

CodeQL raised twelve `py/unreachable-statement` alerts in
`src/agents/goal_manager.py`, and only the SARIF filter's `--strict-surprises`
made anybody look. A sweep found twelve more in five other files plus three in
`api.py` — twenty-seven in total, every one a bare `return None` after a block
that always leaves the frame, several of them under a `-> bool` annotation they
contradicted. CodeQL had been raising most of them all along; they went to a
tab that gates nothing.

The tests below are split in two, because the gate has two ways to fail and
only one of them is obvious. It can miss real dead code — and it can report
REACHABLE code, which is worse: a gate that fails a build over correct code
gets switched off, and then it is not a gate.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_unreachable_code.py"


def _load():
    spec = importlib.util.spec_from_file_location("_unreach", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["_unreach"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def checker():
    return _load()


def _lines(checker, source):
    return [line for line, _after in checker.scan_source(source)]


class TestItCatchesDeadCode:
    def test_a_return_after_a_return(self, checker):
        assert _lines(checker, "def f():\n    return 1\n    return None\n") == [3]

    def test_a_return_after_an_always_returning_with(self, checker):
        """The exact shape of all twenty-seven findings.

        `async with self._lock: ... return X` followed by `return None`. It is
        the one that hid, because the eye reads the `with` as a block that can
        fall through and it cannot.
        """
        source = (
            "async def f() -> bool:\n"
            "    async with lock:\n"
            "        if x:\n"
            "            return True\n"
            "        return False\n"
            "    return None\n"
        )
        assert _lines(checker, source) == [6]

    def test_a_return_after_an_if_else_that_both_return(self, checker):
        source = (
            "def f():\n    if x:\n        return 1\n    else:\n        return 2\n    return 3\n"
        )
        assert _lines(checker, source) == [6]

    def test_a_return_after_a_try_whose_body_and_handler_both_leave(self, checker):
        """Three of the `api.py` findings were exactly this.

        `try: ... return X / except: raise` followed by `return None`.
        """
        source = (
            "def f():\n"
            "    try:\n"
            "        return compute()\n"
            "    except ValueError:\n"
            "        raise HTTPException(404)\n"
            "    return None\n"
        )
        assert _lines(checker, source) == [6]

    def test_a_statement_after_a_raise(self, checker):
        assert _lines(checker, "def f():\n    raise ValueError()\n    x = 1\n") == [3]


class TestItDoesNotReportReachableCode:
    """The failure mode that gets a gate deleted rather than obeyed."""

    def test_an_if_with_no_else_is_not_terminal(self, checker):
        """There is always a path through it, and the code after it runs.

        Treating a bare `if` as terminal would report most of this codebase.
        """
        assert _lines(checker, "def f():\n    if x:\n        return 1\n    return 2\n") == []

    def test_an_if_whose_else_falls_through_is_not_terminal(self, checker):
        source = "def f():\n    if x:\n        return 1\n    else:\n        y = 2\n    return y\n"
        assert _lines(checker, source) == []

    def test_a_try_with_a_falling_through_handler_is_not_terminal(self, checker):
        """One handler that recovers means the code after the `try` runs."""
        source = (
            "def f():\n"
            "    try:\n"
            "        return compute()\n"
            "    except ValueError:\n"
            "        pass\n"
            "    return None\n"
        )
        assert _lines(checker, source) == []

    def test_a_try_with_a_falling_through_else_is_not_terminal(self, checker):
        source = (
            "def f():\n"
            "    try:\n"
            "        return compute()\n"
            "    except ValueError:\n"
            "        raise\n"
            "    else:\n"
            "        y = 1\n"
            "    return y\n"
        )
        assert _lines(checker, source) == []

    def test_a_with_that_does_not_return_is_not_terminal(self, checker):
        source = "def f():\n    with lock:\n        y = 1\n    return y\n"
        assert _lines(checker, source) == []

    def test_a_return_at_the_end_of_a_body_is_not_a_finding(self, checker):
        assert _lines(checker, "def f():\n    return 1\n") == []

    def test_a_loop_is_not_treated_as_terminal(self, checker):
        """A `while True` with no break never exits, but proving that needs
        reasoning this deliberately does not do — a guessing gate that fails a
        build gets disabled, and then it protects nothing."""
        assert _lines(checker, "def f():\n    while True:\n        pass\n    return 1\n") == []

    def test_an_unparseable_file_yields_nothing_rather_than_raising(self, checker):
        """Ruff and the compile step already fail on it; failing twice is noise."""
        assert checker.scan_source("def f(:\n") == []


class TestTheEstate:
    def test_the_repository_is_clean(self, checker):
        """Twenty-seven were removed. This is what stops the next twenty-seven.

        Not a smoke test: it is the whole gate, run against the real tree.
        """
        assert checker.main([]) == 0

    def test_tests_are_out_of_scope_on_purpose(self, checker):
        """This very file needs unreachable code in its fixtures.

        A gate that cannot be tested without failing itself is a gate nobody
        can change safely.
        """
        assert not any(f.startswith("tests/") for f in checker._files())

    def test_submodules_are_excluded(self, checker):
        """Separate repositories; a finding there cannot be fixed by a change here."""
        for prefix in ("compliance/magna-carta", "workers/cranbania"):
            assert prefix in checker.EXCLUDED
