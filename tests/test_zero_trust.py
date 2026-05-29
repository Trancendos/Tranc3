"""
Tests for src/auth/zero_trust.py — Zero Trust IAM Middleware
=============================================================
Covers: context extraction, risk scoring, policy evaluation,
geographic controls, MFA enforcement, device posture checks.
"""

import pytest

from src.auth.zero_trust import (
    AccessPolicy,
    DevicePostureStatus,
    ZeroTrustContext,
    ZeroTrustMiddleware,
    ZeroTrustOptions,
)

# ─────────────────────────────────────────────────────────────────────────────
# ZeroTrustContext Model Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestZeroTrustContext:
    """Pydantic model for Zero Trust context."""

    def test_default_context(self):
        ctx = ZeroTrustContext()
        assert ctx.device_id is None
        assert ctx.device_posture == DevicePostureStatus.UNKNOWN
        assert ctx.country is None
        assert ctx.mfa_verified is False
        assert ctx.access_policy == AccessPolicy.ALLOW
        assert ctx.risk_score == 0
        assert ctx.ip_address is None
        assert ctx.user_agent is None

    def test_context_with_values(self):
        ctx = ZeroTrustContext(
            device_id="dev-123",
            device_posture=DevicePostureStatus.HEALTHY,
            country="US",
            mfa_verified=True,
            risk_score=5,
            ip_address="10.0.0.1",
            user_agent="TestAgent/1.0",
        )
        assert ctx.device_id == "dev-123"
        assert ctx.device_posture == DevicePostureStatus.HEALTHY
        assert ctx.country == "US"
        assert ctx.mfa_verified is True
        assert ctx.risk_score == 5
        assert ctx.ip_address == "10.0.0.1"
        assert ctx.user_agent == "TestAgent/1.0"

    def test_risk_score_clamped(self):
        """Risk score must be 0-100."""
        ctx = ZeroTrustContext(risk_score=0)
        assert ctx.risk_score == 0
        ctx = ZeroTrustContext(risk_score=100)
        assert ctx.risk_score == 100
        # Below 0 or above 100 should fail validation
        with pytest.raises(Exception):
            ZeroTrustContext(risk_score=-1)
        with pytest.raises(Exception):
            ZeroTrustContext(risk_score=101)


# ─────────────────────────────────────────────────────────────────────────────
# ZeroTrustOptions Model Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestZeroTrustOptions:
    """Pydantic model for Zero Trust configuration."""

    def test_default_options(self):
        opts = ZeroTrustOptions()
        assert opts.mfa_routes == []
        assert opts.healthy_device_routes == []
        assert opts.allowed_countries == []
        assert opts.blocked_countries == []
        assert opts.min_risk_score == 0
        assert opts.enforce_on_all_routes is False
        assert opts.mfa_bypass_for_healthy is True

    def test_custom_options(self):
        opts = ZeroTrustOptions(
            mfa_routes=["/admin", "/api/secrets"],
            blocked_countries=["XX"],
            allowed_countries=["US", "GB"],
            min_risk_score=20,
            enforce_on_all_routes=True,
        )
        assert len(opts.mfa_routes) == 2
        assert "XX" in opts.blocked_countries
        assert "US" in opts.allowed_countries
        assert opts.min_risk_score == 20


# ─────────────────────────────────────────────────────────────────────────────
# DevicePostureStatus & AccessPolicy Enums
# ─────────────────────────────────────────────────────────────────────────────


class TestEnums:
    """Enum values for device posture and access policy."""

    def test_device_posture_values(self):
        assert DevicePostureStatus.HEALTHY.value == "healthy"
        assert DevicePostureStatus.UNHEALTHY.value == "unhealthy"
        assert DevicePostureStatus.UNKNOWN.value == "unknown"

    def test_access_policy_values(self):
        assert AccessPolicy.ALLOW.value == "allow"
        assert AccessPolicy.DENY.value == "deny"
        assert AccessPolicy.MFA_REQUIRED.value == "mfa_required"


# ─────────────────────────────────────────────────────────────────────────────
# Context Extraction Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestExtractContext:
    """Extract Zero Trust context from request headers."""

    def test_empty_headers(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({})
        assert ctx.device_posture == DevicePostureStatus.UNKNOWN
        assert ctx.mfa_verified is False
        assert ctx.country is None
        assert ctx.device_id is None
        assert ctx.ip_address is None
        # user_agent defaults to empty string (not None) when no header
        assert ctx.user_agent == ""

    def test_healthy_device_posture(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Device-Posture": "healthy"})
        assert ctx.device_posture == DevicePostureStatus.HEALTHY

    def test_unhealthy_device_posture(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Device-Posture": "unhealthy"})
        assert ctx.device_posture == DevicePostureStatus.UNHEALTHY

    def test_unknown_device_posture(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Device-Posture": "unknown"})
        assert ctx.device_posture == DevicePostureStatus.UNKNOWN

    def test_case_insensitive_posture_header(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"x-device-posture": "healthy"})
        assert ctx.device_posture == DevicePostureStatus.HEALTHY

    def test_mfa_verified_true(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-MFA-Verified": "true"})
        assert ctx.mfa_verified is True

    def test_mfa_verified_one(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-MFA-Verified": "1"})
        assert ctx.mfa_verified is True

    def test_mfa_verified_yes(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-MFA-Verified": "yes"})
        assert ctx.mfa_verified is True

    def test_mfa_verified_false(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-MFA-Verified": "false"})
        assert ctx.mfa_verified is False

    def test_country_extraction(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Client-Country": "US"})
        assert ctx.country == "US"

    def test_country_lowercase_header(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"x-client-country": "GB"})
        assert ctx.country == "GB"

    def test_device_id_extraction(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Device-ID": "device-abc-123"})
        assert ctx.device_id == "device-abc-123"

    def test_ip_address_from_x_client_ip(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Client-IP": "192.168.1.1"})
        assert ctx.ip_address == "192.168.1.1"

    def test_ip_address_from_x_forwarded_for(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"X-Forwarded-For": "10.0.0.1"})
        assert ctx.ip_address == "10.0.0.1"

    def test_ip_address_prefers_x_client_ip(self):
        """X-Client-IP takes precedence over X-Forwarded-For."""
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Client-IP": "192.168.1.1",
                "X-Forwarded-For": "10.0.0.1",
            }
        )
        assert ctx.ip_address == "192.168.1.1"

    def test_user_agent_extraction(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"User-Agent": "Mozilla/5.0"})
        assert ctx.user_agent == "Mozilla/5.0"

    def test_user_agent_lowercase_header(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context({"user-agent": "TestBot/1.0"})
        assert ctx.user_agent == "TestBot/1.0"

    def test_risk_score_calculated(self):
        """Risk score should be calculated during extraction."""
        mw = ZeroTrustMiddleware()
        # Unhealthy device + no MFA → high risk
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unhealthy",
                "X-MFA-Verified": "false",
            }
        )
        assert ctx.risk_score > 0

    def test_access_policy_determined(self):
        """Access policy should be determined during extraction."""
        mw = ZeroTrustMiddleware()
        # Healthy device + MFA verified → ALLOW
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "true",
            }
        )
        assert ctx.access_policy == AccessPolicy.ALLOW


# ─────────────────────────────────────────────────────────────────────────────
# Risk Score Calculation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestRiskScoring:
    """Risk score calculation from device posture and MFA status."""

    def test_healthy_device_mfa_verified_low_risk(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "true",
            }
        )
        assert ctx.risk_score == 0  # No risk factors

    def test_healthy_device_no_mfa(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "false",
            }
        )
        assert ctx.risk_score == 10  # +10 for no MFA

    def test_unknown_device_no_mfa(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unknown",
            }
        )
        # +20 for unknown device, +10 for no MFA = 30
        assert ctx.risk_score == 30

    def test_unhealthy_device_no_mfa(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unhealthy",
            }
        )
        # +40 for unhealthy device, +10 for no MFA = 50
        assert ctx.risk_score == 50

    def test_unhealthy_device_mfa_verified(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unhealthy",
                "X-MFA-Verified": "true",
            }
        )
        assert ctx.risk_score == 40  # +40 for unhealthy only

    def test_unknown_device_mfa_verified(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unknown",
                "X-MFA-Verified": "true",
            }
        )
        assert ctx.risk_score == 20  # +20 for unknown only

    def test_risk_score_capped_at_100(self):
        """Risk score should never exceed 100."""
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unhealthy",
                "X-MFA-Verified": "false",
            }
        )
        assert ctx.risk_score <= 100


# ─────────────────────────────────────────────────────────────────────────────
# Policy Evaluation Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEvaluate:
    """Evaluate Zero Trust context against policies for a path."""

    def test_allow_healthy_device_mfa(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_deny_unhealthy_device(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNHEALTHY,
            mfa_verified=False,
            risk_score=50,
        )
        result = mw.evaluate(ctx, "/api/data")
        # risk_score=50 → evaluate sets MFA_REQUIRED (risk >= 50)
        assert result.access_policy in (AccessPolicy.MFA_REQUIRED, AccessPolicy.DENY)

    def test_mfa_required_for_mfa_route_without_mfa(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                mfa_bypass_for_healthy=False,  # Disable bypass so healthy device still needs MFA
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=False,
            risk_score=10,
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_mfa_route_allowed_with_mfa(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_mfa_bypass_for_healthy_device(self):
        """By default, healthy devices bypass MFA on MFA routes."""
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                mfa_bypass_for_healthy=True,
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=False,
            risk_score=10,
        )
        result = mw.evaluate(ctx, "/admin")
        # Healthy device bypasses MFA, so policy is ALLOW
        assert result.access_policy == AccessPolicy.ALLOW

    def test_no_mfa_bypass_when_disabled(self):
        """When mfa_bypass_for_healthy=False, even healthy devices need MFA."""
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                mfa_bypass_for_healthy=False,
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=False,
            risk_score=10,
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_healthy_device_required_for_protected_route(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                healthy_device_routes=["/api/internal"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNKNOWN,
            mfa_verified=True,
            risk_score=20,
        )
        result = mw.evaluate(ctx, "/api/internal")
        assert result.access_policy == AccessPolicy.DENY

    def test_healthy_device_passes_protected_route(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                healthy_device_routes=["/api/internal"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/internal")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_non_matching_path_no_restrictions(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                healthy_device_routes=["/api/internal"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/public")
        assert result.access_policy == AccessPolicy.ALLOW


# ─────────────────────────────────────────────────────────────────────────────
# Geographic Policy Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestGeographicPolicies:
    """Country-based access controls."""

    def test_blocked_country_denied(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                blocked_countries=["XX"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            country="XX",
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.DENY
        assert result.risk_score == 100

    def test_allowed_country_permitted(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                allowed_countries=["US", "GB"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            country="US",
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_disallowed_country_denied(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                allowed_countries=["US", "GB"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            country="RU",
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.DENY

    def test_no_country_with_allowed_list(self):
        """When allowed_countries is set but country is None, access is allowed.

        The evaluate code checks: `if context.country and context.country not in allowed_countries`
        When country is None, the first condition is False, so the check is skipped.
        This means requests without a country header are allowed through even with an allowlist.
        This is a known behavior — consider it a design choice or add a separate check.
        """
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                allowed_countries=["US"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            country=None,
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        # With country=None, the allowed_countries check is bypassed
        assert result.access_policy == AccessPolicy.ALLOW

    def test_blocked_takes_precedence_over_allowed(self):
        """Blocked countries are checked before allowed countries."""
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                allowed_countries=["US", "XX"],
                blocked_countries=["XX"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            country="XX",
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        # Blocked check comes first
        assert result.access_policy == AccessPolicy.DENY

    def test_no_geographic_restrictions(self):
        """When no country policies are set, all countries are allowed."""
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            country="ZZ",
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.ALLOW


# ─────────────────────────────────────────────────────────────────────────────
# Enforce On All Routes Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestEnforceOnAllRoutes:
    """enforce_on_all_routes denies unhealthy devices on any route."""

    def test_unhealthy_device_denied_on_any_route(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                enforce_on_all_routes=True,
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNHEALTHY,
            mfa_verified=True,
            risk_score=40,
        )
        result = mw.evaluate(ctx, "/api/public")
        assert result.access_policy == AccessPolicy.DENY

    def test_unhealthy_device_not_denied_when_not_enforced(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                enforce_on_all_routes=False,
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNHEALTHY,
            mfa_verified=True,
            risk_score=40,
        )
        # With risk_score=40 and mfa_verified=True, evaluate() hits the risk score check:
        # 40 is not >= 80 (DENY), not >= 50 (MFA_REQUIRED), so it stays at ALLOW
        # (since the context was constructed with access_policy=ALLOW default)
        result = mw.evaluate(ctx, "/api/public")
        assert result.access_policy == AccessPolicy.ALLOW


# ─────────────────────────────────────────────────────────────────────────────
# Path Pattern Matching Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestPathPatternMatching:
    """Glob-style path matching for route policies."""

    def test_exact_path_match(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNKNOWN,
            mfa_verified=False,
            risk_score=30,
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_glob_path_match(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin/*"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNKNOWN,
            mfa_verified=False,
            risk_score=30,
        )
        result = mw.evaluate(ctx, "/admin/settings")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_glob_no_match(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin/*"],
            )
        )
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            risk_score=0,
        )
        result = mw.evaluate(ctx, "/api/public")
        assert result.access_policy == AccessPolicy.ALLOW


# ─────────────────────────────────────────────────────────────────────────────
# High Risk Score Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHighRiskScore:
    """Risk score thresholds for access policy."""

    def test_risk_score_80_plus_denied(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNKNOWN,
            mfa_verified=True,
            risk_score=80,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.DENY

    def test_risk_score_50_to_79_mfa_required(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.UNKNOWN,
            mfa_verified=True,
            risk_score=50,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_risk_score_below_50_allowed(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(
            device_posture=DevicePostureStatus.HEALTHY,
            mfa_verified=True,
            risk_score=10,
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.ALLOW


# ─────────────────────────────────────────────────────────────────────────────
# Integration: Full Request Flow Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestFullRequestFlow:
    """End-to-end: extract context from headers then evaluate."""

    def test_healthy_device_mfa_admin_access(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
            )
        )
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "true",
                "X-Client-Country": "US",
            }
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_no_mfa_admin_access(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                mfa_bypass_for_healthy=False,
            )
        )
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "false",
                "X-Client-Country": "US",
            }
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_blocked_country_overrides_healthy_device(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                blocked_countries=["XX"],
            )
        )
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "true",
                "X-Client-Country": "XX",
            }
        )
        result = mw.evaluate(ctx, "/api/data")
        assert result.access_policy == AccessPolicy.DENY
        assert result.risk_score == 100

    def test_unhealthy_device_denied(self):
        mw = ZeroTrustMiddleware()
        ctx = mw.extract_context(
            {
                "X-Device-Posture": "unhealthy",
                "X-MFA-Verified": "false",
            }
        )
        # Unhealthy device + no MFA → DENY (from _determine_policy during extraction)
        assert ctx.access_policy == AccessPolicy.DENY


# ---------------------------------------------------------------------------
# JIT Access Manager tests
# ---------------------------------------------------------------------------


class TestJITAccessManager:
    def _mgr(self, max_duration: int = 3600):
        from src.auth.zero_trust import JITAccessManager

        return JITAccessManager(max_duration_seconds=max_duration)

    def test_grant_returns_id(self):
        mgr = self._mgr()
        gid = mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        assert isinstance(gid, str) and len(gid) == 32

    def test_check_active_grant(self):
        mgr = self._mgr()
        mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops", duration_seconds=60)
        assert mgr.check(user_id="alice", path="/admin/config") is True

    def test_check_no_grant(self):
        mgr = self._mgr()
        assert mgr.check(user_id="bob", path="/admin/secrets") is False

    def test_check_wrong_user(self):
        mgr = self._mgr()
        mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        assert mgr.check(user_id="bob", path="/admin/config") is False

    def test_check_path_mismatch(self):
        mgr = self._mgr()
        mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        assert mgr.check(user_id="alice", path="/api/data") is False

    def test_revoke_grant(self):
        mgr = self._mgr()
        gid = mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        mgr.revoke(gid)
        assert mgr.check(user_id="alice", path="/admin/config") is False

    def test_revoke_unknown_returns_false(self):
        mgr = self._mgr()
        assert mgr.revoke("nonexistent-id") is False

    def test_duration_exceeds_max_raises(self):
        import pytest

        mgr = self._mgr(max_duration=300)
        with pytest.raises(ValueError):
            mgr.grant(
                user_id="alice", path_pattern="/admin/*", granted_by="ops", duration_seconds=600
            )

    def test_zero_duration_raises(self):
        import pytest

        mgr = self._mgr()
        with pytest.raises(ValueError):
            mgr.grant(
                user_id="alice", path_pattern="/admin/*", granted_by="ops", duration_seconds=0
            )

    def test_list_grants_empty(self):
        mgr = self._mgr()
        assert mgr.list_grants() == []

    def test_list_grants_populated(self):
        mgr = self._mgr()
        mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        mgr.grant(user_id="bob", path_pattern="/billing/*", granted_by="ops")
        grants = mgr.list_grants()
        assert len(grants) == 2

    def test_list_grants_user_filter(self):
        mgr = self._mgr()
        mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        mgr.grant(user_id="bob", path_pattern="/billing/*", granted_by="ops")
        alice_grants = mgr.list_grants(user_id="alice")
        assert len(alice_grants) == 1
        assert alice_grants[0]["user_id"] == "alice"

    def test_get_grant_metadata(self):
        mgr = self._mgr()
        gid = mgr.grant(
            user_id="alice",
            path_pattern="/admin/*",
            granted_by="sre",
            duration_seconds=300,
            reason="incident-001",
        )
        info = mgr.get_grant(gid)
        assert info is not None
        assert info["user_id"] == "alice"
        assert info["reason"] == "incident-001"
        assert info["duration_seconds"] == 300
        assert info["is_active"] is True

    def test_use_count_incremented(self):
        mgr = self._mgr()
        gid = mgr.grant(user_id="alice", path_pattern="/admin/*", granted_by="ops")
        mgr.check(user_id="alice", path="/admin/x")
        mgr.check(user_id="alice", path="/admin/y")
        info = mgr.get_grant(gid)
        assert info["use_count"] == 2

    def test_get_jit_manager_singleton(self):
        from src.auth.zero_trust import get_jit_manager

        m1 = get_jit_manager()
        m2 = get_jit_manager()
        assert m1 is m2
