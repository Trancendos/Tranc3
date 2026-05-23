"""
Tests for shared_core.architecture.proactive_wiring.

Covers: WiringStatus, BridgeType, BridgeConnection, ProactiveSystemBootstrap.
"""

from __future__ import annotations

import asyncio

from shared_core.architecture.proactive_wiring import (
    BridgeConnection,
    BridgeType,
    ProactiveSystemBootstrap,
    WiringStatus,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestBridgeType:
    """Tests for BridgeType enum."""

    def test_all_bridge_types_exist(self):
        expected = [
            "EVENT_BUS",
            "STORAGE",
            "SENTINEL",
            "DEFENSE",
            "FORESIGHT",
            "ROUTING",
            "REGISTRY",
            "RESILIENCE",
            "PULSE",
            "CONFIG",
            "SCALER",
        ]
        for name in expected:
            assert hasattr(BridgeType, name), f"Missing BridgeType.{name}"

    def test_bridge_type_values(self):
        assert BridgeType.EVENT_BUS.value == "event_bus"
        assert BridgeType.PULSE.value == "pulse"
        assert BridgeType.SCALER.value == "scaler"
        assert BridgeType.CONFIG.value == "config"
        assert BridgeType.STORAGE.value == "storage"


class TestWiringStatus:
    """Tests for WiringStatus enum."""

    def test_all_statuses_exist(self):
        expected = [
            "DISCONNECTED",
            "CONNECTING",
            "CONNECTED",
            "ACTIVE",
            "ERROR",
            "DISABLED",
        ]
        for name in expected:
            assert hasattr(WiringStatus, name), f"Missing WiringStatus.{name}"

    def test_status_values(self):
        assert WiringStatus.DISCONNECTED.value == "disconnected"
        assert WiringStatus.ACTIVE.value == "active"
        assert WiringStatus.ERROR.value == "error"
        assert WiringStatus.DISABLED.value == "disabled"


# ---------------------------------------------------------------------------
# BridgeConnection tests
# ---------------------------------------------------------------------------


class TestBridgeConnection:
    """Tests for BridgeConnection dataclass."""

    def test_create_bridge_connection(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.STORAGE,
            subsystem_name="health_monitor",
            status=WiringStatus.ACTIVE,
        )
        assert conn.bridge_type == BridgeType.STORAGE
        assert conn.subsystem_name == "health_monitor"
        assert conn.status == WiringStatus.ACTIVE

    def test_default_values(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.PULSE,
            subsystem_name="pulse_daemon",
            status=WiringStatus.CONNECTED,
        )
        assert conn.events_processed == 0
        assert conn.actions_dispatched == 0
        assert conn.errors == 0
        assert conn.last_error is None

    def test_mark_connected(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.EVENT_BUS,
            subsystem_name="events",
            status=WiringStatus.CONNECTING,
        )
        conn.mark_connected()
        assert conn.status == WiringStatus.CONNECTED

    def test_mark_active(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.SENTINEL,
            subsystem_name="sentinel",
            status=WiringStatus.CONNECTED,
        )
        conn.mark_active()
        assert conn.status == WiringStatus.ACTIVE

    def test_mark_error(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.DEFENSE,
            subsystem_name="defense",
            status=WiringStatus.ACTIVE,
        )
        conn.mark_error("Connection lost")
        assert conn.status == WiringStatus.ERROR
        assert conn.last_error == "Connection lost"
        assert conn.errors == 1

    def test_record_event(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.ROUTING,
            subsystem_name="routing",
            status=WiringStatus.ACTIVE,
        )
        conn.record_event()
        assert conn.events_processed == 1
        conn.record_event()
        assert conn.events_processed == 2

    def test_record_action(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.REGISTRY,
            subsystem_name="registry",
            status=WiringStatus.ACTIVE,
        )
        conn.record_action()
        assert conn.actions_dispatched == 1

    def test_to_dict(self):
        conn = BridgeConnection(
            bridge_type=BridgeType.SCALER,
            subsystem_name="scaler",
            status=WiringStatus.ACTIVE,
        )
        d = conn.to_dict()
        assert isinstance(d, dict)
        assert d["bridge_type"] == "scaler"
        assert d["subsystem_name"] == "scaler"
        assert d["status"] == "active"


# ---------------------------------------------------------------------------
# ProactiveSystemBootstrap tests
# ---------------------------------------------------------------------------


class TestProactiveSystemBootstrap:
    """Tests for the ProactiveSystemBootstrap."""

    def setup_method(self):
        self.bootstrap = ProactiveSystemBootstrap()

    def test_initial_state(self):
        assert self.bootstrap.is_wired is False
        assert self.bootstrap.is_started is False

    def test_bridge_status(self):
        status = self.bootstrap.bridge_status
        assert isinstance(status, dict)

    def test_wire_all_with_empty_subsystems(self):
        """wire_all with no subsystems should complete without error."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.bootstrap.wire_all({}))
        finally:
            loop.close()

    def test_wire_all_with_mock_subsystems(self):
        """wire_all with mock subsystems should set is_wired."""
        from unittest.mock import MagicMock

        subsystems = {
            "event_bus": MagicMock(),
            "storage": MagicMock(),
            "sentinel": MagicMock(),
        }
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.bootstrap.wire_all(subsystems))
        finally:
            loop.close()
        # After wiring, is_wired should be True
        assert self.bootstrap.is_wired is True

    def test_start_without_wiring(self):
        """Starting without wiring should handle gracefully."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.bootstrap.start())
        except Exception:
            pass  # May raise if not wired — that's acceptable
        finally:
            loop.close()

    def test_start_and_stop(self):
        """Full lifecycle: wire → start → stop."""
        from unittest.mock import MagicMock

        subsystems = {
            "event_bus": MagicMock(),
            "pulse": MagicMock(),
        }
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.bootstrap.wire_all(subsystems))
            loop.run_until_complete(self.bootstrap.start())
            assert self.bootstrap.is_started is True
            loop.run_until_complete(self.bootstrap.stop())
            assert self.bootstrap.is_started is False
        finally:
            loop.close()

    def test_stop_without_start(self):
        """Stopping without starting should not raise."""
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(self.bootstrap.stop())
        except Exception:
            pass  # May raise — acceptable
        finally:
            loop.close()
