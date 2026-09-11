"""The `$`-before-newline trap, and the guard that now blocks it.

`re.compile(r"^[a-z]+$").match("abc\\n")` matches. `$` anchors at the end of the
string **or immediately before a trailing newline**, so every anchored pattern
used with `.match()` admits one `\\n` its own character class forbids.

Found while adjudicating the two `py/sql-injection` alerts at CodeQL severity
8.8 in `src/vector/adapter.py`. The alert is a false positive — the validator
holds against every injection shape — and the validator was still wrong.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _load_guard():
    """Load `scripts/check_anchored_validators.py` as a module.

    One copy, not two: cubic pointed out this boilerplate was duplicated
    verbatim across two tests, and the file has since grown four more that need
    it.
    """
    from importlib.util import module_from_spec, spec_from_file_location

    spec = spec_from_file_location(
        "anchored_guard_under_test", _ROOT / "scripts" / "check_anchored_validators.py"
    )
    guard = module_from_spec(spec)
    sys.modules[spec.name] = guard
    spec.loader.exec_module(guard)
    return guard


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
        guard = _load_guard()
        source = '_SAFE_IDENT = __import__("re").compile(r"^[a-z][a-z0-9_]{0,62}$")\n'
        assert guard._anchored_names_ast(ast.parse(source)) == {"_SAFE_IDENT"}, (
            "guard cannot see its own motivating case"
        )

    def test_multiline_patterns_are_exempt(self):
        """A line parser's `$`-before-newline is the point, not a defect."""
        guard = _load_guard()
        parser = '_HEADING = re.compile(r"^##\\s+.+$", re.MULTILINE)\n'
        assert guard._anchored_names_ast(ast.parse(parser)) == set()

    def test_annotated_assignment_is_seen(self):
        """cubic's P2, first half — and it was right.

        The source regex required `NAME = ...compile(`, so a perfectly ordinary
        annotated binding slipped past it and any `.match()` on that name went
        unreported.
        """
        guard = _load_guard()
        source = '_SAFE: re.Pattern[str] = re.compile(r"^[a-z]+$")\n'
        assert guard._anchored_names_ast(ast.parse(source)) == {"_SAFE"}

    def test_multiline_compile_is_seen(self):
        """The form that was actually hiding in this repository.

        `scripts/align_framework_pins.py` compiles a verbose pattern across
        several lines. The regex could not see it, so its `.match()` call went
        unreported until the AST rewrite — at which point the guard named it on
        its first run.
        """
        guard = _load_guard()
        source = (
            "_REQ = re.compile(\n"
            '    r"""^(?P<name>[a-z]+)\n'
            '        (?P<rest>.*)$""",\n'
            "    re.X,\n"
            ")\n"
        )
        assert guard._anchored_names_ast(ast.parse(source)) == {"_REQ"}

    def test_multiline_is_matched_as_a_symbol_not_a_substring(self):
        """cubic, round 8. `"MULTILINE" in ast.unparse(flag)` is a substring test.

        Any flag expression that merely contained the word suppressed a real
        offence. Measured: with a flag named `NOT_MULTILINE` the old test
        returned True and skipped the validator entirely.
        """
        guard = _load_guard()
        source = 'NOT_MULTILINE = 0\n_S = re.compile(r"^[a-z]+$", NOT_MULTILINE)\nx = _S.match(v)\n'
        tree = ast.parse(source)

        # The old behaviour, reproduced so the regression is visible.
        flag = tree.body[1].value.args[1]
        assert "MULTILINE" in ast.unparse(flag), "the substring test did fire here"

        assert guard._anchored_names_ast(tree) == {"_S"}, "symbol-aware check must still see it"
        assert not guard._names_multiline(flag)

    def test_real_multiline_is_still_exempt(self):
        """The counterpart, so the fix is not "never exempt anything"."""
        guard = _load_guard()
        for spelling in ("re.MULTILINE", "MULTILINE", "re.MULTILINE | re.VERBOSE"):
            source = f'_S = re.compile(r"^[a-z]+$", {spelling})\nx = _S.match(v)\n'
            assert guard._anchored_names_ast(ast.parse(source)) == set(), spelling

    def test_exemption_must_be_a_comment_not_a_string(self):
        """cubic, round 8. The marker inside a string argument exempted the call.

        Scanning every source line in the call's span treats data as an
        exemption, so any call could exempt itself by mentioning the marker.
        Tokenising finds real COMMENT tokens instead.
        """
        guard = _load_guard()
        source = (
            '_S = re.compile(r"^[a-z]+$")\n'
            "x = _S.match(\n"
            '    "# anchored-ok: not really a comment",\n'
            ")\n"
        )
        tree = ast.parse(source)
        start, end, _ = guard._match_calls_ast(tree, guard._anchored_names_ast(tree))[0]

        # The old behaviour, reproduced.
        span = source.splitlines()[start - 1 : end]
        assert any(guard._EXEMPT_COMMENT.search(line) for line in span), "line scan did fire"

        assert not (guard._comment_lines(source) & set(range(start, end + 1)))

    def test_a_genuine_comment_still_exempts(self):
        """Otherwise the seven documented line parsers would all fail CI."""
        guard = _load_guard()
        source = '_S = re.compile(r"^[a-z]+$")\nx = _S.match(v)  # anchored-ok: line parser\n'
        assert guard._comment_lines(source) == {2}

    def test_an_untokenisable_file_fails_closed(self):
        """No exemptions rather than blanket exemption.

        A file the tokeniser chokes on must not become a file where every call
        is exempt — that would turn a parse failure into a silent hole.
        """
        guard = _load_guard()
        assert guard._comment_lines("def broken(:\n    # anchored-ok: x\n") == set()

    def test_every_form_the_regex_missed(self):
        """cubic's P2, measured form by form rather than accepted wholesale.

        Four spellings, checked against both implementations. The regex saw one
        of them; the claim that it missed "multiline `.match()` calls" is right
        for the attribute-split spelling and wrong for the args-split one, and
        the form actually hiding in this repository was neither — it was a
        multiline `re.compile(`, in `scripts/align_framework_pins.py`, which the
        AST rewrite named on its first run.

            form                     regex sees call    AST sees call
            call args on next line   yes                yes
            attribute split          no                 yes
            multiline compile        no                 yes
            annotated assignment     no                 yes
        """
        guard = _load_guard()
        forms = {
            "call args on next line": '_S = re.compile(r"^[a-z]+$")\nx = _S.match(\n    v,\n)\n',
            "attribute split": '_S = re.compile(r"^[a-z]+$")\nx = (\n    _S\n    .match(v)\n)\n',
            "multiline compile": (
                '_S = re.compile(\n    r"""^(?P<a>[a-z]+)$""",\n    re.X,\n)\nx = _S.match(v)\n'
            ),
            "annotated assignment": '_S: re.Pattern = re.compile(r"^[a-z]+$")\nx = _S.match(v)\n',
        }
        regex_blind = []
        for label, source in forms.items():
            tree = ast.parse(source)
            names = guard._anchored_names_ast(tree)
            assert guard._match_calls_ast(tree, names), f"AST missed: {label}"
            if not guard._scan_with_regex(source)[1]:
                regex_blind.append(label)

        assert sorted(regex_blind) == [
            "annotated assignment",
            "attribute split",
            "multiline compile",
        ], regex_blind
