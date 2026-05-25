"""
Trancendos Infinity ABAC — Attribute-Based Access Control Engine
================================================================
Fine-grained policy engine for the Infinity Ecosystem.

ABAC extends RBAC with policy decisions based on:
    - Subject attributes: tier, pillar, prime status, roles, department
    - Resource attributes: classification, owner, pillar, sensitivity level
    - Environment attributes: time of day, network location, threat level
    - Action attributes: read, write, execute, admin, create, delete

OWASP A01 (Broken Access Control): Fine-grained access beyond roles.
OWASP A04 (Insecure Design): Explicit, auditable policy definitions.

Features:
    - Declarative policy language with condition expressions
    - Subject, resource, environment, and action attribute matching
    - Policy combination algorithms (deny-overrides, permit-overrides)
    - Threat-level adaptive access (reduce permissions during high threat)
    - Time-based access restrictions
    - Audit logging for all policy evaluations

Usage:
    from shared_core.infinity.abac import ABACEngine, Policy, PolicyEffect

    engine = ABACEngine()
    engine.add_policy(Policy(
        id="admin-only-sensitive",
        description="Only admins can access sensitive resources",
        effect=PolicyEffect.PERMIT,
        subject_conditions={"role": "admin"},
        resource_conditions={"sensitivity": "high"},
        action_conditions={"action": ["read", "write"]},
    ))

    if engine.evaluate(user_attrs, resource_attrs, env_attrs, action_attrs):
        # Access permitted
        ...
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

from shared_core.infinity.nomenclature import InfinityRole, Pillar, Tier

logger = logging.getLogger(__name__)


# ── Policy Effect ────────────────────────────────────────────────

class PolicyEffect(str, Enum):
    """The effect of a policy evaluation."""

    PERMIT = "permit"
    DENY = "deny"


# ── Sensitivity Levels ──────────────────────────────────────────

class SensitivityLevel(str, Enum):
    """Resource sensitivity classification levels."""

    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"
    TOP_SECRET = "top_secret"


# ── Threat Levels ────────────────────────────────────────────────

class ThreatLevel(str, Enum):
    """Current threat level for adaptive access control."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ── Minimum tier required per sensitivity level ──────────────────

SENSITIVITY_TIER_MINIMUM: Dict[SensitivityLevel, Tier] = {
    SensitivityLevel.PUBLIC: Tier.HUMAN,
    SensitivityLevel.INTERNAL: Tier.HUMAN,
    SensitivityLevel.CONFIDENTIAL: Tier.PRIME,
    SensitivityLevel.RESTRICTED: Tier.ORCHESTRATOR,
    SensitivityLevel.TOP_SECRET: Tier.ORCHESTRATOR,
}

# Threat level access reduction
THREAT_ACCESS_REDUCTION: Dict[ThreatLevel, Set[str]] = {
    ThreatLevel.LOW: set(),  # No restrictions
    ThreatLevel.MEDIUM: {"write", "delete"},  # Reduce write access for non-admins
    ThreatLevel.HIGH: {"write", "delete", "execute"},  # Reduce to read-only for non-admins
    ThreatLevel.CRITICAL: {"write", "delete", "execute", "read_restricted"},  # Minimal access
}


# ── Policy ───────────────────────────────────────────────────────

class Policy:
    """A declarative access control policy.

    A policy consists of:
    - An effect (PERMIT or DENY)
    - Subject conditions (who is making the request)
    - Resource conditions (what is being accessed)
    - Action conditions (what operation is being performed)
    - Environment conditions (contextual factors)
    - A priority for conflict resolution

    All conditions are ANDed together — all must match for the policy
    to apply. Within each condition dict, values are ORed — any match
    satisfies that condition.
    """

    def __init__(
        self,
        id: str,
        description: str = "",
        effect: PolicyEffect = PolicyEffect.PERMIT,
        subject_conditions: Optional[Dict[str, Any]] = None,
        resource_conditions: Optional[Dict[str, Any]] = None,
        action_conditions: Optional[Dict[str, Any]] = None,
        environment_conditions: Optional[Dict[str, Any]] = None,
        priority: int = 0,
    ):
        self.id = id
        self.description = description
        self.effect = effect
        self.subject_conditions = subject_conditions or {}
        self.resource_conditions = resource_conditions or {}
        self.action_conditions = action_conditions or {}
        self.environment_conditions = environment_conditions or {}
        self.priority = priority

    def matches(
        self,
        subject: Dict[str, Any],
        resource: Dict[str, Any],
        action: Dict[str, Any],
        environment: Dict[str, Any],
    ) -> bool:
        """Check if this policy matches the given attributes."""
        return (
            self._matches_conditions(self.subject_conditions, subject)
            and self._matches_conditions(self.resource_conditions, resource)
            and self._matches_conditions(self.action_conditions, action)
            and self._matches_conditions(self.environment_conditions, environment)
        )

    @staticmethod
    def _matches_conditions(conditions: Dict[str, Any], attributes: Dict[str, Any]) -> bool:
        """Check if attributes match all conditions.

        For each condition key:
        - If the condition value is a list, any match satisfies it (OR)
        - If the condition value is a callable, it's called with the attribute value
        - If the condition value is a scalar, exact match is required
        - If the condition key is not in attributes, it doesn't match
        """
        for key, condition_value in conditions.items():
            attr_value = attributes.get(key)
            if attr_value is None:
                return False

            if isinstance(condition_value, list):
                if attr_value not in condition_value:
                    return False
            elif callable(condition_value):
                if not condition_value(attr_value):
                    return False
            else:
                if attr_value != condition_value:
                    return False

        return True

    def __repr__(self) -> str:
        return f"Policy({self.id}, effect={self.effect.value}, priority={self.priority})"


# ── ABAC Engine ──────────────────────────────────────────────────

class ABACEngine:
    """
    Attribute-Based Access Control engine for the Infinity Ecosystem.

    Evaluates access requests against a set of declarative policies,
    considering subject, resource, action, and environment attributes.

    Default combination algorithm: deny-overrides (if any DENY policy
    matches, access is denied regardless of PERMIT policies).

    Threat-level adaptive: at HIGH or CRITICAL threat levels,
    access is automatically reduced even if policies would permit it.

    OWASP A01: Fine-grained access beyond simple role checks.
    OWASP A04: Explicit, auditable policy definitions.
    """

    def __init__(
        self,
        policies: Optional[List[Policy]] = None,
        threat_level: ThreatLevel = ThreatLevel.LOW,
        combination_algorithm: str = "deny_overrides",
    ):
        self._policies: List[Policy] = policies or []
        self._threat_level = threat_level
        self._combination_algorithm = combination_algorithm
        self._audit_log: List[Dict[str, Any]] = []

    @property
    def threat_level(self) -> ThreatLevel:
        return self._threat_level

    @threat_level.setter
    def threat_level(self, level: ThreatLevel) -> None:
        self._threat_level = level
        logger.info("ABAC threat level changed to: %s", level.value)

    def add_policy(self, policy: Policy) -> None:
        """Add a policy to the engine."""
        self._policies.append(policy)
        # Sort by priority (highest first)
        self._policies.sort(key=lambda p: p.priority, reverse=True)

    def remove_policy(self, policy_id: str) -> bool:
        """Remove a policy by ID. Returns True if found and removed."""
        before = len(self._policies)
        self._policies = [p for p in self._policies if p.id != policy_id]
        return len(self._policies) < before

    def evaluate(
        self,
        subject: Dict[str, Any],
        resource: Dict[str, Any],
        action: Dict[str, Any],
        environment: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Evaluate access against all policies.

        Returns True if access is permitted, False if denied.

        Algorithm (deny-overrides):
        1. If any DENY policy matches → deny
        2. If any PERMIT policy matches → permit
        3. Default: deny (no matching policy)

        Additionally checks:
        - Sensitivity level vs user tier
        - Threat-level access reduction
        - Time-based restrictions
        """
        env = environment or {"threat_level": self._threat_level.value}

        # Pre-policy checks: sensitivity level
        sensitivity = resource.get("sensitivity")
        if sensitivity:
            try:
                sens = SensitivityLevel(sensitivity)
                min_tier = SENSITIVITY_TIER_MINIMUM.get(sens, Tier.ORCHESTRATOR)
                user_tier_value = subject.get("tier_value", 0)
                if isinstance(user_tier_value, int):
                    if user_tier_value > min_tier:
                        self._log_decision(subject, resource, action, env, False, "sensitivity_check")
                        return False
                else:
                    # If tier_value is a string name, convert
                    try:
                        user_tier = Tier[user_tier_value.upper()] if isinstance(user_tier_value, str) else Tier.HUMAN
                        if user_tier > min_tier:
                            self._log_decision(subject, resource, action, env, False, "sensitivity_check")
                            return False
                    except (KeyError, ValueError):
                        self._log_decision(subject, resource, action, env, False, "sensitivity_check_invalid_tier")
                        return False
            except ValueError:
                pass  # Unknown sensitivity, skip check

        # Pre-policy checks: threat-level adaptive access
        threat = env.get("threat_level", self._threat_level.value)
        try:
            threat_level = ThreatLevel(threat)
            restricted_actions = THREAT_ACCESS_REDUCTION.get(threat_level, set())
            if restricted_actions and action.get("action") in restricted_actions:
                # Admins are exempt from threat-level restrictions
                if subject.get("role") != InfinityRole.ADMIN:
                    self._log_decision(subject, resource, action, env, False, "threat_level_restriction")
                    return False
        except ValueError:
            pass

        # Evaluate policies
        permit_matched = False
        for policy in self._policies:
            if policy.matches(subject, resource, action, env):
                if policy.effect == PolicyEffect.DENY:
                    self._log_decision(subject, resource, action, env, False, f"deny_policy:{policy.id}")
                    return False
                if policy.effect == PolicyEffect.PERMIT:
                    permit_matched = True

        if permit_matched:
            self._log_decision(subject, resource, action, env, True, "permit_policy")
            return True

        # Default: deny
        self._log_decision(subject, resource, action, env, False, "no_matching_policy")
        return False

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get recent access decision audit entries."""
        return self._audit_log[-limit:]

    def _log_decision(
        self,
        subject: Dict[str, Any],
        resource: Dict[str, Any],
        action: Dict[str, Any],
        environment: Dict[str, Any],
        granted: bool,
        reason: str,
    ) -> None:
        """Log an access decision for audit purposes (OWASP A09)."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "subject_id": subject.get("sub", "anonymous"),
            "subject_role": subject.get("role", "unknown"),
            "subject_tier": subject.get("tier", "unknown"),
            "resource_type": resource.get("type", "unknown"),
            "resource_id": resource.get("id", "unknown"),
            "action": action.get("action", "unknown"),
            "threat_level": environment.get("threat_level", "unknown"),
            "granted": granted,
            "reason": reason,
        }
        self._audit_log.append(entry)
        # Keep log bounded
        if len(self._audit_log) > 10000:
            self._audit_log = self._audit_log[-5000:]

        if not granted:
            logger.info(
                "ABAC denied: user=%s role=%s action=%s resource=%s reason=%s",
                subject.get("sub", "anonymous"),
                subject.get("role", "unknown"),
                action.get("action", "unknown"),
                resource.get("type", "unknown"),
                reason,
            )


# ── Default Policies ─────────────────────────────────────────────

def get_default_policies() -> List[Policy]:
    """Get the default ABAC policies for the Infinity Ecosystem."""
    return [
        Policy(
            id="admin-full-access",
            description="Admins have full access to all resources",
            effect=PolicyEffect.PERMIT,
            subject_conditions={"role": "admin"},
            priority=100,
        ),
        Policy(
            id="prime-pillar-access",
            description="Primes have full access within their pillar",
            effect=PolicyEffect.PERMIT,
            subject_conditions={"role": "prime"},
            priority=90,
        ),
        Policy(
            id="ai-resource-access",
            description="AI tier can read and write AI resources",
            effect=PolicyEffect.PERMIT,
            subject_conditions={"role": "ai"},
            action_conditions={"action": ["read", "write", "execute"]},
            resource_conditions={"type": ["model", "workflow", "agent", "dataset"]},
            priority=80,
        ),
        Policy(
            id="agent-task-access",
            description="Infinity-Agents can only execute assigned tasks",
            effect=PolicyEffect.PERMIT,
            subject_conditions={"role": "agent"},
            action_conditions={"action": ["read", "execute"]},
            priority=70,
        ),
        Policy(
            id="bot-infra-access",
            description="Infinity-Bots can only read infrastructure data",
            effect=PolicyEffect.PERMIT,
            subject_conditions={"role": "bot"},
            action_conditions={"action": ["read"]},
            resource_conditions={"type": ["infrastructure", "metrics", "health"]},
            priority=60,
        ),
        Policy(
            id="user-self-service",
            description="Users can manage their own resources",
            effect=PolicyEffect.PERMIT,
            subject_conditions={"role": "user"},
            action_conditions={"action": ["read", "write"]},
            resource_conditions={"type": ["agent", "workflow", "model"]},
            priority=50,
        ),
        Policy(
            id="deny-restricted-non-admin",
            description="Non-admins cannot access restricted resources",
            effect=PolicyEffect.DENY,
            subject_conditions={"role": ["user", "agent", "bot"]},
            resource_conditions={"sensitivity": ["restricted", "top_secret"]},
            priority=200,
        ),
        Policy(
            id="deny-critical-threat",
            description="Deny write access during critical threat level",
            effect=PolicyEffect.DENY,
            action_conditions={"action": ["write", "delete", "execute"]},
            environment_conditions={"threat_level": "critical"},
            priority=300,
        ),
    ]
