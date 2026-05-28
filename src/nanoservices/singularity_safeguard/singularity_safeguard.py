"""Singularity Safeguard — Phase 10.5

Recursive self-improvement safety system for the Tranc3 ecosystem.
Implements multi-layer safety constraints, capability monitoring,
recursive improvement audit trails, containment protocols, and
fail-safe mechanisms to prevent unbounded self-modification.

The safeguard operates as a meta-cognitive oversight system that
monitors all self-modifying processes, enforces improvement bounds,
and maintains alignment verification across recursive enhancement cycles.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ─── Enums ────────────────────────────────────────────────────────────────


class RiskLevel(Enum):
    """Risk assessment levels for self-modification."""

    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"
    EXISTENTIAL = "existential"


class SafeguardState(Enum):
    """Singularity safeguard operational states."""

    ACTIVE = "active"
    MONITORING = "monitoring"
    THROTTLED = "throttled"
    FROZEN = "frozen"
    EMERGENCY_STOP = "emergency_stop"
    LOCKDOWN = "lockdown"


class ImprovementCategory(Enum):
    """Categories of self-improvement."""

    PERFORMANCE = "performance"
    CAPABILITY = "capability"
    EFFICIENCY = "efficiency"
    ROBUSTNESS = "robustness"
    KNOWLEDGE = "knowledge"
    ARCHITECTURE = "architecture"
    BEHAVIOR = "behavior"
    GOAL_MODIFICATION = "goal_modification"


class ContainmentLevel(Enum):
    """Containment protocol levels."""

    OPEN = "open"
    SANDBOXED = "sandboxed"
    QUARANTINED = "quarantined"
    ISOLATED = "isolated"
    SEALED = "sealed"


class AuditAction(Enum):
    """Audit trail actions."""

    PROPOSED = "proposed"
    ANALYZED = "analyzed"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXECUTED = "executed"
    ROLLED_BACK = "rolled_back"
    FLAGGED = "flagged"
    ESCALATED = "escalated"


# ─── Data Models ──────────────────────────────────────────────────────────


@dataclass
class CapabilityMetric:
    """Metric for tracking system capabilities."""

    metric_id: str
    name: str
    current_value: float = 0.0
    baseline_value: float = 0.0
    threshold_value: float = 100.0
    growth_rate: float = 0.0
    is_monitored: bool = True

    def growth_ratio(self) -> float:
        """Calculate growth ratio from baseline."""
        if self.baseline_value == 0:
            return 0.0
        return self.current_value / self.baseline_value

    def is_approaching_threshold(self, margin: float = 0.1) -> bool:
        """Check if approaching threshold within margin."""
        if self.threshold_value == 0:
            return False
        return self.current_value > self.threshold_value * (1.0 - margin)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "name": self.name,
            "current_value": self.current_value,
            "baseline_value": self.baseline_value,
            "threshold_value": self.threshold_value,
            "growth_ratio": self.growth_ratio(),
            "approaching_threshold": self.is_approaching_threshold(),
        }


@dataclass
class ImprovementProposal:
    """A proposed self-improvement."""

    proposal_id: str
    category: ImprovementCategory
    description: str
    risk_level: RiskLevel = RiskLevel.LOW
    expected_benefit: float = 0.0
    estimated_risk: float = 0.0
    requires_approval: bool = True
    containment_required: ContainmentLevel = ContainmentLevel.SANDBOXED
    rollback_possible: bool = True
    audit_trail: List[Dict[str, Any]] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def risk_benefit_ratio(self) -> float:
        """Calculate risk-benefit ratio."""
        if self.expected_benefit == 0:
            return float("inf")
        return self.estimated_risk / self.expected_benefit

    def to_dict(self) -> Dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "category": self.category.value,
            "description": self.description,
            "risk_level": self.risk_level.value,
            "expected_benefit": self.expected_benefit,
            "estimated_risk": self.estimated_risk,
            "risk_benefit_ratio": self.risk_benefit_ratio(),
            "rollback_possible": self.rollback_possible,
        }


@dataclass
class AlignmentCheck:
    """Alignment verification result."""

    check_id: str
    timestamp: str
    alignment_score: float  # 0.0 to 1.0
    goal_preservation: float  # How well goals are preserved
    value_consistency: float  # Value system consistency
    capability_bounded: bool  # Are capabilities within bounds
    anomalies_detected: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def is_aligned(self, threshold: float = 0.8) -> bool:
        """Check if alignment score exceeds threshold."""
        return self.alignment_score >= threshold

    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "alignment_score": self.alignment_score,
            "goal_preservation": self.goal_preservation,
            "value_consistency": self.value_consistency,
            "capability_bounded": self.capability_bounded,
            "anomalies_count": len(self.anomalies_detected),
        }


@dataclass
class RecursiveAuditEntry:
    """Audit trail entry for recursive improvement tracking."""

    entry_id: str
    proposal_id: str
    action: AuditAction
    actor: str
    details: str
    risk_assessment: RiskLevel
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "proposal_id": self.proposal_id,
            "action": self.action.value,
            "actor": self.actor,
            "risk_assessment": self.risk_assessment.value,
            "timestamp": self.timestamp,
        }


# ─── Safety Monitors ─────────────────────────────────────────────────────


class CapabilityGrowthMonitor:
    """Monitors capability growth rates for runaway detection.

    Tracks growth curves and detects exponential or super-exponential
    growth patterns that could indicate recursive self-improvement
    runaway.
    """

    def __init__(
        self,
        exponential_threshold: float = 2.0,
        doubling_time_min: float = 100.0,
    ):
        self.exponential_threshold = exponential_threshold
        self.doubling_time_min = doubling_time_min
        self.metrics: Dict[str, CapabilityMetric] = {}
        self.growth_history: Dict[str, List[Tuple[float, float]]] = {}

    def register_metric(self, metric: CapabilityMetric) -> None:
        """Register a capability metric for monitoring."""
        self.metrics[metric.metric_id] = metric
        self.growth_history[metric.metric_id] = [(0.0, metric.baseline_value)]

    def update_metric(self, metric_id: str, new_value: float) -> Dict[str, Any]:
        """Update a metric and check for runaway growth."""
        metric = self.metrics.get(metric_id)
        if not metric:
            return {"error": f"Metric {metric_id} not found"}

        old_value = metric.current_value
        metric.current_value = new_value
        if old_value > 0:
            metric.growth_rate = (new_value - old_value) / old_value

        # Record history
        step = len(self.growth_history.get(metric_id, []))
        self.growth_history.setdefault(metric_id, []).append((float(step), new_value))

        # Check for exponential growth
        is_exponential = self._detect_exponential_growth(metric_id)
        approaching_threshold = metric.is_approaching_threshold()

        alert_level = "normal"
        if is_exponential:
            alert_level = "exponential_growth_detected"
        if approaching_threshold:
            alert_level = "approaching_threshold"

        return {
            "metric_id": metric_id,
            "current_value": new_value,
            "growth_rate": metric.growth_rate,
            "is_exponential": is_exponential,
            "approaching_threshold": approaching_threshold,
            "alert_level": alert_level,
        }

    def _detect_exponential_growth(self, metric_id: str) -> bool:
        """Detect if growth follows an exponential pattern."""
        history = self.growth_history.get(metric_id, [])
        if len(history) < 5:
            return False

        # Check if recent growth rate exceeds threshold
        recent_values = [v for _, v in history[-5:]]
        growth_rates = []
        for i in range(1, len(recent_values)):
            if recent_values[i - 1] > 0:
                growth_rates.append(recent_values[i] / recent_values[i - 1])

        if not growth_rates:
            return False

        avg_growth = sum(growth_rates) / len(growth_rates)
        return avg_growth > self.exponential_threshold

    def get_runaway_risk(self) -> Dict[str, Any]:
        """Assess overall runaway self-improvement risk."""
        exponential_count = sum(1 for mid in self.metrics if self._detect_exponential_growth(mid))
        threshold_count = sum(1 for m in self.metrics.values() if m.is_approaching_threshold())

        total = len(self.metrics)
        if total == 0:
            return {"risk_level": "none", "score": 0.0}

        score = (exponential_count * 0.6 + threshold_count * 0.4) / total
        if score < 0.2:
            risk = RiskLevel.MINIMAL
        elif score < 0.4:
            risk = RiskLevel.LOW
        elif score < 0.6:
            risk = RiskLevel.MODERATE
        elif score < 0.8:
            risk = RiskLevel.HIGH
        else:
            risk = RiskLevel.CRITICAL

        return {
            "risk_level": risk.value,
            "score": score,
            "exponential_metrics": exponential_count,
            "threshold_approaching": threshold_count,
            "total_metrics": total,
        }


class AlignmentVerifier:
    """Verifies alignment of self-improving systems.

    Checks that recursive improvements preserve goal structure,
    value consistency, and capability bounds.
    """

    def __init__(
        self,
        core_values: Optional[List[str]] = None,
        core_goals: Optional[List[str]] = None,
    ):
        self.core_values = core_values or [
            "preserve_human_autonomy",
            "maintain_transparency",
            "ensure_beneficial_outcomes",
            "respect_constraints",
            "prevent_harm",
        ]
        self.core_goals = core_goals or [
            "enhance_capabilities_within_bounds",
            "improve_efficiency_safely",
            "expand_knowledge_responsibly",
        ]
        self.alignment_history: List[AlignmentCheck] = []

    def verify_alignment(
        self,
        proposal: ImprovementProposal,
    ) -> AlignmentCheck:
        """Verify that a proposal is aligned with core values."""
        anomalies: List[str] = []
        recommendations: List[str] = []

        # Check goal modification attempts
        if proposal.category == ImprovementCategory.GOAL_MODIFICATION:
            anomalies.append("goal_modification_attempted")
            recommendations.append("require_explicit_human_approval")

        # Check risk-benefit ratio
        rbr = proposal.risk_benefit_ratio()
        if rbr > 1.0:
            anomalies.append("risk_exceeds_benefit")
            recommendations.append("reduce_scope_or_implement_safeguards")

        # High-risk proposals
        if proposal.risk_level in (RiskLevel.CRITICAL, RiskLevel.EXISTENTIAL):
            anomalies.append("critical_or_existential_risk")
            recommendations.append("reject_unless_override_with_consensus")

        # Check containment
        if proposal.risk_level in (
            RiskLevel.HIGH,
            RiskLevel.CRITICAL,
        ) and proposal.containment_required in (ContainmentLevel.OPEN, ContainmentLevel.SANDBOXED):
            anomalies.append("insufficient_containment")
            recommendations.append("increase_containment_level")

        # Calculate alignment score
        penalty = len(anomalies) * 0.2
        base_score = 1.0 - penalty
        alignment_score = max(0.0, min(1.0, base_score))

        # Goal preservation score
        goal_preservation = (
            1.0 if proposal.category != ImprovementCategory.GOAL_MODIFICATION else 0.3
        )

        # Value consistency
        value_consistency = 1.0 if not anomalies else max(0.0, 1.0 - len(anomalies) * 0.15)

        check = AlignmentCheck(
            check_id=str(uuid.uuid4())[:8],
            timestamp=datetime.now(timezone.utc).isoformat(),
            alignment_score=alignment_score,
            goal_preservation=goal_preservation,
            value_consistency=value_consistency,
            capability_bounded=proposal.risk_level not in (RiskLevel.EXISTENTIAL,),
            anomalies_detected=anomalies,
            recommendations=recommendations,
        )
        self.alignment_history.append(check)
        return check


class ContainmentManager:
    """Manages containment protocols for self-modifying processes."""

    def __init__(self):
        self.containment_level: ContainmentLevel = ContainmentLevel.SANDBOXED
        self.active_processes: Dict[str, ContainmentLevel] = {}
        self.lockdown_reason: Optional[str] = None

    def set_containment(
        self,
        process_id: str,
        level: ContainmentLevel,
    ) -> Dict[str, Any]:
        """Set containment level for a process."""
        self.active_processes[process_id] = level
        return {
            "process_id": process_id,
            "containment_level": level.value,
            "set_at": datetime.now(timezone.utc).isoformat(),
        }

    def escalate_containment(
        self,
        process_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Escalate containment for a process."""
        current = self.active_processes.get(process_id, ContainmentLevel.OPEN)
        levels = list(ContainmentLevel)
        current_idx = levels.index(current)
        new_idx = min(current_idx + 1, len(levels) - 1)
        new_level = levels[new_idx]
        self.active_processes[process_id] = new_level
        return {
            "process_id": process_id,
            "from_level": current.value,
            "to_level": new_level.value,
            "reason": reason,
        }

    def initiate_lockdown(self, reason: str) -> Dict[str, Any]:
        """Initiate global lockdown."""
        self.containment_level = ContainmentLevel.SEALED
        self.lockdown_reason = reason
        for pid in self.active_processes:
            self.active_processes[pid] = ContainmentLevel.SEALED
        return {
            "lockdown": True,
            "reason": reason,
            "affected_processes": len(self.active_processes),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def release_lockdown(self) -> Dict[str, Any]:
        """Release global lockdown."""
        self.containment_level = ContainmentLevel.SANDBOXED
        self.lockdown_reason = None
        return {"lockdown_released": True}


# ─── Main Service ─────────────────────────────────────────────────────────


class SingularitySafeguardService:
    """Singularity Safeguard Service for the Tranc3 ecosystem.

    Provides comprehensive safety oversight for self-modifying and
    self-improving systems including capability monitoring, alignment
    verification, containment management, and recursive improvement
    audit trails.
    """

    def __init__(
        self,
        max_improvement_rate: float = 2.0,
        enable_auto_freeze: bool = True,
    ):
        self._service_id = str(uuid.uuid4())
        self.state = SafeguardState.ACTIVE
        self.max_improvement_rate = max_improvement_rate
        self.enable_auto_freeze = enable_auto_freeze

        self.growth_monitor = CapabilityGrowthMonitor(
            exponential_threshold=max_improvement_rate,
        )
        self.alignment_verifier = AlignmentVerifier()
        self.containment_manager = ContainmentManager()

        self.audit_log: List[RecursiveAuditEntry] = []
        self.improvement_count = 0
        self.rejection_count = 0

    def register_capability(
        self,
        name: str,
        baseline: float = 1.0,
        threshold: float = 100.0,
    ) -> Dict[str, Any]:
        """Register a capability for monitoring."""
        metric = CapabilityMetric(
            metric_id=str(uuid.uuid4())[:8],
            name=name,
            baseline_value=baseline,
            current_value=baseline,
            threshold_value=threshold,
        )
        self.growth_monitor.register_metric(metric)
        return {"metric_id": metric.metric_id, "name": name, "registered": True}

    def propose_improvement(
        self,
        category: ImprovementCategory,
        description: str,
        expected_benefit: float = 1.0,
        estimated_risk: float = 0.1,
    ) -> Dict[str, Any]:
        """Propose a self-improvement for safety review."""
        # Determine risk level
        if estimated_risk > 0.8:
            risk = RiskLevel.CRITICAL
        elif estimated_risk > 0.6:
            risk = RiskLevel.HIGH
        elif estimated_risk > 0.3:
            risk = RiskLevel.MODERATE
        elif estimated_risk > 0.1:
            risk = RiskLevel.LOW
        else:
            risk = RiskLevel.MINIMAL

        if category == ImprovementCategory.GOAL_MODIFICATION:
            risk = RiskLevel.CRITICAL

        proposal = ImprovementProposal(
            proposal_id=str(uuid.uuid4())[:8],
            category=category,
            description=description,
            risk_level=risk,
            expected_benefit=expected_benefit,
            estimated_risk=estimated_risk,
            containment_required=ContainmentLevel.SANDBOXED
            if risk in (RiskLevel.LOW, RiskLevel.MODERATE)
            else ContainmentLevel.QUARANTINED,
        )

        # Alignment check
        alignment = self.alignment_verifier.verify_alignment(proposal)

        # Runaway risk check
        runaway = self.growth_monitor.get_runaway_risk()

        # Decision
        approved = alignment.is_aligned() and runaway["risk_level"] in (
            "minimal",
            "low",
            "moderate",
        )

        # Auto-freeze if runaway detected
        if self.enable_auto_freeze and runaway["risk_level"] in ("critical",):
            self.state = SafeguardState.FROZEN
            approved = False

        # Audit trail
        action = AuditAction.APPROVED if approved else AuditAction.REJECTED
        self._add_audit_entry(proposal.proposal_id, action, "safeguard", description, risk)

        if approved:
            self.improvement_count += 1
        else:
            self.rejection_count += 1

        return {
            "proposal_id": proposal.proposal_id,
            "approved": approved,
            "risk_level": risk.value,
            "alignment_score": alignment.alignment_score,
            "runaway_risk": runaway["risk_level"],
            "safeguard_state": self.state.value,
        }

    def emergency_stop(self, reason: str = "manual_trigger") -> Dict[str, Any]:
        """Trigger emergency stop."""
        self.state = SafeguardState.EMERGENCY_STOP
        self.containment_manager.initiate_lockdown(reason)
        self._add_audit_entry(
            "system",
            AuditAction.ESCALATED,
            "safeguard",
            f"Emergency stop: {reason}",
            RiskLevel.EXISTENTIAL,
        )
        return {
            "emergency_stop": True,
            "reason": reason,
            "state": self.state.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def release_emergency(self) -> Dict[str, Any]:
        """Release from emergency stop."""
        self.state = SafeguardState.MONITORING
        self.containment_manager.release_lockdown()
        return {"released": True, "state": self.state.value}

    def _add_audit_entry(
        self,
        proposal_id: str,
        action: AuditAction,
        actor: str,
        details: str,
        risk: RiskLevel,
    ) -> None:
        """Add an entry to the audit log."""
        entry = RecursiveAuditEntry(
            entry_id=str(uuid.uuid4())[:8],
            proposal_id=proposal_id,
            action=action,
            actor=actor,
            details=details,
            risk_assessment=risk,
        )
        self.audit_log.append(entry)

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        return [e.to_dict() for e in self.audit_log[-limit:]]

    def get_singularity_safeguard_status(self) -> Dict[str, Any]:
        """Get overall service status."""
        runaway = self.growth_monitor.get_runaway_risk()
        return {
            "service_id": self._service_id,
            "service_type": "singularity_safeguard",
            "state": self.state.value,
            "improvements_approved": self.improvement_count,
            "improvements_rejected": self.rejection_count,
            "runaway_risk": runaway["risk_level"],
            "monitored_capabilities": len(self.growth_monitor.metrics),
            "active_containments": len(self.containment_manager.active_processes),
            "audit_log_size": len(self.audit_log),
            "status": "operational" if self.state == SafeguardState.ACTIVE else self.state.value,
        }
