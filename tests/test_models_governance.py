# tests/test_models_governance.py
# Tests for src/models/governance.py — the Prime -> Cornelius -> Human
# model-advancement governance pipeline.

from __future__ import annotations

import pytest

from src.models.benchmark import BenchmarkRegistry
from src.models.governance import (
    CORNELIUS_MIN_ADVANCEMENT_PCT,
    PRIME_MIN_ADVANCEMENT_PCT,
    InsufficientBenchmarkHistoryError,
    InvalidStageTransitionError,
    ModelGovernanceRegistry,
    ProposalStage,
)


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


def _big_advancement(benchmarks, model="T2ance-CODE", skill="Coder"):
    """A jump comfortably over both Prime and Cornelius thresholds."""
    benchmarks.record_benchmark(model, skill, 60.0)
    benchmarks.record_benchmark(model, skill, 90.0)  # +50%


def _minor_advancement(benchmarks, model="Tranc3-Crypto", skill="Crypto Tokens"):
    """A bump under the Prime threshold."""
    benchmarks.record_benchmark(model, skill, 100.0)
    benchmarks.record_benchmark(model, skill, 101.0)  # +1%


class TestSubmitProposal:
    def test_requires_at_least_two_benchmark_scans(self, governance, benchmarks):
        benchmarks.record_benchmark("T2ance-CODE", "Coder", 60.0)
        with pytest.raises(InsufficientBenchmarkHistoryError):
            governance.submit_proposal("T2ance-CODE", "Coder")

    def test_requires_some_benchmark_history_at_all(self, governance):
        with pytest.raises(InsufficientBenchmarkHistoryError):
            governance.submit_proposal("Nonexistent-Model", "Nothing")

    def test_computes_advancement_pct_from_latest_two_scans(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder", submitted_by="scanner")
        assert proposal.advancement_pct == pytest.approx(50.0, abs=1e-3)
        assert proposal.stage == ProposalStage.PRIME_REVIEW
        assert proposal.submitted_by == "scanner"


class TestPrimeReview:
    def test_rejects_minimal_advancement(self, governance, benchmarks):
        _minor_advancement(benchmarks)
        proposal = governance.submit_proposal("Tranc3-Crypto", "Crypto Tokens")
        assert proposal.advancement_pct < PRIME_MIN_ADVANCEMENT_PCT
        reviewed = governance.prime_review(proposal.id, reviewer="Dorris Fontaine", notes="minor")
        assert reviewed.stage == ProposalStage.REJECTED_BY_PRIME
        assert reviewed.prime_reviewer == "Dorris Fontaine"
        assert reviewed.prime_decided_at is not None

    def test_passes_real_advancement_through_to_cornelius(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        reviewed = governance.prime_review(proposal.id, reviewer="Dorris Fontaine")
        assert reviewed.stage == ProposalStage.CORNELIUS_REVIEW

    def test_cannot_prime_review_twice(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        governance.prime_review(proposal.id, reviewer="Dorris Fontaine")
        with pytest.raises(InvalidStageTransitionError):
            governance.prime_review(proposal.id, reviewer="Dorris Fontaine")

    def test_unknown_proposal_id_raises_keyerror(self, governance):
        with pytest.raises(KeyError):
            governance.prime_review(999999, reviewer="Dorris Fontaine")


class TestCorneliusReview:
    def test_rejects_when_skills_features_assessment_is_below_bar(self, governance, benchmarks):
        _big_advancement(benchmarks)  # +50% clears Prime's 3% bar easily
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        proposal = governance.prime_review(proposal.id, reviewer="Dorris Fontaine")
        # Cornelius's own qualitative assessment can differ from the raw
        # benchmark delta — here it comes in below Cornelius's own bar.
        reviewed = governance.cornelius_review(
            proposal.id, assessed_pct=CORNELIUS_MIN_ADVANCEMENT_PCT - 1, notes="mostly cosmetic"
        )
        assert reviewed.stage == ProposalStage.REJECTED_BY_CORNELIUS
        assert reviewed.cornelius_assessed_pct == CORNELIUS_MIN_ADVANCEMENT_PCT - 1

    def test_defaults_to_raw_advancement_pct_when_not_supplied(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        proposal = governance.prime_review(proposal.id, reviewer="Dorris Fontaine")
        reviewed = governance.cornelius_review(proposal.id)
        assert reviewed.cornelius_assessed_pct == pytest.approx(50.0, abs=1e-3)
        assert reviewed.stage == ProposalStage.HUMAN_REVIEW

    def test_cannot_review_before_prime_stage(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        with pytest.raises(InvalidStageTransitionError):
            governance.cornelius_review(proposal.id)


class TestHumanDecision:
    def _reach_human_review(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        proposal = governance.prime_review(proposal.id, reviewer="Dorris Fontaine")
        return governance.cornelius_review(proposal.id)

    def test_approval_sets_final_stage(self, governance, benchmarks):
        proposal = self._reach_human_review(governance, benchmarks)
        decided = governance.human_decide(
            proposal.id, approved=True, decided_by="Andrew Porter", notes="ship it"
        )
        assert decided.stage == ProposalStage.APPROVED
        assert decided.human_approved is True
        assert decided.human_decider == "Andrew Porter"

    def test_rejection_sets_final_stage(self, governance, benchmarks):
        proposal = self._reach_human_review(governance, benchmarks)
        decided = governance.human_decide(proposal.id, approved=False, decided_by="Andrew Porter")
        assert decided.stage == ProposalStage.REJECTED_BY_HUMAN
        assert decided.human_approved is False

    def test_cannot_decide_before_cornelius_stage(self, governance, benchmarks):
        _big_advancement(benchmarks)
        proposal = governance.submit_proposal("T2ance-CODE", "Coder")
        with pytest.raises(InvalidStageTransitionError):
            governance.human_decide(proposal.id, approved=True, decided_by="Andrew Porter")

    def test_cannot_decide_twice(self, governance, benchmarks):
        proposal = self._reach_human_review(governance, benchmarks)
        governance.human_decide(proposal.id, approved=True, decided_by="Andrew Porter")
        with pytest.raises(InvalidStageTransitionError):
            governance.human_decide(proposal.id, approved=True, decided_by="Andrew Porter")


class TestListAndGet:
    def test_get_unknown_returns_none(self, governance):
        assert governance.get(999999) is None

    def test_list_filters_by_stage(self, governance, benchmarks):
        _minor_advancement(benchmarks)
        rejected_candidate = governance.submit_proposal("Tranc3-Crypto", "Crypto Tokens")
        governance.prime_review(rejected_candidate.id, reviewer="Dorris Fontaine")

        _big_advancement(benchmarks, model="T2ance-CODE-2", skill="Coder2")
        pending = governance.submit_proposal("T2ance-CODE-2", "Coder2")

        rejected = governance.list_proposals(stage=ProposalStage.REJECTED_BY_PRIME)
        awaiting_prime = governance.list_proposals(stage=ProposalStage.PRIME_REVIEW)

        assert {p.id for p in rejected} == {rejected_candidate.id}
        assert {p.id for p in awaiting_prime} == {pending.id}

    def test_list_filters_by_model_name(self, governance, benchmarks):
        _big_advancement(benchmarks)
        governance.submit_proposal("T2ance-CODE", "Coder")
        _big_advancement(benchmarks, model="Tranc3-Crypto", skill="Crypto Tokens")
        governance.submit_proposal("Tranc3-Crypto", "Crypto Tokens")

        only_crypto = governance.list_proposals(model_name="Tranc3-Crypto")
        assert all(p.model_name == "Tranc3-Crypto" for p in only_crypto)
        assert len(only_crypto) == 1


class TestPersistenceAcrossReconnect:
    def test_survives_reopen(self, tmp_path, benchmarks):
        _big_advancement(benchmarks)
        db_path = tmp_path / "gov_reopen.db"
        reg1 = ModelGovernanceRegistry(db_path=db_path, benchmark_registry=benchmarks)
        proposal = reg1.submit_proposal("T2ance-CODE", "Coder")
        reg1.close()
        reg2 = ModelGovernanceRegistry(db_path=db_path, benchmark_registry=benchmarks)
        assert reg2.get(proposal.id) is not None
        reg2.close()
