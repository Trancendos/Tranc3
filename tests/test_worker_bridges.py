"""
tests/test_worker_bridges.py — Phase 23.5 Worker Integration Bridge Tests
=========================================================================
Comprehensive tests for all five worker integration bridges:
    1. NexusSentinelBridge    — NexusHub → SentinelStation
    2. ForesightPortalBridge  — ForesightEngine → SentinelStation
    3. AdminConfigTunerBridge — AdaptiveConfigTuner → Infinity-Admin
    4. DefenseSentinelBridge  — DefenseEngine incidents → Sentinel Station
    5. RegistryDiscoveryBridge — DimensionalServiceRegistry → DimensionalServiceBus

Also tests the WorkerBridge base class, factory functions, and lifecycle.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared_core.infinity.nomenclature import SentinelChannel, Tier
from shared_core.infinity.worker_bridges import (
    AdminConfigTunerBridge,
    BridgeStatus,
    DefenseSentinelBridge,
    ForesightPortalBridge,
    NexusSentinelBridge,
    RegistryDiscoveryBridge,
    WorkerBridge,
    create_all_bridges,
    start_all_bridges,
    stop_all_bridges,
)

# ---------------------------------------------------------------------------
# Mock Sentinel Station
# ---------------------------------------------------------------------------


@dataclass
class MockSentinelEvent:
    """Mock SentinelEvent for testing."""

    id: str = "test-id"
    channel: str = ""
    event_type: str = ""
    source: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""
    compressed: bool = False


class MockSentinelStation:
    """Mock SentinelStation that records published events."""

    def __init__(self) -> None:
        self.published_events: List[MockSentinelEvent] = []
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    async def publish(self, event: Any) -> None:
        self.published_events.append(event)

    async def subscribe(self, channel: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.setdefault(channel, []).append(queue)
        return queue

    def get_events_for_channel(self, channel: str) -> List[MockSentinelEvent]:
        return [e for e in self.published_events if e.channel == channel]

    def get_events_for_type(self, event_type: str) -> List[MockSentinelEvent]:
        return [e for e in self.published_events if e.event_type == event_type]


# ---------------------------------------------------------------------------
# Mock Dimensional Service Bus
# ---------------------------------------------------------------------------


class MockDimensionalBus:
    """Mock DimensionalServiceBus that records sent messages."""

    def __init__(self) -> None:
        self.sent_messages: List[Dict[str, Any]] = []
        self.broadcast_messages: List[Dict[str, Any]] = []

    async def send(self, target: str, payload: Dict[str, Any], source: str = "") -> None:
        self.sent_messages.append(
            {
                "target": target,
                "payload": payload,
                "source": source,
            }
        )

    async def broadcast_pillar(self, pillar: str, payload: Dict[str, Any]) -> None:
        self.broadcast_messages.append(
            {
                "pillar": pillar,
                "payload": payload,
            }
        )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def sentinel():
    return MockSentinelStation()


@pytest.fixture
def bus():
    return MockDimensionalBus()


@pytest.fixture
def nexus_bridge(sentinel, bus):
    return NexusSentinelBridge(sentinel=sentinel, bus=bus)


@pytest.fixture
def foresight_bridge(sentinel, bus):
    return ForesightPortalBridge(sentinel=sentinel, bus=bus)


@pytest.fixture
def admin_bridge(sentinel, bus):
    return AdminConfigTunerBridge(sentinel=sentinel, bus=bus, admin_url="http://localhost:8044")


@pytest.fixture
def defense_bridge(sentinel, bus):
    return DefenseSentinelBridge(sentinel=sentinel, bus=bus)


@pytest.fixture
def registry_bridge(sentinel, bus):
    return RegistryDiscoveryBridge(sentinel=sentinel, bus=bus)


# ===========================================================================
# WorkerBridge Base Class Tests
# ===========================================================================


class TestWorkerBridgeBase:
    """Tests for the WorkerBridge base class."""

    def test_initial_status_inactive(self):
        bridge = WorkerBridge("test-bridge")
        assert bridge.status == BridgeStatus.INACTIVE

    def test_initial_stats(self):
        bridge = WorkerBridge("test-bridge")
        stats = bridge.stats
        assert stats["bridge"] == "test-bridge"
        assert stats["status"] == "inactive"
        assert stats["events_published"] == 0
        assert stats["events_dropped"] == 0
        assert stats["errors"] == 0

    def test_uptime_before_start(self):
        bridge = WorkerBridge("test-bridge")
        assert bridge.uptime == 0.0

    @pytest.mark.asyncio
    async def test_start_degraded_no_deps(self):
        bridge = WorkerBridge("test-bridge")
        await bridge.start()
        assert bridge.status == BridgeStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_start_active_with_sentinel(self, sentinel):
        bridge = WorkerBridge("test-bridge", sentinel=sentinel)
        await bridge.start()
        assert bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_start_active_with_bus(self, bus):
        bridge = WorkerBridge("test-bridge", bus=bus)
        await bridge.start()
        assert bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_stop(self, sentinel):
        bridge = WorkerBridge("test-bridge", sentinel=sentinel)
        await bridge.start()
        await bridge.stop()
        assert bridge.status == BridgeStatus.STOPPED

    @pytest.mark.asyncio
    async def test_uptime_after_start(self, sentinel):
        bridge = WorkerBridge("test-bridge", sentinel=sentinel)
        await bridge.start()
        assert bridge.uptime > 0

    @pytest.mark.asyncio
    async def test_wire_sentinel(self):
        bridge = WorkerBridge("test-bridge")
        assert bridge._sentinel is None
        bridge.wire_sentinel(MockSentinelStation())
        assert bridge._sentinel is not None

    @pytest.mark.asyncio
    async def test_wire_bus(self):
        bridge = WorkerBridge("test-bridge")
        assert bridge._bus is None
        bridge.wire_bus(MockDimensionalBus())
        assert bridge._bus is not None

    @pytest.mark.asyncio
    async def test_publish_sentinel_no_sentinel(self):
        bridge = WorkerBridge("test-bridge")
        result = await bridge._publish_sentinel(
            channel="agents", event_type="test", source="test", payload={}
        )
        assert result is False
        assert bridge._stats["events_dropped"] == 1

    @pytest.mark.asyncio
    async def test_publish_sentinel_with_sentinel(self, sentinel):
        bridge = WorkerBridge("test-bridge", sentinel=sentinel)
        result = await bridge._publish_sentinel(
            channel="agents", event_type="test.event", source="test", payload={"key": "val"}
        )
        assert result is True
        assert bridge._stats["events_published"] == 1
        assert len(sentinel.published_events) == 1

    @pytest.mark.asyncio
    async def test_publish_bus_no_bus(self):
        bridge = WorkerBridge("test-bridge")
        result = await bridge._publish_bus(target="svc", payload={})
        assert result is False
        assert bridge._stats["events_dropped"] == 1

    @pytest.mark.asyncio
    async def test_publish_bus_with_bus(self, bus):
        bridge = WorkerBridge("test-bridge", bus=bus)
        result = await bridge._publish_bus(
            target="test-service", payload={"action": "test"}, source="bridge"
        )
        assert result is True
        assert bridge._stats["events_published"] == 1
        assert len(bus.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_publish_sentinel_error_handling(self):
        """Test that sentinel publish errors are caught gracefully."""
        failing_sentinel = MagicMock()
        failing_sentinel.publish = AsyncMock(side_effect=RuntimeError("Redis down"))

        bridge = WorkerBridge("test-bridge", sentinel=failing_sentinel)
        result = await bridge._publish_sentinel(
            channel="agents", event_type="test", source="test", payload={}
        )
        assert result is False
        assert bridge._stats["errors"] == 1
        assert bridge._stats["events_dropped"] == 1

    @pytest.mark.asyncio
    async def test_publish_bus_error_handling(self):
        """Test that bus publish errors are caught gracefully."""
        failing_bus = MagicMock()
        failing_bus.send = AsyncMock(side_effect=RuntimeError("Bus broken"))

        bridge = WorkerBridge("test-bridge", bus=failing_bus)
        result = await bridge._publish_bus(target="svc", payload={})
        assert result is False
        assert bridge._stats["errors"] == 1


# ===========================================================================
# NexusSentinelBridge Tests
# ===========================================================================


class TestNexusSentinelBridge:
    """Tests for the NexusHub → SentinelStation bridge."""

    @pytest.mark.asyncio
    async def test_start(self, nexus_bridge):
        await nexus_bridge.start()
        assert nexus_bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_stop(self, nexus_bridge):
        await nexus_bridge.start()
        await nexus_bridge.stop()
        assert nexus_bridge.status == BridgeStatus.STOPPED

    @pytest.mark.asyncio
    async def test_on_agent_transfer(self, nexus_bridge, sentinel):
        await nexus_bridge.start()
        result = await nexus_bridge.on_agent_transfer(
            agent_id="agent-001",
            source="infinity-ai",
            destination="tranc3-ai",
            tier=Tier.AI,
        )
        assert result is True
        assert len(sentinel.published_events) == 1
        event = sentinel.published_events[0]
        assert event.event_type == "agent.transfer.initiated"
        assert event.channel == SentinelChannel.AGENTS.value
        assert event.payload["agent_id"] == "agent-001"
        assert event.payload["source"] == "infinity-ai"
        assert event.payload["destination"] == "tranc3-ai"
        assert event.payload["tier"] == Tier.AI.value

    @pytest.mark.asyncio
    async def test_on_agent_transfer_completed(self, nexus_bridge, sentinel):
        await nexus_bridge.start()
        result = await nexus_bridge.on_agent_transfer(
            agent_id="agent-001",
            source="infinity-ai",
            destination="tranc3-ai",
            tier=Tier.AI,
            payload={"event_type": "agent.transfer.completed"},
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "agent.transfer.completed"

    @pytest.mark.asyncio
    async def test_on_agent_transfer_failed(self, nexus_bridge, sentinel):
        await nexus_bridge.start()
        result = await nexus_bridge.on_agent_transfer(
            agent_id="agent-002",
            source="tranc3-ai",
            destination="infinity-ai",
            tier=Tier.AGENT,
            payload={"event_type": "agent.transfer.failed", "error": "timeout"},
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "agent.transfer.failed"
        assert event.payload["error"] == "timeout"

    @pytest.mark.asyncio
    async def test_on_inference_routed(self, nexus_bridge, sentinel):
        await nexus_bridge.start()
        result = await nexus_bridge.on_inference_routed(
            prompt_len=512,
            personality="tranc3-creative",
            engine="luminous",
            request_id="req-001",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "inference.routed"
        assert event.channel == SentinelChannel.NEXUS.value
        assert event.payload["prompt_len"] == 512
        assert event.payload["personality"] == "tranc3-creative"
        assert event.payload["engine"] == "luminous"
        assert event.payload["request_id"] == "req-001"

    @pytest.mark.asyncio
    async def test_on_task_dispatched(self, nexus_bridge, sentinel):
        await nexus_bridge.start()
        result = await nexus_bridge.on_task_dispatched(
            task_type="inference",
            target_service="infinity-ai",
            priority="high",
            task_id="task-001",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "ai.task.dispatched"
        assert event.payload["task_type"] == "inference"
        assert event.payload["target_service"] == "infinity-ai"
        assert event.payload["priority"] == "high"
        assert event.payload["task_id"] == "task-001"

    @pytest.mark.asyncio
    async def test_no_sentinel_graceful_degradation(self):
        bridge = NexusSentinelBridge(sentinel=None)
        await bridge.start()
        assert bridge.status == BridgeStatus.DEGRADED
        result = await bridge.on_agent_transfer(
            agent_id="agent-001",
            source="ai",
            destination="core",
            tier=Tier.AI,
        )
        assert result is False
        assert bridge._stats["events_dropped"] == 1

    @pytest.mark.asyncio
    async def test_stats(self, nexus_bridge, sentinel):
        await nexus_bridge.start()
        await nexus_bridge.on_agent_transfer("a1", "s1", "d1", Tier.AI)
        stats = nexus_bridge.stats
        assert stats["bridge"] == "NexusSentinelBridge"
        assert stats["status"] == "active"
        assert stats["events_published"] == 1


# ===========================================================================
# ForesightPortalBridge Tests
# ===========================================================================


class TestForesightPortalBridge:
    """Tests for the ForesightEngine → SentinelStation bridge."""

    @pytest.mark.asyncio
    async def test_start(self, foresight_bridge):
        await foresight_bridge.start()
        assert foresight_bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_on_trajectory_change(self, foresight_bridge, sentinel):
        await foresight_bridge.start()
        result = await foresight_bridge.on_trajectory_change(
            service="infinity-portal",
            previous="STEADY",
            current="DEGRADING",
            health_score=0.72,
            confidence=0.85,
            time_horizon_seconds=300.0,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "foresight.trajectory.change"
        assert event.channel == SentinelChannel.INFRASTRUCTURE.value
        assert event.payload["service"] == "infinity-portal"
        assert event.payload["trajectory"]["previous"] == "STEADY"
        assert event.payload["trajectory"]["current"] == "DEGRADING"
        assert event.payload["health_score"] == 0.72
        assert event.payload["confidence"] == 0.85

    @pytest.mark.asyncio
    async def test_on_trajectory_change_critical(self, foresight_bridge, sentinel):
        await foresight_bridge.start()
        result = await foresight_bridge.on_trajectory_change(
            service="infinity-auth",
            previous="DEGRADING",
            current="CRITICAL",
            health_score=0.25,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.payload["trajectory"]["current"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_on_anomaly_detected(self, foresight_bridge, sentinel):
        await foresight_bridge.start()
        result = await foresight_bridge.on_anomaly_detected(
            service="infinity-portal",
            metric_name="request_latency_ms",
            metric_value=2500.0,
            expected_range="50-200ms",
            z_score=3.2,
            severity="critical",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "foresight.anomaly.detected"
        assert event.payload["metric_name"] == "request_latency_ms"
        assert event.payload["z_score"] == 3.2
        assert event.payload["severity"] == "critical"

    @pytest.mark.asyncio
    async def test_on_prediction_updated(self, foresight_bridge, sentinel):
        await foresight_bridge.start()
        prediction = {"steady": 0.8, "degrading": 0.15, "critical": 0.05}
        result = await foresight_bridge.on_prediction_updated(
            service="infinity-one",
            prediction=prediction,
            model_version="v2.1",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "foresight.prediction.updated"
        assert event.payload["prediction"] == prediction
        assert event.payload["model_version"] == "v2.1"

    @pytest.mark.asyncio
    async def test_on_recommendation(self, foresight_bridge, sentinel):
        await foresight_bridge.start()
        result = await foresight_bridge.on_recommendation(
            service="infinity-portal",
            parameter="session_cleanup_interval",
            current_value=300,
            recommended_value=180,
            confidence=0.87,
            reason="High session count causing memory pressure",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "foresight.recommendation"
        assert event.payload["parameter"] == "session_cleanup_interval"
        assert event.payload["recommended_value"] == 180
        assert event.payload["confidence"] == 0.87

    @pytest.mark.asyncio
    async def test_metadata_passthrough(self, foresight_bridge, sentinel):
        await foresight_bridge.start()
        result = await foresight_bridge.on_trajectory_change(
            service="infinity-portal",
            previous="STEADY",
            current="DEGRADING",
            health_score=0.6,
            metadata={"anomaly_count": 3, "suggested_action": "scale_up"},
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.payload["anomaly_count"] == 3
        assert event.payload["suggested_action"] == "scale_up"


# ===========================================================================
# AdminConfigTunerBridge Tests
# ===========================================================================


class TestAdminConfigTunerBridge:
    """Tests for the AdaptiveConfigTuner → Infinity-Admin bridge."""

    @pytest.mark.asyncio
    async def test_start(self, admin_bridge, sentinel):
        await admin_bridge.start()
        assert admin_bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_on_config_recommendation(self, admin_bridge, sentinel, bus):
        await admin_bridge.start()
        result = await admin_bridge.on_config_recommendation(
            service="infinity-portal",
            parameter="session_cleanup_interval",
            current_value=300,
            recommended_value=180,
            confidence=0.85,
            reason="Memory pressure detected",
        )
        assert result is True
        # Should be published to both Sentinel and Bus
        assert len(sentinel.published_events) == 1
        event = sentinel.published_events[0]
        assert event.event_type == "config.tuner.recommendation"
        assert event.channel == SentinelChannel.PLATFORM.value
        assert event.payload["parameter"] == "session_cleanup_interval"
        assert event.payload["confidence"] == 0.85
        # Bus should also receive the recommendation
        assert len(bus.sent_messages) == 1

    @pytest.mark.asyncio
    async def test_on_config_recommendation_auto_applied(self, admin_bridge, sentinel):
        await admin_bridge.start()
        result = await admin_bridge.on_config_recommendation(
            service="infinity-portal",
            parameter="max_connections",
            current_value=100,
            recommended_value=200,
            confidence=0.92,
            auto_apply=True,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "config.tuner.applied"

    @pytest.mark.asyncio
    async def test_pending_recommendations(self, admin_bridge, sentinel):
        await admin_bridge.start()
        assert admin_bridge.pending_count == 0
        await admin_bridge.on_config_recommendation(
            service="svc1",
            parameter="p1",
            current_value=10,
            recommended_value=20,
            confidence=0.7,
        )
        assert admin_bridge.pending_count == 1
        await admin_bridge.on_config_recommendation(
            service="svc2",
            parameter="p2",
            current_value=5,
            recommended_value=15,
            confidence=0.6,
        )
        assert admin_bridge.pending_count == 2

    @pytest.mark.asyncio
    async def test_auto_applied_not_pending(self, admin_bridge, sentinel):
        await admin_bridge.start()
        await admin_bridge.on_config_recommendation(
            service="svc1",
            parameter="p1",
            current_value=10,
            recommended_value=20,
            confidence=0.9,
            auto_apply=True,
        )
        assert admin_bridge.pending_count == 0

    @pytest.mark.asyncio
    async def test_on_config_rejected(self, admin_bridge, sentinel):
        await admin_bridge.start()
        # Add a recommendation first
        await admin_bridge.on_config_recommendation(
            service="svc1",
            parameter="p1",
            current_value=10,
            recommended_value=20,
            confidence=0.7,
        )
        rec_id = admin_bridge._pending_recommendations[0]["recommendation_id"]
        assert admin_bridge.pending_count == 1

        # Reject it
        result = await admin_bridge.on_config_rejected(
            service="svc1",
            parameter="p1",
            reason="too_risky",
            recommendation_id=rec_id,
        )
        assert result is True
        assert admin_bridge.pending_count == 0
        # The rejection event should be published
        rejection_events = [
            e for e in sentinel.published_events if e.event_type == "config.tuner.rejected"
        ]
        assert len(rejection_events) == 1

    @pytest.mark.asyncio
    async def test_admin_url_in_payload(self, admin_bridge, sentinel):
        await admin_bridge.start()
        await admin_bridge.on_config_recommendation(
            service="svc1",
            parameter="p1",
            current_value=10,
            recommended_value=20,
            confidence=0.7,
        )
        event = sentinel.published_events[0]
        assert event.payload["admin_url"] == "http://localhost:8044"

    @pytest.mark.asyncio
    async def test_recommendation_id_format(self, admin_bridge, sentinel):
        await admin_bridge.start()
        await admin_bridge.on_config_recommendation(
            service="infinity-portal",
            parameter="timeout",
            current_value=30,
            recommended_value=60,
            confidence=0.8,
        )
        event = sentinel.published_events[0]
        rec_id = event.payload["recommendation_id"]
        assert rec_id.startswith("rec-infinity-portal-timeout-")


# ===========================================================================
# DefenseSentinelBridge Tests
# ===========================================================================


class TestDefenseSentinelBridge:
    """Tests for the DefenseEngine → Sentinel Station bridge."""

    @pytest.mark.asyncio
    async def test_start(self, defense_bridge):
        await defense_bridge.start()
        assert defense_bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_on_threat_detected(self, defense_bridge, sentinel):
        await defense_bridge.start()
        result = await defense_bridge.on_threat_detected(
            threat_type="brute_force",
            source_ip="192.168.1.100",
            target_service="infinity-auth",
            threat_score=0.85,
            details={"attempt_count": 50},
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "defense.threat.detected"
        assert event.channel == SentinelChannel.SECURITY.value
        assert event.payload["threat_type"] == "brute_force"
        assert event.payload["source_ip"] == "192.168.1.100"
        assert event.payload["threat_score"] == 0.85

    @pytest.mark.asyncio
    async def test_on_ip_blocked(self, defense_bridge, sentinel):
        await defense_bridge.start()
        result = await defense_bridge.on_ip_blocked(
            ip="10.0.0.1",
            reason="brute_force",
            source="infinity-portal",
            block_duration_seconds=1800.0,
            violation_count=15,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "defense.ip.blocked"
        assert event.payload["ip"] == "10.0.0.1"
        assert event.payload["block_duration_seconds"] == 1800.0
        assert event.payload["violation_count"] == 15

    @pytest.mark.asyncio
    async def test_on_ip_unblocked(self, defense_bridge, sentinel):
        await defense_bridge.start()
        result = await defense_bridge.on_ip_unblocked(
            ip="10.0.0.1",
            reason="block_expired",
            unblocked_by="admin",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "defense.ip.unblocked"
        assert event.payload["ip"] == "10.0.0.1"
        assert event.payload["unblocked_by"] == "admin"

    @pytest.mark.asyncio
    async def test_on_incident_created(self, defense_bridge, sentinel):
        await defense_bridge.start()
        result = await defense_bridge.on_incident_created(
            incident_id="inc-001",
            severity="high",
            description="Multiple failed login attempts detected",
            affected_service="infinity-auth",
            threat_level="elevated",
            tier_required=Tier.PRIME,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "defense.incident.created"
        assert event.payload["incident_id"] == "inc-001"
        assert event.payload["severity"] == "high"
        assert event.payload["tier_required"] == Tier.PRIME.value

    @pytest.mark.asyncio
    async def test_on_incident_resolved(self, defense_bridge, sentinel):
        await defense_bridge.start()
        result = await defense_bridge.on_incident_resolved(
            incident_id="inc-001",
            resolution="IP blocked and rate limit increased",
            resolved_by="admin_user",
            duration_seconds=3600.0,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "defense.incident.resolved"
        assert event.payload["resolution"] == "IP blocked and rate limit increased"
        assert event.payload["duration_seconds"] == 3600.0

    @pytest.mark.asyncio
    async def test_on_incident_escalated(self, defense_bridge, sentinel):
        await defense_bridge.start()
        result = await defense_bridge.on_incident_escalated(
            incident_id="inc-002",
            from_tier=Tier.AI,
            to_tier=Tier.PRIME,
            reason="Exceeded automated response threshold",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "defense.incident.escalated"
        assert event.payload["escalation"]["from_tier"] == Tier.AI.value
        assert event.payload["escalation"]["to_tier"] == Tier.PRIME.value

    @pytest.mark.asyncio
    async def test_subscriber_services_in_payload(self, defense_bridge, sentinel):
        await defense_bridge.start()
        await defense_bridge.on_threat_detected(
            threat_type="ddos",
            target_service="infinity-portal",
        )
        event = sentinel.published_events[0]
        assert "subscriber_services" in event.payload
        assert "infinity-portal" in event.payload["subscriber_services"]
        assert "infinity-auth" in event.payload["subscriber_services"]

    @pytest.mark.asyncio
    async def test_multiple_events(self, defense_bridge, sentinel):
        await defense_bridge.start()
        await defense_bridge.on_ip_blocked(ip="1.1.1.1", reason="brute_force")
        await defense_bridge.on_ip_blocked(ip="2.2.2.2", reason="injection")
        await defense_bridge.on_threat_detected(threat_type="ddos")
        assert len(sentinel.published_events) == 3
        assert defense_bridge._stats["events_published"] == 3


# ===========================================================================
# RegistryDiscoveryBridge Tests
# ===========================================================================


class TestRegistryDiscoveryBridge:
    """Tests for the DimensionalServiceRegistry → DimensionalServiceBus bridge."""

    @pytest.mark.asyncio
    async def test_start(self, registry_bridge, sentinel):
        await registry_bridge.start()
        assert registry_bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_on_service_registered(self, registry_bridge, sentinel):
        await registry_bridge.start()
        result = await registry_bridge.on_service_registered(
            service_id="gateway",
            name="Gateway Dimensional",
            pillar="ARCHITECTURAL",
            endpoint="http://localhost:8040",
            port=8040,
            capabilities=["routing", "auth"],
            tier=Tier.PRIME,
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "registry.service.registered"
        assert event.channel == SentinelChannel.PILLARS.value
        assert event.payload["service_id"] == "gateway"
        assert event.payload["capabilities"] == ["routing", "auth"]

    @pytest.mark.asyncio
    async def test_on_service_deregistered(self, registry_bridge, sentinel):
        await registry_bridge.start()
        result = await registry_bridge.on_service_deregistered(
            service_id="old-service",
            name="Old Service",
            reason="shutdown",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "registry.service.deregistered"
        assert event.payload["service_id"] == "old-service"
        assert event.payload["reason"] == "shutdown"

    @pytest.mark.asyncio
    async def test_on_status_change(self, registry_bridge, sentinel):
        await registry_bridge.start()
        result = await registry_bridge.on_status_change(
            service_id="sentinel-station",
            previous_status="active",
            current_status="degraded",
            health_score=0.65,
            pillar="SECURITY",
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "registry.service.status_change"
        assert event.payload["status"]["previous"] == "active"
        assert event.payload["status"]["current"] == "degraded"

    @pytest.mark.asyncio
    async def test_on_heartbeat(self, registry_bridge, sentinel):
        await registry_bridge.start()
        result = await registry_bridge.on_heartbeat(
            service_id="infinity-portal",
            status="active",
            health_score=0.95,
            uptime_seconds=86400.0,
            metadata={"version": "0.8.0"},
        )
        assert result is True
        event = sentinel.published_events[0]
        assert event.event_type == "registry.service.heartbeat"
        assert event.payload["service_id"] == "infinity-portal"
        assert event.payload["uptime_seconds"] == 86400.0
        assert event.payload["metadata"]["version"] == "0.8.0"

    @pytest.mark.asyncio
    async def test_service_registered_broadcasts_to_bus(self, registry_bridge, sentinel, bus):
        await registry_bridge.start()
        await registry_bridge.on_service_registered(
            service_id="gateway",
            name="Gateway",
            pillar="ARCHITECTURAL",
        )
        # Should broadcast to the pillar via bus
        assert len(bus.broadcast_messages) == 1
        assert bus.broadcast_messages[0]["pillar"] == "ARCHITECTURAL"

    @pytest.mark.asyncio
    async def test_status_change_broadcasts_to_bus(self, registry_bridge, sentinel, bus):
        await registry_bridge.start()
        await registry_bridge.on_status_change(
            service_id="gateway",
            previous_status="active",
            current_status="degraded",
            pillar="ARCHITECTURAL",
        )
        assert len(bus.broadcast_messages) == 1


# ===========================================================================
# Factory & Lifecycle Tests
# ===========================================================================


class TestBridgeFactory:
    """Tests for the bridge factory and lifecycle functions."""

    def test_create_all_bridges(self, sentinel, bus):
        bridges = create_all_bridges(sentinel=sentinel, bus=bus)
        assert "nexus_sentinel" in bridges
        assert "foresight_portal" in bridges
        assert "admin_config_tuner" in bridges
        assert "defense_sentinel" in bridges
        assert "registry_discovery" in bridges
        assert len(bridges) == 5

    def test_create_all_bridges_types(self, sentinel, bus):
        bridges = create_all_bridges(sentinel=sentinel, bus=bus)
        assert isinstance(bridges["nexus_sentinel"], NexusSentinelBridge)
        assert isinstance(bridges["foresight_portal"], ForesightPortalBridge)
        assert isinstance(bridges["admin_config_tuner"], AdminConfigTunerBridge)
        assert isinstance(bridges["defense_sentinel"], DefenseSentinelBridge)
        assert isinstance(bridges["registry_discovery"], RegistryDiscoveryBridge)

    def test_create_all_bridges_no_deps(self):
        bridges = create_all_bridges()
        assert len(bridges) == 5
        # All should be in degraded mode
        for bridge in bridges.values():
            assert bridge._sentinel is None
            assert bridge._bus is None

    def test_create_all_bridges_custom_admin_url(self):
        bridges = create_all_bridges(admin_url="http://admin:9090")
        assert bridges["admin_config_tuner"]._admin_url == "http://admin:9090"

    @pytest.mark.asyncio
    async def test_start_all_bridges(self, sentinel, bus):
        bridges = create_all_bridges(sentinel=sentinel, bus=bus)
        await start_all_bridges(bridges)
        for bridge in bridges.values():
            assert bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_stop_all_bridges(self, sentinel, bus):
        bridges = create_all_bridges(sentinel=sentinel, bus=bus)
        await start_all_bridges(bridges)
        await stop_all_bridges(bridges)
        for bridge in bridges.values():
            assert bridge.status == BridgeStatus.STOPPED

    @pytest.mark.asyncio
    async def test_start_all_bridges_degraded(self):
        bridges = create_all_bridges()
        await start_all_bridges(bridges)
        for bridge in bridges.values():
            assert bridge.status == BridgeStatus.DEGRADED

    @pytest.mark.asyncio
    async def test_start_all_error_handling(self, sentinel):
        """Test that start_all_bridges handles individual bridge errors."""
        bridges = create_all_bridges(sentinel=sentinel)
        # Force one bridge to fail
        bridges["nexus_sentinel"].start = AsyncMock(side_effect=RuntimeError("test"))
        # Should not raise — errors are caught
        await start_all_bridges(bridges)

    @pytest.mark.asyncio
    async def test_stop_all_error_handling(self, sentinel):
        """Test that stop_all_bridges handles individual bridge errors."""
        bridges = create_all_bridges(sentinel=sentinel)
        await start_all_bridges(bridges)
        # Force one bridge to fail
        bridges["defense_sentinel"].stop = AsyncMock(side_effect=RuntimeError("test"))
        # Should not raise — errors are caught
        await stop_all_bridges(bridges)


# ===========================================================================
# Integration / Edge Case Tests
# ===========================================================================


class TestBridgeIntegration:
    """Integration tests and edge cases for worker bridges."""

    @pytest.mark.asyncio
    async def test_bridge_lifecycle_with_rewire(self, sentinel):
        """Test that bridges can be rewired after construction."""
        bridge = NexusSentinelBridge(sentinel=None)
        await bridge.start()
        assert bridge.status == BridgeStatus.DEGRADED

        # Wire in sentinel after start
        bridge.wire_sentinel(sentinel)
        assert bridge._sentinel is sentinel

        # Now events should work
        result = await bridge.on_agent_transfer("a1", "s", "d", Tier.AI)
        assert result is True
        assert len(sentinel.published_events) == 1

    @pytest.mark.asyncio
    async def test_multiple_bridges_share_sentinel(self, sentinel, bus):
        """Test that multiple bridges can publish to the same sentinel."""
        bridges = create_all_bridges(sentinel=sentinel, bus=bus)
        await start_all_bridges(bridges)

        # Publish from different bridges
        await bridges["nexus_sentinel"].on_agent_transfer("a1", "s", "d", Tier.AI)
        await bridges["foresight_portal"].on_trajectory_change("svc", "S", "D", 0.5)
        await bridges["defense_sentinel"].on_ip_blocked("1.2.3.4", "attack")

        # All should be in the same sentinel
        assert len(sentinel.published_events) == 3

    @pytest.mark.asyncio
    async def test_stats_tracking_across_events(self, sentinel):
        """Test that stats accurately track multiple events."""
        bridge = DefenseSentinelBridge(sentinel=sentinel)
        await bridge.start()

        await bridge.on_ip_blocked("1.1.1.1", "brute_force")
        await bridge.on_ip_blocked("2.2.2.2", "injection")
        await bridge.on_threat_detected("ddos")

        stats = bridge.stats
        assert stats["events_published"] == 3
        assert stats["last_event_at"] is not None

    @pytest.mark.asyncio
    async def test_sentinel_channel_validation(self, sentinel):
        """Test that unknown channels don't crash the bridge."""
        bridge = WorkerBridge("test-bridge", sentinel=sentinel)
        await bridge.start()
        # "unknown_channel" should not crash — falls through to string
        result = await bridge._publish_sentinel(
            channel="unknown_channel",
            event_type="test",
            source="test",
            payload={},
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_large_payload(self, sentinel):
        """Test that bridges handle large payloads correctly."""
        bridge = NexusSentinelBridge(sentinel=sentinel)
        await bridge.start()
        large_payload = {"data": "x" * 10000}
        result = await bridge.on_agent_transfer(
            agent_id="a1",
            source="s",
            destination="d",
            tier=Tier.AI,
            payload=large_payload,
        )
        assert result is True

    @pytest.mark.asyncio
    async def test_concurrent_events(self, sentinel):
        """Test that bridges handle concurrent events correctly."""
        bridge = DefenseSentinelBridge(sentinel=sentinel)
        await bridge.start()

        # Publish many events concurrently
        tasks = [bridge.on_ip_blocked(f"1.1.1.{i}", "brute_force") for i in range(50)]
        results = await asyncio.gather(*tasks)
        assert all(results)
        assert len(sentinel.published_events) == 50

    @pytest.mark.asyncio
    async def test_bridge_start_idempotent(self, sentinel):
        """Test that starting a bridge twice doesn't cause issues."""
        bridge = NexusSentinelBridge(sentinel=sentinel)
        await bridge.start()
        assert bridge.status == BridgeStatus.ACTIVE
        # Start again — should not error
        await bridge.start()
        assert bridge.status == BridgeStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_bridge_stop_idempotent(self, sentinel):
        """Test that stopping a bridge twice doesn't cause issues."""
        bridge = NexusSentinelBridge(sentinel=sentinel)
        await bridge.start()
        await bridge.stop()
        assert bridge.status == BridgeStatus.STOPPED
        # Stop again — should not error
        await bridge.stop()
        assert bridge.status == BridgeStatus.STOPPED

    @pytest.mark.asyncio
    async def test_tier_values_serialized_correctly(self, sentinel):
        """Test that Tier enums are serialized as their integer values."""
        bridge = DefenseSentinelBridge(sentinel=sentinel)
        await bridge.start()
        await bridge.on_incident_created(
            incident_id="inc-1",
            tier_required=Tier.HUMAN,  # Human/Admin — highest authority
        )
        event = sentinel.published_events[0]
        assert event.payload["tier_required"] == 0  # Tier.HUMAN.value == 0

    @pytest.mark.asyncio
    async def test_timestamp_in_all_events(self, sentinel):
        """Test that all events include a timestamp."""
        bridge = NexusSentinelBridge(sentinel=sentinel)
        await bridge.start()
        await bridge.on_agent_transfer("a1", "s", "d", Tier.AI)
        event = sentinel.published_events[0]
        assert "timestamp" in event.payload
        assert isinstance(event.payload["timestamp"], float)
        assert event.payload["timestamp"] > 0

    @pytest.mark.asyncio
    async def test_defense_subscriber_services_list(self):
        """Test that the defense bridge has the correct subscriber list."""
        bridge = DefenseSentinelBridge()
        assert "infinity-portal" in bridge.DEFENSE_SUBSCRIBER_SERVICES
        assert "infinity-one" in bridge.DEFENSE_SUBSCRIBER_SERVICES
        assert "infinity-auth" in bridge.DEFENSE_SUBSCRIBER_SERVICES
        assert "infinity-admin" in bridge.DEFENSE_SUBSCRIBER_SERVICES
        assert "sentinel-station" in bridge.DEFENSE_SUBSCRIBER_SERVICES
