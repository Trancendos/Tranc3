# src/townhall/governance.py
# The Town Hall — governance, policy, and compliance management.
#
# Responsibilities:
#   - Policy registry: named policies (GDPR, UK-GDPR, PRINCE2, ITIL 4, Zero-Cost)
#   - Compliance checks: evaluate platform actions against active policies
#   - Governance events: emit audit events via The Observatory
#   - Policy enforcement hooks: callable from any service layer

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class PolicyStatus(str, Enum):
    ACTIVE   = "active"
    DRAFT    = "draft"
    RETIRED  = "retired"


class ComplianceResult(str, Enum):
    PASS    = "pass"
    WARN    = "warn"
    FAIL    = "fail"
    UNKNOWN = "unknown"


@dataclass
class Policy:
    id: str
    name: str
    framework: str                        # "GDPR", "UK-GDPR", "Zero-Cost", etc.
    description: str = ""
    status: PolicyStatus = PolicyStatus.ACTIVE
    score: float = 1.0                    # 0.0–1.0 current compliance score
    articles: str = ""                    # human-readable article list
    check: Optional[Callable[[Dict[str, Any]], ComplianceResult]] = field(default=None, repr=False)

    def evaluate(self, context: Dict[str, Any]) -> ComplianceResult:
        if self.check is None:
            return ComplianceResult.UNKNOWN
        try:
            return self.check(context)
        except Exception as exc:
            logger.warning("policy %s check error: %s", self.id, exc)
            return ComplianceResult.UNKNOWN


@dataclass
class GovernanceEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    policy_id: str = ""
    result: ComplianceResult = ComplianceResult.UNKNOWN
    actor: Optional[str] = None
    context_summary: str = ""


class TownHall:
    """
    The Town Hall — centralised policy store and governance engine.

    All platform services should route sensitive actions through check()
    so policy violations are surfaced and audited.
    """

    def __init__(self):
        self._policies: Dict[str, Policy] = {}
        self._history: List[GovernanceEvent] = []
        self._register_default_policies()

    # ── Policy management ─────────────────────────────────────────────────────

    def register(self, policy: Policy) -> None:
        self._policies[policy.id] = policy
        logger.debug("townhall: registered policy %s (%s)", policy.id, policy.framework)

    def get(self, policy_id: str) -> Optional[Policy]:
        return self._policies.get(policy_id)

    def active_policies(self) -> List[Policy]:
        return [p for p in self._policies.values() if p.status == PolicyStatus.ACTIVE]

    # ── Compliance checks ─────────────────────────────────────────────────────

    def check(
        self,
        context: Dict[str, Any],
        policy_ids: Optional[List[str]] = None,
        actor: Optional[str] = None,
    ) -> Dict[str, ComplianceResult]:
        """
        Run context against named policies (or all active if policy_ids=None).
        Returns a dict of {policy_id: result}. Emits Observatory events on WARN/FAIL.
        """
        policies = (
            [self._policies[pid] for pid in policy_ids if pid in self._policies]
            if policy_ids
            else self.active_policies()
        )

        results: Dict[str, ComplianceResult] = {}
        for policy in policies:
            result = policy.evaluate(context)
            results[policy.id] = result

            ev = GovernanceEvent(
                policy_id=policy.id,
                result=result,
                actor=actor,
                context_summary=str(context)[:200],
            )
            self._history.append(ev)

            if result in (ComplianceResult.WARN, ComplianceResult.FAIL):
                try:
                    from src.observability.observatory import observe, EventCategory, EventSeverity
                    observe(
                        f"governance.policy.{result.value}",
                        actor=actor,
                        target=f"policy:{policy.id}",
                        category=EventCategory.GOVERNANCE,
                        severity=EventSeverity.WARNING if result == ComplianceResult.WARN else EventSeverity.CRITICAL,
                        service="townhall",
                        outcome=result.value,
                        metadata={"framework": policy.framework, "context": str(context)[:200]},
                    )
                except Exception:
                    pass

        return results

    def overall_score(self) -> float:
        """Return mean compliance score across all active policies."""
        policies = self.active_policies()
        if not policies:
            return 1.0
        return sum(p.score for p in policies) / len(policies)

    def status(self) -> Dict[str, Any]:
        policies = self.active_policies()
        return {
            "policies": len(policies),
            "overall_score": round(self.overall_score(), 4),
            "frameworks": list({p.framework for p in policies}),
            "recent_events": len(self._history),
            "policy_scores": {p.id: p.score for p in policies},
        }

    # ── Default policies ──────────────────────────────────────────────────────

    def _register_default_policies(self) -> None:
        self.register(Policy(
            id="gdpr",
            name="GDPR Compliance",
            framework="GDPR",
            description="EU General Data Protection Regulation",
            score=1.0,
            articles="Art.5,6,13,17,25,32,33,35",
            check=_check_gdpr,
        ))
        self.register(Policy(
            id="uk-gdpr",
            name="UK-GDPR",
            framework="UK-GDPR",
            description="UK GDPR / Data Protection Act 2018",
            score=0.97,
            articles="DPDPD Act 2024 deviations",
        ))
        self.register(Policy(
            id="zero-cost",
            name="Zero-Cost Mandate",
            framework="Zero-Cost",
            description="All services must stay within free tiers",
            score=1.0,
            articles="All services within free tiers",
            check=_check_zero_cost,
        ))
        self.register(Policy(
            id="magna-carta",
            name="Trancendos Magna Carta",
            framework="Magna Carta",
            description="User data ownership and zero lock-in guarantee",
            score=0.95,
            articles="User ownership · Zero lock-in · Right to export",
        ))
        self.register(Policy(
            id="prince2",
            name="PRINCE2 7th Edition",
            framework="PRINCE2 7",
            description="Project management principles",
            score=0.92,
            articles="7 principles · 7 themes · 7 processes",
        ))
        self.register(Policy(
            id="itil4",
            name="ITIL 4",
            framework="ITIL 4",
            description="IT service management best practices",
            score=0.88,
            articles="34 practices · Service Value System",
        ))


# ── Built-in policy checks ────────────────────────────────────────────────────

def _check_gdpr(context: Dict[str, Any]) -> ComplianceResult:
    """Minimal GDPR check: personal data must have a lawful basis."""
    if context.get("personal_data") and not context.get("lawful_basis"):
        return ComplianceResult.FAIL
    if context.get("cross_border_transfer") and not context.get("adequacy_decision"):
        return ComplianceResult.WARN
    return ComplianceResult.PASS


def _check_zero_cost(context: Dict[str, Any]) -> ComplianceResult:
    """Zero-cost check: monthly cost must be 0."""
    cost = context.get("monthly_cost_usd", 0)
    if cost > 0:
        return ComplianceResult.FAIL
    return ComplianceResult.PASS


# ── Module-level singleton ────────────────────────────────────────────────────
_townhall: Optional[TownHall] = None


def get_townhall() -> TownHall:
    global _townhall
    if _townhall is None:
        _townhall = TownHall()
    return _townhall
