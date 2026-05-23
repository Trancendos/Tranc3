# tests/test_auth.py — Tests for src/auth/zero_trust.py
"""Comprehensive tests for the Zero Trust IAM middleware."""

from __future__ import annotations

import pytest

from src.auth.zero_trust import (
    AccessPolicy,
    DevicePostureStatus,
    ZeroTrustContext,
    ZeroTrustMiddleware,
    ZeroTrustOptions,
)


# ── Enum tests ──────────────────────────────────────────────────────────────


class TestDevicePostureStatus:
    def test_values(self):
        assert DevicePostureStatus.HEALTHY == "healthy"
        assert DevicePostureStatus.UNHEALTHY == "unhealthy"
        assert DevicePostureStatus.UNKNOWN == "unknown"

    def test_from_value(self):
        assert DevicePostureStatus("healthy") == DevicePostureStatus.HEALTHY
        assert DevicePostureStatus("unhealthy") == DevicePostureStatus.UNHEALTHY
        assert DevicePostureStatus("unknown") == DevicePostureStatus.UNKNOWN

    def test_is_str(self):
        for member in DevicePostureStatus:
            assert isinstance(member, str)


class TestAccessPolicy:
    def test_values(self):
        assert AccessPolicy.ALLOW == "allow"
        assert AccessPolicy.DENY == "deny"
        assert AccessPolicy.MFA_REQUIRED == "mfa_required"

    def test_from_value(self):
        assert AccessPolicy("allow") == AccessPolicy.ALLOW
        assert AccessPolicy("deny") == AccessPolicy.DENY
        assert AccessPolicy("mfa_required") == AccessPolicy.MFA_REQUIRED


# ── Model tests ─────────────────────────────────────────────────────────────


class TestZeroTrustContext:
    def test_defaults(self):
        ctx = ZeroTrustContext()
        assert ctx.device_id is None
        assert ctx.device_posture == DevicePostureStatus.UNKNOWN
        assert ctx.country is None
        assert ctx.mfa_verified is False
        assert ctx.access_policy == AccessPolicy.ALLOW
        assert ctx.risk_score == 0
        assert ctx.ip_address is None
        assert ctx.user_agent is None

    def test_custom_values(self):
        ctx = ZeroTrustContext(
            device_id="dev-123",
            device_posture=DevicePostureStatus.HEALTHY,
            country="US",
            mfa_verified=True,
            access_policy=AccessPolicy.ALLOW,
            risk_score=10,
            ip_address="1.2.3.4",
            user_agent="test-agent",
        )
        assert ctx.device_id == "dev-123"
        assert ctx.device_posture == DevicePostureStatus.HEALTHY
        assert ctx.country == "US"
        assert ctx.mfa_verified is True
        assert ctx.risk_score == 10
        assert ctx.ip_address == "1.2.3.4"
        assert ctx.user_agent == "test-agent"

    def test_risk_score_bounds(self):
        with pytest.raises(Exception):
            ZeroTrustContext(risk_score=-1)
        with pytest.raises(Exception):
            ZeroTrustContext(risk_score=101)


class TestZeroTrustOptions:
    def test_defaults(self):
        opts = ZeroTrustOptions()
        assert opts.mfa_routes == []
        assert opts.healthy_device_routes == []
        assert opts.allowed_countries == []
        assert opts.blocked_countries == []
        assert opts.min_risk_score == 0
        assert opts.enforce_on_all_routes is False
        assert opts.mfa_bypass_for_healthy is True

    def test_custom_config(self):
        opts = ZeroTrustOptions(
            mfa_routes=["/admin", "/api/secrets"],
            blocked_countries=["XX"],
            allowed_countries=["US", "GB"],
            min_risk_score=30,
            enforce_on_all_routes=True,
            mfa_bypass_for_healthy=False,
        )
        assert opts.mfa_routes == ["/admin", "/api/secrets"]
        assert opts.blocked_countries == ["XX"]
        assert opts.allowed_countries == ["US", "GB"]
        assert opts.min_risk_score == 30
        assert opts.enforce_on_all_routes is True
        assert opts.mfa_bypass_for_healthy is False


# ── Middleware tests ─────────────────────────────────────────────────────────


class TestZeroTrustMiddleware:
    def setup_method(self):
        self.mw = ZeroTrustMiddleware()

    # ── extract_context ─────────────────────────────────────────────────

    def test_extract_context_empty_headers(self):
        ctx = self.mw.extract_context({})
        assert ctx.device_posture == DevicePostureStatus.UNKNOWN
        assert ctx.mfa_verified is False
        assert ctx.country is None
        assert ctx.device_id is None
        assert ctx.ip_address is None

    def test_extract_context_healthy_device(self):
        ctx = self.mw.extract_context({"X-Device-Posture": "healthy"})
        assert ctx.device_posture == DevicePostureStatus.HEALTHY

    def test_extract_context_unhealthy_device(self):
        ctx = self.mw.extract_context({"X-Device-Posture": "unhealthy"})
        assert ctx.device_posture == DevicePostureStatus.UNHEALTHY

    def test_extract_context_lowercase_headers(self):
        ctx = self.mw.extract_context({"x-device-posture": "healthy"})
        assert ctx.device_posture == DevicePostureStatus.HEALTHY

    def test_extract_context_mfa_verified_true(self):
        ctx = self.mw.extract_context({"X-MFA-Verified": "true"})
        assert ctx.mfa_verified is True

    def test_extract_context_mfa_verified_1(self):
        ctx = self.mw.extract_context({"X-MFA-Verified": "1"})
        assert ctx.mfa_verified is True

    def test_extract_context_mfa_verified_yes(self):
        ctx = self.mw.extract_context({"X-MFA-Verified": "yes"})
        assert ctx.mfa_verified is True

    def test_extract_context_mfa_not_verified(self):
        ctx = self.mw.extract_context({"X-MFA-Verified": "false"})
        assert ctx.mfa_verified is False

    def test_extract_context_country(self):
        ctx = self.mw.extract_context({"X-Client-Country": "US"})
        assert ctx.country == "US"

    def test_extract_context_device_id(self):
        ctx = self.mw.extract_context({"X-Device-ID": "dev-abc"})
        assert ctx.device_id == "dev-abc"

    def test_extract_context_ip_from_x_client_ip(self):
        ctx = self.mw.extract_context({"X-Client-IP": "10.0.0.1"})
        assert ctx.ip_address == "10.0.0.1"

    def test_extract_context_ip_from_x_forwarded_for(self):
        ctx = self.mw.extract_context({"X-Forwarded-For": "10.0.0.2"})
        assert ctx.ip_address == "10.0.0.2"

    def test_extract_context_ip_x_client_ip_takes_precedence(self):
        ctx = self.mw.extract_context(
            {
                "X-Client-IP": "10.0.0.1",
                "X-Forwarded-For": "10.0.0.2",
            }
        )
        assert ctx.ip_address == "10.0.0.1"

    def test_extract_context_user_agent(self):
        ctx = self.mw.extract_context({"User-Agent": "Mozilla/5.0"})
        assert ctx.user_agent == "Mozilla/5.0"

    def test_extract_context_user_agent_lowercase(self):
        ctx = self.mw.extract_context({"user-agent": "curl/7.0"})
        assert ctx.user_agent == "curl/7.0"

    def test_extract_context_risk_score_healthy_mfa(self):
        ctx = self.mw.extract_context(
            {
                "X-Device-Posture": "healthy",
                "X-MFA-Verified": "true",
            }
        )
        assert ctx.risk_score == 0

    def test_extract_context_risk_score_unhealthy(self):
        ctx = self.mw.extract_context({"X-Device-Posture": "unhealthy"})
        # unhealthy=40 + no MFA=10 = 50
        assert ctx.risk_score == 50

    def test_extract_context_risk_score_unknown_no_mfa(self):
        ctx = self.mw.extract_context({})
        assert ctx.risk_score == 30  # unknown(20) + no MFA(10)

    # ── evaluate ────────────────────────────────────────────────────────

    def test_evaluate_blocked_country(self):
        mw = ZeroTrustMiddleware(ZeroTrustOptions(blocked_countries=["XX"]))
        ctx = ZeroTrustContext(country="XX")
        result = mw.evaluate(ctx, "/any")
        assert result.access_policy == AccessPolicy.DENY
        assert result.risk_score == 100

    def test_evaluate_allowed_country(self):
        mw = ZeroTrustMiddleware(ZeroTrustOptions(allowed_countries=["US"]))
        ctx = ZeroTrustContext(country="US")
        result = mw.evaluate(ctx, "/any")
        assert result.access_policy != AccessPolicy.DENY

    def test_evaluate_disallowed_country(self):
        mw = ZeroTrustMiddleware(ZeroTrustOptions(allowed_countries=["US"]))
        ctx = ZeroTrustContext(country="RU")
        result = mw.evaluate(ctx, "/any")
        assert result.access_policy == AccessPolicy.DENY

    def test_evaluate_mfa_route_not_verified(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                mfa_bypass_for_healthy=False,
            )
        )
        ctx = ZeroTrustContext(mfa_verified=False)
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_evaluate_mfa_route_verified(self):
        mw = ZeroTrustMiddleware(ZeroTrustOptions(mfa_routes=["/admin"]))
        ctx = ZeroTrustContext(mfa_verified=True)
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_evaluate_mfa_bypass_for_healthy(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin"],
                mfa_bypass_for_healthy=True,
            )
        )
        ctx = ZeroTrustContext(
            mfa_verified=False,
            device_posture=DevicePostureStatus.HEALTHY,
        )
        result = mw.evaluate(ctx, "/admin")
        assert result.access_policy == AccessPolicy.ALLOW

    def test_evaluate_healthy_device_route(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                healthy_device_routes=["/secrets"],
            )
        )
        ctx = ZeroTrustContext(device_posture=DevicePostureStatus.HEALTHY)
        result = mw.evaluate(ctx, "/secrets")
        assert result.access_policy != AccessPolicy.DENY

    def test_evaluate_unhealthy_device_on_device_route(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                healthy_device_routes=["/secrets"],
            )
        )
        ctx = ZeroTrustContext(device_posture=DevicePostureStatus.UNHEALTHY)
        result = mw.evaluate(ctx, "/secrets")
        assert result.access_policy == AccessPolicy.DENY

    def test_evaluate_enforce_on_all_routes_unhealthy(self):
        mw = ZeroTrustMiddleware(ZeroTrustOptions(enforce_on_all_routes=True))
        ctx = ZeroTrustContext(device_posture=DevicePostureStatus.UNHEALTHY)
        result = mw.evaluate(ctx, "/any")
        assert result.access_policy == AccessPolicy.DENY

    def test_evaluate_high_risk_score(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(risk_score=85)
        result = mw.evaluate(ctx, "/any")
        assert result.access_policy == AccessPolicy.DENY

    def test_evaluate_medium_risk_score(self):
        mw = ZeroTrustMiddleware()
        ctx = ZeroTrustContext(risk_score=55)
        result = mw.evaluate(ctx, "/any")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    def test_evaluate_glob_pattern_mfa(self):
        mw = ZeroTrustMiddleware(
            ZeroTrustOptions(
                mfa_routes=["/admin/*"],
                mfa_bypass_for_healthy=False,
            )
        )
        ctx = ZeroTrustContext(mfa_verified=False)
        result = mw.evaluate(ctx, "/admin/settings")
        assert result.access_policy == AccessPolicy.MFA_REQUIRED

    # ── _calculate_risk_score ───────────────────────────────────────────

    def test_calculate_risk_score_healthy_mfa(self):
        score = self.mw._calculate_risk_score(DevicePostureStatus.HEALTHY, True, None)
        assert score == 0

    def test_calculate_risk_score_unhealthy(self):
        score = self.mw._calculate_risk_score(DevicePostureStatus.UNHEALTHY, True, None)
        assert score == 40

    def test_calculate_risk_score_unknown_no_mfa(self):
        score = self.mw._calculate_risk_score(DevicePostureStatus.UNKNOWN, False, None)
        assert score == 30

    def test_calculate_risk_score_healthy_no_mfa(self):
        score = self.mw._calculate_risk_score(DevicePostureStatus.HEALTHY, False, None)
        assert score == 10

    # ── _determine_policy ───────────────────────────────────────────────

    def test_determine_policy_healthy_mfa(self):
        policy = self.mw._determine_policy(DevicePostureStatus.HEALTHY, True, 0)
        assert policy == AccessPolicy.ALLOW

    def test_determine_policy_unhealthy(self):
        policy = self.mw._determine_policy(DevicePostureStatus.UNHEALTHY, True, 40)
        assert policy == AccessPolicy.DENY

    def test_determine_policy_no_mfa(self):
        policy = self.mw._determine_policy(DevicePostureStatus.HEALTHY, False, 10)
        assert policy == AccessPolicy.MFA_REQUIRED
