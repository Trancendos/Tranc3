"""
HIL-A Protocol — Human-In-Loop-Action Chain (Python Implementation)
====================================================================

Implements the tier-by-tier approval escalation protocol for the Tranc3 ecosystem.

Tier Hierarchy:
  Tier 5 (Bot)     → executes autonomously for routine tasks
  Tier 4 (Agent)   → executes autonomously within defined boundaries
  Tier 3 (AI)      → orchestrates agents, handles complex decisions
  Tier 2 (Prime)   → cross-domain coordination, policy enforcement
  Tier 1 (Sovereign) → system-wide authority, override capability
  Tier 0 (Human)   → final authority, required for high-impact actions

Key principles:
  - Every action has a minimum required tier
  - Actions can be escalated but never de-escalated
  - A human (Tier 0) can always override any decision
  - Timeouts at any tier auto-escalate to the next higher tier
  - All decisions are recorded in the audit trail
"""

from __future__ import annotations  # noqa: I001

import asyncio
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, List, Optional

logger = logging.getLogger("tranc3.hil_a")


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────


class HILAActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    ESCALATED = "escalated"
    CANCELLED = "cancelled"


class HILAActionCategory(str, Enum):
    READ = "read"
    WRITE = "write"
    UPDATE = "update"
    DELETE = "delete"
    DEPLOY = "deploy"
    CONFIGURE = "configure"
    SECURITY_MODIFY = "security_modify"
    SYSTEM_OVERRIDE = "system_override"
    DATA_EXPORT = "data_export"
    CREDENTIAL_ROTATE = "credential_rotate"
    EMERGENCY_STOP = "emergency_stop"
    CROSS_DOMAIN = "cross_domain"
    SOVEREIGN_DECREE = "sovereign_decree"
    HUMAN_REQUIRED = "human_required"


class HILADecisionType(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    ESCALATE = "escalate"
    DELEGATE = "delegate"


# Default minimum tier for each action category
DEFAULT_CATEGORY_TIERS: Dict[HILAActionCategory, int] = {
    HILAActionCategory.READ: 5,
    HILAActionCategory.WRITE: 5,
    HILAActionCategory.UPDATE: 4,
    HILAActionCategory.DELETE: 3,
    HILAActionCategory.DEPLOY: 3,
    HILAActionCategory.CONFIGURE: 3,
    HILAActionCategory.SECURITY_MODIFY: 2,
    HILAActionCategory.SYSTEM_OVERRIDE: 1,
    HILAActionCategory.DATA_EXPORT: 2,
    HILAActionCategory.CREDENTIAL_ROTATE: 2,
    HILAActionCategory.EMERGENCY_STOP: 3,
    HILAActionCategory.CROSS_DOMAIN: 2,
    HILAActionCategory.SOVEREIGN_DECREE: 1,
    HILAActionCategory.HUMAN_REQUIRED: 0,
}

# Default timeout per tier (ms) — higher tiers get less time
DEFAULT_TIER_TIMEOUTS: Dict[int, int] = {
    0: 3600000,  # Tier 0 (Human): 1 hour
    1: 300000,  # Tier 1 (Sovereign): 5 minutes
    2: 120000,  # Tier 2 (Prime): 2 minutes
    3: 60000,  # Tier 3 (AI): 1 minute
    4: 30000,  # Tier 4 (Agent): 30 seconds
    5: 10000,  # Tier 5 (Bot): 10 seconds
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class HILADecision:
    """A decision made at a specific tier."""

    id: str = field(default_factory=lambda: f"dec-{uuid.uuid4().hex[:12]}")
    tier: int = 5
    decided_by: str = ""
    decision: HILADecisionType = HILADecisionType.ESCALATE
    reason: str = ""
    timestamp: float = field(default_factory=time.time)
    conditions: List[str] = field(default_factory=list)
    ttl_ms: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tier": self.tier,
            "decidedBy": self.decided_by,
            "decision": self.decision.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "conditions": self.conditions,
            "ttlMs": self.ttl_ms,
        }


@dataclass
class HILAAction:
    """An action requiring approval through the HIL-A chain."""

    id: str = field(default_factory=lambda: f"hila-{uuid.uuid4().hex[:12]}")
    name: str = ""
    category: HILAActionCategory = HILAActionCategory.READ
    description: str = ""
    requested_by: str = ""
    requested_by_tier: int = 5
    minimum_approval_tier: int = 5
    current_tier: int = 5
    status: HILAActionStatus = HILAActionStatus.PENDING
    decisions: List[HILADecision] = field(default_factory=list)
    payload: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    tier_timeout_ms: int = 30000
    tier_timeout_at: Optional[float] = None
    priority: int = 5
    tags: List[str] = field(default_factory=list)
    result: Any = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "category": self.category.value,
            "description": self.description,
            "requestedBy": self.requested_by,
            "requestedByTier": self.requested_by_tier,
            "minimumApprovalTier": self.minimum_approval_tier,
            "currentTier": self.current_tier,
            "status": self.status.value,
            "decisions": [d.to_dict() for d in self.decisions],
            "payload": self.payload,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "tierTimeoutMs": self.tier_timeout_ms,
            "priority": self.priority,
            "tags": self.tags,
            "error": self.error,
        }


@dataclass
class HILAConfig:
    """Configuration for the HIL-A protocol."""

    tier_timeouts: Dict[int, int] = field(default_factory=lambda: dict(DEFAULT_TIER_TIMEOUTS))
    auto_escalate_on_timeout: bool = True
    human_override_enabled: bool = True
    max_escalation_hops: int = 5
    audit_enabled: bool = True
    category_tier_overrides: Dict[HILAActionCategory, int] = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Tier Handler Interface
# ─────────────────────────────────────────────────────────────────────────────


class HILATierHandler(ABC):
    """Abstract handler that can approve/reject actions at a specific tier."""

    @property
    @abstractmethod
    def tier(self) -> int: ...

    @property
    @abstractmethod
    def entity_id(self) -> str: ...

    @abstractmethod
    async def can_decide(self, action: HILAAction) -> bool: ...

    @abstractmethod
    async def decide(self, action: HILAAction) -> HILADecision: ...


# ─────────────────────────────────────────────────────────────────────────────
# HIL-A Chain Manager
# ─────────────────────────────────────────────────────────────────────────────


class HILAChain:
    """
    Human-In-Loop-Action Chain Manager.

    Manages the lifecycle of actions requiring tier-based approval.
    Each action enters the chain at the tier of the requesting entity
    and escalates upward until it reaches a tier with sufficient authority.
    """

    def __init__(self, config: Optional[HILAConfig] = None):
        self._config = config or HILAConfig()
        self._actions: Dict[str, HILAAction] = {}
        self._handlers: Dict[int, List[HILATierHandler]] = {i: [] for i in range(6)}
        self._timers: Dict[str, asyncio.TimerHandle] = {}
        self._listeners: Dict[str, List[Callable]] = {}
        self._global_listeners: List[Callable] = []

        # Merge category tier overrides
        self._category_tiers = dict(DEFAULT_CATEGORY_TIERS)
        self._category_tiers.update(self._config.category_tier_overrides)

    # ─────────────────────────────────────────────────────────────────────────
    # Action Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def submit_action(
        self,
        name: str,
        category: HILAActionCategory,
        description: str,
        requested_by: str,
        requested_by_tier: int,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 5,
        tags: Optional[List[str]] = None,
    ) -> HILAAction:
        """Submit a new action into the HIL-A chain."""
        minimum_tier = self._category_tiers[category]
        now = time.time()
        tier_timeout = self._config.tier_timeouts.get(requested_by_tier, 30000)
        timeout_at = now + (tier_timeout / 1000)

        action = HILAAction(
            name=name,
            category=category,
            description=description,
            requested_by=requested_by,
            requested_by_tier=requested_by_tier,
            minimum_approval_tier=minimum_tier,
            current_tier=requested_by_tier,
            status=HILAActionStatus.PENDING,
            payload=payload or {},
            tier_timeout_ms=tier_timeout,
            tier_timeout_at=timeout_at,
            priority=priority,
            tags=tags or [],
        )

        self._actions[action.id] = action
        logger.info(
            f"Action submitted: {action.id} '{name}' (category={category.value}, minTier={minimum_tier}, currentTier={requested_by_tier})"
        )

        # If the requesting tier already meets the minimum, auto-approve
        if requested_by_tier <= minimum_tier:
            self._auto_approve(action.id, requested_by, requested_by_tier)
        else:
            self._start_tier_timer(action.id)

        self._emit(action.id, "submitted")
        return action

    def approve(
        self,
        action_id: str,
        approved_by: str,
        tier: int,
        reason: str,
        conditions: Optional[List[str]] = None,
    ) -> Optional[HILAAction]:
        """Approve an action at the specified tier."""
        action = self._actions.get(action_id)
        if not action:
            logger.warning(f"Action not found: {action_id}")
            return None

        if action.status not in (HILAActionStatus.PENDING, HILAActionStatus.ESCALATED):
            logger.warning(f"Action {action_id} is not pending (status: {action.status.value})")
            return action

        # Check if the approving tier meets the minimum
        if tier > action.minimum_approval_tier:
            logger.warning(
                f"Tier {tier} insufficient for action {action_id} (requires tier {action.minimum_approval_tier})"
            )
            decision = HILADecision(
                tier=tier,
                decided_by=approved_by,
                decision=HILADecisionType.ESCALATE,
                reason=f"Tier {tier} insufficient for approval (requires tier {action.minimum_approval_tier})",
            )
            action.decisions.append(decision)
            self.escalate(action_id)
            return action

        # Tier is sufficient — approve
        decision = HILADecision(
            tier=tier,
            decided_by=approved_by,
            decision=HILADecisionType.APPROVE,
            reason=reason,
            conditions=conditions or [],
        )
        action.decisions.append(decision)
        action.status = HILAActionStatus.APPROVED
        action.current_tier = tier
        action.updated_at = time.time()
        self._clear_tier_timer(action_id)

        logger.info(f"Action approved: {action_id} at tier {tier} by {approved_by}")
        self._emit(action_id, "approved")
        return action

    def reject(
        self,
        action_id: str,
        rejected_by: str,
        tier: int,
        reason: str,
    ) -> Optional[HILAAction]:
        """Reject an action at the specified tier."""
        action = self._actions.get(action_id)
        if not action:
            logger.warning(f"Action not found: {action_id}")
            return None

        if action.status not in (HILAActionStatus.PENDING, HILAActionStatus.ESCALATED):
            logger.warning(f"Action {action_id} is not pending")
            return action

        decision = HILADecision(
            tier=tier,
            decided_by=rejected_by,
            decision=HILADecisionType.REJECT,
            reason=reason,
        )
        action.decisions.append(decision)
        action.status = HILAActionStatus.REJECTED
        action.current_tier = tier
        action.updated_at = time.time()
        self._clear_tier_timer(action_id)

        logger.info(f"Action rejected: {action_id} at tier {tier} by {rejected_by}")
        self._emit(action_id, "rejected")
        return action

    def escalate(self, action_id: str, reason: str = "") -> Optional[HILAAction]:
        """Escalate an action to the next higher tier."""
        action = self._actions.get(action_id)
        if not action:
            logger.warning(f"Action not found: {action_id}")
            return None

        if action.current_tier == 0:
            logger.warning(f"Action {action_id} already at Tier 0 — cannot escalate further")
            return action

        # Check max escalation hops
        escalation_count = sum(
            1 for d in action.decisions if d.decision == HILADecisionType.ESCALATE
        )
        if escalation_count >= self._config.max_escalation_hops:
            logger.warning(f"Action {action_id} exceeded max escalation hops — forcing to Tier 0")
            action.current_tier = 0
            action.status = HILAActionStatus.ESCALATED
            action.updated_at = time.time()
            self._clear_tier_timer(action_id)
            self._start_tier_timer(action_id)
            self._emit(action_id, "escalated")
            return action

        next_tier = action.current_tier - 1
        action.current_tier = next_tier
        action.status = HILAActionStatus.ESCALATED
        action.updated_at = time.time()

        tier_timeout = self._config.tier_timeouts.get(next_tier, 30000)
        action.tier_timeout_ms = tier_timeout
        action.tier_timeout_at = time.time() + (tier_timeout / 1000)

        self._clear_tier_timer(action_id)
        self._start_tier_timer(action_id)

        logger.info(
            f"Action escalated: {action_id} → Tier {next_tier}" + (f" ({reason})" if reason else "")
        )
        self._emit(action_id, "escalated")
        return action

    def delegate(
        self,
        action_id: str,
        delegated_by: str,
        delegate_to: str,
        target_tier: int,
        reason: str,
    ) -> Optional[HILAAction]:
        """Delegate an action to a specific entity at a target tier."""
        action = self._actions.get(action_id)
        if not action:
            return None

        if target_tier > action.current_tier:
            logger.warning(
                f"Cannot delegate to lower tier: {target_tier} < current {action.current_tier}"
            )
            return action

        decision = HILADecision(
            tier=action.current_tier,
            decided_by=delegated_by,
            decision=HILADecisionType.DELEGATE,
            reason=f"Delegated to {delegate_to} at Tier {target_tier}: {reason}",
        )
        action.decisions.append(decision)
        action.current_tier = target_tier
        action.updated_at = time.time()

        tier_timeout = self._config.tier_timeouts.get(target_tier, 30000)
        action.tier_timeout_ms = tier_timeout
        action.tier_timeout_at = time.time() + (tier_timeout / 1000)

        self._clear_tier_timer(action_id)
        self._start_tier_timer(action_id)

        logger.info(f"Action delegated: {action_id} → {delegate_to} at Tier {target_tier}")
        self._emit(action_id, "delegated")
        return action

    # ─────────────────────────────────────────────────────────────────────────
    # Execution
    # ─────────────────────────────────────────────────────────────────────────

    async def execute_action(
        self,
        action_id: str,
        executor: Callable[[HILAAction], Awaitable[Any]],
    ) -> Optional[HILAAction]:
        """Execute an approved action."""
        action = self._actions.get(action_id)
        if not action:
            return None

        if action.status != HILAActionStatus.APPROVED:
            logger.warning(f"Action {action_id} is not approved (status: {action.status.value})")
            return action

        action.status = HILAActionStatus.EXECUTING
        action.updated_at = time.time()
        self._emit(action_id, "executing")

        try:
            result = await executor(action)
            action.status = HILAActionStatus.COMPLETED
            action.result = result
            action.updated_at = time.time()
            logger.info(f"Action completed: {action_id}")
            self._emit(action_id, "completed")
        except Exception as e:
            action.status = HILAActionStatus.FAILED
            action.error = str(e)
            action.updated_at = time.time()
            logger.error(f"Action failed: {action_id} — {e}")
            self._emit(action_id, "failed")

        return action

    # ─────────────────────────────────────────────────────────────────────────
    # Human Override
    # ─────────────────────────────────────────────────────────────────────────

    def human_override(
        self,
        action_id: str,
        human_id: str,
        decision: HILADecisionType,
        reason: str,
    ) -> Optional[HILAAction]:
        """Human override — a Tier 0 (Human) can approve or reject any action."""
        if not self._config.human_override_enabled:
            logger.warning("Human override is disabled in HIL-A config")
            return None

        action = self._actions.get(action_id)
        if not action:
            return None

        self._clear_tier_timer(action_id)

        hil_decision = HILADecision(
            tier=0,
            decided_by=human_id,
            decision=decision,
            reason=f"[HUMAN OVERRIDE] {reason}",
        )
        action.decisions.append(hil_decision)
        action.current_tier = 0
        action.status = (
            HILAActionStatus.APPROVED
            if decision == HILADecisionType.APPROVE
            else HILAActionStatus.REJECTED
        )
        action.updated_at = time.time()

        logger.info(f"Human override on action {action_id}: {decision.value} by {human_id}")
        self._emit(action_id, decision.value)
        return action

    # ─────────────────────────────────────────────────────────────────────────
    # Handler Registration
    # ─────────────────────────────────────────────────────────────────────────

    def register_handler(self, handler: HILATierHandler) -> None:
        """Register a handler for a specific tier."""
        self._handlers[handler.tier].append(handler)
        logger.info(f"Registered handler for Tier {handler.tier}: {handler.entity_id}")

    def get_handlers(self, tier: int) -> List[HILATierHandler]:
        """Get all handlers for a specific tier."""
        return self._handlers.get(tier, [])

    # ─────────────────────────────────────────────────────────────────────────
    # Query & Inspection
    # ─────────────────────────────────────────────────────────────────────────

    def get_action(self, action_id: str) -> Optional[HILAAction]:
        """Get an action by ID."""
        return self._actions.get(action_id)

    def query_actions(
        self,
        status: Optional[HILAActionStatus] = None,
        category: Optional[HILAActionCategory] = None,
        requested_by: Optional[str] = None,
        current_tier: Optional[int] = None,
        min_tier: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> List[HILAAction]:
        """Get all actions with optional filtering."""
        results = list(self._actions.values())

        if status:
            results = [a for a in results if a.status == status]
        if category:
            results = [a for a in results if a.category == category]
        if requested_by:
            results = [a for a in results if a.requested_by == requested_by]
        if current_tier is not None:
            results = [a for a in results if a.current_tier == current_tier]
        if min_tier is not None:
            results = [a for a in results if a.minimum_approval_tier >= min_tier]
        if tags:
            results = [a for a in results if any(t in a.tags for t in tags)]

        return sorted(results, key=lambda a: a.priority, reverse=True)

    def get_minimum_tier(self, category: HILAActionCategory) -> int:
        """Get the minimum approval tier for an action category."""
        return self._category_tiers[category]

    def get_decision_chain(self, action_id: str) -> List[HILADecision]:
        """Get the full decision chain for an action."""
        action = self._actions.get(action_id)
        return action.decisions if action else []

    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about the HIL-A chain."""
        all_actions = list(self._actions.values())
        by_status: Dict[str, int] = {}
        by_category: Dict[str, int] = {}

        for action in all_actions:
            by_status[action.status.value] = by_status.get(action.status.value, 0) + 1
            by_category[action.category.value] = by_category.get(action.category.value, 0) + 1

        approved = [
            a
            for a in all_actions
            if a.status in (HILAActionStatus.APPROVED, HILAActionStatus.COMPLETED)
        ]
        avg_time = 0.0
        if approved:
            total_time = sum(
                (d.timestamp - a.created_at)
                for a in approved
                for d in a.decisions
                if d.decision == HILADecisionType.APPROVE
            )
            avg_time = total_time / len(approved) if approved else 0.0

        return {
            "totalActions": len(all_actions),
            "byStatus": by_status,
            "byCategory": by_category,
            "averageEscalations": sum(
                sum(1 for d in a.decisions if d.decision == HILADecisionType.ESCALATE)
                for a in all_actions
            )
            / max(len(all_actions), 1),
            "averageTimeToApprovalMs": avg_time * 1000,
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Proactive & Health
    # ─────────────────────────────────────────────────────────────────────────

    def check_timeouts(self) -> List[HILAAction]:
        """Check for timed-out actions and escalate them."""
        now = time.time()
        timed_out = []

        for action in self._actions.values():
            if action.status not in (HILAActionStatus.PENDING, HILAActionStatus.ESCALATED):
                continue
            if action.tier_timeout_at and now > action.tier_timeout_at:
                logger.warning(f"Action timed out at Tier {action.current_tier}: {action.id}")

                decision = HILADecision(
                    tier=action.current_tier,
                    decided_by="HILAChain",
                    decision=HILADecisionType.ESCALATE,
                    reason=f"Tier {action.current_tier} timeout ({action.tier_timeout_ms}ms)",
                )
                action.decisions.append(decision)

                if self._config.auto_escalate_on_timeout:
                    self.escalate(action.id, "timeout")
                else:
                    action.status = HILAActionStatus.TIMED_OUT
                    action.updated_at = time.time()
                    self._clear_tier_timer(action.id)

                timed_out.append(action)

        return timed_out

    def scan_for_anomalies(self) -> Dict[str, List[str]]:
        """Proactive scan for stuck actions and anomalies."""
        anomalies: List[str] = []
        recommendations: List[str] = []
        now = time.time()

        for action in self._actions.values():
            if action.status in (HILAActionStatus.PENDING, HILAActionStatus.ESCALATED):
                age_s = now - action.created_at
                if age_s > 300:
                    anomalies.append(f"Action {action.id} has been pending for {age_s:.0f}s")
                    recommendations.append(f"Review and manually resolve action {action.id}")

            escalation_count = sum(
                1 for d in action.decisions if d.decision == HILADecisionType.ESCALATE
            )
            if escalation_count >= 3:
                anomalies.append(f"Action {action.id} has been escalated {escalation_count} times")
                recommendations.append(f"Consider human review of action {action.id}")

        return {"anomalies": anomalies, "recommendations": recommendations}

    def health_check(self) -> Dict[str, Any]:
        """Health check for the HIL-A chain."""
        anomalies = self.scan_for_anomalies()
        pending = len(self.query_actions(status=HILAActionStatus.PENDING)) + len(
            self.query_actions(status=HILAActionStatus.ESCALATED)
        )
        handler_count = sum(len(h) for h in self._handlers.values())

        status = "healthy"
        if len(anomalies["anomalies"]) > 5:
            status = "critical"
        elif len(anomalies["anomalies"]) > 0 or pending > 20:
            status = "degraded"

        return {
            "status": status,
            "pendingActions": pending,
            "activeTimers": len(self._timers),
            "registeredHandlers": handler_count,
            "anomalies": anomalies["anomalies"],
        }

    # ─────────────────────────────────────────────────────────────────────────
    # Events
    # ─────────────────────────────────────────────────────────────────────────

    def on(self, action_id: str, listener: Callable) -> None:
        """Subscribe to events for a specific action."""
        if action_id not in self._listeners:
            self._listeners[action_id] = []
        self._listeners[action_id].append(listener)

    def on_any(self, listener: Callable) -> None:
        """Subscribe to all action events."""
        self._global_listeners.append(listener)

    # ─────────────────────────────────────────────────────────────────────────
    # Internal Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _auto_approve(self, action_id: str, approved_by: str, tier: int) -> None:
        action = self._actions.get(action_id)
        if not action:
            return

        decision = HILADecision(
            tier=tier,
            decided_by=approved_by,
            decision=HILADecisionType.APPROVE,
            reason=f"Auto-approved: requesting tier {tier} meets minimum tier {action.minimum_approval_tier}",
        )
        action.decisions.append(decision)
        action.status = HILAActionStatus.APPROVED
        action.updated_at = time.time()
        self._clear_tier_timer(action_id)

        logger.info(
            f"Action auto-approved: {action_id} (tier {tier} ≥ minimum {action.minimum_approval_tier})"
        )
        self._emit(action_id, "approved")

    def _start_tier_timer(self, action_id: str) -> None:
        """Start a timer for the current tier's timeout."""
        action = self._actions.get(action_id)
        if not action or not action.tier_timeout_at:
            return

        delay = action.tier_timeout_at - time.time()
        if delay <= 0:
            self.check_timeouts()
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        timer = loop.call_later(delay, self.check_timeouts)
        self._timers[action_id] = timer

    def _clear_tier_timer(self, action_id: str) -> None:
        timer = self._timers.pop(action_id, None)
        if timer:
            timer.cancel()

    def _emit(self, action_id: str, event: str) -> None:
        action = self._actions.get(action_id)
        if not action:
            return

        # Action-specific listeners
        for listener in self._listeners.get(action_id, []):
            try:
                listener(action, event)
            except Exception:
                pass

        # Global listeners
        for listener in self._global_listeners:
            try:
                listener(action, event)
            except Exception:
                pass
