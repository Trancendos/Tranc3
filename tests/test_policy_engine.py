"""
Tests for the ABAC Policy Engine.
"""

from __future__ import annotations


from src.auth.policy_engine import (
    PolicyCondition,
    PolicyDecision,
    PolicyEffect,
    PolicyEngine,
    PolicyOperator,
    PolicyRule,
    PolicySet,
)


def _engine_with_set(ps: PolicySet) -> PolicyEngine:
    engine = PolicyEngine()
    engine.add_policy_set(ps)
    return engine


def _simple_rule(
    rule_id: str,
    effect: PolicyEffect,
    conditions: list[PolicyCondition],
    resources: list[str] | None = None,
    actions: list[str] | None = None,
    priority: int = 0,
) -> PolicyRule:
    return PolicyRule(
        id=rule_id,
        effect=effect,
        conditions=conditions,
        resources=resources or [],
        actions=actions or [],
        priority=priority,
    )


# ── Allow rule matches ─────────────────────────────────────────────────────────


def test_allow_rule_matches():
    rule = _simple_rule(
        "r1",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.role", PolicyOperator.eq, "admin")],
    )
    ps = PolicySet(id="ps1", rules=[rule], combine_strategy="first_match")
    engine = _engine_with_set(ps)

    decision = engine.evaluate({"role": "admin"}, "docs/secret", "read")
    assert decision.effect == PolicyEffect.ALLOW
    assert decision.matched_rule_id == "r1"


def test_deny_rule_matches():
    rule = _simple_rule(
        "deny-guests",
        PolicyEffect.DENY,
        [PolicyCondition("subject.role", PolicyOperator.eq, "guest")],
    )
    ps = PolicySet(id="ps2", rules=[rule], combine_strategy="first_match")
    engine = _engine_with_set(ps)

    decision = engine.evaluate({"role": "guest"}, "admin/panel", "write")
    assert decision.effect == PolicyEffect.DENY


def test_default_deny_when_no_rules_match():
    rule = _simple_rule(
        "r-admin",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.role", PolicyOperator.eq, "admin")],
    )
    ps = PolicySet(
        id="ps3", rules=[rule], combine_strategy="first_match", default_effect=PolicyEffect.DENY
    )
    engine = _engine_with_set(ps)

    decision = engine.evaluate({"role": "user"}, "any/resource", "read")
    assert decision.effect == PolicyEffect.DENY
    assert decision.matched_rule_id is None


# ── Deny override strategy ────────────────────────────────────────────────────


def test_deny_overrides_strategy():
    allow_rule = _simple_rule(
        "allow-all",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.id", PolicyOperator.exists)],
        priority=0,
    )
    deny_rule = _simple_rule(
        "deny-blocked",
        PolicyEffect.DENY,
        [PolicyCondition("subject.blocked", PolicyOperator.eq, True)],
        priority=10,
    )
    ps = PolicySet(
        id="ps-deny-override",
        rules=[allow_rule, deny_rule],
        combine_strategy="deny_overrides",
    )
    engine = _engine_with_set(ps)

    # Non-blocked user should be allowed
    d1 = engine.evaluate({"id": "user1", "blocked": False}, "res", "read")
    assert d1.effect == PolicyEffect.ALLOW

    # Blocked user should be denied even though allow rule also matches
    d2 = engine.evaluate({"id": "user2", "blocked": True}, "res", "read")
    assert d2.effect == PolicyEffect.DENY


# ── Dot-notation attribute resolution ─────────────────────────────────────────


def test_dot_notation_resolution():
    rule = _simple_rule(
        "r-tier",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.profile.tier", PolicyOperator.eq, "pro")],
    )
    ps = PolicySet(id="ps-dot", rules=[rule], combine_strategy="first_match")
    engine = _engine_with_set(ps)

    subject = {"profile": {"tier": "pro"}}
    decision = engine.evaluate(subject, "api/v2", "call")
    assert decision.effect == PolicyEffect.ALLOW


def test_dot_notation_missing_path_fails_condition():
    rule = _simple_rule(
        "r-nested",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.profile.tier", PolicyOperator.eq, "pro")],
    )
    ps = PolicySet(
        id="ps-dot-miss",
        rules=[rule],
        combine_strategy="first_match",
        default_effect=PolicyEffect.DENY,
    )
    engine = _engine_with_set(ps)

    # subject has no nested profile
    decision = engine.evaluate({"role": "user"}, "api/v2", "call")
    assert decision.effect == PolicyEffect.DENY


# ── Glob resource matching ────────────────────────────────────────────────────


def test_glob_resource_matching():
    rule = _simple_rule(
        "r-glob",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.role", PolicyOperator.eq, "admin")],
        resources=["admin/*"],
        actions=["read", "write"],
    )
    ps = PolicySet(
        id="ps-glob", rules=[rule], combine_strategy="first_match", default_effect=PolicyEffect.DENY
    )
    engine = _engine_with_set(ps)

    # Matching resource and action
    d1 = engine.evaluate({"role": "admin"}, "admin/users", "read")
    assert d1.effect == PolicyEffect.ALLOW

    # Non-matching resource
    d2 = engine.evaluate({"role": "admin"}, "public/docs", "read")
    assert d2.effect == PolicyEffect.DENY


# ── Various operators ──────────────────────────────────────────────────────────


def test_operator_in():
    rule = _simple_rule(
        "r-in",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.role", PolicyOperator.in_, ["admin", "moderator"])],
    )
    ps = PolicySet(
        id="ps-in", rules=[rule], combine_strategy="first_match", default_effect=PolicyEffect.DENY
    )
    engine = _engine_with_set(ps)
    assert engine.evaluate({"role": "moderator"}, "r", "a").effect == PolicyEffect.ALLOW
    assert engine.evaluate({"role": "guest"}, "r", "a").effect == PolicyEffect.DENY


def test_operator_exists():
    rule = _simple_rule(
        "r-exists",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.mfa_verified", PolicyOperator.exists)],
    )
    ps = PolicySet(
        id="ps-exists",
        rules=[rule],
        combine_strategy="first_match",
        default_effect=PolicyEffect.DENY,
    )
    engine = _engine_with_set(ps)
    assert engine.evaluate({"mfa_verified": True}, "r", "a").effect == PolicyEffect.ALLOW
    assert engine.evaluate({"role": "user"}, "r", "a").effect == PolicyEffect.DENY


def test_operator_matches_regex():
    rule = _simple_rule(
        "r-regex",
        PolicyEffect.ALLOW,
        [PolicyCondition("subject.email", PolicyOperator.matches, r"@trancendos\.com$")],
    )
    ps = PolicySet(
        id="ps-regex",
        rules=[rule],
        combine_strategy="first_match",
        default_effect=PolicyEffect.DENY,
    )
    engine = _engine_with_set(ps)
    assert engine.evaluate({"email": "user@trancendos.com"}, "r", "a").effect == PolicyEffect.ALLOW
    assert engine.evaluate({"email": "user@gmail.com"}, "r", "a").effect == PolicyEffect.DENY


# ── Audit log ─────────────────────────────────────────────────────────────────


def test_audit_log_records_decisions():
    engine = PolicyEngine()
    ps = PolicySet(
        id="ps-audit",
        rules=[
            _simple_rule("allow-all", PolicyEffect.ALLOW, []),
        ],
        combine_strategy="first_match",
    )
    engine.add_policy_set(ps)

    for _ in range(5):
        engine.evaluate({"id": "u1"}, "res", "read")

    log = engine.get_audit_log()
    assert len(log) >= 5
    for entry in log:
        assert isinstance(entry, PolicyDecision)
        assert entry.audit_id
        assert entry.evaluated_at
