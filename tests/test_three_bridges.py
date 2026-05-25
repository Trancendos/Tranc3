"""
Tranc3 Three-Bridge Integration Tests
======================================
Cross-bridge tests that verify the InfinityBridge, Nexus, and HIVE
all work together through Sentinel Station with proper traffic scoping.

Critical Architecture Rules:
    - InfinityBridge = User/human traffic and context ONLY
    - Nexus = AI, Agent, Bot movement and traffic ONLY
    - HIVE = Data movement and swarm systems ONLY

These tests enforce the separation of concerns and verify that
events flow correctly between the three bridge systems.
"""

import asyncio

from Dimensional.infinity.bridge.bridge_core import (
    BridgeEvent,
    BridgePathManager,
    ContextType,
    ContextWindow,
    InfinityBridge,
    PresenceTracker,
    SessionStatus,
    UserContext,
    UserTier,
    get_infinity_bridge,
    get_sentinel_bridge,
)
from Dimensional.nexus.nexus_core import (
    Nexus,
)
from Dimensional.hive.hive_core import (
    Hive,
)
from Dimensional.infinity.nomenclature import SentinelChannel, TransferSystem


# Helper to run async functions in sync tests
def run_async(coro):
    """Run an async coroutine in a sync test."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ── InfinityBridge Unit Tests ──────────────────────────────────────────────────

class TestUserContext:
    """Tests for the UserContext data model."""

    def test_default_context(self):
        ctx = UserContext(user_id="user-1")
        assert ctx.user_id == "user-1"
        assert ctx.location == "infinity_portal"
        assert ctx.tier == UserTier.HUMAN
        assert ctx.status == SessionStatus.ACTIVE
        assert ContextType.SESSION.value in ctx.context_types

    def test_custom_context(self):
        ctx = UserContext(
            user_id="admin-1",
            location="infinity_admin",
            tier=UserTier.ORCHESTRATOR,
            metadata={"role": "admin"},
        )
        assert ctx.location == "infinity_admin"
        assert ctx.tier == UserTier.ORCHESTRATOR
        assert ctx.metadata["role"] == "admin"

    def test_touch_updates_timestamp(self):
        ctx = UserContext(user_id="user-1")
        old_time = ctx.last_active
        ctx.touch()
        assert ctx.last_active >= old_time

    def test_to_dict(self):
        ctx = UserContext(user_id="user-1", location="infinity_gate")
        d = ctx.to_dict()
        assert d["user_id"] == "user-1"
        assert d["location"] == "infinity_gate"
        assert "session_id" in d
        assert "connected_at" in d


class TestContextWindow:
    """Tests for the ContextWindow manager."""

    def test_register_and_get(self):
        cw = ContextWindow()
        ctx = UserContext(user_id="user-1", location="infinity_portal")
        cw.register(ctx)
        assert cw.get("user-1") is ctx
        assert cw.total_users == 1

    def test_get_by_session(self):
        cw = ContextWindow()
        ctx = UserContext(user_id="user-1")
        cw.register(ctx)
        found = cw.get_by_session(ctx.session_id)
        assert found is ctx

    def test_update_location(self):
        cw = ContextWindow()
        ctx = UserContext(user_id="user-1", location="infinity_portal")
        cw.register(ctx)
        updated = cw.update_location("user-1", "infinity_gate")
        assert updated.location == "infinity_gate"
        assert updated.previous_location == "infinity_portal"

    def test_update_location_removes_from_old_index(self):
        cw = ContextWindow()
        cw.register(UserContext(user_id="user-1", location="loc-a"))
        cw.register(UserContext(user_id="user-2", location="loc-a"))
        cw.update_location("user-1", "loc-b")
        users_at_a = cw.get_users_at("loc-a")
        assert len(users_at_a) == 1
        assert users_at_a[0].user_id == "user-2"

    def test_update_status(self):
        cw = ContextWindow()
        cw.register(UserContext(user_id="user-1"))
        updated = cw.update_status("user-1", SessionStatus.IDLE)
        assert updated.status == SessionStatus.IDLE

    def test_remove(self):
        cw = ContextWindow()
        cw.register(UserContext(user_id="user-1"))
        removed = cw.remove("user-1")
        assert removed is not None
        assert cw.get("user-1") is None
        assert cw.total_users == 0

    def test_get_users_at_location(self):
        cw = ContextWindow()
        cw.register(UserContext(user_id="user-1", location="loc-a"))
        cw.register(UserContext(user_id="user-2", location="loc-a"))
        cw.register(UserContext(user_id="user-3", location="loc-b"))
        users = cw.get_users_at("loc-a")
        assert len(users) == 2

    def test_location_counts(self):
        cw = ContextWindow()
        cw.register(UserContext(user_id="u1", location="loc-a"))
        cw.register(UserContext(user_id="u2", location="loc-a"))
        cw.register(UserContext(user_id="u3", location="loc-b"))
        counts = cw.get_location_counts()
        assert counts["loc-a"] == 2
        assert counts["loc-b"] == 1

    def test_active_users_count(self):
        cw = ContextWindow()
        cw.register(UserContext(user_id="u1", status=SessionStatus.ACTIVE))
        cw.register(UserContext(user_id="u2", status=SessionStatus.IDLE))
        cw.register(UserContext(user_id="u3", status=SessionStatus.TRANSITIONING))
        assert cw.active_users == 2  # ACTIVE + TRANSITIONING


class TestPresenceTracker:
    """Tests for the PresenceTracker."""

    def test_update_and_get(self):
        pt = PresenceTracker()
        pt.update_presence("user-1", "infinity_portal", "active")
        pres = pt.get_presence("user-1")
        assert pres is not None
        assert pres["location"] == "infinity_portal"

    def test_remove_presence(self):
        pt = PresenceTracker()
        pt.update_presence("user-1", "infinity_portal")
        pt.remove_presence("user-1")
        assert pt.get_presence("user-1") is None

    def test_location_presence(self):
        pt = PresenceTracker()
        pt.update_presence("u1", "loc-a")
        pt.update_presence("u2", "loc-a")
        pt.update_presence("u3", "loc-b")
        loc_a = pt.get_location_presence("loc-a")
        assert len(loc_a) == 2

    def test_idle_users(self):
        pt = PresenceTracker(idle_timeout_seconds=0)
        pt.update_presence("u1", "loc-a")
        import time
        time.sleep(0.01)
        idle = pt.get_idle_users()
        assert "u1" in idle

    def test_stats(self):
        pt = PresenceTracker()
        pt.update_presence("u1", "loc-a", "active")
        pt.update_presence("u2", "loc-b", "idle")
        stats = pt.get_stats()
        assert stats["total_online"] == 2


class TestBridgePathManager:
    """Tests for the BridgePathManager."""

    def test_open_path(self):
        bpm = BridgePathManager()
        path = bpm.open_path("loc-a", "loc-b")
        assert path.source == "loc-a"
        assert path.target == "loc-b"
        assert path.is_open is True

    def test_close_path(self):
        bpm = BridgePathManager()
        bpm.open_path("loc-a", "loc-b")
        closed = bpm.close_path("loc-a", "loc-b")
        assert closed.is_open is False

    def test_record_transition(self):
        bpm = BridgePathManager()
        bpm.record_transition("loc-a", "loc-b", 50.0)
        path = bpm.get_path("loc-a", "loc-b")
        assert path.total_transitions == 1
        assert path.avg_transition_ms == 50.0

    def test_get_open_paths(self):
        bpm = BridgePathManager()
        bpm.open_path("a", "b")
        bpm.open_path("b", "c")
        bpm.close_path("a", "b")
        open_paths = bpm.get_open_paths()
        assert len(open_paths) == 1
        assert open_paths[0].path_id == "b→c"

    def test_paths_from_location(self):
        bpm = BridgePathManager()
        bpm.open_path("a", "b")
        bpm.open_path("a", "c")
        bpm.open_path("b", "c")
        from_a = bpm.get_paths_from("a")
        assert len(from_a) == 2


class TestInfinityBridge:
    """Tests for the InfinityBridge core."""

    def test_connect_user(self):
        bridge = InfinityBridge()
        ctx = bridge.connect_user("user-1", "infinity_portal")
        assert ctx.user_id == "user-1"
        assert ctx.location == "infinity_portal"
        assert ctx.status == SessionStatus.ACTIVE
        assert bridge.context_window.total_users == 1

    def test_disconnect_user(self):
        bridge = InfinityBridge()
        bridge.connect_user("user-1")
        ctx = bridge.disconnect_user("user-1")
        assert ctx is not None
        assert bridge.context_window.total_users == 0

    def test_disconnect_nonexistent(self):
        bridge = InfinityBridge()
        ctx = bridge.disconnect_user("nobody")
        assert ctx is None

    def test_transition_user(self):
        bridge = InfinityBridge()
        bridge.connect_user("user-1", "infinity_portal")
        ctx = bridge.transition_user("user-1", "infinity_gate", 42.0)
        assert ctx.location == "infinity_gate"
        assert ctx.previous_location == "infinity_portal"
        assert bridge.stats["total_transitions"] == 1

    def test_update_context(self):
        bridge = InfinityBridge()
        bridge.connect_user("user-1")
        ctx = bridge.update_context("user-1", ContextType.NAVIGATION.value, {"page": "dashboard"})
        assert ctx is not None
        assert ContextType.NAVIGATION.value in ctx.context_types
        assert ctx.metadata["page"] == "dashboard"

    def test_update_presence(self):
        bridge = InfinityBridge()
        bridge.connect_user("user-1")
        result = bridge.update_presence("user-1", "idle")
        assert result is True

    def test_get_users_at_location(self):
        bridge = InfinityBridge()
        bridge.connect_user("u1", "loc-a")
        bridge.connect_user("u2", "loc-a")
        bridge.connect_user("u3", "loc-b")
        users = bridge.get_users_at_location("loc-a")
        assert len(users) == 2

    def test_event_handler_registration(self):
        bridge = InfinityBridge()
        received = []
        bridge.register_handler(BridgeEvent.USER_CONNECT.value, lambda e: received.append(e))
        bridge.connect_user("user-1")
        assert len(received) == 1
        assert received[0].event_type == BridgeEvent.USER_CONNECT.value

    def test_wildcard_handler(self):
        bridge = InfinityBridge()
        received = []
        bridge.register_handler("*", lambda e: received.append(e))
        bridge.connect_user("user-1")
        bridge.transition_user("user-1", "loc-b")
        assert len(received) == 2

    def test_open_and_close_bridge(self):
        bridge = InfinityBridge()
        path = bridge.open_bridge("loc-a", "loc-b")
        assert path.is_open is True
        closed = bridge.close_bridge("loc-a", "loc-b")
        assert closed.is_open is False

    def test_get_status(self):
        bridge = InfinityBridge()
        bridge.connect_user("user-1")
        status = bridge.get_status()
        assert status["bridge"] == "InfinityBridge"
        assert status["bridge_type"] == "infinity"
        assert "three_bridges" in status
        assert "infinity_bridge" in status["three_bridges"]
        assert "nexus" in status["three_bridges"]
        assert "hive" in status["three_bridges"]

    def test_get_health(self):
        bridge = InfinityBridge()
        bridge.connect_user("user-1")
        health = bridge.get_health()
        assert health["healthy"] is True
        assert health["users"]["total"] == 1

    def test_stats_tracking(self):
        bridge = InfinityBridge()
        bridge.connect_user("u1")
        bridge.transition_user("u1", "loc-b")
        bridge.update_context("u1")
        bridge.disconnect_user("u1")
        stats = bridge.stats
        assert stats["total_connections"] == 1
        assert stats["total_disconnections"] == 1
        assert stats["total_transitions"] == 1
        assert stats["total_context_updates"] == 1


class TestInfinityBridgeEnums:
    """Tests for InfinityBridge enum definitions."""

    def test_user_tier(self):
        assert UserTier.HUMAN == 0
        assert UserTier.ORCHESTRATOR == 1
        assert UserTier.PRIME == 2

    def test_session_status(self):
        assert SessionStatus.ACTIVE.value == "active"
        assert SessionStatus.IDLE.value == "idle"
        assert SessionStatus.TRANSITIONING.value == "transitioning"

    def test_context_type(self):
        assert ContextType.SESSION.value == "session"
        assert ContextType.NAVIGATION.value == "navigation"
        assert ContextType.PRESENCE.value == "presence"

    def test_bridge_event(self):
        assert BridgeEvent.USER_CONNECT.value == "user_connect"
        assert BridgeEvent.USER_TRANSITION.value == "user_transition"
        assert BridgeEvent.BRIDGE_OPEN.value == "bridge_open"


# ── Cross-Bridge Integration Tests ─────────────────────────────────────────────

class TestThreeBridgeSeparation:
    """Tests that enforce the three-bridge traffic separation.

    InfinityBridge = User/human traffic ONLY
    Nexus = AI/Agent/Bot traffic ONLY
    HIVE = Data movement and swarm coordination ONLY
    """

    def test_infinity_bridge_user_traffic(self):
        """InfinityBridge handles user connect/disconnect/transition."""
        bridge = InfinityBridge()
        ctx = bridge.connect_user("user-1", "infinity_portal", tier=0)
        assert ctx.tier == UserTier.HUMAN  # Tier 0 = HUMAN

    def test_nexus_ai_traffic(self):
        """Nexus handles AI/Agent/Bot service registration."""
        nexus = Nexus()
        # Nexus.register_service(service_id, service_name, pillar, tier_requirement)
        run_async(nexus.register_service("ai-llm-1", "AI LLM Service", "ai", 3))
        run_async(nexus.register_service("agent-worker-1", "Agent Worker", "agents", 4))
        run_async(nexus.register_service("bot-scraper-1", "Bot Scraper", "bots", 5))
        # Verify services are registered in topology
        topology = run_async(nexus.get_topology())
        assert len(topology["nodes"]) == 3

    def test_hive_data_traffic(self):
        """HIVE handles data sources, sinks, and pipelines."""
        hive = Hive()
        # Hive methods are async
        run_async(hive.register_source("metrics-src", "metrics", "monitoring"))
        run_async(hive.register_sink("dashboard-sink", "metrics", "monitoring"))
        run_async(hive.create_pipeline("metrics-pipe", "metrics-src", ["dashboard-sink"]))
        status = run_async(hive.get_status())
        assert status["registered_sources"] == 1
        assert status["registered_sinks"] == 1

    def test_bridge_type_identifiers(self):
        """Each bridge reports the correct bridge_type."""
        bridge = InfinityBridge()
        nexus = Nexus()
        hive = Hive()

        assert bridge.get_status()["bridge_type"] == "infinity"
        nexus_status = run_async(nexus.get_status())
        assert nexus_status["bridge_type"] == "nexus"
        hive_status = run_async(hive.get_status())
        assert hive_status["bridge_type"] == "hive"

    def test_three_bridges_dict_in_all_status(self):
        """All three bridges report the three_bridges dict."""
        bridge = InfinityBridge()
        nexus = Nexus()
        hive = Hive()

        # InfinityBridge (sync)
        ib_status = bridge.get_status()
        assert "three_bridges" in ib_status
        assert "infinity_bridge" in ib_status["three_bridges"]
        assert "nexus" in ib_status["three_bridges"]
        assert "hive" in ib_status["three_bridges"]

        # Nexus (async)
        nexus_status = run_async(nexus.get_status())
        assert "three_bridges" in nexus_status
        assert "infinity_bridge" in nexus_status["three_bridges"]
        assert "nexus" in nexus_status["three_bridges"]
        assert "hive" in nexus_status["three_bridges"]

        # HIVE (async)
        hive_status = run_async(hive.get_status())
        assert "three_bridges" in hive_status
        assert "infinity_bridge" in hive_status["three_bridges"]
        assert "nexus" in hive_status["three_bridges"]
        assert "hive" in hive_status["three_bridges"]

    def test_infinity_bridge_no_ai_agent_bot_methods(self):
        """InfinityBridge should NOT have AI/Agent/Bot-specific methods."""
        bridge = InfinityBridge()
        # These methods should NOT exist on InfinityBridge
        assert not hasattr(bridge, "register_service")  # Nexus method
        assert not hasattr(bridge, "register_source")   # HIVE method
        assert not hasattr(bridge, "register_sink")     # HIVE method
        assert not hasattr(bridge, "create_swarm")      # HIVE method

    def test_nexus_no_user_or_data_methods(self):
        """Nexus should NOT have user context or data pipeline methods."""
        nexus = Nexus()
        assert not hasattr(nexus, "connect_user")       # InfinityBridge method
        assert not hasattr(nexus, "register_source")     # HIVE method
        assert not hasattr(nexus, "create_pipeline")     # HIVE method

    def test_hive_no_user_or_ai_methods(self):
        """HIVE should NOT have user context or AI service methods."""
        hive = Hive()
        assert not hasattr(hive, "connect_user")        # InfinityBridge method
        assert not hasattr(hive, "register_service")    # Nexus method
        assert not hasattr(hive, "emit_event_nexus")    # Nexus method


class TestThreeBridgeNomenclature:
    """Tests that verify the nomenclature correctly defines three bridges."""

    def test_transfer_system_enum(self):
        """TransferSystem enum has exactly NEXUS, HIVE, BRIDGE."""
        assert TransferSystem.NEXUS.value == "nexus"
        assert TransferSystem.HIVE.value == "hive"
        assert TransferSystem.BRIDGE.value == "bridge"
        assert len(TransferSystem) == 3

    def test_transfer_systems_dict(self):
        """TRANSFER_SYSTEMS dict has entries for all three."""
        from Dimensional.infinity.nomenclature import TRANSFER_SYSTEMS
        assert TransferSystem.NEXUS in TRANSFER_SYSTEMS
        assert TransferSystem.HIVE in TRANSFER_SYSTEMS
        assert TransferSystem.BRIDGE in TRANSFER_SYSTEMS

    def test_nexus_transfer_description(self):
        """Nexus is described as handling AI/Agent/Bot traffic."""
        from Dimensional.infinity.nomenclature import TRANSFER_SYSTEMS
        nexus_info = TRANSFER_SYSTEMS[TransferSystem.NEXUS]
        assert "AI" in nexus_info["transfers"] or "intelligence" in nexus_info["description"].lower()

    def test_hive_transfer_description(self):
        """HIVE is described as handling data traffic."""
        from Dimensional.infinity.nomenclature import TRANSFER_SYSTEMS
        hive_info = TRANSFER_SYSTEMS[TransferSystem.HIVE]
        assert "Data" in hive_info["transfers"] or "data" in hive_info["description"].lower()

    def test_bridge_transfer_description(self):
        """Bridge (InfinityBridge) is described as handling user traffic."""
        from Dimensional.infinity.nomenclature import TRANSFER_SYSTEMS
        bridge_info = TRANSFER_SYSTEMS[TransferSystem.BRIDGE]
        assert "User" in bridge_info["transfers"] or "user" in bridge_info["description"].lower()

    def test_sentinel_channel_has_all_bridges(self):
        """SentinelChannel enum has HIVE, NEXUS, and BRIDGE channels."""
        assert SentinelChannel.HIVE.value == "hive"
        assert SentinelChannel.NEXUS.value == "nexus"
        assert SentinelChannel.BRIDGE.value == "bridge"


class TestInfinityBridgeSingleton:
    """Tests for the InfinityBridge singleton pattern."""

    def test_get_infinity_bridge_returns_same_instance(self):
        """get_infinity_bridge() returns the same instance."""
        # Reset singleton for testing
        import Dimensional.infinity.bridge.bridge_core as bc
        bc._bridge_instance = None
        b1 = get_infinity_bridge()
        b2 = get_infinity_bridge()
        assert b1 is b2
        bc._bridge_instance = None  # Clean up

    def test_get_sentinel_bridge_returns_same_instance(self):
        """get_sentinel_bridge() returns the same instance."""
        import Dimensional.infinity.bridge.bridge_core as bc
        bc._sentinel_bridge_instance = None
        sb1 = get_sentinel_bridge()
        sb2 = get_sentinel_bridge()
        assert sb1 is sb2
        bc._sentinel_bridge_instance = None  # Clean up


class TestCrossBridgeEventRouting:
    """Tests that verify events route correctly between bridges
    when they're all connected through Sentinel Station."""

    def test_user_event_does_not_pollute_nexus(self):
        """A user connect event should not be registered in Nexus."""
        bridge = InfinityBridge()
        nexus = Nexus()

        # Connect a user on InfinityBridge
        bridge.connect_user("user-1")
        # Verify each bridge maintains its own traffic domain
        nexus_status = run_async(nexus.get_status())
        assert nexus_status["bridge_type"] == "nexus"
        assert bridge.get_status()["bridge_type"] == "infinity"
        # Nexus topology should be empty (no user services registered)
        assert nexus_status["topology_nodes"] == 0

    def test_ai_event_does_not_pollute_hive(self):
        """An AI service event should not be registered in HIVE."""
        nexus = Nexus()
        hive = Hive()

        # Register an AI service on Nexus
        run_async(nexus.register_service("ai-llm-1", "AI LLM Service", "ai", 3))
        # HIVE should still have zero sources/sinks
        hive_status = run_async(hive.get_status())
        assert hive_status["registered_sources"] == 0
        assert hive_status["registered_sinks"] == 0

    def test_data_event_does_not_pollute_infinity_bridge(self):
        """A data pipeline event should not affect InfinityBridge users."""
        bridge = InfinityBridge()
        hive = Hive()

        # Create a data source on HIVE (async methods)
        run_async(hive.register_source("src-1", "telemetry", "monitoring"))
        run_async(hive.register_sink("sink-1", "telemetry", "monitoring"))
        run_async(hive.create_pipeline("data-pipe-1", "src-1", ["sink-1"]))

        # InfinityBridge should still have zero users
        assert bridge.context_window.total_users == 0

    def test_all_three_bridges_can_coexist(self):
        """All three bridges can be instantiated and work independently."""
        bridge = InfinityBridge()
        nexus = Nexus()
        hive = Hive()

        # User traffic on InfinityBridge
        ctx = bridge.connect_user("user-1", "infinity_portal")
        assert ctx.user_id == "user-1"

        # AI traffic on Nexus
        run_async(nexus.register_service("ai-1", "AI Service", "ai", 3))
        topology = run_async(nexus.get_topology())
        assert len(topology["nodes"]) == 1

        # Data traffic on HIVE
        run_async(hive.register_source("data-src-1", "metrics", "monitoring"))
        run_async(hive.register_sink("data-sink-1", "metrics", "monitoring"))
        run_async(hive.create_pipeline("data-pipe-1", "data-src-1", ["data-sink-1"]))
        hive_status = run_async(hive.get_status())
        assert hive_status["registered_sources"] == 1

        # All three report correct bridge_type
        assert bridge.get_status()["bridge_type"] == "infinity"
        nexus_status = run_async(nexus.get_status())
        assert nexus_status["bridge_type"] == "nexus"
        hive_status = run_async(hive.get_status())
        assert hive_status["bridge_type"] == "hive"

        # All three report three_bridges
        ib_status = bridge.get_status()
        assert "three_bridges" in ib_status
        nexus_status = run_async(nexus.get_status())
        assert "three_bridges" in nexus_status
        hive_status = run_async(hive.get_status())
        assert "three_bridges" in hive_status
