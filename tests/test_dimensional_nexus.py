"""
Tests for Dimensional Nexus — Central Nervous System
=====================================================
Comprehensive test suite covering:
- Causal Ordering Engine (vector clocks, event ordering)
- Tier Access Bridge (RBAC + ABAC + Tier hierarchy)
- Health Aggregator (service health, anomaly detection)
- Event Router (cross-dimensional event distribution)
- Dimensional Nexus (full integration)
- FastAPI endpoints
"""

import os
import sys
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

# Ensure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from Dimensional.infinity.nomenclature import SentinelChannel
from Dimensional.nexus.nexus_core import (
    CausalOrderingEngine,
    DimensionalNexus,
    EventRouter,
    HealthAggregator,
    NexusAccessDecision,
    NexusEvent,
    NexusHealthSummary,
    NexusServiceHealth,
    NexusTopologyEdge,
    NexusTopologyNode,
    TierAccessBridge,
    get_nexus,
)

# ---------------------------------------------------------------------------
# Causal Ordering Engine Tests
# ---------------------------------------------------------------------------


class TestCausalOrderingEngine:
    """Tests for the vector-clock based causal ordering engine."""

    def setup_method(self):
        self.engine_a = CausalOrderingEngine("node-a")
        self.engine_b = CausalOrderingEngine("node-b")

    def test_increment(self):
        """Clock increments on the local node."""
        vc = self.engine_a.increment()
        assert vc == {"node-a": 1}
        vc = self.engine_a.increment()
        assert vc == {"node-a": 2}

    def test_merge(self):
        """Merge incorporates remote clock and increments local."""
        self.engine_a.increment()  # node-a: 1
        self.engine_b.increment()  # node-b: 1
        self.engine_b.increment()  # node-b: 2

        # node-a receives message from node-b with clock {node-b: 2}
        merged = self.engine_a.merge({"node-b": 2})
        assert merged["node-a"] == 2  # incremented after merge
        assert merged["node-b"] == 2  # absorbed from incoming

    def test_happened_before(self):
        """Detect happens-before relationship."""
        vc1 = {"node-a": 1}
        vc2 = {"node-a": 2}
        assert self.engine_a.happened_before(vc1, vc2)
        assert not self.engine_a.happened_before(vc2, vc1)

    def test_happened_before_different_nodes(self):
        """Happens-before with different node clocks."""
        vc1 = {"node-a": 1}
        vc2 = {"node-a": 1, "node-b": 1}
        assert self.engine_a.happened_before(vc1, vc2)
        assert not self.engine_a.happened_before(vc2, vc1)

    def test_concurrent(self):
        """Detect concurrent events (no causal relationship)."""
        vc1 = {"node-a": 1}
        vc2 = {"node-b": 1}
        assert self.engine_a.concurrent(vc1, vc2)
        assert self.engine_a.concurrent(vc2, vc1)

    def test_not_concurrent_when_ordered(self):
        """Events with causal relationship are not concurrent."""
        vc1 = {"node-a": 1}
        vc2 = {"node-a": 2}
        assert not self.engine_a.concurrent(vc1, vc2)

    def test_causality_hash(self):
        """Causality hash is deterministic."""
        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="test",
            source_tier=3,
            event_type="test_event",
            vector_clock={"node-a": 1},
            timestamp="2025-01-01T00:00:00+00:00",
        )
        hash1 = self.engine_a.compute_causality_hash(event)
        hash2 = self.engine_a.compute_causality_hash(event)
        assert hash1 == hash2
        assert len(hash1) == 16

    @pytest.mark.asyncio
    async def test_record_event_local(self):
        """Recording a local event increments the vector clock."""
        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="node-a",
            source_tier=3,
            event_type="test",
        )
        result = await self.engine_a.record_event(event)
        assert result.vector_clock["node-a"] == 1
        assert result.causality_hash is not None

    @pytest.mark.asyncio
    async def test_record_event_remote(self):
        """Recording a remote event merges the vector clock."""
        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="node-b",
            source_tier=3,
            event_type="test",
            vector_clock={"node-b": 5},
        )
        result = await self.engine_a.record_event(event)
        assert result.vector_clock["node-b"] == 5
        assert result.vector_clock["node-a"] == 1  # incremented after merge

    @pytest.mark.asyncio
    async def test_get_ordered_events(self):
        """Events can be retrieved in causal order."""
        for i in range(5):
            event = NexusEvent(
                channel="PLATFORM",
                source_dimension="node-a",
                source_tier=3,
                event_type=f"event_{i}",
            )
            await self.engine_a.record_event(event)

        events = await self.engine_a.get_ordered_events()
        assert len(events) == 5

    @pytest.mark.asyncio
    async def test_get_ordered_events_filtered(self):
        """Events can be filtered by channel."""
        for channel in ["PLATFORM", "AGENTS", "PLATFORM"]:
            event = NexusEvent(
                channel=channel,
                source_dimension="node-a",
                source_tier=3,
                event_type="test",
            )
            await self.engine_a.record_event(event)

        platform_events = await self.engine_a.get_ordered_events(channel="PLATFORM")
        assert len(platform_events) == 2

    @pytest.mark.asyncio
    async def test_event_buffer_size_limit(self):
        """Event buffer respects the configured size limit."""
        original_size = os.environ.get("NEXUS_EVENT_BUFFER_SIZE")
        os.environ["NEXUS_EVENT_BUFFER_SIZE"] = "5"
        try:
            engine = CausalOrderingEngine("buffer-test")
            for i in range(10):
                event = NexusEvent(
                    channel="PLATFORM",
                    source_dimension="buffer-test",
                    source_tier=3,
                    event_type=f"event_{i}",
                )
                await engine.record_event(event)
            events = await engine.get_ordered_events()
            assert len(events) == 5  # capped at buffer size
        finally:
            if original_size:
                os.environ["NEXUS_EVENT_BUFFER_SIZE"] = original_size
            else:
                os.environ.pop("NEXUS_EVENT_BUFFER_SIZE", None)


# ---------------------------------------------------------------------------
# Tier Access Bridge Tests
# ---------------------------------------------------------------------------


class TestTierAccessBridge:
    """Tests for the unified RBAC + ABAC + Tier access control bridge."""

    def setup_method(self):
        self.bridge = TierAccessBridge()
        self.bridge.set_tier_requirement("admin_panel", 0)  # HUMAN only
        self.bridge.set_tier_requirement("orchestrator_api", 1)
        self.bridge.set_tier_requirement("prime_dashboard", 2)
        self.bridge.set_tier_requirement("ai_training", 3)
        self.bridge.set_tier_requirement("agent_tasks", 4)
        self.bridge.set_tier_requirement("bot_endpoints", 5)

    def test_tier_check_allows_lower_tier(self):
        """Lower tier numbers (higher privilege) can access higher tier resources."""
        result = self.bridge.check_access(
            subject="ai_system",
            resource="bot_endpoints",
            action="read",
            subject_tier=3,  # AI can access BOT endpoints
        )
        assert result.allowed is True
        assert result.tier_valid is True

    def test_tier_check_denies_higher_tier(self):
        """Higher tier numbers (lower privilege) cannot access lower tier resources."""
        result = self.bridge.check_access(
            subject="bot_worker",
            resource="ai_training",
            action="read",
            subject_tier=5,  # BOT cannot access AI resources
        )
        assert result.allowed is False
        assert result.tier_valid is False
        assert "insufficient_tier" in result.constraints

    def test_explicit_deny(self):
        """Explicit deny overrides all other checks."""
        self.bridge.add_deny("blocked_resource")
        result = self.bridge.check_access(
            subject="human_user",
            resource="blocked_resource",
            action="read",
            subject_tier=0,  # Even HUMAN is denied
        )
        assert result.allowed is False
        assert "explicit_deny" in result.constraints

    def test_explicit_deny_removed(self):
        """Removing explicit deny restores access."""
        self.bridge.add_deny("temp_deny")
        self.bridge.remove_deny("temp_deny")
        result = self.bridge.check_access(
            subject="bot",
            resource="temp_deny",
            action="read",
            subject_tier=5,
        )
        assert result.allowed is True

    def test_human_access_all(self):
        """Tier 0 (HUMAN) can access all resources."""
        for resource in [
            "admin_panel",
            "orchestrator_api",
            "prime_dashboard",
            "ai_training",
            "agent_tasks",
            "bot_endpoints",
        ]:
            result = self.bridge.check_access(
                subject="human",
                resource=resource,
                action="read",
                subject_tier=0,
            )
            assert result.allowed is True, f"HUMAN should access {resource}"

    def test_bot_access_limited(self):
        """Tier 5 (BOT) can only access tier 5 resources."""
        result = self.bridge.check_access(
            subject="bot",
            resource="bot_endpoints",
            action="read",
            subject_tier=5,
        )
        assert result.allowed is True

        result = self.bridge.check_access(
            subject="bot",
            resource="agent_tasks",
            action="read",
            subject_tier=5,
        )
        assert result.allowed is False

    def test_tier_hierarchy_definition(self):
        """Verify the tier hierarchy matches the mandatory custom definitions."""
        # AI = Tier 3, Agent = Tier 4, Bot = Tier 5
        ai_result = self.bridge.check_access(
            subject="ai_complex",
            resource="ai_training",
            action="execute",
            subject_tier=3,
        )
        assert ai_result.allowed is True

        agent_result = self.bridge.check_access(
            subject="agent_entity",
            resource="ai_training",
            action="execute",
            subject_tier=4,
        )
        assert agent_result.allowed is False  # Agent cannot access AI tier

        bot_result = self.bridge.check_access(
            subject="bot_service",
            resource="agent_tasks",
            action="execute",
            subject_tier=5,
        )
        assert bot_result.allowed is False  # Bot cannot access Agent tier

    def test_default_tier_is_bot(self):
        """Resources without explicit tier requirement default to tier 5 (BOT)."""
        result = self.bridge.check_access(
            subject="bot",
            resource="unknown_resource",
            action="read",
            subject_tier=5,
        )
        assert result.allowed is True
        assert result.required_tier == 5

    def test_with_rbac_only(self):
        """When only RBAC is configured, it determines access."""
        mock_rbac = MagicMock()
        mock_rbac.check_permission.return_value = True
        bridge = TierAccessBridge(rbac_engine=mock_rbac)
        bridge.set_tier_requirement("resource", 5)

        result = bridge.check_access(
            subject="user",
            resource="resource",
            action="read",
            subject_tier=5,
            subject_role="viewer",
        )
        assert result.allowed is True
        assert result.matched_policy == "rbac"

    def test_with_abac_only(self):
        """When only ABAC is configured, it determines access."""
        mock_abac = MagicMock()
        mock_abac.evaluate.return_value = True
        bridge = TierAccessBridge(abac_engine=mock_abac)
        bridge.set_tier_requirement("resource", 5)

        result = bridge.check_access(
            subject="user",
            resource="resource",
            action="read",
            subject_tier=5,
            subject_attributes={"department": "engineering"},
        )
        assert result.allowed is True
        assert result.matched_policy == "abac"

    def test_rbac_and_abac_both_must_allow(self):
        """When both RBAC and ABAC are configured, both must allow."""
        mock_rbac = MagicMock()
        mock_abac = MagicMock()

        # RBAC allows, ABAC denies
        mock_rbac.check_permission.return_value = True
        mock_abac.evaluate.return_value = False
        bridge = TierAccessBridge(rbac_engine=mock_rbac, abac_engine=mock_abac)
        bridge.set_tier_requirement("resource", 5)

        result = bridge.check_access(
            subject="user",
            resource="resource",
            action="read",
            subject_tier=5,
            subject_role="viewer",
            subject_attributes={"department": "engineering"},
        )
        assert result.allowed is False
        assert "abac_denied" in result.constraints

    def test_no_access_control_configured(self):
        """When no access control is configured, tier check alone determines access."""
        bridge = TierAccessBridge()
        bridge.set_tier_requirement("resource", 3)

        result = bridge.check_access(
            subject="ai",
            resource="resource",
            action="read",
            subject_tier=3,
        )
        assert result.allowed is True
        assert result.matched_policy == "tier_only"


# ---------------------------------------------------------------------------
# Health Aggregator Tests
# ---------------------------------------------------------------------------


class TestHealthAggregator:
    """Tests for the health aggregation system."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_nexus.db")
        self.aggregator = HealthAggregator(db_path=self.db_path)

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_register_service(self):
        """Services can be registered for health tracking."""
        health = NexusServiceHealth(
            service_id="svc-1",
            service_name="Test Service",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        await self.aggregator.register_service(health)
        assert "svc-1" in self.aggregator._services

    @pytest.mark.asyncio
    async def test_update_heartbeat(self):
        """Heartbeats update service health status."""
        health = NexusServiceHealth(
            service_id="svc-1",
            service_name="Test Service",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        await self.aggregator.register_service(health)
        await self.aggregator.update_heartbeat(
            service_id="svc-1",
            status="healthy",
            response_time_ms=42.5,
        )
        assert self.aggregator._services["svc-1"].status == "healthy"
        assert self.aggregator._services["svc-1"].response_time_ms == 42.5

    @pytest.mark.asyncio
    async def test_get_summary_empty(self):
        """Summary shows zero counts when no services registered."""
        summary = await self.aggregator.get_summary()
        assert summary.total_services == 0
        assert summary.overall_status == "unknown"

    @pytest.mark.asyncio
    async def test_get_summary_with_services(self):
        """Summary correctly aggregates service health."""
        for i, (status, pillar) in enumerate(
            [
                ("healthy", "PLATFORM"),
                ("healthy", "AGENTS"),
                ("degraded", "MODELS"),
                ("unhealthy", "SECURITY"),
            ]
        ):
            health = NexusServiceHealth(
                service_id=f"svc-{i}",
                service_name=f"Service {i}",
                pillar=pillar,
                tier_requirement=3,
                status=status,
            )
            await self.aggregator.register_service(health)

        summary = await self.aggregator.get_summary()
        assert summary.total_services == 4
        assert summary.healthy == 2
        assert summary.degraded == 1
        assert summary.unhealthy == 1
        assert summary.overall_status == "critical"

    @pytest.mark.asyncio
    async def test_anomaly_detection_heartbeat_timeout(self):
        """Anomalies are detected for heartbeat timeouts."""
        health = NexusServiceHealth(
            service_id="svc-stale",
            service_name="Stale Service",
            pillar="PLATFORM",
            tier_requirement=3,
            status="healthy",
            last_heartbeat="2020-01-01T00:00:00+00:00",  # Very old
        )
        await self.aggregator.register_service(health)
        anomalies = await self.aggregator.detect_anomalies()
        assert len(anomalies) >= 1
        assert anomalies[0]["type"] == "heartbeat_timeout"

    @pytest.mark.asyncio
    async def test_anomaly_detection_high_response_time(self):
        """Anomalies are detected for high response times."""
        health = NexusServiceHealth(
            service_id="svc-slow",
            service_name="Slow Service",
            pillar="PLATFORM",
            tier_requirement=3,
            status="healthy",
            response_time_ms=5000.0,  # Way above threshold
            last_heartbeat=datetime.now(timezone.utc).isoformat(),
        )
        await self.aggregator.register_service(health)
        anomalies = await self.aggregator.detect_anomalies()
        high_rt = [a for a in anomalies if a["type"] == "high_response_time"]
        assert len(high_rt) >= 1

    @pytest.mark.asyncio
    async def test_error_count_tracking(self):
        """Error count increments on unhealthy status updates."""
        health = NexusServiceHealth(
            service_id="svc-err",
            service_name="Error Service",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        await self.aggregator.register_service(health)
        for _ in range(3):
            await self.aggregator.update_heartbeat(
                service_id="svc-err",
                status="unhealthy",
            )
        assert self.aggregator._services["svc-err"].error_count == 3


# ---------------------------------------------------------------------------
# Event Router Tests
# ---------------------------------------------------------------------------


class TestEventRouter:
    """Tests for cross-dimensional event routing."""

    def setup_method(self):
        self.causal_engine = CausalOrderingEngine("router-test")
        self.router = EventRouter(self.causal_engine)

    @pytest.mark.asyncio
    async def test_subscribe(self):
        """Services can subscribe to channels."""
        await self.router.subscribe("PLATFORM", "svc-1")
        subs = await self.router.get_subscriptions()
        assert "PLATFORM" in subs
        assert "svc-1" in subs["PLATFORM"]

    @pytest.mark.asyncio
    async def test_unsubscribe(self):
        """Services can unsubscribe from channels."""
        await self.router.subscribe("PLATFORM", "svc-1")
        await self.router.unsubscribe("PLATFORM", "svc-1")
        subs = await self.router.get_subscriptions()
        assert "svc-1" not in subs.get("PLATFORM", [])

    @pytest.mark.asyncio
    async def test_publish(self):
        """Events are published to channel subscribers."""
        await self.router.subscribe("PLATFORM", "svc-1")
        await self.router.subscribe("PLATFORM", "svc-2")

        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="svc-origin",
            source_tier=3,
            event_type="test_event",
        )
        subscribers = await self.router.publish(event)
        assert "svc-1" in subscribers
        assert "svc-2" in subscribers

    @pytest.mark.asyncio
    async def test_publish_no_subscribers(self):
        """Publishing to a channel with no subscribers returns empty list."""
        event = NexusEvent(
            channel="NEXUS",
            source_dimension="svc-origin",
            source_tier=3,
            event_type="test_event",
        )
        subscribers = await self.router.publish(event)
        assert len(subscribers) == 0

    @pytest.mark.asyncio
    async def test_handler_invoked(self):
        """Registered handlers are invoked when events are published."""
        received = []

        async def handler(event):
            received.append(event)

        await self.router.register_handler("PLATFORM", handler)
        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="svc-origin",
            source_tier=3,
            event_type="test_event",
        )
        await self.router.publish(event)
        assert len(received) == 1
        assert received[0].event_type == "test_event"

    @pytest.mark.asyncio
    async def test_handler_error_doesnt_block(self):
        """A failing handler doesn't block other handlers or publishing."""

        async def bad_handler(event):
            raise ValueError("Handler error")

        good_received = []

        async def good_handler(event):
            good_received.append(event)

        await self.router.register_handler("PLATFORM", bad_handler)
        await self.router.register_handler("PLATFORM", good_handler)

        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="svc-origin",
            source_tier=3,
            event_type="test_event",
        )
        _subscribers = await self.router.publish(event)
        assert len(good_received) == 1

    @pytest.mark.asyncio
    async def test_get_routing_table(self):
        """Routing table shows all subscriptions."""
        await self.router.subscribe("PLATFORM", "svc-1")
        await self.router.subscribe("AGENTS", "svc-2")
        table = await self.router.get_routing_table()
        assert table["total_channels"] == 2
        assert table["total_subscriptions"] == 2


# ---------------------------------------------------------------------------
# Dimensional Nexus Integration Tests
# ---------------------------------------------------------------------------


class TestDimensionalNexus:
    """Integration tests for the full Dimensional Nexus."""

    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_nexus.db")
        self.nexus = DimensionalNexus(db_path=self.db_path)

    def teardown_method(self):
        import shutil

        shutil.rmtree(self.tmpdir, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_register_service(self):
        """Services can be registered with the Nexus."""
        health = await self.nexus.register_service(
            service_id="svc-1",
            service_name="Gateway Service",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        assert health.service_id == "svc-1"
        assert "svc-1" in self.nexus._topology_nodes

    @pytest.mark.asyncio
    async def test_emit_event(self):
        """Events can be emitted through the Nexus."""
        await self.nexus.register_service(
            service_id="svc-1",
            service_name="Test",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        event = await self.nexus.emit_event(
            channel="PLATFORM",
            source_dimension="svc-1",
            source_tier=3,
            event_type="service_started",
        )
        assert event.event_id is not None
        assert event.causality_hash is not None

    @pytest.mark.asyncio
    async def test_check_access(self):
        """Access control decisions are made correctly."""
        self.nexus.access_bridge.set_tier_requirement("admin", 0)
        result = await self.nexus.check_access(
            subject="bot",
            resource="admin",
            action="read",
            subject_tier=5,
        )
        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_get_topology(self):
        """Topology graph includes registered services."""
        await self.nexus.register_service(
            service_id="svc-1",
            service_name="Service 1",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        await self.nexus.register_service(
            service_id="svc-2",
            service_name="Service 2",
            pillar="AGENTS",
            tier_requirement=4,
        )
        await self.nexus.add_topology_edge("svc-1", "svc-2", "data_flow")

        topology = await self.nexus.get_topology()
        assert topology["node_count"] == 2
        assert topology["edge_count"] == 1

    @pytest.mark.asyncio
    async def test_get_status(self):
        """Nexus status includes all subsystem states."""
        status = await self.nexus.get_status()
        assert "nexus_id" in status
        assert "health" in status
        assert "event_routing" in status
        assert "tier_hierarchy" in status
        assert "sentinel_channels" in status
        assert status["tier_hierarchy"]["AI"] == 3
        assert status["tier_hierarchy"]["AGENT"] == 4
        assert status["tier_hierarchy"]["BOT"] == 5

    @pytest.mark.asyncio
    async def test_service_subscribed_to_all_channels(self):
        """Registered services are subscribed to all Sentinel channels."""
        await self.nexus.register_service(
            service_id="svc-1",
            service_name="Test",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        routing = await self.nexus.event_router.get_routing_table()
        assert routing["total_channels"] == len(SentinelChannel)

    @pytest.mark.asyncio
    async def test_heartbeat_updates_health(self):
        """Heartbeats update the health aggregator."""
        await self.nexus.register_service(
            service_id="svc-1",
            service_name="Test",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        await self.nexus.health_aggregator.update_heartbeat(
            service_id="svc-1",
            status="healthy",
            response_time_ms=100.0,
        )
        summary = await self.nexus.health_aggregator.get_summary()
        assert summary.healthy == 1


# ---------------------------------------------------------------------------
# Singleton Tests
# ---------------------------------------------------------------------------


class TestNexusSingleton:
    """Tests for the singleton nexus instance."""

    def test_get_nexus_returns_instance(self):
        """get_nexus returns a DimensionalNexus instance."""
        nexus = get_nexus()
        assert isinstance(nexus, DimensionalNexus)

    def test_get_nexus_returns_same_instance(self):
        """get_nexus returns the same instance on subsequent calls."""
        nexus1 = get_nexus()
        nexus2 = get_nexus()
        assert nexus1 is nexus2


# ---------------------------------------------------------------------------
# Data Model Tests
# ---------------------------------------------------------------------------


class TestDataModels:
    """Tests for Nexus data models."""

    def test_nexus_service_health_defaults(self):
        """NexusServiceHealth has correct defaults."""
        health = NexusServiceHealth(
            service_id="test",
            service_name="Test",
            pillar="PLATFORM",
            tier_requirement=3,
        )
        assert health.status == "unknown"
        assert health.uptime_seconds == 0.0
        assert health.error_count == 0
        assert health.metadata == {}

    def test_nexus_event_auto_fields(self):
        """NexusEvent auto-generates id and timestamp."""
        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="test",
            source_tier=3,
            event_type="test",
        )
        assert event.event_id is not None
        assert event.timestamp is not None
        assert len(event.event_id) > 0

    def test_nexus_access_decision_defaults(self):
        """NexusAccessDecision has correct defaults."""
        decision = NexusAccessDecision(allowed=True)
        assert decision.reason == ""
        assert decision.tier_valid is True
        assert decision.effective_tier == 5
        assert decision.constraints == []

    def test_nexus_health_summary_defaults(self):
        """NexusHealthSummary has correct defaults."""
        summary = NexusHealthSummary()
        assert summary.total_services == 0
        assert summary.overall_status == "unknown"

    def test_nexus_topology_node(self):
        """NexusTopologyNode model works correctly."""
        node = NexusTopologyNode(
            node_id="test",
            node_type="dimension",
            tier=3,
            pillar="PLATFORM",
        )
        assert node.health_status == "unknown"
        assert node.connections == []

    def test_nexus_topology_edge(self):
        """NexusTopologyEdge model works correctly."""
        edge = NexusTopologyEdge(
            source="a",
            target="b",
            edge_type="data_flow",
        )
        assert edge.sentinel_channel is None
        assert edge.bandwidth is None


# ---------------------------------------------------------------------------
# Test WebSocket Manager
# ---------------------------------------------------------------------------


class TestNexusWSManager:
    """Tests for the WebSocket connection manager."""

    @pytest.mark.asyncio
    async def test_ws_manager_connect_disconnect(self):
        """WSManager tracks connections correctly."""
        from Dimensional.nexus.nexus_core import NexusWSManager

        manager = NexusWSManager()
        assert len(manager._connections) == 0

        class FakeWS:
            def __init__(self):
                self.accepted = False

            async def accept(self):
                self.accepted = True

        ws = FakeWS()
        await manager.connect(ws)
        assert len(manager._connections) == 1
        assert ws.accepted is True

        manager.disconnect(ws)
        assert len(manager._connections) == 0

    @pytest.mark.asyncio
    async def test_ws_manager_channel_subscribe(self):
        """WSManager tracks channel subscriptions."""
        from Dimensional.nexus.nexus_core import NexusWSManager

        manager = NexusWSManager()

        class FakeWS:
            async def accept(self):
                pass

        ws = FakeWS()
        await manager.connect(ws, channels=["PLATFORM", "SECURITY"])
        assert ws in manager._channel_subs.get("PLATFORM", [])
        assert ws in manager._channel_subs.get("SECURITY", [])
        assert ws not in manager._channel_subs.get("HIVE", [])

        manager.disconnect(ws)
        assert ws not in manager._channel_subs.get("PLATFORM", [])
        assert ws not in manager._channel_subs.get("SECURITY", [])

    @pytest.mark.asyncio
    async def test_ws_manager_broadcast(self):
        """WSManager broadcasts events to all connections."""
        from Dimensional.nexus.nexus_core import NexusEvent, NexusWSManager

        manager = NexusWSManager()

        messages = []

        class FakeWS:
            async def accept(self):
                pass

            async def send_text(self, msg):
                messages.append(msg)

        ws1 = FakeWS()
        ws2 = FakeWS()
        await manager.connect(ws1)
        await manager.connect(ws2)

        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="test",
            source_tier=3,
            event_type="test_event",
        )
        await manager.broadcast(event)
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_ws_manager_broadcast_removes_dead(self):
        """WSManager removes connections that fail on broadcast."""
        from Dimensional.nexus.nexus_core import NexusEvent, NexusWSManager

        manager = NexusWSManager()

        class DeadWS:
            async def accept(self):
                pass

            async def send_text(self, msg):
                raise ConnectionError("dead")

        ws = DeadWS()
        await manager.connect(ws)
        assert len(manager._connections) == 1

        event = NexusEvent(
            channel="PLATFORM",
            source_dimension="test",
            source_tier=3,
            event_type="test_event",
        )
        await manager.broadcast(event)
        assert len(manager._connections) == 0


# ---------------------------------------------------------------------------
# Test Dashboard Endpoint
# ---------------------------------------------------------------------------


class TestDashboardEndpoint:
    """Tests for the /dashboard and /ws/events endpoints."""

    @pytest.mark.asyncio
    async def test_dashboard_endpoint_exists(self):
        """Dashboard endpoint returns HTML when file exists."""
        from httpx import ASGITransport, AsyncClient

        from Dimensional.nexus.nexus_core import create_nexus_app

        app = create_nexus_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/dashboard")
            assert resp.status_code == 200
            assert (
                "Dimensional Nexus" in resp.text
                or "Dashboard" in resp.text
                or "html" in resp.text.lower()
            )

    @pytest.mark.asyncio
    async def test_root_includes_dashboard_endpoint(self):
        """Root endpoint lists the dashboard in available endpoints."""
        from httpx import ASGITransport, AsyncClient

        from Dimensional.nexus.nexus_core import create_nexus_app

        app = create_nexus_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/")
            data = resp.json()
            assert "/dashboard" in data.get("endpoints", [])
            assert "/ws/events (WebSocket)" in data.get("endpoints", [])


# ---------------------------------------------------------------------------
# Test Sentinel Bridge
# ---------------------------------------------------------------------------


class TestNexusSentinelBridge:
    """Tests for the Nexus ↔ Sentinel Station bidirectional bridge."""

    def test_bridge_creation(self):
        """Bridge can be created with or without a nexus."""
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        bridge = NexusSentinelBridge()
        assert bridge._nexus is None
        assert bridge._sentinel_station is None
        assert bridge._forward_to_sentinel is True
        assert bridge._forward_to_nexus is True

    def test_bridge_stats(self):
        """Bridge stats track forwarded events."""
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        bridge = NexusSentinelBridge()
        stats = bridge.stats
        assert stats["nexus_to_sentinel"] == 0
        assert stats["sentinel_to_nexus"] == 0
        assert stats["errors"] == 0

    def test_bridge_pause_resume_sentinel(self):
        """Bridge can pause/resume forwarding to Sentinel."""
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        bridge = NexusSentinelBridge()
        bridge.pause_sentinel_forward()
        assert bridge._forward_to_sentinel is False
        bridge.resume_sentinel_forward()
        assert bridge._forward_to_sentinel is True

    def test_bridge_pause_resume_nexus(self):
        """Bridge can pause/resume forwarding to Nexus."""
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        bridge = NexusSentinelBridge()
        bridge.pause_nexus_forward()
        assert bridge._forward_to_nexus is False
        bridge.resume_nexus_forward()
        assert bridge._forward_to_nexus is True

    @pytest.mark.asyncio
    async def test_bridge_status(self):
        """Bridge status returns correct info."""
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        bridge = NexusSentinelBridge()
        status = await bridge.get_status()
        assert status["bridge"] == "NexusSentinelBridge"
        assert status["sentinel_attached"] is False
        assert status["forward_to_sentinel"] is True
        assert status["forward_to_nexus"] is True
        assert "channel_map" in status
        assert "platform" in status["channel_map"]

    @pytest.mark.asyncio
    async def test_bridge_on_sentinel_event(self):
        """Bridge forwards Sentinel events into the Nexus."""
        from Dimensional.nexus.nexus_core import DimensionalNexus
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        nexus = DimensionalNexus("bridge-test")
        bridge = NexusSentinelBridge(nexus)

        await bridge.on_sentinel_event(
            channel="security",
            payload={"alert": "test"},
            event_type="security_alert",
            source="sentinel:test-dim",
        )
        assert bridge.stats["sentinel_to_nexus"] == 1

    @pytest.mark.asyncio
    async def test_bridge_on_sentinel_event_paused(self):
        """Bridge does not forward when Nexus forwarding is paused."""
        from Dimensional.nexus.nexus_core import DimensionalNexus
        from Dimensional.nexus.sentinel_bridge import NexusSentinelBridge

        nexus = DimensionalNexus("bridge-pause-test")
        bridge = NexusSentinelBridge(nexus)
        bridge.pause_nexus_forward()

        await bridge.on_sentinel_event(
            channel="platform",
            payload={"test": True},
            event_type="test",
            source="sentinel",
        )
        assert bridge.stats["sentinel_to_nexus"] == 0

    def test_bridge_singleton(self):
        """get_bridge returns a singleton instance."""
        # Reset singleton for test isolation
        import Dimensional.nexus.sentinel_bridge as _sb
        from Dimensional.nexus.sentinel_bridge import get_bridge

        _sb._bridge_instance = None
        b1 = get_bridge()
        b2 = get_bridge()
        assert b1 is b2
        # Cleanup
        _sb._bridge_instance = None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
