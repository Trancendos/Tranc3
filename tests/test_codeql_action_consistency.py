"""Regression coverage for scripts/check_codeql_action_consistency.py.

The checker guards an invariant that took CodeQL red on main for three days:
every `github/codeql-action/*` pin inside one workflow file must resolve to the
same ref, because `init` stamps its config with its own release version and
`analyze` refuses to load a config written by a different one.

A checker that silently matches nothing is worse than no checker, so these
tests pin both halves: that it sees the references it is supposed to see
(bare *and* quoted -- the first version of the regex missed quoted scalars
entirely and reported OK for a file whose pins disagreed), and that it
actually fails when they disagree.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "check_codeql_action_consistency",
    Path(__file__).resolve().parent.parent / "scripts" / "check_codeql_action_consistency.py",
)
assert _SPEC and _SPEC.loader
checker = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(checker)


class TestUsesPattern:
    """The `uses:` scalar may be bare, double-quoted or single-quoted YAML."""

    def test_matches_bare_scalar(self):
        m = checker.USES_RE.match("      uses: github/codeql-action/init@v4")
        assert m and (m.group("sub"), m.group("ref")) == ("init", "v4")

    def test_matches_double_quoted_scalar(self):
        m = checker.USES_RE.match('      uses: "github/codeql-action/init@v4"')
        assert m and (m.group("sub"), m.group("ref")) == ("init", "v4")

    def test_matches_single_quoted_scalar(self):
        m = checker.USES_RE.match("      uses: 'github/codeql-action/analyze@abc123'")
        assert m and (m.group("sub"), m.group("ref")) == ("analyze", "abc123")

    def test_matches_list_item_with_trailing_comment(self):
        m = checker.USES_RE.match("      - uses: github/codeql-action/upload-sarif@d1e2 # v4")
        assert m and (m.group("sub"), m.group("ref")) == ("upload-sarif", "d1e2")

    def test_quoting_does_not_change_the_ref(self):
        """The closing quote must not become part of the ref.

        If it did, `init@v4` and `"init@v4"` would read as two different refs
        and a correctly-pinned file would fail.
        """
        bare = checker.USES_RE.match("  uses: github/codeql-action/init@v4")
        quoted = checker.USES_RE.match('  uses: "github/codeql-action/init@v4"')
        assert bare.group("ref") == quoted.group("ref") == "v4"

    def test_ignores_other_actions(self):
        assert checker.USES_RE.match("      uses: actions/checkout@v4") is None


class TestCollect:
    """`collect()` groups a file's codeql-action references by ref."""

    def _write(self, tmp_path: Path, body: str) -> Path:
        path = tmp_path / "wf.yml"
        path.write_text(body)
        return path

    def test_consistent_file_yields_one_ref(self, tmp_path):
        path = self._write(
            tmp_path,
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - uses: github/codeql-action/init@aaa\n"
            "      - uses: github/codeql-action/analyze@aaa\n",
        )
        assert len(checker.collect(path)) == 1

    def test_inconsistent_file_yields_two_refs(self, tmp_path):
        path = self._write(
            tmp_path,
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - uses: github/codeql-action/init@aaa\n"
            "      - uses: github/codeql-action/analyze@bbb\n",
        )
        by_ref = checker.collect(path)
        assert set(by_ref) == {"aaa", "bbb"}

    def test_quoted_disagreement_is_still_detected(self, tmp_path):
        """The case the original regex missed entirely.

        With a bare `init` and a quoted `analyze` on a different ref, the old
        pattern saw only one reference and reported the file consistent.
        """
        path = self._write(
            tmp_path,
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            "      - uses: github/codeql-action/init@aaa\n"
            '      - uses: "github/codeql-action/analyze@bbb"\n',
        )
        by_ref = checker.collect(path)
        assert set(by_ref) == {"aaa", "bbb"}, "quoted pin must be compared, not skipped"

    def test_all_quoted_and_consistent_is_not_a_false_failure(self, tmp_path):
        path = self._write(
            tmp_path,
            "jobs:\n"
            "  a:\n"
            "    steps:\n"
            '      - uses: "github/codeql-action/init@aaa"\n'
            "      - uses: 'github/codeql-action/analyze@aaa'\n",
        )
        assert len(checker.collect(path)) == 1

    def test_file_without_codeql_yields_nothing(self, tmp_path):
        path = self._write(tmp_path, "jobs:\n  a:\n    steps:\n      - uses: actions/checkout@v4\n")
        assert checker.collect(path) == {}


def test_repo_workflows_are_consistent():
    """The invariant holds on this repository right now."""
    assert checker.main() == 0
