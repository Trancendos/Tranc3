"""
tests/test_infinity_admin.py
Phase 22 — Infinity Admin service unit tests.
Tests: RBAC engine, Permission enum, Sentinel config, INFINITY_LOCATIONS,
       GATE_ROUTING structure.
"""

from __future__ import annotations

import os
import sys

os.environ.setdefault("SECRET_KEY", "test-secret-key-admin-00001")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-admin-000001")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from shared_core.infinity.nomenclature import (
    GATE_ROUTING,
    INFINITY_LOCATIONS,
    SENTINEL_CHANNELS,
    InfinityLocation,
    SentinelChannel,
)
from shared_core.infinity.rbac import Permission, RBACEngine


# ---------------------------------------------------------------------------
# RBAC Engine
# ---------------------------------------------------------------------------
class TestRBACEngine:
    def setup_method(self):
        self.rbac = RBACEngine()

    def test_instantiation(self):
        assert self.rbac is not None

    def test_check_permission_method_exists(self):
        assert hasattr(self.rbac, "check_permission")

    def test_check_access_method_exists(self):
        assert hasattr(self.rbac, "check_access")

    def test_get_user_permissions_returns_something_for_admin(self):
        # get_user_permissions expects a dict with 'role' key
        perms = self.rbac.get_user_permissions({"role": "admin", "tier": 0})
        assert perms is not None

    def test_get_user_permissions_returns_something_for_user(self):
        perms = self.rbac.get_user_permissions({"role": "user", "tier": 0})
        assert perms is not None

    def test_admin_has_more_permissions_than_user(self):
        admin_perms = self.rbac.get_user_permissions({"role": "admin", "tier": 0})
        user_perms = self.rbac.get_user_permissions({"role": "user", "tier": 0})
        # Admin should have at least as many permissions as user
        assert len(admin_perms) >= len(user_perms)


# ---------------------------------------------------------------------------
# Permission enum
# ---------------------------------------------------------------------------
class TestPermissionEnum:
    def test_read_permission_exists(self):
        # Permissions use READ_* pattern
        read_perms = [p for p in Permission if p.name.startswith("READ")]
        assert len(read_perms) > 0

    def test_write_permission_exists(self):
        write_perms = [p for p in Permission if p.name.startswith("WRITE")]
        assert len(write_perms) > 0

    def test_admin_permission_exists(self):
        admin_perms = [p for p in Permission if p.name.startswith("ADMIN")]
        assert len(admin_perms) > 0

    def test_all_permissions_have_integer_or_string_values(self):
        for perm in Permission:
            assert isinstance(perm.value, (str, int)), (
                f"Permission.{perm.name}.value is unexpected type: {type(perm.value)}"
            )

    def test_at_least_5_permissions(self):
        assert len(list(Permission)) >= 5


# ---------------------------------------------------------------------------
# Sentinel Station config
# ---------------------------------------------------------------------------
class TestSentinelChannelConfig:
    def test_sentinel_channels_dict_populated(self):
        assert len(SENTINEL_CHANNELS) > 0

    def test_platform_channel_in_config(self):
        assert SentinelChannel.PLATFORM in SENTINEL_CHANNELS

    def test_security_channel_in_config(self):
        assert SentinelChannel.SECURITY in SENTINEL_CHANNELS

    def test_all_channels_have_name_key(self):
        for ch, cfg in SENTINEL_CHANNELS.items():
            assert "name" in cfg, f"Channel {ch} has no 'name' key"

    def test_all_channels_have_description_key(self):
        for ch, cfg in SENTINEL_CHANNELS.items():
            assert "description" in cfg, f"Channel {ch} has no 'description' key"


# ---------------------------------------------------------------------------
# Infinity Locations
# ---------------------------------------------------------------------------
class TestInfinityLocations:
    def test_locations_not_empty(self):
        assert len(INFINITY_LOCATIONS) > 0

    def test_location_keys_are_infinity_location_enum(self):
        for key in INFINITY_LOCATIONS:
            assert isinstance(key, InfinityLocation), f"Key {key!r} is not InfinityLocation"

    def test_each_location_has_name(self):
        for loc, cfg in INFINITY_LOCATIONS.items():
            assert "name" in cfg, f"Location {loc} missing 'name'"

    def test_each_location_has_purpose(self):
        for loc, cfg in INFINITY_LOCATIONS.items():
            assert "purpose" in cfg, f"Location {loc} missing 'purpose'"


# ---------------------------------------------------------------------------
# Gate Routing config
# ---------------------------------------------------------------------------
class TestGateRouting:
    def test_gate_routing_not_empty(self):
        assert len(GATE_ROUTING) > 0

    def test_admin_route_exists(self):
        assert "admin" in GATE_ROUTING

    def test_user_route_exists(self):
        assert "user" in GATE_ROUTING

    def test_gate_routing_values_are_infinity_location(self):
        """GATE_ROUTING maps role → InfinityLocation enum member."""
        for role, location in GATE_ROUTING.items():
            assert isinstance(location, InfinityLocation), (
                f"GATE_ROUTING['{role}'] = {location!r} is not InfinityLocation"
            )

    def test_admin_routes_to_admin_location(self):
        assert GATE_ROUTING["admin"] == InfinityLocation.ADMIN

    def test_user_routes_to_arcadia(self):
        assert GATE_ROUTING["user"] == InfinityLocation.ARCADIA
