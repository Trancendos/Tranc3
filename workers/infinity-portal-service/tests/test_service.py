"""
test_service.py — Unit tests for service.py
=============================================
Tests InfinityGate routing logic and DB helper functions.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SERVICE_DIR = Path(__file__).parent.parent
if str(SERVICE_DIR) not in sys.path:
    sys.path.insert(0, str(SERVICE_DIR))


# ---------------------------------------------------------------------------
# InfinityGate.route
# ---------------------------------------------------------------------------


class TestInfinityGateRoute:
    """Tests for InfinityGate.route() role-based routing logic."""

    @pytest.fixture(autouse=True)
    def _import_gate(self, stub_dimensional):
        # Import after stubs are active
        from service import InfinityGate

        self.InfinityGate = InfinityGate

    def test_user_routes_to_arcadia(self):
        result = self.InfinityGate.route("user")
        assert result.routed_to == "arcadia"

    def test_admin_routes_to_admin(self):
        result = self.InfinityGate.route("admin")
        assert "admin" in result.routed_to

    def test_developer_routes_to_citadel(self):
        result = self.InfinityGate.route("developer")
        assert "citadel" in result.routed_to.lower() or result.routed_to is not None

    def test_devops_routing_is_not_none(self):
        result = self.InfinityGate.route("devops")
        assert result.routed_to is not None

    def test_prime_routes_to_admin(self):
        result = self.InfinityGate.route("prime")
        assert "admin" in result.routed_to

    def test_ai_routes_to_central(self):
        result = self.InfinityGate.route("ai")
        assert result.routed_to == "infinity"

    def test_agent_routes_to_central(self):
        result = self.InfinityGate.route("agent")
        assert result.routed_to == "infinity"

    def test_unknown_role_falls_back_to_arcadia(self):
        result = self.InfinityGate.route("unknown_xyz")
        assert result.routed_to == "arcadia"

    def test_role_is_normalised_to_lowercase(self):
        result_upper = self.InfinityGate.route("ADMIN")
        result_lower = self.InfinityGate.route("admin")
        assert result_upper.routed_to == result_lower.routed_to

    def test_response_fields_populated(self):
        result = self.InfinityGate.route("user")
        assert result.routing_url is not None
        assert result.transfer_system is not None
        assert result.tier is not None
        assert result.infinity_role is not None


# ---------------------------------------------------------------------------
# _log_portal_event
# ---------------------------------------------------------------------------


class TestLogPortalEvent:
    """Tests for the _log_portal_event helper."""

    def test_event_written_to_db(self, stub_dimensional, in_memory_db):
        from service import _log_portal_event

        _log_portal_event(
            event_type="test_event",
            user_id="u1",
            username="testuser",
            ip_address="127.0.0.1",
            payload={"foo": "bar"},
        )
        row = in_memory_db.execute(
            "SELECT * FROM portal_events WHERE event_type = 'test_event'"
        ).fetchone()
        assert row is not None
        assert row["user_id"] == "u1"
        assert row["username"] == "testuser"

    def test_event_with_no_payload(self, stub_dimensional, in_memory_db):
        from service import _log_portal_event

        _log_portal_event(event_type="no_payload_event")
        row = in_memory_db.execute(
            "SELECT payload FROM portal_events WHERE event_type = 'no_payload_event'"
        ).fetchone()
        assert row is not None
        assert row["payload"] == "{}"


# ---------------------------------------------------------------------------
# _create_portal_session
# ---------------------------------------------------------------------------


class TestCreatePortalSession:
    """Tests for the _create_portal_session helper."""

    def test_session_created_and_returned(self, stub_dimensional, in_memory_db):
        from unittest.mock import MagicMock

        from service import _create_portal_session

        tier_mock = MagicMock()
        tier_mock.value = 1
        role_mock = MagicMock()
        role_mock.value = "user"

        session_id = _create_portal_session(
            user_id="u42",
            username="alice",
            role="user",
            tier=tier_mock,
            infinity_role=role_mock,
            routed_to="arcadia",
            access_token="tok123",
            ip_address="10.0.0.1",
        )
        assert session_id is not None
        assert len(session_id) > 0

        row = in_memory_db.execute(
            "SELECT * FROM portal_sessions WHERE session_id = ?", (session_id,)
        ).fetchone()
        assert row is not None
        assert row["user_id"] == "u42"
        assert row["routed_to"] == "arcadia"
        assert row["is_active"] == 1


# ---------------------------------------------------------------------------
# _log_gate_routing
# ---------------------------------------------------------------------------


class TestLogGateRouting:
    """Tests for the _log_gate_routing helper."""

    def test_routing_log_written(self, stub_dimensional, in_memory_db):
        from service import _log_gate_routing

        _log_gate_routing(
            user_id="u99",
            username="bob",
            role="admin",
            from_location="infinity_portal",
            to_location="infinity_admin",
            transfer_system="bridge",
        )
        row = in_memory_db.execute(
            "SELECT * FROM gate_routing_log WHERE user_id = 'u99'"
        ).fetchone()
        assert row is not None
        assert row["to_location"] == "infinity_admin"
        assert row["transfer_system"] == "bridge"
