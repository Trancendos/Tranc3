"""
shared_core.infinity.hil_a — Human-In-Loop-Action (HIL-A) Chain Protocol Engine
================================================================================
Phase 23 — Tier-by-tier approval escalation with self-governing voting.

The HIL-A protocol formalizes the approval chain for enhancement requests,
repair authorizations, and cost approvals across the Trancendos tier hierarchy:

    Tier 3 (AI) → Tier 2 (Prime) → Tier 1 (Orchestrator) → Tier 0 (Human)

Each request escalates upward through the tier chain. If a higher tier is
non-functional (offline, unresponsive, or disqualified), lower tiers can
vote to bypass it through the Self-Governing Voting System.

Architecture
============

    ┌──────────────────────────────────────────────────────────────────┐
    │                    ChainProtocol Engine                         │
    │                                                                  │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
    │  │ Enhancement   │  │ Escalation   │  │ Self-Governing       │  │
    │  │ Request       │  │ Router       │  │ Voting System        │  │
    │  │ (0-cost model)│  │ (tier chain) │  │ (bypass dead tiers)  │  │
    │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
    │         │                  │                      │              │
    │  ┌──────┴──────────────────┴──────────────────────┴───────────┐  │
    │  │                    Approval Ledger                          │  │
    │  │  (immutable audit trail of all decisions + votes)          │  │
    │  └────────────────────────────────────────────────────────────┘  │
    │                                                                  │
    │  ┌────────────────────────────────────────────────────────────┐  │
    │  │  Prime Integration                                        │  │
    │  │  The Dr → Dorris → Human (cost approval chain)            │  │
    │  │  Guardian → Sentinel Station (security incident chain)    │  │
    │  │  Any Prime → Orchestrator → Human (escalation chain)      │  │
    │  └────────────────────────────────────────────────────────────┘  │
    └──────────────────────────────────────────────────────────────────┘

Usage
-----
    from shared_core.infinity.hil_a import (
        ChainProtocol, EnhancementRequest, UrgencyLevel, EnhancementStatus
    )

    # Create a chain protocol instance
    chain = ChainProtocol()

    # Submit an enhancement request from The Dr (Development Prime)
    request = EnhancementRequest(
        title="Optimize inference pipeline",
        justification="Current latency exceeds 200ms SLA threshold",
        remit="performance_optimization",
        request_type=EnhancementType.REPAIR,
        specs={"target_latency_ms": 100, "current_latency_ms": 250},
        code_changes={"files": ["inference/pipeline.py"], "lines_added": 45, "lines_removed": 12},
        urgency=UrgencyLevel.URGENT,
        requester_tier=Tier.PRIME,
        requester_id="the_dr",
    )

    # Submit and route through the chain
    result = chain.submit(request)
    # → Status: TIER2_REVIEW (escalated to Orchestrator tier)

    # An Orchestrator approves
    result = chain.approve(request.request_id, approver_id="cornelius", tier=Tier.ORCHESTRATOR)
    # → Status: HUMAN_PENDING (requires human approval for cost)

    # Self-governing vote to bypass non-functional tier
    chain.cast_vote(request.request_id, voter_id="the_dr", voter_tier=Tier.PRIME, vote=Vote.BYPASS)
    chain.cast_vote(request.request_id, voter_id="guardian", voter_tier=Tier.PRIME, vote=Vote.BYPASS)
    # → If quorum reached, the non-functional tier is bypassed
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from shared_core.infinity.nomenclature import PRIMES, Tier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EnhancementType(str, Enum):
    """Type of enhancement request."""

    REPAIR = "repair"
    FEATURE = "feature"
    OPTIMIZATION = "optimization"
    SECURITY = "security"
    INFRASTRUCTURE = "infrastructure"
    CONFIGURATION = "configuration"
    COST_APPROVAL = "cost_approval"


class EnhancementStatus(str, Enum):
    """Status of an enhancement request as it moves through the chain."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    TIER3_REVIEW = "tier3_review"  # AI tier review
    TIER2_REVIEW = "tier2_review"  # Prime tier review
    TIER1_REVIEW = "tier1_review"  # Orchestrator tier review
    HUMAN_PENDING = "human_pending"  # Awaiting human (Tier 0) approval
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"  # Moved to next tier
    BYPASSED = "bypassed"  # Tier bypassed via self-governing vote
    EXPIRED = "expired"  # Request timed out
    CANCELLED = "cancelled"


class UrgencyLevel(str, Enum):
    """Urgency level of an enhancement request."""

    ROUTINE = "routine"
    MONTHLY = "monthly"
    URGENT = "urgent"
    CRITICAL = "critical"


class Vote(str, Enum):
    """Vote cast by a tier entity."""

    APPROVE = "approve"
    REJECT = "reject"
    BYPASS = "bypass"  # Vote to bypass a non-functional higher tier
    ABSTAIN = "abstain"


class BypassReason(str, Enum):
    """Reason for bypassing a tier via self-governing vote."""

    TIER_OFFLINE = "tier_offline"
    TIER_UNRESPONSIVE = "tier_unresponsive"
    TIER_DISQUALIFIED = "tier_disqualified"
    TIER_CONFLICT_OF_INTEREST = "tier_conflict_of_interest"
    EMERGENCY_OVERRIDE = "emergency_override"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------


@dataclass
class EnhancementRequest:
    """A request for enhancement, repair, or cost approval.

    The 0-cost model: all requests default to zero cost unless explicitly
    specifying financial impact. Cost-bearing requests require Dorris
    (Commercial Prime) review before reaching Human tier.
    """

    title: str
    justification: str
    remit: str  # Domain/scope of the request
    request_type: EnhancementType
    specs: Dict[str, Any] = field(default_factory=dict)
    code_changes: Dict[str, Any] = field(default_factory=dict)
    urgency: UrgencyLevel = UrgencyLevel.ROUTINE
    requester_tier: Tier = Tier.AI
    requester_id: str = ""
    cost_estimate: float = 0.0  # 0-cost model default
    cost_currency: str = "USD"
    risk_assessment: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: float = field(default_factory=time.time)
    status: EnhancementStatus = EnhancementStatus.DRAFT
    current_tier: Tier = Tier.AI
    approval_chain: List[Dict[str, Any]] = field(default_factory=list)
    expires_at: Optional[float] = None

    def __post_init__(self):
        """Set expiry based on urgency if not explicitly set."""
        if self.expires_at is None:
            ttl = {
                UrgencyLevel.ROUTINE: 7 * 24 * 3600,  # 7 days
                UrgencyLevel.MONTHLY: 3 * 24 * 3600,  # 3 days
                UrgencyLevel.URGENT: 24 * 3600,  # 24 hours
                UrgencyLevel.CRITICAL: 4 * 3600,  # 4 hours
            }
            self.expires_at = self.created_at + ttl.get(self.urgency, 7 * 24 * 3600)

        # Start the current_tier at the tier above the requester
        if self.status == EnhancementStatus.DRAFT:
            self.current_tier = self._next_tier_up(self.requester_tier)

    @staticmethod
    def _next_tier_up(tier: Tier) -> Tier:
        """Return the next tier up in the hierarchy."""
        escalation = {
            Tier.BOT: Tier.AGENT,
            Tier.AGENT: Tier.AI,
            Tier.AI: Tier.PRIME,
            Tier.PRIME: Tier.ORCHESTRATOR,
            Tier.ORCHESTRATOR: Tier.HUMAN,
            Tier.HUMAN: Tier.HUMAN,  # Already at top
        }
        return escalation.get(tier, Tier.HUMAN)

    def is_expired(self) -> bool:
        """Check if the request has expired."""
        if self.expires_at is None:
            return False
        return time.time() > self.expires_at

    def is_cost_bearing(self) -> bool:
        """Check if this request has a non-zero cost estimate."""
        return self.cost_estimate > 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "request_id": self.request_id,
            "title": self.title,
            "justification": self.justification,
            "remit": self.remit,
            "request_type": self.request_type.value,
            "specs": self.specs,
            "code_changes": self.code_changes,
            "urgency": self.urgency.value,
            "requester_tier": int(self.requester_tier),
            "requester_id": self.requester_id,
            "cost_estimate": self.cost_estimate,
            "cost_currency": self.cost_currency,
            "risk_assessment": self.risk_assessment,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "status": self.status.value,
            "current_tier": int(self.current_tier),
            "approval_chain": self.approval_chain,
            "expires_at": self.expires_at,
        }


@dataclass
class ApprovalEntry:
    """An entry in the approval chain ledger."""

    request_id: str
    action: str  # "approved", "rejected", "escalated", "bypassed", "vote"
    actor_id: str
    actor_tier: Tier
    timestamp: float = field(default_factory=time.time)
    reason: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "action": self.action,
            "actor_id": self.actor_id,
            "actor_tier": int(self.actor_tier),
            "timestamp": self.timestamp,
            "reason": self.reason,
            "metadata": self.metadata,
        }


@dataclass
class VoteRecord:
    """A record of a self-governing vote."""

    request_id: str
    voter_id: str
    voter_tier: Tier
    vote: Vote
    bypass_reason: Optional[BypassReason] = None
    target_tier: Optional[Tier] = None  # The tier being voted on for bypass
    timestamp: float = field(default_factory=time.time)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_id": self.request_id,
            "voter_id": self.voter_id,
            "voter_tier": int(self.voter_tier),
            "vote": self.vote.value,
            "bypass_reason": self.bypass_reason.value if self.bypass_reason else None,
            "target_tier": int(self.target_tier) if self.target_tier else None,
            "timestamp": self.timestamp,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Self-Governing Voting System
# ---------------------------------------------------------------------------


class SelfGoverningVotingSystem:
    """Enables lower tiers to vote to bypass non-functional higher tiers.

    Voting Rules:
    - Only entities at Tier.PRIME or below can vote
    - A minimum quorum of 2 votes is required for ROUTINE/MONTHLY urgency
    - A minimum quorum of 3 votes is required for URGENT urgency
    - CRITICAL urgency requires Human approval (no bypass allowed)
    - Only votes from tiers below the target tier count
    - A simple majority (>50%) of eligible votes is required to pass
    - The same entity cannot vote twice on the same request
    - Votes are immutable once cast
    """

    # Minimum votes required by urgency
    QUORUM: Dict[UrgencyLevel, int] = {
        UrgencyLevel.ROUTINE: 2,
        UrgencyLevel.MONTHLY: 2,
        UrgencyLevel.URGENT: 3,
        UrgencyLevel.CRITICAL: -1,  # No bypass allowed
    }

    def __init__(self):
        self._votes: Dict[str, List[VoteRecord]] = {}  # request_id → votes
        self._bypass_results: Dict[str, bool] = {}  # request_id → bypassed

    def cast_vote(
        self,
        request_id: str,
        voter_id: str,
        voter_tier: Tier,
        vote: Vote,
        bypass_reason: Optional[BypassReason] = None,
        target_tier: Optional[Tier] = None,
        reason: str = "",
    ) -> VoteRecord:
        """Cast a vote on a request. Returns the vote record."""
        # Prevent duplicate votes
        if request_id in self._votes:
            for existing in self._votes[request_id]:
                if existing.voter_id == voter_id:
                    raise ValueError(
                        f"Entity '{voter_id}' has already voted on request '{request_id}'",
                    )

        # Validate voter tier (only Prime and below can vote)
        # Note: Lower tier numbers = higher authority. Prime=2, AI=3, Agent=4, Bot=5
        # "Prime and below" means tier value >= Prime.PRIME (i.e., Prime, AI, Agent, Bot)
        if voter_tier.value < Tier.PRIME.value:
            raise ValueError(f"Only Tier.PRIME and below can vote, got Tier.{voter_tier.name}")

        # Validate bypass vote
        if vote == Vote.BYPASS:
            if target_tier is None:
                raise ValueError("BYPASS votes must specify a target_tier")
            # "Below" the target tier means higher tier number (less authority)
            # e.g., Prime (2) is below Orchestrator (1) — Prime CAN vote to bypass Orchestrator
            if voter_tier.value <= target_tier.value:
                raise ValueError(f"Only tiers below Tier.{target_tier.name} can vote to bypass it")

        record = VoteRecord(
            request_id=request_id,
            voter_id=voter_id,
            voter_tier=voter_tier,
            vote=vote,
            bypass_reason=bypass_reason,
            target_tier=target_tier,
            reason=reason,
        )

        if request_id not in self._votes:
            self._votes[request_id] = []
        self._votes[request_id].append(record)

        logger.info(
            "HIL-A vote cast: %s by %s (Tier %s) on %s — %s",
            vote.value,
            voter_id,
            voter_tier.name,
            request_id,
            bypass_reason.value if bypass_reason else "no bypass",
        )

        return record

    def check_bypass(self, request_id: str, urgency: UrgencyLevel) -> bool:
        """Check if a bypass vote has passed for the given request."""
        if urgency == UrgencyLevel.CRITICAL:
            return False  # No bypass for CRITICAL

        if request_id in self._bypass_results:
            return self._bypass_results[request_id]

        votes = self._votes.get(request_id, [])
        bypass_votes = [v for v in votes if v.vote == Vote.BYPASS]

        if not bypass_votes:
            return False

        # Group bypass votes by target tier
        target_tiers: Dict[Tier, List[VoteRecord]] = {}
        for v in bypass_votes:
            if v.target_tier:
                target_tiers.setdefault(v.target_tier, []).append(v)

        quorum = self.QUORUM.get(urgency, 2)

        for target_tier, tier_votes in target_tiers.items():
            if len(tier_votes) >= quorum:
                # Simple majority check among all votes on this request
                approve_count = sum(1 for v in tier_votes if v.vote == Vote.BYPASS)
                reject_count = sum(
                    1 for v in votes if v.vote == Vote.REJECT and v.target_tier == target_tier
                )

                if approve_count > reject_count and approve_count >= quorum:
                    self._bypass_results[request_id] = True
                    logger.info(
                        "HIL-A bypass approved for %s: %d bypass votes (quorum: %d)",
                        request_id,
                        approve_count,
                        quorum,
                    )
                    return True

        return False

    def get_votes(self, request_id: str) -> List[VoteRecord]:
        """Get all votes for a request."""
        return self._votes.get(request_id, [])

    def get_vote_summary(self, request_id: str) -> Dict[str, Any]:
        """Get a summary of votes for a request."""
        votes = self._votes.get(request_id, [])
        return {
            "request_id": request_id,
            "total_votes": len(votes),
            "approve": sum(1 for v in votes if v.vote == Vote.APPROVE),
            "reject": sum(1 for v in votes if v.vote == Vote.REJECT),
            "bypass": sum(1 for v in votes if v.vote == Vote.BYPASS),
            "abstain": sum(1 for v in votes if v.vote == Vote.ABSTAIN),
        }


# ---------------------------------------------------------------------------
# Chain Protocol Engine
# ---------------------------------------------------------------------------


class ChainProtocol:
    """The HIL-A Chain Protocol Engine — routes enhancement requests through
    the tier hierarchy with approval escalation and self-governing voting.

    Escalation Chain:
        Tier 3 (AI) → Tier 2 (Prime) → Tier 1 (Orchestrator) → Tier 0 (Human)

    Cost Approval Chain:
        The Dr (Development) → Dorris (Commercial) → Human

    Security Incident Chain:
        Guardian (Security) → Sentinel Station → Orchestrator → Human
    """

    # Timeout for tier response before allowing bypass votes (seconds)
    TIER_RESPONSE_TIMEOUT: Dict[UrgencyLevel, float] = {
        UrgencyLevel.ROUTINE: 24 * 3600,  # 24 hours
        UrgencyLevel.MONTHLY: 12 * 3600,  # 12 hours
        UrgencyLevel.URGENT: 4 * 3600,  # 4 hours
        UrgencyLevel.CRITICAL: 1 * 3600,  # 1 hour (but bypass not allowed)
    }

    # Tier escalation order (bottom to top)
    ESCALATION_CHAIN: List[Tier] = [
        Tier.BOT,
        Tier.AGENT,
        Tier.AI,
        Tier.PRIME,
        Tier.ORCHESTRATOR,
        Tier.HUMAN,
    ]

    # Special routing: cost-bearing requests must go through Dorris
    COST_APPROVAL_PRIME = "dorris"

    # Special routing: security requests must go through Guardian
    SECURITY_PRIME = "guardian"

    def __init__(self):
        self._requests: Dict[str, EnhancementRequest] = {}
        self._ledger: List[ApprovalEntry] = []
        self._voting = SelfGoverningVotingSystem()
        self._tier_status: Dict[str, bool] = {}  # entity_id → is_active

        # Mark all Primes as active by default
        for prime_id in PRIMES:
            self._tier_status[prime_id] = True

    # -----------------------------------------------------------------------
    # Request Submission
    # -----------------------------------------------------------------------

    def submit(self, request: EnhancementRequest) -> EnhancementRequest:
        """Submit an enhancement request and route it to the appropriate tier."""
        if request.status != EnhancementStatus.DRAFT:
            raise ValueError(f"Can only submit DRAFT requests, got {request.status.value}")

        # Check expiry
        if request.is_expired():
            request.status = EnhancementStatus.EXPIRED
            self._requests[request.request_id] = request
            logger.warning("HIL-A request %s expired at submission", request.request_id)
            return request

        # Determine initial routing tier
        request.current_tier = EnhancementRequest._next_tier_up(request.requester_tier)
        request.status = self._tier_to_status(request.current_tier)

        # Special routing for cost-bearing requests
        if request.is_cost_bearing():
            request = self._route_cost_approval(request)

        # Special routing for security requests
        if request.request_type == EnhancementType.SECURITY:
            request = self._route_security(request)

        # Record in ledger
        self._record(
            request.request_id,
            "submitted",
            request.requester_id,
            request.requester_tier,
            reason=f"Routed to {request.current_tier.name}",
        )

        self._requests[request.request_id] = request
        logger.info(
            "HIL-A request %s submitted: '%s' → %s (urgency: %s)",
            request.request_id,
            request.title,
            request.current_tier.name,
            request.urgency.value,
        )

        return request

    # -----------------------------------------------------------------------
    # Approval / Rejection
    # -----------------------------------------------------------------------

    def approve(
        self,
        request_id: str,
        approver_id: str,
        tier: Tier,
        reason: str = "",
    ) -> EnhancementRequest:
        """Approve a request at the current tier. Escalates to next tier or finalizes."""
        request = self._get_request(request_id)

        if request.is_expired():
            request.status = EnhancementStatus.EXPIRED
            return request

        # Verify the approver is at the correct tier
        if tier != request.current_tier:
            # Allow higher-tier approval (e.g., Human can approve at any tier)
            # Higher tier = lower tier number (Human=0, Orchestrator=1, etc.)
            if tier.value < request.current_tier.value:
                # Higher authority approves — all intermediate tiers are implicitly approved
                request.status = EnhancementStatus.APPROVED
                self._record(
                    request_id,
                    "approved",
                    approver_id,
                    tier,
                    reason=f"Higher authority override: Tier.{tier.name} approved at Tier.{request.current_tier.name}",
                )
                request.approval_chain.append(
                    {
                        "action": "approved",
                        "actor_id": approver_id,
                        "actor_tier": int(tier),
                        "timestamp": time.time(),
                        "reason": reason or "Higher authority override",
                    },
                )
                logger.info(
                    "HIL-A request %s: Higher authority Tier.%s approved (was at Tier.%s)",
                    request_id,
                    tier.name,
                    request.current_tier.name,
                )
                return request
            else:
                raise ValueError(
                    f"Approver at Tier.{tier.name} cannot approve request at "
                    f"Tier.{request.current_tier.name}",
                )

        # Record approval
        self._record(request_id, "approved", approver_id, tier, reason=reason)
        request.approval_chain.append(
            {
                "action": "approved",
                "actor_id": approver_id,
                "actor_tier": int(tier),
                "timestamp": time.time(),
                "reason": reason,
            },
        )

        # Check if this is the final approval tier
        next_tier = EnhancementRequest._next_tier_up(request.current_tier)

        if next_tier == Tier.HUMAN and request.current_tier == Tier.ORCHESTRATOR:
            # Orchestrator approved — escalate to Human
            request.current_tier = Tier.HUMAN
            request.status = EnhancementStatus.HUMAN_PENDING
            logger.info("HIL-A request %s escalated to Human", request_id)
        elif next_tier == Tier.HUMAN and tier == Tier.HUMAN:
            # Human approved — finalized
            request.status = EnhancementStatus.APPROVED
            logger.info("HIL-A request %s fully approved by Human", request_id)
        elif request.current_tier == Tier.HUMAN:
            # Human approval
            request.status = EnhancementStatus.APPROVED
            logger.info("HIL-A request %s approved by Human", request_id)
        else:
            # Escalate to next tier
            request.current_tier = next_tier
            request.status = self._tier_to_status(next_tier)
            request.status = EnhancementStatus.ESCALATED
            # Then update to the review status
            request.status = self._tier_to_status(next_tier)
            logger.info("HIL-A request %s escalated to Tier.%s", request_id, next_tier.name)

        return request

    def reject(
        self,
        request_id: str,
        rejector_id: str,
        tier: Tier,
        reason: str = "",
    ) -> EnhancementRequest:
        """Reject a request at the current tier."""
        request = self._get_request(request_id)

        self._record(request_id, "rejected", rejector_id, tier, reason=reason)
        request.approval_chain.append(
            {
                "action": "rejected",
                "actor_id": rejector_id,
                "actor_tier": int(tier),
                "timestamp": time.time(),
                "reason": reason,
            },
        )
        request.status = EnhancementStatus.REJECTED

        logger.info("HIL-A request %s rejected by %s (Tier %s)", request_id, rejector_id, tier.name)
        return request

    # -----------------------------------------------------------------------
    # Self-Governing Voting
    # -----------------------------------------------------------------------

    def cast_vote(
        self,
        request_id: str,
        voter_id: str,
        voter_tier: Tier,
        vote: Vote,
        bypass_reason: Optional[BypassReason] = None,
        target_tier: Optional[Tier] = None,
        reason: str = "",
    ) -> VoteRecord:
        """Cast a vote on a request through the self-governing system."""
        request = self._get_request(request_id)

        record = self._voting.cast_vote(
            request_id=request_id,
            voter_id=voter_id,
            voter_tier=voter_tier,
            vote=vote,
            bypass_reason=bypass_reason,
            target_tier=target_tier,
            reason=reason,
        )

        # Check if bypass has been approved
        if vote == Vote.BYPASS and self._voting.check_bypass(request_id, request.urgency):
            self._handle_bypass_approved(request, target_tier)

        return record

    def _handle_bypass_approved(self, request: EnhancementRequest, bypassed_tier: Optional[Tier]):
        """Handle a successful bypass vote — skip the non-functional tier."""
        if bypassed_tier is None:
            return

        # Record the bypass in the ledger
        self._record(
            request.request_id,
            "bypassed",
            "self_governing_vote",
            Tier.PRIME,
            reason=f"Tier.{bypassed_tier.name} bypassed via vote",
        )

        # Move past the bypassed tier
        next_tier = EnhancementRequest._next_tier_up(bypassed_tier)
        request.current_tier = next_tier
        request.status = EnhancementStatus.BYPASSED
        # Then update to the new tier's review status
        request.status = self._tier_to_status(next_tier)

        logger.info(
            "HIL-A request %s: Tier.%s bypassed, escalated to Tier.%s",
            request.request_id,
            bypassed_tier.name,
            next_tier.name,
        )

    # -----------------------------------------------------------------------
    # Tier Status Management
    # -----------------------------------------------------------------------

    def set_tier_status(self, entity_id: str, is_active: bool):
        """Set the operational status of a tier entity (Prime, Orchestrator, etc.)."""
        self._tier_status[entity_id] = is_active
        logger.info("HIL-A tier status: %s → %s", entity_id, "active" if is_active else "inactive")

    def is_tier_active(self, entity_id: str) -> bool:
        """Check if a tier entity is active."""
        return self._tier_status.get(entity_id, True)

    # -----------------------------------------------------------------------
    # Query Methods
    # -----------------------------------------------------------------------

    def get_request(self, request_id: str) -> Optional[EnhancementRequest]:
        """Get a request by ID."""
        return self._requests.get(request_id)

    def get_requests_by_status(self, status: EnhancementStatus) -> List[EnhancementRequest]:
        """Get all requests with a given status."""
        return [r for r in self._requests.values() if r.status == status]

    def get_requests_by_requester(self, requester_id: str) -> List[EnhancementRequest]:
        """Get all requests from a specific requester."""
        return [r for r in self._requests.values() if r.requester_id == requester_id]

    def get_pending_for_tier(self, tier: Tier) -> List[EnhancementRequest]:
        """Get all requests pending at a specific tier."""
        return [
            r
            for r in self._requests.values()
            if r.current_tier == tier
            and r.status
            not in (
                EnhancementStatus.APPROVED,
                EnhancementStatus.REJECTED,
                EnhancementStatus.EXPIRED,
                EnhancementStatus.CANCELLED,
            )
        ]

    def get_ledger(self, request_id: Optional[str] = None) -> List[ApprovalEntry]:
        """Get the approval ledger, optionally filtered by request_id."""
        if request_id:
            return [e for e in self._ledger if e.request_id == request_id]
        return list(self._ledger)

    def get_vote_summary(self, request_id: str) -> Dict[str, Any]:
        """Get the vote summary for a request."""
        return self._voting.get_vote_summary(request_id)

    def get_stats(self) -> Dict[str, Any]:
        """Get chain protocol statistics."""
        requests = list(self._requests.values())
        return {
            "total_requests": len(requests),
            "pending": len(
                [
                    r
                    for r in requests
                    if r.status
                    not in (
                        EnhancementStatus.APPROVED,
                        EnhancementStatus.REJECTED,
                        EnhancementStatus.EXPIRED,
                        EnhancementStatus.CANCELLED,
                    )
                ],
            ),
            "approved": len([r for r in requests if r.status == EnhancementStatus.APPROVED]),
            "rejected": len([r for r in requests if r.status == EnhancementStatus.REJECTED]),
            "bypassed": len([r for r in requests if r.status == EnhancementStatus.BYPASSED]),
            "expired": len([r for r in requests if r.status == EnhancementStatus.EXPIRED]),
            "ledger_entries": len(self._ledger),
            "active_entities": sum(1 for v in self._tier_status.values() if v),
            "inactive_entities": sum(1 for v in self._tier_status.values() if not v),
        }

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _get_request(self, request_id: str) -> EnhancementRequest:
        """Get a request or raise KeyError."""
        request = self._requests.get(request_id)
        if request is None:
            raise KeyError(f"Request '{request_id}' not found")
        return request

    def _record(
        self,
        request_id: str,
        action: str,
        actor_id: str,
        actor_tier: Tier,
        reason: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Record an entry in the approval ledger."""
        entry = ApprovalEntry(
            request_id=request_id,
            action=action,
            actor_id=actor_id,
            actor_tier=actor_tier,
            reason=reason,
            metadata=metadata or {},
        )
        self._ledger.append(entry)

    @staticmethod
    def _tier_to_status(tier: Tier) -> EnhancementStatus:
        """Map a tier to its corresponding review status."""
        mapping = {
            Tier.BOT: EnhancementStatus.TIER3_REVIEW,
            Tier.AGENT: EnhancementStatus.TIER3_REVIEW,
            Tier.AI: EnhancementStatus.TIER3_REVIEW,
            Tier.PRIME: EnhancementStatus.TIER2_REVIEW,
            Tier.ORCHESTRATOR: EnhancementStatus.TIER1_REVIEW,
            Tier.HUMAN: EnhancementStatus.HUMAN_PENDING,
        }
        return mapping.get(tier, EnhancementStatus.SUBMITTED)

    def _route_cost_approval(self, request: EnhancementRequest) -> EnhancementRequest:
        """Route cost-bearing requests through Dorris (Commercial Prime)."""
        request.metadata["cost_approval_required"] = True
        request.metadata["cost_approver"] = self.COST_APPROVAL_PRIME

        # If the request isn't already routed to Prime tier, redirect it
        if request.current_tier.value > Tier.PRIME.value:
            request.current_tier = Tier.PRIME
            request.metadata["cost_routing"] = "redirected_to_dorris"

        return request

    def _route_security(self, request: EnhancementRequest) -> EnhancementRequest:
        """Route security requests through Guardian (Security Prime)."""
        request.metadata["security_review_required"] = True
        request.metadata["security_reviewer"] = self.SECURITY_PRIME

        return request


# ---------------------------------------------------------------------------
# Pre-configured Chain Instances
# ---------------------------------------------------------------------------


def create_default_chain() -> ChainProtocol:
    """Create a ChainProtocol with default Prime statuses from nomenclature."""
    chain = ChainProtocol()
    for prime_id, _prime in PRIMES.items():
        chain.set_tier_status(prime_id, True)
    return chain


# Module-level singleton
_default_chain: Optional[ChainProtocol] = None


def get_default_chain() -> ChainProtocol:
    """Get the default module-level ChainProtocol singleton."""
    global _default_chain
    if _default_chain is None:
        _default_chain = create_default_chain()
    return _default_chain
