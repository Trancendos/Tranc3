"""The `$`-before-newline trap, and the guard that now blocks it.

`re.compile(r"^[a-z]+$").match("abc\\n")` matches. `$` anchors at the end of the
string **or immediately before a trailing newline**, so every anchored pattern
used with `.match()` admits one `\\n` its own character class forbids.

Found while adjudicating the two `py/sql-injection` alerts at CodeQL severity
8.8 in `src/vector/adapter.py`. The alert is a false positive — the validator
holds against every injection shape — and the validator was still wrong.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


class TestTheTrapItself:
    """The language behaviour the guard exists for, asserted rather than assumed."""

    def test_match_admits_a_trailing_newline(self):
        pattern = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
        assert pattern.match(  # anchored-ok: demonstrating the trap is the test
            "vec_abc\n"
        ), "if this ever fails, the guard is obsolete"

    def test_fullmatch_does_not(self):
        pattern = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
        assert pattern.fullmatch("vec_abc\n") is None
        assert pattern.fullmatch("vec_abc") is not None


class TestTheValidatorsThatMotivatedIt:
    """The SQL table-name allowlist CodeQL flagged, end to end."""

    _PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,62}$")

    @staticmethod
    def _derive(collection: str) -> str:
        return f"vec_{collection.replace('-', '_').lower()}"

    @pytest.mark.parametrize(
        "collection",
        [
            "x'; DROP TABLE t; --",
            'x"y',
            "x;y",
            "x(y)",
            "a b",
            "abc\nDROP TABLE t",
        ],
    )
    def test_the_allowlist_holds_against_injection(self, collection):
        """Why this is an FP and not a vulnerability — the claim, measured."""
        assert self._PATTERN.fullmatch(self._derive(collection)) is None

    def test_but_it_admitted_a_trailing_newline(self):
        """And why it was still wrong. `.match` accepts what `.fullmatch` refuses."""
        table = self._derive("abc\n")
        assert self._PATTERN.match(table), "the defect, as it was"  # anchored-ok: shows the defect
        assert self._PATTERN.fullmatch(table) is None, "the fix"

    def test_legitimate_collection_names_still_work(self):
        """Containment is not a ban. A guard that broke these would pass every
        attack test above while breaking the feature."""
        for good in ("docs", "my-docs", "Notes", "a_b_9"):
            assert self._PATTERN.fullmatch(self._derive(good)) is not None


class TestTheGuard:
    """`scripts/check_anchored_validators.py` — clean now, and able to see."""

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run(  # noqa: S603
            [sys.executable, "scripts/check_anchored_validators.py", *args],
            cwd=str(_ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

    def test_the_estate_is_clean(self):
        proc = self._run()
        assert proc.returncode == 0, proc.stdout + proc.stderr

    def test_it_can_see_a_dunder_import_compile(self):
        """The calibration that failed first time, kept as a test.

        The guard's first version matched only a literal `re.compile(`, so it
        could not see the validator it was written for:

            _SAFE_IDENT = __import__("re").compile(r"^[a-z][a-z0-9_]{0,62}$")

        Planting `.match()` back into `src/vector/adapter.py` left the guard
        green. A guard blind to its own motivating case is the defect this
        estate keeps finding, and it had one run of existing before doing it too.
        """
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "anchored_guard_under_test", _ROOT / "scripts" / "check_anchored_validators.py"
        )
        guard = module_from_spec(spec)
        sys.modules[spec.name] = guard
        spec.loader.exec_module(guard)

        source = '_SAFE_IDENT = __import__("re").compile(r"^[a-z][a-z0-9_]{0,62}$")\n'
        found = [m.group("name") for m in guard._COMPILE.finditer(source)]
        assert found == ["_SAFE_IDENT"], f"guard cannot see its own motivating case: {found}"

    def test_multiline_patterns_are_exempt(self):
        """A line parser's `$`-before-newline is the point, not a defect."""
        from importlib.util import module_from_spec, spec_from_file_location

        spec = spec_from_file_location(
            "anchored_guard_multiline", _ROOT / "scripts" / "check_anchored_validators.py"
        )
        guard = module_from_spec(spec)
        sys.modules[spec.name] = guard
        spec.loader.exec_module(guard)

        parser = '_HEADING = re.compile(r"^##\\s+.+$", re.MULTILINE)\n'
        assert [m.group("name") for m in guard._COMPILE.finditer(parser)] == ["_HEADING"]
        # ...but the scan skips it, because the flag is in the trailing group.
        assert "MULTILINE" in next(guard._COMPILE.finditer(parser)).group("rest")
