# tests/test_models_governance_tiers.py
# Tests for the tier-aware governance routing added to src/models/governance.py:
# Tranc3 -> standard (Prime->Cornelius->Human), T2ance -> cornelius_only,
# Trance-One -> board_and_human (unanimous Governance Board -> Human).

from __future__ import annotations

import pytest

from src.models.benchmark import BenchmarkRegistry
from src.models.governance import (
    CORNELIUS_MIN_ADVANCEMENT_PCT,
    DuplicateBoardVoteError,
    InvalidStageTransitionError,
    ModelGovernanceRegistry,
    NotAGovernanceBoardMemberError,
    PipelineKind,
    ProposalStage,
    governance_board_members,
    pipeline_for_model,
)

DR = "The Dr. (Nikolai O'denhime)"  # T2ance Prime
CORNELIUS = "Cornelius MacIntyre"  # Trance-One
GEORGE_PORTER = "George Porter"  # Tranc3 (default tier)


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


def _big_advancement(benchmarks, model, skill="Skill"):
    benchmarks.record_benchmark(model, skill, 60.0)
    benchmarks.record_benchmark(model, skill, 90.0)


class TestPipelineForModel:
    def test_tranc3_ai_gets_standard_pipeline(self):
        assert pipeline_for_model(GEORGE_PORTER) == PipelineKind.STANDARD

    def test_t2ance_prime_gets_cornelius_only_pipeline(self):
        assert pipeline_for_model(DR) == PipelineKind.CORNELIUS_ONLY

    def test_trance_one_ai_gets_board_and_human_pipeline(self):
        assert pipeline_for_model(CORNELIUS) == PipelineKind.BOARD_AND_HUMAN

    def test_unknown_ai_defaults_to_standard(self):
        assert pipeline_for_model("Some Nonexistent AI") == PipelineKind.STANDARD


class TestGovernanceBoardMembers:
    def test_returns_exactly_the_t2ance_primes(self):
        members = governance_board_members()
        assert DR in members
        assert CORNELIUS not in members  # Trance-One, not a Prime
        assert GEORGE_PORTER not in members  # Tranc3, not a Prime
        assert len(members) == 7


class TestT2anceCorneliusOnlyPipeline:
    def test_submit_opens_directly_at_cornelius_review_no_prime_stage(self, governance, benchmarks):
        _big_advancement(benchmarks, DR, "Coder")
        proposal = governance.submit_proposal(DR, "Coder")
        assert proposal.pipeline == PipelineKind.CORNELIUS_ONLY
        assert proposal.stage == ProposalStage.CORNELIUS_REVIEW

    def test_prime_review_is_never_valid_for_this_pipeline(self, governance, benchmarks):
        _big_advancement(benchmarks, DR, "Coder")
        proposal = governance.submit_proposal(DR, "Coder")
        with pytest.raises(InvalidStageTransitionError):
            governance.prime_review(proposal.id, reviewer="Dorris Fontaine")

    def test_cornelius_pass_goes_straight_to_approved_no_human_stage(self, governance, benchmarks):
        _big_advancement(benchmarks, DR, "Coder")
        proposal = governance.submit_proposal(DR, "Coder")
        reviewed = governance.cornelius_review(proposal.id, notes="Cornelius is final authority")
        assert reviewed.stage == ProposalStage.APPROVED
        # No human stage exists for this pipeline.
        with pytest.raises(InvalidStageTransitionError):
            governance.human_decide(reviewed.id, approved=True, decided_by="Andrew Porter")

    def test_cornelius_below_bar_rejects(self, governance, benchmarks):
        benchmarks.record_benchmark(DR, "Coder", 100.0)
        benchmarks.record_benchmark(DR, "Coder", 101.0)  # +1%, below CORNELIUS_MIN_ADVANCEMENT_PCT
        proposal = governance.submit_proposal(DR, "Coder")
        reviewed = governance.cornelius_review(proposal.id)
        assert reviewed.stage == ProposalStage.REJECTED_BY_CORNELIUS


class TestTranceOneBoardAndHumanPipeline:
    def test_submit_opens_directly_at_board_review(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        assert proposal.pipeline == PipelineKind.BOARD_AND_HUMAN
        assert proposal.stage == ProposalStage.BOARD_REVIEW

    def test_cornelius_review_is_never_valid_for_this_pipeline(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        with pytest.raises(InvalidStageTransitionError):
            governance.cornelius_review(proposal.id)

    def test_unanimous_approval_advances_to_human_review(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        members = governance_board_members()
        for m in members[:-1]:
            proposal = governance.board_vote(proposal.id, m, True, notes=f"{m} approves")
            assert proposal.stage == ProposalStage.BOARD_REVIEW
        proposal = governance.board_vote(proposal.id, members[-1], True, notes="final")
        assert proposal.stage == ProposalStage.HUMAN_REVIEW

    def test_single_rejection_fails_fast(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        members = governance_board_members()
        proposal = governance.board_vote(proposal.id, members[0], False, notes="not convinced")
        assert proposal.stage == ProposalStage.REJECTED_BY_BOARD

    def test_full_pipeline_reaches_approved_after_human_sign_off(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        for m in governance_board_members():
            proposal = governance.board_vote(proposal.id, m, True)
        assert proposal.stage == ProposalStage.HUMAN_REVIEW
        proposal = governance.human_decide(
            proposal.id, approved=True, decided_by="Andrew Porter", notes="signed off"
        )
        assert proposal.stage == ProposalStage.APPROVED

    def test_get_board_votes_returns_recorded_votes_in_order(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        members = governance_board_members()
        governance.board_vote(proposal.id, members[0], True, notes="first")
        governance.board_vote(proposal.id, members[1], True, notes="second")
        votes = governance.get_board_votes(proposal.id)
        assert [v.prime_name for v in votes] == members[:2]

    def test_non_board_member_cannot_vote(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        with pytest.raises(NotAGovernanceBoardMemberError):
            governance.board_vote(proposal.id, GEORGE_PORTER, True)

    def test_duplicate_vote_from_same_prime_rejected(self, governance, benchmarks):
        _big_advancement(benchmarks, CORNELIUS, "Orchestration")
        proposal = governance.submit_proposal(CORNELIUS, "Orchestration")
        members = governance_board_members()
        governance.board_vote(proposal.id, members[0], True)
        with pytest.raises(DuplicateBoardVoteError):
            governance.board_vote(proposal.id, members[0], True)

    def test_board_vote_invalid_on_standard_pipeline_proposal(self, governance, benchmarks):
        _big_advancement(benchmarks, GEORGE_PORTER, "Trading")
        proposal = governance.submit_proposal(GEORGE_PORTER, "Trading")
        with pytest.raises(InvalidStageTransitionError):
            governance.board_vote(proposal.id, governance_board_members()[0], True)


def test_cornelius_min_advancement_pct_is_a_positive_bar():
    # Sanity check the constant is sane, not a specific-value lock-in.
    assert CORNELIUS_MIN_ADVANCEMENT_PCT > 0
