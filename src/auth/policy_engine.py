"""
ABAC Policy Engine — Attribute-Based Access Control
====================================================
CEL-inspired policy evaluation engine. Evaluates structured policy rules
against request contexts to produce allow/deny decisions with full
audit trail support.

Ported from: @trancendos/policy-engine (infinity-adminOS)
Zero-cost: Pure Python stdlib. No external dependencies.
"""

from __future__ import annotations

import fnmatch
import re
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

# ── Enums ────────────────────────────────────────────────────────────────────


class PolicyEffect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


class PolicyOperator(str, Enum):
    eq = "eq"
    neq = "neq"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    not_in = "not_in"
    contains = "contains"
    starts_with = "starts_with"
    ends_with = "ends_with"
    matches = "matches"
    exists = "exists"
    not_exists = "not_exists"


# ── Dataclasses ───────────────────────────────────────────────────────────────


@dataclass
class PolicyCondition:
    """A single condition in a policy rule.

    Attributes:
        attribute: Dot-notation path into evaluation context, e.g. ``subject.role``.
        operator: Comparison operator.
        value: Value to compare against (not used for ``exists`` / ``not_exists``).
    """

    attribute: str
    operator: PolicyOperator
    value: Any = None


@dataclass
class PolicyRule:
    """A single rule within a policy set."""

    id: str
    effect: PolicyEffect
    conditions: list[PolicyCondition]
    description: str = ""
    priority: int = 0
    resources: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)


@dataclass
class PolicySet:
    """An ordered collection of rules with a combination strategy."""

    id: str
    rules: list[PolicyRule]
    combine_strategy: str = "first_match"  # first_match|deny_overrides|allow_overrides|majority
    default_effect: PolicyEffect = PolicyEffect.DENY


@dataclass
class PolicyDecision:
    """The result of a policy evaluation."""

    effect: PolicyEffect
    matched_rule_id: Optional[str]
    explanation: str
    audit_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    evaluated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


# ── Helpers ───────────────────────────────────────────────────────────────────


def _resolve_path(obj: dict, path: str) -> tuple[bool, Any]:
    """Resolve a dot-notation *path* into *obj*.

    Returns ``(exists, value)`` — ``exists=False`` when any segment is missing.
    """
    parts = path.split(".")
    cur: Any = obj
    for part in parts:
        if not isinstance(cur, dict) or part not in cur:
            return False, None
        cur = cur[part]
    return True, cur


def _evaluate_condition(condition: PolicyCondition, ctx: dict) -> bool:
    """Return True if the condition holds for the given flat context dict."""
    exists, value = _resolve_path(ctx, condition.attribute)
    op = condition.operator

    if op == PolicyOperator.exists:
        return exists
    if op == PolicyOperator.not_exists:
        return not exists
    if not exists:
        return False  # attribute missing → condition cannot hold

    cmp = condition.value
    try:
        if op == PolicyOperator.eq:
            return value == cmp
        if op == PolicyOperator.neq:
            return value != cmp
        if op == PolicyOperator.gt:
            return value > cmp  # type: ignore[operator]
        if op == PolicyOperator.gte:
            return value >= cmp  # type: ignore[operator]
        if op == PolicyOperator.lt:
            return value < cmp  # type: ignore[operator]
        if op == PolicyOperator.lte:
            return value <= cmp  # type: ignore[operator]
        if op == PolicyOperator.in_:
            return value in (cmp or [])
        if op == PolicyOperator.not_in:
            return value not in (cmp or [])
        if op == PolicyOperator.contains:
            return str(cmp) in str(value)
        if op == PolicyOperator.starts_with:
            return str(value).startswith(str(cmp))
        if op == PolicyOperator.ends_with:
            return str(value).endswith(str(cmp))
        if op == PolicyOperator.matches:
            return bool(re.search(str(cmp), str(value)))
    except (TypeError, ValueError):
        return False
    return False


def _rule_matches_request(
    rule: PolicyRule, resource: str, action: str
) -> bool:
    """Return True if the rule is applicable to this resource/action."""
    if rule.resources:
        if not any(fnmatch.fnmatch(resource, pat) for pat in rule.resources):
            return False
    if rule.actions:
        if action not in rule.actions and "*" not in rule.actions:
            return False
    return True


def _apply_conditions(rule: PolicyRule, ctx: dict) -> bool:
    """Return True only if every condition in the rule holds."""
    return all(_evaluate_condition(c, ctx) for c in rule.conditions)


# ── Engine ────────────────────────────────────────────────────────────────────


class PolicyEngine:
    """Evaluates policy sets against request contexts.

    Usage::

        engine = PolicyEngine()
        engine.add_policy_set(PolicySet(...))
        decision = engine.evaluate(subject={"role": "admin"}, resource="docs/*", action="read")
    """

    def __init__(self) -> None:
        self._policy_sets: dict[str, PolicySet] = {}
        self._audit_log: deque[PolicyDecision] = deque(maxlen=1000)
        self._cache: dict[str, PolicyDecision] = {}

    def add_policy_set(self, policy_set: PolicySet) -> None:
        """Register a policy set."""
        self._policy_sets[policy_set.id] = policy_set
        # Invalidate cache when policy sets change
        self._cache.clear()

    def evaluate(
        self,
        subject: dict,
        resource: str,
        action: str,
        context: dict | None = None,
    ) -> PolicyDecision:
        """Evaluate all registered policy sets and return the final decision."""
        ctx = {
            "subject": subject,
            "resource": resource,
            "action": action,
            **(context or {}),
        }
        # Build a hashable cache key
        cache_key = _make_cache_key(subject, resource, action, context or {})
        if cache_key in self._cache:
            decision = self._cache[cache_key]
        else:
            decision = self._evaluate_ctx(resource, action, ctx)
            # Limit cache size to 1000 entries
            if len(self._cache) >= 1000:
                self._cache.pop(next(iter(self._cache)))
            self._cache[cache_key] = decision
        self._audit_log.append(decision)
        return decision

    def _evaluate_ctx(
        self,
        resource: str,
        action: str,
        ctx: dict,
    ) -> PolicyDecision:
        for ps in sorted(
            self._policy_sets.values(), key=lambda p: p.id
        ):
            decision = self._evaluate_policy_set(ps, resource, action, ctx)
            if decision is not None:
                return decision

        return PolicyDecision(
            effect=PolicyEffect.DENY,
            matched_rule_id=None,
            explanation="No policy sets registered; default DENY",
        )

    def _evaluate_policy_set(
        self,
        ps: PolicySet,
        resource: str,
        action: str,
        ctx: dict,
    ) -> Optional[PolicyDecision]:
        sorted_rules = sorted(ps.rules, key=lambda r: r.priority, reverse=True)
        matching: list[PolicyRule] = []

        for rule in sorted_rules:
            if _rule_matches_request(rule, resource, action) and _apply_conditions(
                rule, ctx
            ):
                matching.append(rule)

        if not matching:
            return PolicyDecision(
                effect=ps.default_effect,
                matched_rule_id=None,
                explanation=f"No rules matched in policy set '{ps.id}'; using default {ps.default_effect.value}",
            )

        strategy = ps.combine_strategy

        if strategy == "first_match":
            rule = matching[0]
            return PolicyDecision(
                effect=rule.effect,
                matched_rule_id=rule.id,
                explanation=f"First match: rule '{rule.id}' → {rule.effect.value}",
            )

        if strategy == "deny_overrides":
            deny_rules = [r for r in matching if r.effect == PolicyEffect.DENY]
            if deny_rules:
                r = deny_rules[0]
                return PolicyDecision(
                    effect=PolicyEffect.DENY,
                    matched_rule_id=r.id,
                    explanation=f"Deny override: rule '{r.id}'",
                )
            r = matching[0]
            return PolicyDecision(
                effect=PolicyEffect.ALLOW,
                matched_rule_id=r.id,
                explanation=f"Deny override: no deny found; allow via '{r.id}'",
            )

        if strategy == "allow_overrides":
            allow_rules = [r for r in matching if r.effect == PolicyEffect.ALLOW]
            if allow_rules:
                r = allow_rules[0]
                return PolicyDecision(
                    effect=PolicyEffect.ALLOW,
                    matched_rule_id=r.id,
                    explanation=f"Allow override: rule '{r.id}'",
                )
            r = matching[0]
            return PolicyDecision(
                effect=PolicyEffect.DENY,
                matched_rule_id=r.id,
                explanation=f"Allow override: no allow found; deny via '{r.id}'",
            )

        if strategy == "majority":
            allows = sum(1 for r in matching if r.effect == PolicyEffect.ALLOW)
            denies = len(matching) - allows
            effect = PolicyEffect.ALLOW if allows > denies else PolicyEffect.DENY
            return PolicyDecision(
                effect=effect,
                matched_rule_id=matching[0].id,
                explanation=f"Majority: {allows} allow vs {denies} deny → {effect.value}",
            )

        return None

    def get_audit_log(self) -> list[PolicyDecision]:
        """Return a list of recent decisions (last 1 000)."""
        return list(self._audit_log)


def _make_cache_key(
    subject: dict, resource: str, action: str, context: dict
) -> str:
    """Create a deterministic string key for LRU cache."""
    import json

    def _serialise(d: dict) -> str:
        return json.dumps(d, sort_keys=True, default=str)

    return f"{_serialise(subject)}|{resource}|{action}|{_serialise(context)}"


__all__ = [
    "PolicyCondition",
    "PolicyDecision",
    "PolicyEffect",
    "PolicyEngine",
    "PolicyOperator",
    "PolicyRule",
    "PolicySet",
]
