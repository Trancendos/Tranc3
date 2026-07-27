# tests/test_models_intervention.py
# Tests for src/models/intervention.py — Governance Board failover/repair/
# override authority over a malfunctioning Trance-One (Sovereign) AI.

from __future__ import annotations

import pytest

from src.models.governance import (
    DuplicateBoardVoteError,
    InvalidStageTransitionError,
    NotAGovernanceBoardMemberError,
    governance_board_members,
)
from src.models.intervention import (
    InterventionRegistry,
    InterventionStatus,
    InterventionType,
    NotASovereignTierModelError,
)

CORNELIUS = "Cornelius MacIntyre"
QUEEN = "The Queen"
DR = "The Dr. (Nikolai O'denhime)"  # T2ance Prime, a valid Board member
GEORGE_PORTER = "George Porter"  # Tranc3


@pytest.fixture
def registry(tmp_path):
    reg = InterventionRegistry(db_path=tmp_path / "interv.db")
    yield reg
    reg.close()


class TestRaiseIntervention:
    def test_requires_board_membership(self, registry):
        with pytest.raises(NotAGovernanceBoardMemberError):
            registry.raise_intervention(
                CORNELIUS, InterventionType.REPAIR_REQUEST, "unresponsive", raised_by=GEORGE_PORTER
            )

    def test_requires_a_sovereign_tier_target(self, registry):
        with pytest.raises(NotASovereignTierModelError):
            registry.raise_intervention(
                GEORGE_PORTER, InterventionType.REPAIR_REQUEST, "seems off", raised_by=DR
            )

    def test_valid_raise_opens_at_open_status(self, registry):
        iv = registry.raise_intervention(
            CORNELIUS,
            InterventionType.CORRUPTION_OVERRIDE,
            "anomalous output pattern detected",
            raised_by=DR,
        )
        assert iv.status == InterventionStatus.OPEN
        assert iv.target_model == CORNELIUS
        assert iv.intervention_type == InterventionType.CORRUPTION_OVERRIDE

    def test_can_target_any_of_the_three_trance_one_slots(self, registry):
        for target in (CORNELIUS, QUEEN, "tAImra"):
            iv = registry.raise_intervention(
                target, InterventionType.SYSTEM_RECOVERY, "stalled", raised_by=DR
            )
            assert iv.status == InterventionStatus.OPEN


class TestInterventionVote:
    def test_requires_board_membership(self, registry):
        iv = registry.raise_intervention(
            CORNELIUS, InterventionType.REPAIR_REQUEST, "test", raised_by=DR
        )
        with pytest.raises(NotAGovernanceBoardMemberError):
            registry.intervention_vote(iv.id, GEORGE_PORTER, True)

    def test_unanimous_approval_executes(self, registry):
        iv = registry.raise_intervention(
            CORNELIUS,
            InterventionType.REPAIR_REQUEST,
            "unresponsive to health checks",
            raised_by=DR,
        )
        members = governance_board_members()
        for m in members[:-1]:
            iv = registry.intervention_vote(iv.id, m, True, notes=f"{m} concurs")
            assert iv.status == InterventionStatus.OPEN
        iv = registry.intervention_vote(iv.id, members[-1], True, notes="final concurrence")
        assert iv.status == InterventionStatus.EXECUTED
        assert iv.resolved_at is not None

    def test_single_rejection_withdraws_immediately(self, registry):
        iv = registry.raise_intervention(
            QUEEN, InterventionType.SYSTEM_RECOVERY, "queue stalled", raised_by="Norman Hawkins"
        )
        iv = registry.intervention_vote(iv.id, "Voxx", False, notes="not yet warranted")
        assert iv.status == InterventionStatus.WITHDRAWN

    def test_duplicate_vote_rejected(self, registry):
        iv = registry.raise_intervention(
            CORNELIUS, InterventionType.REPAIR_REQUEST, "test", raised_by=DR
        )
        registry.intervention_vote(iv.id, "Dorris Fontaine", True)
        with pytest.raises(DuplicateBoardVoteError):
            registry.intervention_vote(iv.id, "Dorris Fontaine", True)

    def test_cannot_vote_on_resolved_intervention(self, registry):
        iv = registry.raise_intervention(
            CORNELIUS, InterventionType.REPAIR_REQUEST, "test", raised_by=DR
        )
        iv = registry.intervention_vote(iv.id, "Dorris Fontaine", False)
        assert iv.status == InterventionStatus.WITHDRAWN
        with pytest.raises(InvalidStageTransitionError):
            registry.intervention_vote(iv.id, "Norman Hawkins", True)

    def test_unknown_intervention_raises_keyerror(self, registry):
        with pytest.raises(KeyError):
            registry.intervention_vote(999999, "Dorris Fontaine", True)

    def test_get_intervention_votes_in_order(self, registry):
        iv = registry.raise_intervention(
            CORNELIUS, InterventionType.REPAIR_REQUEST, "test", raised_by=DR
        )
        registry.intervention_vote(iv.id, "Dorris Fontaine", True, notes="first")
        registry.intervention_vote(iv.id, "Norman Hawkins", True, notes="second")
        votes = registry.get_intervention_votes(iv.id)
        assert [v.prime_name for v in votes] == ["Dorris Fontaine", "Norman Hawkins"]


class TestListAndGet:
    def test_get_unknown_returns_none(self, registry):
        assert registry.get(999999) is None

    def test_list_filters_by_status(self, registry):
        executed = registry.raise_intervention(
            CORNELIUS, InterventionType.REPAIR_REQUEST, "a", raised_by=DR
        )
        for m in governance_board_members():
            executed = registry.intervention_vote(executed.id, m, True)
        withdrawn = registry.raise_intervention(
            QUEEN, InterventionType.SYSTEM_RECOVERY, "b", raised_by="Voxx"
        )
        withdrawn = registry.intervention_vote(withdrawn.id, "Savania", False)

        assert {
            iv.id for iv in registry.list_interventions(status=InterventionStatus.EXECUTED)
        } == {executed.id}
        assert {
            iv.id for iv in registry.list_interventions(status=InterventionStatus.WITHDRAWN)
        } == {withdrawn.id}

    def test_list_filters_by_target_model(self, registry):
        registry.raise_intervention(CORNELIUS, InterventionType.REPAIR_REQUEST, "a", raised_by=DR)
        registry.raise_intervention(QUEEN, InterventionType.SYSTEM_RECOVERY, "b", raised_by=DR)
        cornelius_only = registry.list_interventions(target_model=CORNELIUS)
        assert all(iv.target_model == CORNELIUS for iv in cornelius_only)
        assert len(cornelius_only) == 1


class TestPersistenceAcrossReconnect:
    def test_survives_reopen(self, tmp_path):
        db_path = tmp_path / "reopen.db"
        reg1 = InterventionRegistry(db_path=db_path)
        iv = reg1.raise_intervention(CORNELIUS, InterventionType.REPAIR_REQUEST, "x", raised_by=DR)
        reg1.close()
        reg2 = InterventionRegistry(db_path=db_path)
        assert reg2.get(iv.id) is not None
        reg2.close()
