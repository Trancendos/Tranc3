"""
tests/test_infinity_one.py
Phase 22 — Infinity One (single identity) unit tests.
Tests: InfinityRole enum, Pillar enum, role/tier mapping correctness.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-one-00001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-one-000001")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Dimensional.infinity.nomenclature import (
    PILLAR_DISPLAY_NAMES,
    ROLE_INFINITY_ROLE_MAP,
    ROLE_TIER_MAP,
    InfinityRole,
    Pillar,
)


# ---------------------------------------------------------------------------
# InfinityRole enum
# ---------------------------------------------------------------------------
class TestInfinityRoleEnum:
    def test_user_role_value(self):
        assert InfinityRole.USER.value == "user"

    def test_admin_role_exists(self):
        assert InfinityRole.ADMIN is not None

    def test_prime_role_exists(self):
        assert InfinityRole.PRIME is not None

    def test_ai_role_value(self):
        assert InfinityRole.AI.value == "ai"

    def test_agent_role_value(self):
        assert InfinityRole.AGENT.value == "agent"

    def test_bot_role_value(self):
        assert InfinityRole.BOT.value == "bot"

    def test_all_roles_have_string_values(self):
        for role in InfinityRole:
            assert isinstance(role.value, str), f"InfinityRole.{role.name} value is not a string"


# ---------------------------------------------------------------------------
# Pillar system
# ---------------------------------------------------------------------------
class TestPillarSystem:
    def test_pillar_display_names_not_empty(self):
        assert len(PILLAR_DISPLAY_NAMES) > 0

    def test_security_pillar_exists(self):
        assert Pillar.SECURITY in PILLAR_DISPLAY_NAMES

    def test_all_display_names_are_strings(self):
        for pillar, name in PILLAR_DISPLAY_NAMES.items():
            assert isinstance(name, str), f"Pillar {pillar} has non-string display name"

    def test_pillar_values_are_strings(self):
        for p in Pillar:
            assert isinstance(p.value, str)

    def test_at_least_5_pillars(self):
        assert len(list(Pillar)) >= 5


# ---------------------------------------------------------------------------
# Role → Tier mapping correctness
# ---------------------------------------------------------------------------
class TestRoleTierMapping:
    def test_human_tier_roles_all_return_0(self):
        human_roles = ["admin", "user", "developer", "devops"]
        for role in human_roles:
            assert ROLE_TIER_MAP[role] == 0, f"Expected tier 0 for role '{role}'"

    def test_prime_role_returns_tier_2(self):
        assert ROLE_TIER_MAP["prime"] == 2

    def test_ai_role_returns_tier_3(self):
        assert ROLE_TIER_MAP["ai"] == 3

    def test_agent_role_returns_tier_4(self):
        assert ROLE_TIER_MAP["agent"] == 4

    def test_bot_service_roles_return_tier_5(self):
        assert ROLE_TIER_MAP["bot"] == 5
        assert ROLE_TIER_MAP["service"] == 5

    def test_no_negative_tiers(self):
        for role, tier in ROLE_TIER_MAP.items():
            assert tier >= 0, f"Role '{role}' has negative tier {tier}"

    def test_no_tier_above_5(self):
        for role, tier in ROLE_TIER_MAP.items():
            assert tier <= 5, f"Role '{role}' has tier {tier} > 5"


# ---------------------------------------------------------------------------
# Role → InfinityRole mapping correctness
# ---------------------------------------------------------------------------
class TestRoleInfinityRoleMapping:
    def test_admin_maps_to_admin_or_prime_role(self):
        """Admin must map to an elevated InfinityRole."""
        inf_role = ROLE_INFINITY_ROLE_MAP["admin"]
        elevated = {InfinityRole.ADMIN, InfinityRole.PRIME}
        assert inf_role in elevated, f"Expected admin → ADMIN/PRIME, got {inf_role}"

    def test_user_maps_to_user(self):
        assert ROLE_INFINITY_ROLE_MAP["user"] == InfinityRole.USER

    def test_developer_has_mapping(self):
        assert "developer" in ROLE_INFINITY_ROLE_MAP

    def test_all_mappings_are_valid_infinity_roles(self):
        valid_values = set(InfinityRole)
        for role, inf_role in ROLE_INFINITY_ROLE_MAP.items():
            assert inf_role in valid_values, (
                f"Role '{role}' maps to '{inf_role}' which is not a valid InfinityRole"
            )
