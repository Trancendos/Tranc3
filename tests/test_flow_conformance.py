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

    def test_every_rule_has_at_least_one_existence_probe(self):
        """Without one, `classify` cannot reach `absent`.

        A rule carrying only coupling probes reports a deleted hub as `unwired`
        -- built and unreached -- when the truth is that nothing is there at
        all. It can also reach `enforced` on coupling alone, because `all([])`
        is True for the empty existence list.
        """
        for rule in fc.load_contract():
            kinds = {p.get("kind") for p in rule.get("probes", [])}
            assert kinds & fc.EXISTENCE_KINDS, f"{rule['id']} cannot ever report `absent`"

    def test_rule_ids_are_unique(self):
        ids = [r["id"] for r in fc.load_contract()]
        assert len(ids) == len(set(ids))

    def test_every_rule_is_evaluable_today(self):
        """No rule may sit at `unknown` -- that is a broken probe, not a finding."""
        report = fc.build_report()
        assert report["counts"].get("unknown", 0) == 0


class TestBaselineComparison:
    """The baseline is a ratchet, and a ratchet that only catches one direction
    is not a ratchet.

    The first implementation failed only on a lower verdict. That let an
    improvement pass unrecorded, which left the baseline stale -- and a later
    slide back to the stale value then also passed, because it matched. The gate
    stayed green across the entire round trip while silently giving back the
    improvement it never recorded.
    """

    @staticmethod
    def _report(**verdicts):
        return {
            "rules": [
                {"id": rid, "verdict": v, "claim": f"claim for {rid}"}
                for rid, v in verdicts.items()
            ]
        }

    def _with_baseline(self, monkeypatch, tmp_path, mapping):
        path = tmp_path / "flow_baseline.json"
        path.write_text(__import__("json").dumps(mapping))
        monkeypatch.setattr(fc, "BASELINE", path)

    def test_exact_match_passes(self, monkeypatch, tmp_path):
        self._with_baseline(monkeypatch, tmp_path, {"FLOW-001": "partial"})
        assert fc.check_against_baseline(self._report(**{"FLOW-001": "partial"})) == []

    def test_regression_fails(self, monkeypatch, tmp_path):
        self._with_baseline(monkeypatch, tmp_path, {"FLOW-001": "enforced"})
        failures = fc.check_against_baseline(self._report(**{"FLOW-001": "partial"}))
        assert len(failures) == 1 and "regressed" in failures[0]

    def test_improvement_also_fails(self, monkeypatch, tmp_path):
        """Not pedantry: refreshing the baseline is the act that makes the
        improvement real, and a gate that does not require it turns
        --write-baseline into an optional courtesy."""
        self._with_baseline(monkeypatch, tmp_path, {"FLOW-001": "unwired"})
        failures = fc.check_against_baseline(self._report(**{"FLOW-001": "enforced"}))
        assert len(failures) == 1
        assert "improved" in failures[0] and "refresh the baseline" in failures[0]

    def test_a_rule_missing_from_the_baseline_fails(self, monkeypatch, tmp_path):
        self._with_baseline(monkeypatch, tmp_path, {})
        failures = fc.check_against_baseline(self._report(**{"FLOW-001": "enforced"}))
        assert len(failures) == 1 and "not in the baseline" in failures[0]

    def test_a_rule_deleted_from_the_contract_fails(self, monkeypatch, tmp_path):
        """Otherwise a flow stops being watched and nothing says so."""
        self._with_baseline(monkeypatch, tmp_path, {"FLOW-001": "enforced", "FLOW-999": "partial"})
        failures = fc.check_against_baseline(self._report(**{"FLOW-001": "enforced"}))
        assert len(failures) == 1 and "not in the contract" in failures[0]

    def test_a_missing_baseline_file_fails_rather_than_passes(self, monkeypatch, tmp_path):
        monkeypatch.setattr(fc, "BASELINE", tmp_path / "absent.json")
        assert fc.check_against_baseline(self._report(**{"FLOW-001": "enforced"}))


class TestTheContractDocument:
    """The written contract, checked against the recorded baseline.

    The document is hand-maintained and the baseline is refreshed by
    `--write-baseline`, so the two drift in exactly one direction: the
    document keeps stating a verdict that stopped being true. It did — for a
    fortnight it called FLOW-064 `unwired` after the Town Hall's PLM gate was
    wired, with counts of 22/12 against a baseline holding 23/11. Nothing
    read the document, so nothing could say so.
    """

    def _doc(self, monkeypatch, tmp_path, body: str) -> None:
        path = tmp_path / "contract.md"
        path.write_text(body, encoding="utf-8")
        monkeypatch.setattr(fc, "CONTRACT_DOC", path)

    def _rows(self, verdicts: dict[str, str]) -> str:
        rows = "\n".join(
            f"| `{rule}` | A Hub | a claim | **{verdict}** |" for rule, verdict in verdicts.items()
        )
        counts: dict[str, int] = {}
        for verdict in verdicts.values():
            counts[verdict] = counts.get(verdict, 0) + 1
        table = "\n".join(f"| `{v}` | {n} |" for v, n in counts.items())
        return f"{table}\n\n{rows}\n"

    def test_a_document_matching_the_baseline_passes(self, monkeypatch, tmp_path):
        baseline = {"FLOW-001": "enforced", "FLOW-002": "unwired"}
        self._doc(monkeypatch, tmp_path, self._rows(baseline))
        assert fc.check_contract_document(baseline) == []

    def test_a_stale_verdict_fails(self, monkeypatch, tmp_path):
        """Calibrated: not reading the document at all fails this."""
        self._doc(monkeypatch, tmp_path, self._rows({"FLOW-001": "unwired"}))
        failures = fc.check_contract_document({"FLOW-001": "enforced"})
        assert any("document says unwired" in f for f in failures)

    def test_a_stale_count_fails(self, monkeypatch, tmp_path):
        """The counts drift on their own, being a second hand-kept copy."""
        self._doc(
            monkeypatch,
            tmp_path,
            "| `enforced` | 9 |\n\n| `FLOW-001` | A Hub | a claim | **enforced** |\n",
        )
        failures = fc.check_contract_document({"FLOW-001": "enforced"})
        assert any("count table says 9 enforced" in f for f in failures)

    def test_a_flow_the_document_omits_fails(self, monkeypatch, tmp_path):
        self._doc(monkeypatch, tmp_path, self._rows({"FLOW-001": "enforced"}))
        failures = fc.check_contract_document({"FLOW-001": "enforced", "FLOW-002": "unwired"})
        assert any("omits it" in f for f in failures)

    def test_an_unbolded_verdict_reads_the_same(self, monkeypatch, tmp_path):
        """Calibrated: requiring the bold markers fails this.

        The document bolds some verdicts and not others. Presentation must
        not decide what a checker sees, or four `partial`/`absent` rows go
        unread and the check silently covers less than it claims.
        """
        self._doc(
            monkeypatch,
            tmp_path,
            "| `partial` | 1 |\n\n| `FLOW-001` | A Hub | a claim | partial |\n",
        )
        assert fc.check_contract_document({"FLOW-001": "partial"}) == []

    def test_the_live_document_matches_the_live_baseline(self):
        import json

        assert fc.check_contract_document(json.loads(fc.BASELINE.read_text(encoding="utf-8"))) == []
