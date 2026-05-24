"""
tests/test_infinity_portal.py
Phase 22 — Infinity Portal service unit tests.
Tests: gate routing tiers, role maps, SentinelChannel, Tier enum.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-portal-000001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-portal-00001")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared_core.infinity.nomenclature import (
    ROLE_INFINITY_ROLE_MAP,
    ROLE_TIER_MAP,
    InfinityLocation,
    InfinityRole,
    SentinelChannel,
    Tier,
)


# ---------------------------------------------------------------------------
# Infinity Gate routing — tier resolution
# ---------------------------------------------------------------------------
class TestInfinityGateRouting:
    """Verify ROLE_TIER_MAP and ROLE_INFINITY_ROLE_MAP are DRY and correct."""

    def test_admin_tier_is_0(self):
        assert ROLE_TIER_MAP["admin"] == 0

    def test_user_tier_is_0(self):
        assert ROLE_TIER_MAP["user"] == 0

    def test_developer_tier_is_0(self):
        assert ROLE_TIER_MAP["developer"] == 0

    def test_prime_tier_is_2(self):
        assert ROLE_TIER_MAP["prime"] == 2

    def test_ai_tier_is_3(self):
        assert ROLE_TIER_MAP["ai"] == 3

    def test_agent_tier_is_4(self):
        assert ROLE_TIER_MAP["agent"] == 4

    def test_bot_tier_is_5(self):
        assert ROLE_TIER_MAP["bot"] == 5

    def test_service_tier_is_5(self):
        assert ROLE_TIER_MAP["service"] == 5

    def test_admin_infinity_role_is_admin_or_prime(self):
        """Admin role should map to either ADMIN or PRIME infinity role."""
        inf_role = ROLE_INFINITY_ROLE_MAP["admin"]
        valid = {InfinityRole.ADMIN, InfinityRole.PRIME}
        assert inf_role in valid, f"Expected admin→ADMIN/PRIME, got {inf_role}"

    def test_user_infinity_role_is_user(self):
        assert ROLE_INFINITY_ROLE_MAP["user"] == InfinityRole.USER

    def test_ai_infinity_role_is_ai(self):
        assert ROLE_INFINITY_ROLE_MAP["ai"] == InfinityRole.AI

    def test_agent_infinity_role_is_agent(self):
        assert ROLE_INFINITY_ROLE_MAP["agent"] == InfinityRole.AGENT

    def test_bot_infinity_role_is_bot(self):
        assert ROLE_INFINITY_ROLE_MAP["bot"] == InfinityRole.BOT

    def test_all_roles_have_tier_mapping(self):
        known_roles = {
            "admin",
            "user",
            "developer",
            "devops",
            "prime",
            "ai",
            "agent",
            "bot",
            "service",
        }
        for role in known_roles:
            assert role in ROLE_TIER_MAP, f"'{role}' missing from ROLE_TIER_MAP"

    def test_all_roles_have_infinity_role_mapping(self):
        known_roles = {
            "admin",
            "user",
            "developer",
            "devops",
            "prime",
            "ai",
            "agent",
            "bot",
            "service",
        }
        for role in known_roles:
            assert role in ROLE_INFINITY_ROLE_MAP, f"'{role}' missing from ROLE_INFINITY_ROLE_MAP"


# ---------------------------------------------------------------------------
# InfinityLocation enum
# ---------------------------------------------------------------------------
class TestInfinityLocation:
    def test_admin_location_exists(self):
        assert InfinityLocation.ADMIN is not None

    def test_arcadia_location_exists(self):
        assert InfinityLocation.ARCADIA is not None

    def test_citadel_location_exists(self):
        assert InfinityLocation.CITADEL is not None

    def test_location_values_are_strings(self):
        for loc in InfinityLocation:
            assert isinstance(loc.value, str), f"InfinityLocation.{loc.name}.value is not str"


# ---------------------------------------------------------------------------
# SentinelChannel enum
# ---------------------------------------------------------------------------
class TestSentinelChannels:
    def test_platform_channel(self):
        assert SentinelChannel.PLATFORM is not None

    def test_security_channel(self):
        assert SentinelChannel.SECURITY is not None

    def test_bridge_channel(self):
        assert SentinelChannel.BRIDGE is not None

    def test_agents_channel(self):
        # Channel is AGENTS (plural) in the actual nomenclature
        assert SentinelChannel.AGENTS is not None

    def test_all_channels_have_string_values(self):
        for ch in SentinelChannel:
            assert isinstance(ch.value, str), f"SentinelChannel.{ch.name}.value is not str"


# ---------------------------------------------------------------------------
# Tier enum completeness
# ---------------------------------------------------------------------------
class TestTierEnum:
    def test_all_tiers_present(self):
        tier_values = {t.value for t in Tier}
        for n in range(6):  # 0-5
            assert n in tier_values, f"Tier {n} missing from Tier enum"

    def test_tier_human_is_0(self):
        assert Tier.HUMAN.value == 0

    def test_tier_orchestrator_is_1(self):
        assert Tier.ORCHESTRATOR.value == 1

    def test_tier_prime_is_2(self):
        assert Tier.PRIME.value == 2

    def test_tier_ai_is_3(self):
        assert Tier.AI.value == 3

    def test_tier_agent_is_4(self):
        assert Tier.AGENT.value == 4

    def test_tier_bot_is_5(self):
        assert Tier.BOT.value == 5
