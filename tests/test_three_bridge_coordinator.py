"""
Tranc3 Three-Bridge Coordinator Tests
======================================
Tests for the ThreeBridgeCoordinator that wires all three bridges
together through Sentinel Station.

Tests verify:
    - Coordinator lifecycle (start/stop)
    - Bridge health monitoring
    - Cross-bridge event tracking
    - Traffic separation enforcement at the coordinator level
    - Unified status reporting
    - Singleton pattern
"""

import asyncio
# Note: Direct _sentinel_station assignment used instead of patch.object
# because sentinel_station is a property without a setter

from Dimensional.three_bridge_coordinator import (
    BridgeIdentity,
    CoordinatorState,
    CrossBridgeEvent,
    ThreeBridgeCoordinator,
    get_coordinator,
)
from Dimensional.infinity.bridge.bridge_core import (
    InfinityBridge,
)
from Dimensional.nexus.nexus_core import Nexus
from Dimensional.hive.hive_core import Hive


def run_async(coro):
    """Run an async coroutine in a sync test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── Coordinator Lifecycle Tests ────────────────────────────────────────────

class TestCoordinatorLifecycle:
    """Tests for the coordinator start/stop lifecycle."""

    def test_initial_state(self):
        """Coordinator starts in STOPPED state."""
        coordinator = ThreeBridgeCoordinator()
        assert coordinator.state == CoordinatorState.STOPPED
        assert not coordinator.is_running

    def test_start_transitions_to_running(self):
        """Starting the coordinator transitions to RUNNING state."""
        coordinator = ThreeBridgeCoordinator()
        # Bypass sentinel station to avoid actual Redis connection
        coordinator._sentinel_station = None
        run_async(coordinator.start())
        assert coordinator.is_running
        assert coordinator.state == CoordinatorState.RUNNING

    def test_stop_transitions_to_stopped(self):
        """Stopping the coordinator transitions to STOPPED state."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        run_async(coordinator.start())
        run_async(coordinator.stop())
        assert coordinator.state == CoordinatorState.STOPPED
        assert not coordinator.is_running

    def test_double_start_is_idempotent(self):
        """Starting twice doesn't change state."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        run_async(coordinator.start())
        run_async(coordinator.start())  # Should not raise
        assert coordinator.state == CoordinatorState.RUNNING

    def test_double_stop_is_idempotent(self):
        """Stopping twice doesn't change state."""
        coordinator = ThreeBridgeCoordinator()
        run_async(coordinator.stop())  # Should not raise
        assert coordinator.state == CoordinatorState.STOPPED

    def test_start_increments_start_count(self):
        """Starting the coordinator increments the start counter."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        run_async(coordinator.start())
        assert coordinator.get_stats()["start_count"] == 1

    def test_stop_increments_stop_count(self):
        """Stopping the coordinator increments the stop counter."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        run_async(coordinator.start())
        run_async(coordinator.stop())
        assert coordinator.get_stats()["stop_count"] == 1


# ── Bridge Health Tests ───────────────────────────────────────────────────

class TestBridgeHealth:
    """Tests for bridge health monitoring."""

    def test_infinity_bridge_health(self):
        """InfinityBridge health reports correctly."""
        coordinator = ThreeBridgeCoordinator()
        health = coordinator.get_bridge_health(BridgeIdentity.INFINITY_BRIDGE.value)
        assert health.bridge_type == "infinity"
        assert health.healthy is True
        assert health.sentinel_attached is False  # Not started yet

    def test_nexus_health(self):
        """Nexus health reports correctly."""
        coordinator = ThreeBridgeCoordinator()
        health = coordinator.get_bridge_health(BridgeIdentity.NEXUS.value)
        assert health.bridge_type == "nexus"
        assert health.healthy is True
        assert health.sentinel_attached is False

    def test_hive_health(self):
        """HIVE health reports correctly."""
        coordinator = ThreeBridgeCoordinator()
        health = coordinator.get_bridge_health(BridgeIdentity.HIVE.value)
        assert health.bridge_type == "hive"
        assert health.healthy is True
        assert health.sentinel_attached is False

    def test_unknown_bridge_health(self):
        """Unknown bridge type returns unhealthy."""
        coordinator = ThreeBridgeCoordinator()
        health = coordinator.get_bridge_health("unknown")
        assert health.healthy is False
        assert health.error is not None

    def test_infinity_bridge_health_after_connect(self):
        """InfinityBridge health reflects connected users."""
        coordinator = ThreeBridgeCoordinator()
        coordinator.infinity_bridge.connect_user("user-1")
        health = coordinator.get_bridge_health(BridgeIdentity.INFINITY_BRIDGE.value)
        assert health.healthy is True
        assert health.stats["users"]["total"] == 1


# ── Unified Status Tests ──────────────────────────────────────────────────

class TestUnifiedStatus:
    """Tests for the unified status endpoint."""

    def test_unified_status_structure(self):
        """Unified status contains all required sections."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        assert "coordinator" in status
        assert "three_bridges" in status
        assert "traffic_separation" in status
        assert "cross_bridge_events" in status
        assert "stats" in status
        assert "tier_system" in status
        assert "port_assignments" in status
        assert "transfer_systems" in status

    def test_unified_status_contains_all_bridges(self):
        """Unified status includes all three bridges."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        bridges = status["three_bridges"]
        assert "infinity_bridge" in bridges
        assert "nexus" in bridges
        assert "hive" in bridges

    def test_unified_status_bridge_types(self):
        """Each bridge in unified status reports correct bridge_type."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        bridges = status["three_bridges"]
        assert bridges["infinity_bridge"]["bridge_type"] == "infinity"
        assert bridges["nexus"]["bridge_type"] == "nexus"
        assert bridges["hive"]["bridge_type"] == "hive"

    def test_traffic_separation_descriptions(self):
        """Traffic separation section describes each bridge's domain."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        ts = status["traffic_separation"]
        assert "infinity_bridge" in ts
        assert "nexus" in ts
        assert "hive" in ts
        assert "cross_bridge" in ts

    def test_tier_system_in_status(self):
        """Tier system is included in unified status."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        tiers = status["tier_system"]
        assert tiers["HUMAN"] == 0
        assert tiers["AI"] == 3
        assert tiers["BOT"] == 5

    def test_port_assignments_in_status(self):
        """Port assignments are included in unified status."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        ports = status["port_assignments"]
        assert ports["nexus"] == 8050
        assert ports["hive"] == 8060
        assert ports["infinity_bridge"] == 8070

    def test_transfer_systems_in_status(self):
        """Transfer systems are included in unified status."""
        coordinator = ThreeBridgeCoordinator()
        status = run_async(coordinator.get_unified_status())
        systems = status["transfer_systems"]
        assert "nexus" in systems
        assert "hive" in systems
        assert "bridge" in systems


# ── Cross-Bridge Event Tests ──────────────────────────────────────────────

class TestCrossBridgeEvents:
    """Tests for cross-bridge event tracking and forwarding."""

    def test_cross_bridge_event_creation(self):
        """CrossBridgeEvent can be created and serialized."""
        event = CrossBridgeEvent(
            event_id="test-123",
            source_bridge="infinity",
            target_bridges=["nexus", "hive"],
            sentinel_channel="bridge",
            event_type="user_transition",
            payload={"user_id": "user-1"},
        )
        d = event.to_dict()
        assert d["source_bridge"] == "infinity"
        assert d["target_bridges"] == ["nexus", "hive"]
        assert d["event_type"] == "user_transition"
        assert d["payload"]["user_id"] == "user-1"

    def test_cross_bridge_event_tracking(self):
        """Cross-bridge events are tracked by the coordinator."""
        coordinator = ThreeBridgeCoordinator()
        event = CrossBridgeEvent(
            source_bridge="nexus",
            target_bridges=["infinity", "hive"],
            sentinel_channel="nexus",
            event_type="ai_service_registered",
        )
        coordinator._track_cross_bridge_event(event)
        recent = coordinator.get_recent_cross_bridge_events()
        assert len(recent) == 1
        assert recent[0]["source_bridge"] == "nexus"

    def test_cross_bridge_event_limit(self):
        """Cross-bridge event tracking respects the max limit."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._max_tracked_events = 5
        for i in range(10):
            coordinator._track_cross_bridge_event(
                CrossBridgeEvent(event_type=f"event-{i}")
            )
        _recent = coordinator.get_recent_cross_bridge_events()
        # Should only keep the last 5
        total = len(coordinator._cross_bridge_events)
        assert total <= 5

    def test_publish_cross_bridge_event(self):
        """Cross-bridge events can be published through the coordinator."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        event = run_async(
            coordinator.publish_cross_bridge_event(
                source_bridge="infinity",
                sentinel_channel="bridge",
                event_type="user_connected",
                payload={"user_id": "user-1"},
            )
        )
        assert event.source_bridge == "infinity"
        assert "nexus" in event.target_bridges
        assert "hive" in event.target_bridges
        assert coordinator.get_stats()["total_cross_bridge_events"] == 1

    def test_publish_with_explicit_targets(self):
        """Cross-bridge events can specify explicit target bridges."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        event = run_async(
            coordinator.publish_cross_bridge_event(
                source_bridge="nexus",
                sentinel_channel="nexus",
                event_type="ai_alert",
                payload={"severity": "high"},
                target_bridges=["infinity"],
            )
        )
        assert event.target_bridges == ["infinity"]


# ── Traffic Separation at Coordinator Level ───────────────────────────────

class TestCoordinatorTrafficSeparation:
    """Tests that the coordinator enforces traffic separation."""

    def test_infinity_bridge_has_user_methods(self):
        """InfinityBridge through coordinator has user methods."""
        coordinator = ThreeBridgeCoordinator()
        bridge = coordinator.infinity_bridge
        assert hasattr(bridge, "connect_user")
        assert hasattr(bridge, "disconnect_user")
        assert hasattr(bridge, "transition_user")

    def test_nexus_has_no_user_methods(self):
        """Nexus through coordinator has no user methods."""
        coordinator = ThreeBridgeCoordinator()
        nexus = coordinator.nexus
        assert not hasattr(nexus, "connect_user")
        assert not hasattr(nexus, "disconnect_user")

    def test_hive_has_no_user_methods(self):
        """HIVE through coordinator has no user methods."""
        coordinator = ThreeBridgeCoordinator()
        hive = coordinator.hive
        assert not hasattr(hive, "connect_user")

    def test_bridge_identity_enum(self):
        """BridgeIdentity enum has all three bridges."""
        assert BridgeIdentity.INFINITY_BRIDGE.value == "infinity"
        assert BridgeIdentity.NEXUS.value == "nexus"
        assert BridgeIdentity.HIVE.value == "hive"
        assert len(BridgeIdentity) == 3

    def test_coordinator_state_enum(self):
        """CoordinatorState enum has all expected states."""
        assert CoordinatorState.STOPPED.value == "stopped"
        assert CoordinatorState.STARTING.value == "starting"
        assert CoordinatorState.RUNNING.value == "running"
        assert CoordinatorState.DEGRADED.value == "degraded"
        assert CoordinatorState.STOPPING.value == "stopping"


# ── Health Check Tests ────────────────────────────────────────────────────

class TestHealthCheck:
    """Tests for the health check endpoint."""

    def test_health_check_structure(self):
        """Health check returns expected structure."""
        coordinator = ThreeBridgeCoordinator()
        health = run_async(coordinator.health_check())
        assert "status" in health
        assert "all_bridges_healthy" in health
        assert "all_sentinels_attached" in health
        assert "bridges" in health
        assert "coordinator_state" in health

    def test_health_check_before_start(self):
        """Health check shows bridges healthy but sentinels not attached."""
        coordinator = ThreeBridgeCoordinator()
        health = run_async(coordinator.health_check())
        assert health["all_bridges_healthy"] is True
        assert health["all_sentinels_attached"] is False
        assert health["bridges"]["infinity_bridge"]["healthy"] is True
        assert health["bridges"]["nexus"]["healthy"] is True
        assert health["bridges"]["hive"]["healthy"] is True

    def test_health_check_bridge_details(self):
        """Health check includes details for each bridge."""
        coordinator = ThreeBridgeCoordinator()
        health = run_async(coordinator.health_check())
        for bridge_name in ["infinity_bridge", "nexus", "hive"]:
            assert bridge_name in health["bridges"]
            bridge_info = health["bridges"][bridge_name]
            assert "healthy" in bridge_info
            assert "sentinel_attached" in bridge_info


# ── Singleton Tests ───────────────────────────────────────────────────────

class TestCoordinatorSingleton:
    """Tests for the coordinator singleton pattern."""

    def test_get_coordinator_returns_same_instance(self):
        """get_coordinator() returns the same instance."""
        import Dimensional.three_bridge_coordinator as tbc
        tbc._coordinator_instance = None
        c1 = get_coordinator()
        c2 = get_coordinator()
        assert c1 is c2
        tbc._coordinator_instance = None  # Clean up


# ── Integration: All Three Bridges Through Coordinator ────────────────────

class TestAllThreeBridgesThroughCoordinator:
    """Integration tests that verify all three bridges work through coordinator."""

    def test_user_traffic_on_infinity_bridge(self):
        """User traffic flows correctly through InfinityBridge via coordinator."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        run_async(coordinator.start())

        # Connect a user
        ctx = coordinator.infinity_bridge.connect_user("user-1", "infinity_portal")
        assert ctx.user_id == "user-1"
        assert ctx.location == "infinity_portal"

        # User traffic stats reflect the connection
        ib_health = coordinator.get_bridge_health(BridgeIdentity.INFINITY_BRIDGE.value)
        assert ib_health.stats["users"]["total"] == 1

        # Clean up
        coordinator.infinity_bridge.disconnect_user("user-1")

    def test_unified_status_after_activity(self):
        """Unified status reflects activity across all three bridges."""
        coordinator = ThreeBridgeCoordinator()
        coordinator._sentinel_station = None
        run_async(coordinator.start())

        # Activity on InfinityBridge
        coordinator.infinity_bridge.connect_user("user-1")

        # Get unified status
        status = run_async(coordinator.get_unified_status())
        assert status["coordinator"]["state"] == "running"
        assert status["three_bridges"]["infinity_bridge"]["status"]["users"]["total"] == 1

    def test_coordinator_with_custom_bridge_instances(self):
        """Coordinator accepts custom bridge instances."""
        custom_bridge = InfinityBridge()
        custom_nexus = Nexus()
        custom_hive = Hive()

        coordinator = ThreeBridgeCoordinator(
            infinity_bridge=custom_bridge,
            nexus=custom_nexus,
            hive=custom_hive,
        )

        assert coordinator.infinity_bridge is custom_bridge
        assert coordinator.nexus is custom_nexus
        assert coordinator.hive is custom_hive

    def test_coordinator_stats_tracking(self):
        """Coordinator tracks statistics across operations."""
        coordinator = ThreeBridgeCoordinator()
        stats = coordinator.get_stats()
        assert "total_cross_bridge_events" in stats
        assert "infinity_to_sentinel" in stats
        assert "nexus_to_sentinel" in stats
        assert "hive_to_sentinel" in stats
        assert "start_count" in stats
        assert "stop_count" in stats
