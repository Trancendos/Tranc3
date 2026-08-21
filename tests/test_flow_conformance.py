"""Behaviour of the Location flow conformance checker.

These tests exist because the first run of this checker was wrong in a
particular way: it reported the Basement-to-Library promotion as `enforced`
because its own module docstring -- the paragraph explaining that `promote()`
is called by nothing -- contains the text `promote()`. The tool cited its own
prose as evidence that the flow was live.

That is the same defect shape as the vulnerability census inferring `blocked`
from register membership: a control that reports health from the very artefact
that documents its absence. The prose-stripping tests below are what stop it
coming back.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import flow_conformance as fc  # noqa: E402


class TestClassify:
    """The five verdicts, one test per branch. `classify` is total by design."""

    def test_all_probes_passing_is_enforced(self):
        assert fc.classify([True, True], [True], errored=False) == "enforced"

    def test_nothing_exists_is_absent(self):
        assert fc.classify([False, False], [False], errored=False) == "absent"

    def test_exists_but_nothing_reaches_it_is_unwired(self):
        """The verdict this checker exists for.

        A hub that is built, composed, imported cleanly and reached by nothing
        reads as done in every review. `absent` and `unwired` cost different
        amounts to fix and must not share a label.
        """
        assert fc.classify([True, True], [False, False], errored=False) == "unwired"

    def test_some_coupling_is_partial(self):
        assert fc.classify([True, True], [True, False], errored=False) == "partial"

    def test_an_unevaluable_probe_is_never_healthy(self):
        """Fail-closed. An error is `unknown`, and `--check` treats it as failure.

        Note this holds even when every probe that DID run passed -- otherwise a
        broken probe would be indistinguishable from a satisfied one.
        """
        assert fc.classify([True], [True], errored=True) == "unknown"

    def test_unknown_ranks_below_every_real_verdict(self):
        assert fc.VERDICT_RANK["unknown"] < min(
            fc.VERDICT_RANK[v] for v in ("absent", "unwired", "partial", "enforced")
        )


class TestProseStripping:
    """A probe must not match on description of the thing it looks for."""

    def test_docstrings_are_stripped(self):
        source = '"""This module never calls promote() anywhere."""\nx = 1\n'
        assert "promote" not in fc._strip_prose(source)

    def test_line_comments_are_stripped(self):
        assert "promote" not in fc._strip_prose("x = 1  # we should call promote() one day\n")

    def test_real_code_survives_stripping(self):
        assert "promote(" in fc._strip_prose("from a import promote\npromote(limit=5)\n")

    def test_the_checker_never_reads_itself(self, tmp_path):
        """The concrete regression: scripts/ is searched for call sites, and this
        file lives in scripts/, so without the exclusion its own docstring is a
        call site for every symbol it describes."""
        collected = fc._code_files(fc.REPO / "scripts")
        assert Path(fc.__file__).resolve() not in [p.resolve() for p in collected]

    def test_bytecode_caches_are_excluded(self):
        """A .pyc contains every string literal in its module, so matching inside
        one counts the same source twice and calls it corroboration."""
        assert all("__pycache__" not in p.parts for p in fc._code_files(fc.REPO / "src"))


class TestProbeSafety:
    def test_unknown_probe_kind_raises_rather_than_passing(self):
        with pytest.raises(fc.ProbeError):
            fc.run_probe({"kind": "wishful_thinking"})

    def test_probe_paths_cannot_escape_the_repository(self):
        with pytest.raises(ValueError):
            fc._inside_repo(Path("/etc/passwd"))

    def test_a_raising_probe_surfaces_as_error_not_as_false(self):
        """`False` and "could not tell" are different answers; conflating them is
        how a scanning failure becomes a clean bill of health."""
        with pytest.raises(fc.ProbeError):
            fc.run_probe({"kind": "code_pattern", "path": "src", "pattern": "((("})


class TestContract:
    def test_every_rule_has_at_least_one_coupling_probe(self):
        """Existence probes alone can only ever produce `enforced`, which would
        let a rule claim a flow purely because the hub's directory is present."""
        for rule in fc.load_contract():
            kinds = {p.get("kind") for p in rule.get("probes", [])}
            assert kinds & fc.COUPLING_KINDS, f"{rule['id']} asserts flow with no coupling probe"

    def test_rule_ids_are_unique(self):
        ids = [r["id"] for r in fc.load_contract()]
        assert len(ids) == len(set(ids))

    def test_every_rule_is_evaluable_today(self):
        """No rule may sit at `unknown` -- that is a broken probe, not a finding."""
        report = fc.build_report()
        assert report["counts"].get("unknown", 0) == 0
