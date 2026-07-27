# tests/test_models_governance_provenance.py
# Tests that ModelGovernanceRegistry.submit_proposal() actually enforces
# the MC-013 provenance gate (src/models/compliance.py) before opening an
# advancement proposal.

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.models.benchmark import BenchmarkRegistry
from src.models.compliance import OpenProvenanceRiskError, ProvenanceClearanceRegistry
from src.models.governance import ModelGovernanceRegistry

MADAM_KRYSTAL = "Madam Krystal"
GEORGE_PORTER = "George Porter"


@pytest.fixture
def clearance_registry(tmp_path):
    reg = ProvenanceClearanceRegistry(db_path=tmp_path / "provenance.db")
    yield reg
    reg.close()


@pytest.fixture
def benchmarks(tmp_path):
    reg = BenchmarkRegistry(db_path=tmp_path / "bench.db")
    yield reg
    reg.close()


@pytest.fixture
def governance(tmp_path, benchmarks):
    reg = ModelGovernanceRegistry(db_path=tmp_path / "gov.db", benchmark_registry=benchmarks)
    yield reg
    reg.close()


def _isolated(clearance_registry):
    return patch("src.models.compliance.get_clearance_registry", return_value=clearance_registry)


class TestSubmitProposalProvenanceGate:
    def test_blocks_ai_with_open_provenance_risk(self, governance, benchmarks, clearance_registry):
        benchmarks.record_benchmark(MADAM_KRYSTAL, "Image Generation", 60.0)
        benchmarks.record_benchmark(MADAM_KRYSTAL, "Image Generation", 90.0)
        with _isolated(clearance_registry):
            with pytest.raises(OpenProvenanceRiskError):
                governance.submit_proposal(MADAM_KRYSTAL, "Image Generation")

    def test_allows_ai_with_no_seed_risk(self, governance, benchmarks, clearance_registry):
        benchmarks.record_benchmark(GEORGE_PORTER, "Trading", 60.0)
        benchmarks.record_benchmark(GEORGE_PORTER, "Trading", 90.0)
        with _isolated(clearance_registry):
            proposal = governance.submit_proposal(GEORGE_PORTER, "Trading")
        assert proposal.model_name == GEORGE_PORTER

    def test_allows_after_clearance_recorded(self, governance, benchmarks, clearance_registry):
        benchmarks.record_benchmark(MADAM_KRYSTAL, "Image Generation", 60.0)
        benchmarks.record_benchmark(MADAM_KRYSTAL, "Image Generation", 90.0)
        clearance_registry.clear(MADAM_KRYSTAL, cleared_by="Andrew Porter", notes="reviewed")
        with _isolated(clearance_registry):
            proposal = governance.submit_proposal(MADAM_KRYSTAL, "Image Generation")
        assert proposal.model_name == MADAM_KRYSTAL

    def test_provenance_gate_runs_before_benchmark_history_check(
        self, governance, clearance_registry
    ):
        """Even with zero benchmark history, the provenance block should
        still be the error raised — order matters for a clear message."""
        with _isolated(clearance_registry):
            with pytest.raises(OpenProvenanceRiskError):
                governance.submit_proposal(MADAM_KRYSTAL, "Image Generation")
