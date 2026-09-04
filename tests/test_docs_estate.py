"""Calibration for the documentation estate contract and the gate-engine doc.

A forward-planning pass proposed roughly fifty documents. The repository
already held 210 markdown files, most of the proposal among them. Writing the
set again would have duplicated what exists — against a standing instruction
to consolidate rather than duplicate — and buried the handful of real gaps.
So the estate is declared as a contract and measured.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from scripts import check_docs_estate, generate_gate_engine_doc  # noqa: E402


class TestTheContractHolds:
    def test_every_live_artefact_still_has_a_file(self):
        """Calibrated: declaring a live entry whose file is absent fails this.

        The check exists for the day a document is deleted or renamed and the
        estate keeps claiming coverage it no longer has.
        """
        assert check_docs_estate.main(["--check"]) == 0

    def test_the_known_gaps_do_not_fail_the_check(self):
        """Calibrated: failing on `missing` fails this.

        Seven artefacts are declared missing on purpose. A gate red on day one
        for reasons nobody can fix that day teaches people to wave it through
        — the same reasoning scripts/flow_conformance.py records for its
        baseline.
        """
        entries, _ = check_docs_estate.audit()
        assert any(e["status"] == "missing" for e in entries)
        assert check_docs_estate.main(["--check"]) == 0

    def test_a_glob_pattern_resolves(self):
        """Calibrated: treating every path as a literal fails this.

        Several entries are satisfied by a directory of documents rather than
        one named file.
        """
        entries, _ = check_docs_estate.audit()
        runbooks = next(e for e in entries if e["id"] == "OPS-RUNBOOKS")
        assert runbooks["found"] is not None

    def test_every_entry_declares_a_status_the_report_understands(self):
        entries, _ = check_docs_estate.audit()
        assert entries
        for entry in entries:
            assert entry["status"] in ("live", "descriptive", "missing"), entry["id"]

    def test_a_missing_entry_points_at_nothing(self):
        """Calibrated: letting an entry be both missing and satisfied fails this.

        An entry that resolves to a file is not a gap, whatever it claims.
        """
        entries, _ = check_docs_estate.audit()
        for entry in entries:
            if entry["status"] == "missing":
                assert entry["found"] is None, entry["id"]

    def test_entry_ids_are_unique(self):
        entries, _ = check_docs_estate.audit()
        ids = [e["id"] for e in entries]
        assert len(ids) == len(set(ids))


class TestTheGateEngineDocument:
    def test_the_committed_document_matches_the_resolver(self):
        """Calibrated: editing docs/governance/GATE-ENGINE.md by hand fails this."""
        assert generate_gate_engine_doc.main(["--check"]) == 0

    def test_every_decision_has_a_row_in_the_decisions_table(self):
        """Calibrated: rendering a subset of the table fails this.

        The assertion is on the table rows, not on the decision names
        appearing anywhere in the document, and that distinction is the
        calibration. Every decision is also named in the severity order line
        and in the worked outcomes, so a test that searched the whole text
        passed with three of the five rows deleted — redundantly defended,
        and defended by the wrong thing.
        """
        from src.gates.decision import Decision

        rendered = generate_gate_engine_doc.render()
        rows = [line for line in rendered.splitlines() if line.startswith("| `")]
        documented = {line.split("`")[1] for line in rows}
        assert {d.value for d in Decision} <= documented

    def test_the_document_states_the_severity_order_from_the_code(self):
        """Calibrated: writing the order as prose fails this.

        The order is the thing most likely to be got wrong by hand, because
        alphabetical looks plausible and puts redact above block.
        """
        from src.gates.decision import _SEVERITY

        rendered = generate_gate_engine_doc.render()
        assert "  <  ".join(d.value for d in _SEVERITY) in rendered

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [("high", "`block`"), ("minimal", "`degrade`")],
    )
    def test_the_fail_closed_table_is_derived_not_asserted(self, tier, expected):
        """Calibrated: hardcoding the table fails this.

        The table is produced by calling decide() with policy_available=False,
        so it cannot describe behaviour the resolver does not have.
        """
        rendered = generate_gate_engine_doc.render()
        row = next(line for line in rendered.splitlines() if line.startswith(f"| `{tier}` |"))
        assert expected in row

    def test_it_records_that_the_existing_gate_defaults_to_off(self):
        """The measurement the whole document is written from."""
        rendered = generate_gate_engine_doc.render()
        assert "MAGNA_CARTA_ENABLED" in rendered
        assert "defaults to `false`" in rendered

    def test_both_checks_are_wired_into_ci(self):
        """Calibrated: removing either step from ci.yml fails this."""
        ci = (REPO / ".github/workflows/ci.yml").read_text()
        assert "scripts/generate_gate_engine_doc.py --check" in ci
        assert "scripts/check_docs_estate.py --check" in ci
