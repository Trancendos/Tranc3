"""
tests/test_hil_a.py — HIL-A (Human In Loop Action) Chain Protocol tests.
Phase 23 — Comprehensive coverage of the chain protocol engine.
"""

from __future__ import annotations

import os
import sys
import time

os.environ.setdefault("SECRET_KEY", "test-secret-key-hil-a-00001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-hil-a-00001")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared_core.infinity.hil_a import (
    BypassReason,
    ChainProtocol,
    EnhancementRequest,
    EnhancementStatus,
    EnhancementType,
    SelfGoverningVotingSystem,
    UrgencyLevel,
    Vote,
    VoteRecord,
    create_default_chain,
    get_default_chain,
)
from shared_core.infinity.nomenclature import Tier


# ---------------------------------------------------------------------------
# EnhancementRequest
# ---------------------------------------------------------------------------
class TestEnhancementRequest:
    def test_creation_defaults(self):
        req = EnhancementRequest(
            title="Test request",
            justification="Test justification",
            remit="test",
            request_type=EnhancementType.REPAIR,
        )
        assert req.title == "Test request"
        assert req.urgency == UrgencyLevel.ROUTINE
        assert req.requester_tier == Tier.AI
        assert req.status == EnhancementStatus.DRAFT
        assert req.cost_estimate == 0.0
        assert req.request_id  # UUID generated
        assert req.expires_at is not None

    def test_urgency_sets_expiry(self):
        req_critical = EnhancementRequest(
            title="Critical",
            justification="Urgent",
            remit="test",
            request_type=EnhancementType.SECURITY,
            urgency=UrgencyLevel.CRITICAL,
        )
        req_routine = EnhancementRequest(
            title="Routine",
            justification="Normal",
            remit="test",
            request_type=EnhancementType.FEATURE,
            urgency=UrgencyLevel.ROUTINE,
        )
        # Critical should have shorter TTL than routine
        critical_ttl = req_critical.expires_at - req_critical.created_at
        routine_ttl = req_routine.expires_at - req_routine.created_at
        assert critical_ttl < routine_ttl

    def test_is_expired_false(self):
        req = EnhancementRequest(
            title="Test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
        )
        assert req.is_expired() is False

    def test_is_expired_true(self):
        req = EnhancementRequest(
            title="Test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
            expires_at=time.time() - 100,  # Expired 100 seconds ago
        )
        assert req.is_expired() is True

    def test_is_cost_bearing(self):
        req_free = EnhancementRequest(
            title="Free",
            justification="No cost",
            remit="test",
            request_type=EnhancementType.FEATURE,
        )
        req_cost = EnhancementRequest(
            title="Costly",
            justification="Has cost",
            remit="test",
            request_type=EnhancementType.COST_APPROVAL,
            cost_estimate=500.0,
        )
        assert req_free.is_cost_bearing() is False
        assert req_cost.is_cost_bearing() is True

    def test_to_dict(self):
        req = EnhancementRequest(
            title="Dict test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.OPTIMIZATION,
            requester_tier=Tier.PRIME,
            requester_id="the_dr",
        )
        d = req.to_dict()
        assert d["title"] == "Dict test"
        assert d["request_type"] == "optimization"
        assert d["requester_tier"] == 2  # Tier.PRIME.value
        assert d["requester_id"] == "the_dr"
        assert isinstance(d["specs"], dict)

    def test_next_tier_up(self):
        assert EnhancementRequest._next_tier_up(Tier.BOT) == Tier.AGENT
        assert EnhancementRequest._next_tier_up(Tier.AGENT) == Tier.AI
        assert EnhancementRequest._next_tier_up(Tier.AI) == Tier.PRIME
        assert EnhancementRequest._next_tier_up(Tier.PRIME) == Tier.ORCHESTRATOR
        assert EnhancementRequest._next_tier_up(Tier.ORCHESTRATOR) == Tier.HUMAN
        assert EnhancementRequest._next_tier_up(Tier.HUMAN) == Tier.HUMAN

    def test_custom_request_id(self):
        custom_id = "custom-req-001"
        req = EnhancementRequest(
            title="Custom ID",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
            request_id=custom_id,
        )
        assert req.request_id == custom_id

    def test_requester_tier_sets_current_tier(self):
        req = EnhancementRequest(
            title="Agent request",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
            requester_tier=Tier.AGENT,
        )
        # DRAFT request should set current_tier to next tier up
        assert req.current_tier == Tier.AI  # Agent → AI (next up)


# ---------------------------------------------------------------------------
# SelfGoverningVotingSystem
# ---------------------------------------------------------------------------
class TestSelfGoverningVotingSystem:
    def setup_method(self):
        self.voting = SelfGoverningVotingSystem()

    def test_cast_approve_vote(self):
        record = self.voting.cast_vote(
            request_id="req-1",
            voter_id="voter-a",
            voter_tier=Tier.PRIME,
            vote=Vote.APPROVE,
        )
        assert isinstance(record, VoteRecord)
        assert record.vote == Vote.APPROVE

    def test_cast_bypass_vote(self):
        record = self.voting.cast_vote(
            request_id="req-2",
            voter_id="voter-a",
            voter_tier=Tier.PRIME,
            vote=Vote.BYPASS,
            bypass_reason=BypassReason.TIER_OFFLINE,
            target_tier=Tier.ORCHESTRATOR,
        )
        assert record.vote == Vote.BYPASS
        assert record.bypass_reason == BypassReason.TIER_OFFLINE

    def test_duplicate_vote_rejected(self):
        self.voting.cast_vote(
            request_id="req-3",
            voter_id="voter-a",
            voter_tier=Tier.PRIME,
            vote=Vote.APPROVE,
        )
        try:
            self.voting.cast_vote(
                request_id="req-3",
                voter_id="voter-a",
                voter_tier=Tier.PRIME,
                vote=Vote.REJECT,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "already voted" in str(e)

    def test_orchestrator_cannot_vote(self):
        try:
            self.voting.cast_vote(
                request_id="req-4",
                voter_id="orch-1",
                voter_tier=Tier.ORCHESTRATOR,
                vote=Vote.APPROVE,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "Tier.PRIME and below" in str(e)

    def test_bypass_without_target_rejected(self):
        try:
            self.voting.cast_vote(
                request_id="req-5",
                voter_id="voter-a",
                voter_tier=Tier.PRIME,
                vote=Vote.BYPASS,
            )
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "target_tier" in str(e)

    def test_bypass_from_same_or_higher_tier_rejected(self):
        try:
            self.voting.cast_vote(
                request_id="req-6",
                voter_id="voter-a",
                voter_tier=Tier.AI,
                vote=Vote.BYPASS,
                target_tier=Tier.AGENT,
            )
            assert False, "Should have raised ValueError — AI > AGENT"
        except ValueError as e:
            assert "below" in str(e).lower()

    def test_check_bypass_no_votes(self):
        assert self.voting.check_bypass("nonexistent", UrgencyLevel.ROUTINE) is False

    def test_check_bypass_routine_quorum(self):
        # Need 2 votes for ROUTINE
        self.voting.cast_vote(
            request_id="req-r1",
            voter_id="v1",
            voter_tier=Tier.PRIME,
            vote=Vote.BYPASS,
            target_tier=Tier.ORCHESTRATOR,
            bypass_reason=BypassReason.TIER_OFFLINE,
        )
        assert self.voting.check_bypass("req-r1", UrgencyLevel.ROUTINE) is False  # Only 1 vote

        self.voting.cast_vote(
            request_id="req-r1",
            voter_id="v2",
            voter_tier=Tier.PRIME,
            vote=Vote.BYPASS,
            target_tier=Tier.ORCHESTRATOR,
            bypass_reason=BypassReason.TIER_OFFLINE,
        )
        assert self.voting.check_bypass("req-r1", UrgencyLevel.ROUTINE) is True  # 2 votes = quorum

    def test_check_bypass_urgent_quorum(self):
        # Need 3 votes for URGENT
        self.voting.cast_vote(
            "req-u1", "v1", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        self.voting.cast_vote(
            "req-u1", "v2", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        assert self.voting.check_bypass("req-u1", UrgencyLevel.URGENT) is False  # Only 2

        self.voting.cast_vote(
            "req-u1", "v3", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        assert self.voting.check_bypass("req-u1", UrgencyLevel.URGENT) is True  # 3 = quorum

    def test_check_bypass_critical_not_allowed(self):
        self.voting.cast_vote(
            "req-c1", "v1", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        self.voting.cast_vote(
            "req-c1", "v2", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        self.voting.cast_vote(
            "req-c1", "v3", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        # Even with 3 votes, CRITICAL cannot be bypassed
        assert self.voting.check_bypass("req-c1", UrgencyLevel.CRITICAL) is False

    def test_get_votes(self):
        self.voting.cast_vote("req-gv", "v1", Tier.PRIME, Vote.APPROVE)
        self.voting.cast_vote("req-gv", "v2", Tier.AI, Vote.REJECT)
        votes = self.voting.get_votes("req-gv")
        assert len(votes) == 2

    def test_get_vote_summary(self):
        self.voting.cast_vote("req-vs", "v1", Tier.PRIME, Vote.APPROVE)
        self.voting.cast_vote("req-vs", "v2", Tier.AI, Vote.REJECT)
        self.voting.cast_vote(
            "req-vs", "v3", Tier.PRIME, Vote.BYPASS, target_tier=Tier.ORCHESTRATOR
        )
        summary = self.voting.get_vote_summary("req-vs")
        assert summary["total_votes"] == 3
        assert summary["approve"] == 1
        assert summary["reject"] == 1
        assert summary["bypass"] == 1


# ---------------------------------------------------------------------------
# ChainProtocol
# ---------------------------------------------------------------------------
class TestChainProtocol:
    def setup_method(self):
        self.chain = ChainProtocol()

    def test_submit_request(self):
        req = EnhancementRequest(
            title="Test submit",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
            requester_id="test_ai",
        )
        result = self.chain.submit(req)
        assert result.status != EnhancementStatus.DRAFT
        assert result.request_id == req.request_id

    def test_submit_sets_tier3_review_for_ai_requester(self):
        req = EnhancementRequest(
            title="AI request",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
            requester_tier=Tier.AI,
        )
        result = self.chain.submit(req)
        # AI requester → next tier up is PRIME → TIER2_REVIEW
        assert result.current_tier == Tier.PRIME
        assert result.status == EnhancementStatus.TIER2_REVIEW

    def test_submit_sets_tier2_review_for_prime_requester(self):
        req = EnhancementRequest(
            title="Prime request",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
            requester_tier=Tier.PRIME,
            requester_id="the_dr",
        )
        result = self.chain.submit(req)
        assert result.current_tier == Tier.ORCHESTRATOR
        assert result.status == EnhancementStatus.TIER1_REVIEW

    def test_submit_sets_human_pending_for_orchestrator_requester(self):
        req = EnhancementRequest(
            title="Orch request",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
            requester_tier=Tier.ORCHESTRATOR,
            requester_id="cornelius",
        )
        result = self.chain.submit(req)
        assert result.current_tier == Tier.HUMAN
        assert result.status == EnhancementStatus.HUMAN_PENDING

    def test_approve_at_prime_tier(self):
        req = EnhancementRequest(
            title="Approve test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        # Approve at Prime tier
        result = self.chain.approve(submitted.request_id, "the_dr", Tier.PRIME)
        # Should escalate to Orchestrator
        assert result.current_tier == Tier.ORCHESTRATOR
        assert result.status == EnhancementStatus.TIER1_REVIEW

    def test_approve_at_orchestrator_tier(self):
        req = EnhancementRequest(
            title="Orch approve",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        # Approve at Prime
        self.chain.approve(submitted.request_id, "the_dr", Tier.PRIME)
        # Approve at Orchestrator
        result = self.chain.approve(submitted.request_id, "cornelius", Tier.ORCHESTRATOR)
        # Should escalate to Human
        assert result.status == EnhancementStatus.HUMAN_PENDING

    def test_full_approval_chain(self):
        req = EnhancementRequest(
            title="Full chain",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        # Approve at Prime
        r1 = self.chain.approve(submitted.request_id, "the_dr", Tier.PRIME)
        assert r1.status == EnhancementStatus.TIER1_REVIEW
        # Approve at Orchestrator
        r2 = self.chain.approve(submitted.request_id, "cornelius", Tier.ORCHESTRATOR)
        assert r2.status == EnhancementStatus.HUMAN_PENDING
        # Approve at Human
        r3 = self.chain.approve(submitted.request_id, "human_admin", Tier.HUMAN)
        assert r3.status == EnhancementStatus.APPROVED

    def test_reject(self):
        req = EnhancementRequest(
            title="Reject test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        result = self.chain.reject(
            submitted.request_id, "the_dr", Tier.PRIME, reason="Not justified"
        )
        assert result.status == EnhancementStatus.REJECTED

    def test_approve_wrong_tier_raises(self):
        req = EnhancementRequest(
            title="Wrong tier",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        try:
            # AI tier cannot approve a request at Prime tier
            self.chain.approve(submitted.request_id, "some_ai", Tier.AI)
            assert False, "Should have raised ValueError"
        except ValueError as e:
            assert "cannot approve" in str(e)

    def test_cost_bearing_route_to_dorris(self):
        req = EnhancementRequest(
            title="Cost request",
            justification="Need budget",
            remit="test",
            request_type=EnhancementType.COST_APPROVAL,
            requester_tier=Tier.PRIME,
            requester_id="the_dr",
            cost_estimate=1000.0,
        )
        result = self.chain.submit(req)
        # Should have cost_approval_required metadata
        assert result.metadata.get("cost_approval_required") is True
        assert result.metadata.get("cost_approver") == "dorris"

    def test_security_route_to_guardian(self):
        req = EnhancementRequest(
            title="Security issue",
            justification="Vulnerability",
            remit="security",
            request_type=EnhancementType.SECURITY,
            requester_tier=Tier.AI,
        )
        result = self.chain.submit(req)
        assert result.metadata.get("security_review_required") is True
        assert result.metadata.get("security_reviewer") == "guardian"

    def test_expired_request_at_submission(self):
        req = EnhancementRequest(
            title="Expired",
            justification="Too late",
            remit="test",
            request_type=EnhancementType.FEATURE,
            expires_at=time.time() - 1000,
        )
        result = self.chain.submit(req)
        assert result.status == EnhancementStatus.EXPIRED

    def test_expired_request_during_approval(self):
        req = EnhancementRequest(
            title="Will expire",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        # Manually expire
        self.chain._requests[submitted.request_id].expires_at = time.time() - 1000
        result = self.chain.approve(submitted.request_id, "the_dr", Tier.PRIME)
        assert result.status == EnhancementStatus.EXPIRED

    def test_higher_tier_override(self):
        """A higher tier can approve a request at a lower tier."""
        req = EnhancementRequest(
            title="Override",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        # Human can override and approve at any tier
        result = self.chain.approve(submitted.request_id, "human_admin", Tier.HUMAN)
        assert result.status == EnhancementStatus.APPROVED

    def test_nonexistent_request_raises(self):
        try:
            self.chain.approve("nonexistent-id", "someone", Tier.PRIME)
            assert False, "Should have raised KeyError"
        except KeyError:
            pass


# ---------------------------------------------------------------------------
# ChainProtocol — Voting Integration
# ---------------------------------------------------------------------------
class TestChainVoting:
    def setup_method(self):
        self.chain = ChainProtocol()

    def test_cast_vote_via_chain(self):
        req = EnhancementRequest(
            title="Vote test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        record = self.chain.cast_vote(
            submitted.request_id,
            "the_dr",
            Tier.PRIME,
            Vote.APPROVE,
        )
        assert record.vote == Vote.APPROVE

    def test_bypass_vote_approves(self):
        req = EnhancementRequest(
            title="Bypass test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
            urgency=UrgencyLevel.ROUTINE,
        )
        submitted = self.chain.submit(req)
        # Cast 2 bypass votes (quorum for ROUTINE)
        self.chain.cast_vote(
            submitted.request_id,
            "the_dr",
            Tier.PRIME,
            Vote.BYPASS,
            bypass_reason=BypassReason.TIER_OFFLINE,
            target_tier=Tier.ORCHESTRATOR,
        )
        self.chain.cast_vote(
            submitted.request_id,
            "guardian",
            Tier.PRIME,
            Vote.BYPASS,
            bypass_reason=BypassReason.TIER_OFFLINE,
            target_tier=Tier.ORCHESTRATOR,
        )
        # The request should have been bypassed past Orchestrator to Human
        request = self.chain.get_request(submitted.request_id)
        assert request.current_tier == Tier.HUMAN


# ---------------------------------------------------------------------------
# ChainProtocol — Query Methods
# ---------------------------------------------------------------------------
class TestChainQueries:
    def setup_method(self):
        self.chain = ChainProtocol()

    def test_get_request(self):
        req = EnhancementRequest(
            title="Query test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
        )
        submitted = self.chain.submit(req)
        found = self.chain.get_request(submitted.request_id)
        assert found is not None
        assert found.title == "Query test"

    def test_get_requests_by_status(self):
        req1 = EnhancementRequest(
            title="Active 1",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
        )
        req2 = EnhancementRequest(
            title="Active 2",
            justification="Test",
            remit="test",
            request_type=EnhancementType.REPAIR,
        )
        self.chain.submit(req1)
        self.chain.submit(req2)
        # Both should be in some review status
        active = self.chain.get_requests_by_status(EnhancementStatus.TIER2_REVIEW)
        assert len(active) >= 2

    def test_get_pending_for_tier(self):
        req = EnhancementRequest(
            title="Pending test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        self.chain.submit(req)
        # Should be pending at Prime tier
        pending = self.chain.get_pending_for_tier(Tier.PRIME)
        assert len(pending) >= 1

    def test_get_ledger(self):
        req = EnhancementRequest(
            title="Ledger test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
        )
        submitted = self.chain.submit(req)
        ledger = self.chain.get_ledger(submitted.request_id)
        assert len(ledger) >= 1
        assert ledger[0].action == "submitted"

    def test_get_stats(self):
        req = EnhancementRequest(
            title="Stats test",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
        )
        self.chain.submit(req)
        stats = self.chain.get_stats()
        assert stats["total_requests"] >= 1
        assert stats["pending"] >= 1
        assert isinstance(stats["ledger_entries"], int)


# ---------------------------------------------------------------------------
# ChainProtocol — Tier Status
# ---------------------------------------------------------------------------
class TestTierStatus:
    def setup_method(self):
        self.chain = ChainProtocol()

    def test_set_tier_status(self):
        self.chain.set_tier_status("the_dr", False)
        assert self.chain.is_tier_active("the_dr") is False

    def test_default_tier_active(self):
        assert self.chain.is_tier_active("unknown_entity") is True

    def test_primes_default_active(self):
        chain = create_default_chain()
        assert chain.is_tier_active("cornelius") is True
        assert chain.is_tier_active("the_dr") is True
        assert chain.is_tier_active("dorris") is True
        assert chain.is_tier_active("guardian") is True


# ---------------------------------------------------------------------------
# Factory Functions
# ---------------------------------------------------------------------------
class TestFactoryFunctions:
    def test_create_default_chain(self):
        chain = create_default_chain()
        assert isinstance(chain, ChainProtocol)
        stats = chain.get_stats()
        assert stats["active_entities"] > 0

    def test_get_default_chain_singleton(self):
        chain1 = get_default_chain()
        chain2 = get_default_chain()
        assert chain1 is chain2


# ---------------------------------------------------------------------------
# Enhancement Types and Enums
# ---------------------------------------------------------------------------
class TestEnums:
    def test_enhancement_types(self):
        assert EnhancementType.REPAIR.value == "repair"
        assert EnhancementType.FEATURE.value == "feature"
        assert EnhancementType.SECURITY.value == "security"
        assert EnhancementType.COST_APPROVAL.value == "cost_approval"

    def test_enhancement_statuses(self):
        assert EnhancementStatus.DRAFT.value == "draft"
        assert EnhancementStatus.APPROVED.value == "approved"
        assert EnhancementStatus.REJECTED.value == "rejected"
        assert EnhancementStatus.BYPASSED.value == "bypassed"
        assert EnhancementStatus.HUMAN_PENDING.value == "human_pending"

    def test_urgency_levels(self):
        assert UrgencyLevel.ROUTINE.value == "routine"
        assert UrgencyLevel.CRITICAL.value == "critical"

    def test_votes(self):
        assert Vote.APPROVE.value == "approve"
        assert Vote.BYPASS.value == "bypass"

    def test_bypass_reasons(self):
        assert BypassReason.TIER_OFFLINE.value == "tier_offline"
        assert BypassReason.EMERGENCY_OVERRIDE.value == "emergency_override"


# ---------------------------------------------------------------------------
# The Dr → Dorris → Human Cost Approval Chain
# ---------------------------------------------------------------------------
class TestDrDorrisHumanChain:
    """Test the specific cost approval chain mentioned in the spec:
    The Dr (Development) → Dorris (Commercial) → Human
    """

    def setup_method(self):
        self.chain = ChainProtocol()

    def test_dr_submits_cost_request(self):
        req = EnhancementRequest(
            title="New GPU cluster",
            justification="Training requires GPU acceleration",
            remit="infrastructure",
            request_type=EnhancementType.COST_APPROVAL,
            requester_tier=Tier.PRIME,
            requester_id="the_dr",
            cost_estimate=2500.0,
            cost_currency="USD",
        )
        result = self.chain.submit(req)
        # Should be routed to Dorris for cost approval
        assert result.metadata.get("cost_approver") == "dorris"
        assert result.is_cost_bearing() is True

    def test_dorris_approves_then_human_approves(self):
        req = EnhancementRequest(
            title="Cloud storage upgrade",
            justification="Need more capacity",
            remit="storage",
            request_type=EnhancementType.COST_APPROVAL,
            requester_tier=Tier.AI,
            requester_id="some_ai",
            cost_estimate=500.0,
        )
        submitted = self.chain.submit(req)
        # Request is at Prime tier — Dorris (Prime) can approve
        r1 = self.chain.approve(submitted.request_id, "dorris", Tier.PRIME)
        assert r1.status == EnhancementStatus.TIER1_REVIEW
        # Cornelius (Orchestrator) approves
        r2 = self.chain.approve(submitted.request_id, "cornelius", Tier.ORCHESTRATOR)
        assert r2.status == EnhancementStatus.HUMAN_PENDING
        # Human approves
        r3 = self.chain.approve(submitted.request_id, "human_admin", Tier.HUMAN)
        assert r3.status == EnhancementStatus.APPROVED

    def test_dorris_rejects_cost(self):
        req = EnhancementRequest(
            title="Overpriced feature",
            justification="Not worth it",
            remit="test",
            request_type=EnhancementType.COST_APPROVAL,
            requester_tier=Tier.PRIME,
            requester_id="the_dr",
            cost_estimate=100000.0,
        )
        submitted = self.chain.submit(req)
        result = self.chain.reject(submitted.request_id, "dorris", Tier.PRIME, reason="Over budget")
        assert result.status == EnhancementStatus.REJECTED


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------
class TestEdgeCases:
    def test_human_requester_goes_to_human_pending(self):
        req = EnhancementRequest(
            title="Human request",
            justification="Direct",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.HUMAN,
        )
        result = self.chain.submit(req)
        # Human requester → next tier is HUMAN → HUMAN_PENDING
        assert result.status == EnhancementStatus.HUMAN_PENDING

    def test_bot_requester_escalates_correctly(self):
        req = EnhancementRequest(
            title="Bot request",
            justification="Automated",
            remit="test",
            request_type=EnhancementType.INFRASTRUCTURE,
            requester_tier=Tier.BOT,
        )
        result = self.chain.submit(req)
        # BOT → next tier is AGENT → TIER3_REVIEW
        assert result.current_tier == Tier.AGENT

    def test_cancelled_status(self):
        req = EnhancementRequest(
            title="To cancel",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
        )
        req.status = EnhancementStatus.CANCELLED
        assert req.status == EnhancementStatus.CANCELLED

    def test_approval_chain_recorded(self):
        req = EnhancementRequest(
            title="Chain record",
            justification="Test",
            remit="test",
            request_type=EnhancementType.FEATURE,
            requester_tier=Tier.AI,
        )
        submitted = self.chain.submit(req)
        self.chain.approve(submitted.request_id, "the_dr", Tier.PRIME, reason="Looks good")
        request = self.chain.get_request(submitted.request_id)
        # Check approval chain has entries
        assert len(request.approval_chain) >= 1
        assert request.approval_chain[-1]["action"] == "approved"
        assert request.approval_chain[-1]["actor_id"] == "the_dr"

    def setup_method(self):
        self.chain = ChainProtocol()
