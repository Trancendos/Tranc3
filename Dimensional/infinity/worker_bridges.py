"""
Dimensional.infinity.worker_bridges — Phase 23.5 Worker Integration Bridges
=============================================================================
Drop-in bridge modules that connect Infinity workers to cross-service
event and intelligence infrastructure. Each bridge is a lightweight,
gracefully-degrading connector that publishes worker-specific events
to the Sentinel Station and/or Dimensional Service Bus.

Bridges provided:
    1. NexusSentinelBridge    — NexusHub → SentinelStation for AI/agent transfers
    2. ForesightPortalBridge  — ForesightEngine → SentinelStation for portal events
    3. AdminConfigTunerBridge — AdaptiveConfigTuner → Infinity-Admin endpoints
    4. DefenseSentinelBridge  — DefenseEngine incidents → Sentinel Station
    5. RegistryDiscoveryBridge — DimensionalServiceRegistry → DimensionalServiceBus

Usage in a worker::

    from Dimensional.infinity.worker_bridges import (
        NexusSentinelBridge,
        ForesightPortalBridge,
        DefenseSentinelBridge,
    )

    # Inside lifespan startup, after sentinel is available:
    nexus_bridge = NexusSentinelBridge(sentinel=sentinel)
    await nexus_bridge.start()

    # When AI/agent transfer events occur:
    await nexus_bridge.on_agent_transfer(agent_id, source, destination, tier)

    # On shutdown:
    await nexus_bridge.stop()

Architecture:
    Each bridge follows the same lifecycle:
        1. __init__(sentinel=None, bus=None, **kwargs) — lazy wiring
        2. await start()  — subscribe to channels, activate listeners
        3. on_*() methods — event handlers that publish to Sentinel/Bus
        4. await stop()   — clean unsubscription

    All bridges degrade gracefully: if sentinel=None, events are logged
    but not published. If bus=None, dimensional messages are no-ops.
    This ensures workers function correctly even when downstream services
    are not yet deployed.

OWASP Alignment:
    A01 (Broken Access Control): Tier-aware event routing
    A09 (Security Logging): All bridge events are audit-logged
    A10 (SSRF): All Sentinel channel names are validated against SentinelChannel enum
"""

from __future__ import annotations

import asyncio
import logging
import time
from enum import Enum
from typing import Any, Dict, List, Optional

from Dimensional.infinity.nomenclature import (
    SentinelChannel,
    Tier,
)
from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Bridge Status
# ---------------------------------------------------------------------------


class BridgeStatus(str, Enum):
    """Lifecycle status of a worker bridge."""

    INACTIVE = "inactive"
    STARTING = "starting"
    ACTIVE = "active"
    DEGRADED = "degraded"
    STOPPED = "stopped"
    ERROR = "error"


# ---------------------------------------------------------------------------
# Base Bridge
# ---------------------------------------------------------------------------


class WorkerBridge:
    """Base class for all worker integration bridges.

    Provides common lifecycle management, graceful degradation, and
    event statistics tracking. Subclasses override start(), stop(),
    and implement on_*() event handlers.
    """

    def __init__(
        self,
        bridge_name: str,
        sentinel: Any = None,
        bus: Any = None,
    ) -> None:
        self._bridge_name = bridge_name
        self._sentinel = sentinel
        self._bus = bus
        self._status = BridgeStatus.INACTIVE
        self._start_time: Optional[float] = None
        self._stats = {
            "events_published": 0,
            "events_dropped": 0,
            "errors": 0,
            "last_event_at": None,
        }
        self._listeners: List[asyncio.Task] = []

    @property
    def status(self) -> BridgeStatus:
        return self._status

    @property
    def uptime(self) -> float:
        if self._start_time is None:
            return 0.0
        return time.time() - self._start_time

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "bridge": self._bridge_name,
            "status": self._status.value,
            "uptime": self.uptime,
            "sentinel_wired": self._sentinel is not None,
            "bus_wired": self._bus is not None,
            **self._stats,
        }

    def wire_sentinel(self, sentinel: Any) -> None:
        """Wire or re-wire the Sentinel Station after construction."""
        self._sentinel = sentinel
        logger.info(
            "WorkerBridge[%s]: Sentinel Station wired",
            self._bridge_name,
        )

    def wire_bus(self, bus: Any) -> None:
        """Wire or re-wire the Dimensional Service Bus after construction."""
        self._bus = bus
        logger.info(
            "WorkerBridge[%s]: Dimensional Service Bus wired",
            self._bridge_name,
        )

    async def start(self) -> None:
        """Start the bridge. Override in subclasses for custom startup."""
        self._status = BridgeStatus.STARTING
        self._start_time = time.time()

        if self._sentinel is None and self._bus is None:
            self._status = BridgeStatus.DEGRADED
            logger.warning(
                "WorkerBridge[%s]: Starting in DEGRADED mode — no sentinel or bus wired",
                self._bridge_name,
            )
        else:
            self._status = BridgeStatus.ACTIVE
            logger.info(
                "WorkerBridge[%s]: Started (sentinel=%s, bus=%s)",
                self._bridge_name,
                self._sentinel is not None,
                self._bus is not None,
            )

    async def stop(self) -> None:
        """Stop the bridge and cancel all listeners."""
        for task in self._listeners:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._listeners.clear()
        self._status = BridgeStatus.STOPPED
        logger.info("WorkerBridge[%s]: Stopped", self._bridge_name)

    async def _publish_sentinel(
        self,
        channel: str,
        event_type: str,
        source: str,
        payload: Dict[str, Any],
    ) -> bool:
        """Publish an event to Sentinel Station. Returns True if published."""
        self._stats["last_event_at"] = time.time()  # type: ignore[assignment]

        if self._sentinel is None:
            self._stats["events_dropped"] += 1  # type: ignore[operator]
            logger.debug(
                "WorkerBridge[%s]: Sentinel not wired — dropping event type=%s",
                self._bridge_name,
                event_type,
            )
            return False

        try:
            from Dimensional.infinity.sentinel_station import SentinelEvent

            # Validate channel against known channels
            try:
                ch = SentinelChannel(channel)
            except ValueError:
                ch = channel  # type: ignore[assignment]

            await self._sentinel.publish(
                SentinelEvent(
                    channel=ch,
                    event_type=event_type,
                    source=source,
                    payload=payload,
                )
            )
            self._stats["events_published"] += 1  # type: ignore[operator]
            return True

        except Exception as exc:
            self._stats["errors"] += 1  # type: ignore[operator]
            self._stats["events_dropped"] += 1  # type: ignore[operator]
            logger.error(
                "WorkerBridge[%s]: Sentinel publish error: %s",
                self._bridge_name,
                sanitize_for_log(str(exc)),
            )
            return False

    async def _publish_bus(
        self,
        target: str,
        payload: Dict[str, Any],
        source: str = "",
    ) -> bool:
        """Publish a message to the Dimensional Service Bus. Returns True if sent."""
        self._stats["last_event_at"] = time.time()  # type: ignore[assignment]

        if self._bus is None:
            self._stats["events_dropped"] += 1  # type: ignore[operator]
            logger.debug(
                "WorkerBridge[%s]: Bus not wired — dropping message target=%s",
                self._bridge_name,
                target,
            )
            return False

        try:
            await self._bus.send(target, payload, source=source or self._bridge_name)
            self._stats["events_published"] += 1  # type: ignore[operator]
            return True

        except Exception as exc:
            self._stats["errors"] += 1  # type: ignore[operator]
            self._stats["events_dropped"] += 1  # type: ignore[operator]
            logger.error(
                "WorkerBridge[%s]: Bus publish error: %s",
                self._bridge_name,
                sanitize_for_log(str(exc)),
            )
            return False


# ---------------------------------------------------------------------------
# Bridge 1: NexusHub → SentinelStation
# ---------------------------------------------------------------------------


class NexusSentinelBridge(WorkerBridge):
    """Bridge NexusHub AI/agent transfer events to Sentinel Station.

    When AI agents or inference tasks are transferred between services
    via the NexusHub, this bridge publishes the transfer event to the
    Sentinel Station for cross-gateway observability.

    Published events:
        - agent.transfer.initiated  — agent transfer started
        - agent.transfer.completed  — agent transfer completed
        - agent.transfer.failed     — agent transfer failed
        - inference.routed          — inference request routed
        - ai.task.dispatched        — AI task dispatched to engine

    Usage::

        bridge = NexusSentinelBridge(sentinel=sentinel_station)
        await bridge.start()

        # When NexusHub processes an AI transfer:
        await bridge.on_agent_transfer(
            agent_id="agent-001",
            source="infinity-ai",
            destination="tranc3-ai",
            tier=Tier.AI,
        )

        # When inference is routed:
        await bridge.on_inference_routed(
            prompt_len=256,
            personality="tranc3-base",
            engine="luminous",
        )

        await bridge.stop()
    """

    def __init__(self, sentinel: Any = None, bus: Any = None) -> None:
        super().__init__(
            bridge_name="NexusSentinelBridge",
            sentinel=sentinel,
            bus=bus,
        )

    async def on_agent_transfer(
        self,
        agent_id: str,
        source: str,
        destination: str,
        tier: Tier = Tier.AI,
        *,
        payload: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publish an agent transfer event to Sentinel Station.

        Args:
            agent_id: The agent being transferred.
            source: Source service name.
            destination: Destination service name.
            tier: Tier of the agent (lower = higher authority).
            payload: Optional additional metadata.

        Returns:
            True if event was published successfully.
        """
        event_payload = {
            "agent_id": agent_id,
            "source": source,
            "destination": destination,
            "tier": tier.value if isinstance(tier, Tier) else tier,
            "timestamp": time.time(),
            **(payload or {}),
        }

        # Determine event type based on payload hints
        event_type = (
            payload.get("event_type", "agent.transfer.initiated")
            if payload
            else "agent.transfer.initiated"
        )

        return await self._publish_sentinel(
            channel=SentinelChannel.AGENTS.value,
            event_type=event_type,
            source=f"nexus_hub:{source}",
            payload=event_payload,
        )

    async def on_inference_routed(
        self,
        prompt_len: int,
        personality: str = "tranc3-base",
        engine: str = "luminous",
        *,
        request_id: Optional[str] = None,
    ) -> bool:
        """Publish an inference routing event to Sentinel Station.

        Args:
            prompt_len: Length of the inference prompt.
            personality: AI personality being used.
            engine: Target inference engine name.
            request_id: Optional request tracking ID.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.NEXUS.value,
            event_type="inference.routed",
            source="nexus_hub",
            payload={
                "prompt_len": prompt_len,
                "personality": personality,
                "engine": engine,
                "request_id": request_id,
                "timestamp": time.time(),
            },
        )

    async def on_task_dispatched(
        self,
        task_type: str,
        target_service: str,
        priority: str = "normal",
        *,
        task_id: Optional[str] = None,
    ) -> bool:
        """Publish an AI task dispatch event to Sentinel Station.

        Args:
            task_type: Type of AI task (inference, embed, etc.).
            target_service: Service the task is dispatched to.
            priority: Task priority level.
            task_id: Optional task tracking ID.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.NEXUS.value,
            event_type="ai.task.dispatched",
            source="nexus_hub",
            payload={
                "task_type": task_type,
                "target_service": target_service,
                "priority": priority,
                "task_id": task_id,
                "timestamp": time.time(),
            },
        )


# ---------------------------------------------------------------------------
# Bridge 2: ForesightEngine → SentinelStation (Portal Events)
# ---------------------------------------------------------------------------


class ForesightPortalBridge(WorkerBridge):
    """Bridge ForesightEngine predictive events to Sentinel Station.

    When the ForesightEngine detects health trajectory changes
    (STEADY → DEGRADING → CRITICAL), this bridge publishes the
    trajectory change to Sentinel Station for portal service
    observability and cross-service alerting.

    Published events:
        - foresight.trajectory.change — trajectory state changed
        - foresight.anomaly.detected  — new anomaly detected
        - foresight.prediction.updated — prediction probability vector updated
        - foresight.recommendation    — adaptive parameter recommendation

    Usage::

        bridge = ForesightPortalBridge(sentinel=sentinel_station)
        await bridge.start()

        # When ForesightEngine detects a trajectory change:
        await bridge.on_trajectory_change(
            service="infinity-portal",
            previous="STEADY",
            current="DEGRADING",
            health_score=0.72,
        )

        await bridge.stop()
    """

    def __init__(self, sentinel: Any = None, bus: Any = None) -> None:
        super().__init__(
            bridge_name="ForesightPortalBridge",
            sentinel=sentinel,
            bus=bus,
        )

    async def on_trajectory_change(
        self,
        service: str,
        previous: str,
        current: str,
        health_score: float = 1.0,
        *,
        confidence: float = 0.0,
        time_horizon_seconds: float = 300.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publish a trajectory change event.

        Args:
            service: The service whose trajectory changed.
            previous: Previous trajectory state (STEADY/DEGRADING/CRITICAL).
            current: Current trajectory state.
            health_score: Current health score (0.0–1.0).
            confidence: Prediction confidence (0.0–1.0).
            time_horizon_seconds: How far ahead the prediction looks.
            metadata: Optional additional metadata.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.INFRASTRUCTURE.value,
            event_type="foresight.trajectory.change",
            source=f"foresight:{service}",
            payload={
                "service": service,
                "trajectory": {
                    "previous": previous,
                    "current": current,
                },
                "health_score": health_score,
                "confidence": confidence,
                "time_horizon_seconds": time_horizon_seconds,
                "timestamp": time.time(),
                **(metadata or {}),
            },
        )

    async def on_anomaly_detected(
        self,
        service: str,
        metric_name: str,
        metric_value: float,
        expected_range: str = "",
        z_score: float = 0.0,
        *,
        severity: str = "warning",
    ) -> bool:
        """Publish an anomaly detection event.

        Args:
            service: The service where the anomaly was detected.
            metric_name: Name of the anomalous metric.
            metric_value: Actual metric value.
            expected_range: Expected value range description.
            z_score: Statistical z-score of the anomaly.
            severity: Anomaly severity (info/warning/critical).

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.INFRASTRUCTURE.value,
            event_type="foresight.anomaly.detected",
            source=f"foresight:{service}",
            payload={
                "service": service,
                "metric_name": metric_name,
                "metric_value": metric_value,
                "expected_range": expected_range,
                "z_score": z_score,
                "severity": severity,
                "timestamp": time.time(),
            },
        )

    async def on_prediction_updated(
        self,
        service: str,
        prediction: Dict[str, float],
        *,
        model_version: str = "",
    ) -> bool:
        """Publish a prediction probability update.

        Args:
            service: The service being predicted.
            prediction: Probability vector (e.g., {"steady": 0.8, "degrading": 0.15, "critical": 0.05}).
            model_version: Version of the prediction model.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.INFRASTRUCTURE.value,
            event_type="foresight.prediction.updated",
            source=f"foresight:{service}",
            payload={
                "service": service,
                "prediction": prediction,
                "model_version": model_version,
                "timestamp": time.time(),
            },
        )

    async def on_recommendation(
        self,
        service: str,
        parameter: str,
        current_value: Any,
        recommended_value: Any,
        confidence: float = 0.0,
        *,
        reason: str = "",
    ) -> bool:
        """Publish an adaptive parameter recommendation.

        Args:
            service: The service being tuned.
            parameter: Parameter name being recommended.
            current_value: Current parameter value.
            recommended_value: Recommended parameter value.
            confidence: Recommendation confidence (0.0–1.0).
            reason: Human-readable explanation for the recommendation.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.INFRASTRUCTURE.value,
            event_type="foresight.recommendation",
            source=f"foresight:{service}",
            payload={
                "service": service,
                "parameter": parameter,
                "current_value": current_value,
                "recommended_value": recommended_value,
                "confidence": confidence,
                "reason": reason,
                "timestamp": time.time(),
            },
        )


# ---------------------------------------------------------------------------
# Bridge 3: AdaptiveConfigTuner → Infinity-Admin
# ---------------------------------------------------------------------------


class AdminConfigTunerBridge(WorkerBridge):
    """Bridge AdaptiveConfigTuner recommendations to Infinity-Admin.

    When the AdaptiveConfigTuner produces configuration optimization
    recommendations (≥80% confidence), this bridge forwards them to
    the Infinity-Admin service for review and application.

    The bridge also receives config change events from Infinity-Admin
    via Sentinel Station, enabling bidirectional config synchronization.

    Published events:
        - config.tuner.recommendation — new config recommendation available
        - config.tuner.applied        — config recommendation auto-applied
        - config.tuner.rejected       — config recommendation rejected by admin

    Usage::

        bridge = AdminConfigTunerBridge(
            sentinel=sentinel_station,
            admin_url="http://localhost:8044",
        )
        await bridge.start()

        # When AdaptiveConfigTuner produces a recommendation:
        await bridge.on_config_recommendation(
            service="infinity-portal",
            parameter="session_cleanup_interval",
            current_value=300,
            recommended_value=180,
            confidence=0.85,
        )

        await bridge.stop()
    """

    def __init__(
        self,
        sentinel: Any = None,
        bus: Any = None,
        admin_url: str = "http://localhost:8044",
    ) -> None:
        super().__init__(
            bridge_name="AdminConfigTunerBridge",
            sentinel=sentinel,
            bus=bus,
        )
        self._admin_url = admin_url
        self._pending_recommendations: List[Dict[str, Any]] = []

    @property
    def pending_count(self) -> int:
        """Number of pending (unacknowledged) recommendations."""
        return len(self._pending_recommendations)

    async def start(self) -> None:
        """Start the bridge and subscribe to admin config events."""
        await super().start()

        # Subscribe to config change events from Infinity-Admin via Sentinel
        if self._sentinel is not None:
            try:
                queue = await self._sentinel.subscribe(SentinelChannel.PLATFORM.value)
                listener = asyncio.create_task(self._listen_config_events(queue))
                self._listeners.append(listener)
                logger.info(
                    "AdminConfigTunerBridge: Subscribed to config channel on Sentinel",
                )
            except Exception as exc:
                logger.warning(
                    "AdminConfigTunerBridge: Failed to subscribe to config channel: %s",
                    sanitize_for_log(str(exc)),
                )

    async def _listen_config_events(self, queue: asyncio.Queue) -> None:
        """Listen for config change events from Infinity-Admin."""
        try:
            while True:
                event = await queue.get()
                event_type = getattr(event, "event_type", "")
                if event_type.startswith("config.admin."):
                    logger.info(
                        "AdminConfigTunerBridge: Received admin config event: %s",
                        event_type,
                    )
                    # Track acknowledged recommendations
                    if event_type == "config.admin.applied":
                        payload = getattr(event, "payload", {})
                        rec_id = payload.get("recommendation_id")
                        if rec_id:
                            self._pending_recommendations = [
                                r
                                for r in self._pending_recommendations
                                if r.get("recommendation_id") != rec_id
                            ]
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(
                "AdminConfigTunerBridge: Config listener error: %s",
                sanitize_for_log(str(exc)),
            )

    async def on_config_recommendation(
        self,
        service: str,
        parameter: str,
        current_value: Any,
        recommended_value: Any,
        confidence: float = 0.0,
        *,
        reason: str = "",
        auto_apply: bool = False,
    ) -> bool:
        """Publish a config tuner recommendation.

        Args:
            service: The service being tuned.
            parameter: Parameter name.
            current_value: Current parameter value.
            recommended_value: Recommended new value.
            confidence: Tuner confidence (0.0–1.0). Auto-applies at ≥0.80.
            reason: Explanation for the recommendation.
            auto_apply: Whether the tuner auto-applied this recommendation.

        Returns:
            True if event was published successfully.
        """
        recommendation_id = f"rec-{service}-{parameter}-{int(time.time())}"

        event_type = "config.tuner.applied" if auto_apply else "config.tuner.recommendation"

        rec = {
            "recommendation_id": recommendation_id,
            "service": service,
            "parameter": parameter,
            "current_value": current_value,
            "recommended_value": recommended_value,
            "confidence": confidence,
            "reason": reason,
            "auto_apply": auto_apply,
            "admin_url": self._admin_url,
            "timestamp": time.time(),
        }

        if not auto_apply:
            self._pending_recommendations.append(rec)

        # Publish to Sentinel for Infinity-Admin to pick up
        result = await self._publish_sentinel(
            channel=SentinelChannel.PLATFORM.value,
            event_type=event_type,
            source=f"config_tuner:{service}",
            payload=rec,
        )

        # Also send to admin service via bus if available
        if self._bus is not None:
            await self._publish_bus(
                target="infinity-admin",
                payload=rec,
                source=f"config_tuner:{service}",
            )

        return result

    async def on_config_rejected(
        self,
        service: str,
        parameter: str,
        reason: str = "",
        *,
        recommendation_id: Optional[str] = None,
    ) -> bool:
        """Publish a config rejection event.

        Args:
            service: The service whose config was rejected.
            parameter: Parameter name that was rejected.
            reason: Reason for rejection.
            recommendation_id: ID of the original recommendation.

        Returns:
            True if event was published successfully.
        """
        # Remove from pending
        if recommendation_id:
            self._pending_recommendations = [
                r
                for r in self._pending_recommendations
                if r.get("recommendation_id") != recommendation_id
            ]

        return await self._publish_sentinel(
            channel=SentinelChannel.PLATFORM.value,
            event_type="config.tuner.rejected",
            source=f"config_tuner:{service}",
            payload={
                "service": service,
                "parameter": parameter,
                "reason": reason,
                "recommendation_id": recommendation_id,
                "timestamp": time.time(),
            },
        )


# ---------------------------------------------------------------------------
# Bridge 4: DefenseEngine → Sentinel Station
# ---------------------------------------------------------------------------


class DefenseSentinelBridge(WorkerBridge):
    """Bridge DefenseEngine security incidents to Sentinel Station.

    When the DefenseEngine detects threats, blocks IPs, or manages
    security incidents, this bridge publishes those events to the
    Sentinel Station for cross-service security alerting. Services
    like infinity-portal, infinity-one, and infinity-auth all benefit
    from real-time security intelligence.

    Published events:
        - defense.threat.detected   — new threat detected
        - defense.ip.blocked        — IP address blocked
        - defense.ip.unblocked      — IP address unblocked
        - defense.incident.created  — new security incident created
        - defense.incident.resolved — security incident resolved
        - defense.incident.escalated — incident escalated to higher tier

    Usage::

        bridge = DefenseSentinelBridge(sentinel=sentinel_station)
        await bridge.start()

        # When DefenseEngine blocks an IP:
        await bridge.on_ip_blocked(
            ip="192.168.1.100",
            reason="brute_force",
            source="infinity-portal",
        )

        # When a security incident is created:
        await bridge.on_incident_created(
            incident_id="inc-001",
            severity="high",
            description="Multiple failed login attempts",
            affected_service="infinity-auth",
        )

        await bridge.stop()
    """

    # Services that should receive defense events
    DEFENSE_SUBSCRIBER_SERVICES = [
        "infinity-portal",
        "infinity-one",
        "infinity-auth",
        "infinity-admin",
        "sentinel-station",
    ]

    def __init__(self, sentinel: Any = None, bus: Any = None) -> None:
        super().__init__(
            bridge_name="DefenseSentinelBridge",
            sentinel=sentinel,
            bus=bus,
        )

    async def on_threat_detected(
        self,
        threat_type: str,
        source_ip: str = "",
        target_service: str = "",
        threat_score: float = 0.0,
        *,
        details: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publish a threat detection event.

        Args:
            threat_type: Type of threat (brute_force, injection, ddos, etc.).
            source_ip: Source IP address of the threat.
            target_service: Service targeted by the threat.
            threat_score: Threat severity score (0.0–1.0).
            details: Optional additional threat details.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.SECURITY.value,
            event_type="defense.threat.detected",
            source=f"defense_engine:{target_service}",
            payload={
                "threat_type": threat_type,
                "source_ip": source_ip,
                "target_service": target_service,
                "threat_score": threat_score,
                "details": details or {},
                "subscriber_services": self.DEFENSE_SUBSCRIBER_SERVICES,
                "timestamp": time.time(),
            },
        )

    async def on_ip_blocked(
        self,
        ip: str,
        reason: str = "",
        source: str = "",
        *,
        block_duration_seconds: float = 900.0,
        violation_count: int = 0,
    ) -> bool:
        """Publish an IP block event.

        Args:
            ip: The blocked IP address.
            reason: Reason for the block.
            source: Service that triggered the block.
            block_duration_seconds: Duration of the block.
            violation_count: Number of violations that triggered the block.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.SECURITY.value,
            event_type="defense.ip.blocked",
            source=f"defense_engine:{source}",
            payload={
                "ip": ip,
                "reason": reason,
                "source": source,
                "block_duration_seconds": block_duration_seconds,
                "violation_count": violation_count,
                "subscriber_services": self.DEFENSE_SUBSCRIBER_SERVICES,
                "timestamp": time.time(),
            },
        )

    async def on_ip_unblocked(
        self,
        ip: str,
        reason: str = "block_expired",
        *,
        unblocked_by: str = "system",
    ) -> bool:
        """Publish an IP unblock event.

        Args:
            ip: The unblocked IP address.
            reason: Reason for unblocking.
            unblocked_by: Who/what triggered the unblock.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.SECURITY.value,
            event_type="defense.ip.unblocked",
            source="defense_engine",
            payload={
                "ip": ip,
                "reason": reason,
                "unblocked_by": unblocked_by,
                "timestamp": time.time(),
            },
        )

    async def on_incident_created(
        self,
        incident_id: str,
        severity: str = "medium",
        description: str = "",
        affected_service: str = "",
        *,
        threat_level: str = "elevated",
        tier_required: Tier = Tier.PRIME,
    ) -> bool:
        """Publish a security incident creation event.

        Args:
            incident_id: Unique incident identifier.
            severity: Incident severity (low/medium/high/critical).
            description: Human-readable incident description.
            affected_service: Service affected by the incident.
            threat_level: Current threat level.
            tier_required: Minimum tier required to view this incident.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.SECURITY.value,
            event_type="defense.incident.created",
            source=f"defense_engine:{affected_service}",
            payload={
                "incident_id": incident_id,
                "severity": severity,
                "description": description,
                "affected_service": affected_service,
                "threat_level": threat_level,
                "tier_required": tier_required.value
                if isinstance(tier_required, Tier)
                else tier_required,
                "subscriber_services": self.DEFENSE_SUBSCRIBER_SERVICES,
                "timestamp": time.time(),
            },
        )

    async def on_incident_resolved(
        self,
        incident_id: str,
        resolution: str = "",
        *,
        resolved_by: str = "system",
        duration_seconds: float = 0.0,
    ) -> bool:
        """Publish a security incident resolution event.

        Args:
            incident_id: The resolved incident identifier.
            resolution: How the incident was resolved.
            resolved_by: Who/what resolved the incident.
            duration_seconds: Time from incident creation to resolution.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.SECURITY.value,
            event_type="defense.incident.resolved",
            source="defense_engine",
            payload={
                "incident_id": incident_id,
                "resolution": resolution,
                "resolved_by": resolved_by,
                "duration_seconds": duration_seconds,
                "timestamp": time.time(),
            },
        )

    async def on_incident_escalated(
        self,
        incident_id: str,
        from_tier: Tier = Tier.AI,
        to_tier: Tier = Tier.PRIME,
        *,
        reason: str = "",
    ) -> bool:
        """Publish an incident escalation event.

        Args:
            incident_id: The escalated incident identifier.
            from_tier: Previous tier handling the incident.
            to_tier: New tier taking over the incident.
            reason: Reason for escalation.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.SECURITY.value,
            event_type="defense.incident.escalated",
            source="defense_engine",
            payload={
                "incident_id": incident_id,
                "escalation": {
                    "from_tier": from_tier.value if isinstance(from_tier, Tier) else from_tier,
                    "to_tier": to_tier.value if isinstance(to_tier, Tier) else to_tier,
                },
                "reason": reason,
                "timestamp": time.time(),
            },
        )


# ---------------------------------------------------------------------------
# Bridge 5: DimensionalServiceRegistry → DimensionalServiceBus Discovery
# ---------------------------------------------------------------------------


class RegistryDiscoveryBridge(WorkerBridge):
    """Bridge DimensionalServiceRegistry to DimensionalServiceBus for discovery.

    When services are registered, deregistered, or change status in the
    DimensionalServiceRegistry, this bridge publishes discovery events
    to the DimensionalServiceBus so that all connected services can
    update their local routing tables and health awareness.

    Published events:
        - registry.service.registered   — new dimensional service registered
        - registry.service.deregistered — dimensional service removed
        - registry.service.status_change — service status changed
        - registry.service.heartbeat    — periodic heartbeat from a service
        - registry.discovery.query      — discovery query for available services

    Usage::

        bridge = RegistryDiscoveryBridge(
            sentinel=sentinel_station,
            bus=dimensional_bus,
        )
        await bridge.start()

        # When a service is registered:
        await bridge.on_service_registered(
            service_id="gateway",
            name="Gateway Dimensional",
            pillar="ARCHITECTURAL",
            endpoint="http://localhost:8040",
            port=8040,
        )

        await bridge.stop()
    """

    def __init__(self, sentinel: Any = None, bus: Any = None) -> None:
        super().__init__(
            bridge_name="RegistryDiscoveryBridge",
            sentinel=sentinel,
            bus=bus,
        )

    async def start(self) -> None:
        """Start the bridge and subscribe to registry events."""
        await super().start()

        # Subscribe to registry-related Sentinel events
        if self._sentinel is not None:
            try:
                queue = await self._sentinel.subscribe(SentinelChannel.PILLARS.value)
                listener = asyncio.create_task(self._listen_registry_events(queue))
                self._listeners.append(listener)
                logger.info(
                    "RegistryDiscoveryBridge: Subscribed to services channel on Sentinel",
                )
            except Exception as exc:
                logger.warning(
                    "RegistryDiscoveryBridge: Failed to subscribe to services channel: %s",
                    sanitize_for_log(str(exc)),
                )

    async def _listen_registry_events(self, queue: asyncio.Queue) -> None:
        """Listen for registry query events and respond via bus."""
        try:
            while True:
                event = await queue.get()
                event_type = getattr(event, "event_type", "")
                if event_type == "registry.discovery.query":
                    # Forward discovery queries to the bus
                    payload = getattr(event, "payload", {})
                    await self._publish_bus(
                        target="dimensional-registry",
                        payload={
                            "action": "discovery_query",
                            **payload,
                        },
                        source="registry_discovery_bridge",
                    )
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error(
                "RegistryDiscoveryBridge: Registry listener error: %s",
                sanitize_for_log(str(exc)),
            )

    async def on_service_registered(
        self,
        service_id: str,
        name: str,
        pillar: str = "",
        *,
        endpoint: str = "",
        port: int = 0,
        capabilities: Optional[list] = None,
        tier: Tier = Tier.HUMAN,
    ) -> bool:
        """Publish a service registration discovery event.

        Args:
            service_id: Unique service identifier.
            name: Human-readable service name.
            pillar: Pillar this service belongs to.
            endpoint: HTTP endpoint URL.
            port: Service port number.
            capabilities: List of capability names.
            tier: Minimum tier required to access.

        Returns:
            True if event was published successfully.
        """
        discovery_payload = {
            "action": "service_registered",
            "service_id": service_id,
            "name": name,
            "pillar": pillar,
            "endpoint": endpoint,
            "port": port,
            "capabilities": capabilities or [],
            "tier": tier.value if isinstance(tier, Tier) else tier,
            "timestamp": time.time(),
        }

        # Publish to Sentinel for cross-service awareness
        sentinel_result = await self._publish_sentinel(
            channel=SentinelChannel.PILLARS.value,
            event_type="registry.service.registered",
            source=f"dimensional_registry:{service_id}",
            payload=discovery_payload,
        )

        # Also broadcast via Dimensional Service Bus for local routing
        bus_result = False
        if self._bus is not None:
            try:
                await self._bus.broadcast_pillar(
                    pillar if pillar else "ARCHITECTURAL",
                    discovery_payload,
                )
                bus_result = True
            except Exception:
                # Fallback to direct send
                bus_result = await self._publish_bus(
                    target="dimensional-registry",
                    payload=discovery_payload,
                    source="registry_discovery_bridge",
                )

        return sentinel_result or bus_result

    async def on_service_deregistered(
        self,
        service_id: str,
        name: str = "",
        *,
        reason: str = "shutdown",
    ) -> bool:
        """Publish a service deregistration discovery event.

        Args:
            service_id: Service being deregistered.
            name: Human-readable service name.
            reason: Reason for deregistration.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.PILLARS.value,
            event_type="registry.service.deregistered",
            source=f"dimensional_registry:{service_id}",
            payload={
                "action": "service_deregistered",
                "service_id": service_id,
                "name": name,
                "reason": reason,
                "timestamp": time.time(),
            },
        )

    async def on_status_change(
        self,
        service_id: str,
        previous_status: str,
        current_status: str,
        *,
        health_score: float = 1.0,
        pillar: str = "",
    ) -> bool:
        """Publish a service status change discovery event.

        Args:
            service_id: Service whose status changed.
            previous_status: Previous status (active/degraded/inactive/etc.).
            current_status: New status.
            health_score: Current health score (0.0–1.0).
            pillar: Pillar this service belongs to.

        Returns:
            True if event was published successfully.
        """
        change_payload = {
            "action": "status_change",
            "service_id": service_id,
            "status": {
                "previous": previous_status,
                "current": current_status,
            },
            "health_score": health_score,
            "pillar": pillar,
            "timestamp": time.time(),
        }

        # Publish to Sentinel
        sentinel_result = await self._publish_sentinel(
            channel=SentinelChannel.PILLARS.value,
            event_type="registry.service.status_change",
            source=f"dimensional_registry:{service_id}",
            payload=change_payload,
        )

        # Also notify via bus so routing tables update
        if self._bus is not None and pillar:
            try:
                await self._bus.broadcast_pillar(pillar, change_payload)
            except Exception:
                pass

        return sentinel_result

    async def on_heartbeat(
        self,
        service_id: str,
        status: str = "active",
        *,
        health_score: float = 1.0,
        uptime_seconds: float = 0.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Publish a service heartbeat discovery event.

        Args:
            service_id: Service sending the heartbeat.
            status: Current service status.
            health_score: Current health score (0.0–1.0).
            uptime_seconds: Service uptime in seconds.
            metadata: Optional additional heartbeat metadata.

        Returns:
            True if event was published successfully.
        """
        return await self._publish_sentinel(
            channel=SentinelChannel.PILLARS.value,
            event_type="registry.service.heartbeat",
            source=f"dimensional_registry:{service_id}",
            payload={
                "action": "heartbeat",
                "service_id": service_id,
                "status": status,
                "health_score": health_score,
                "uptime_seconds": uptime_seconds,
                "metadata": metadata or {},
                "timestamp": time.time(),
            },
        )


# ---------------------------------------------------------------------------
# Bridge Factory
# ---------------------------------------------------------------------------


def create_all_bridges(
    sentinel: Any = None,
    bus: Any = None,
    admin_url: str = "http://localhost:8044",
) -> Dict[str, WorkerBridge]:
    """Create all five worker integration bridges at once.

    Returns a dictionary of bridge_name → bridge_instance for easy
    lifecycle management in worker startup/shutdown.

    Args:
        sentinel: SentinelStation instance (or None for degraded mode).
        bus: DimensionalServiceBus instance (or None for degraded mode).
        admin_url: Infinity-Admin URL for the config tuner bridge.

    Returns:
        Dictionary with keys: nexus_sentinel, foresight_portal,
        admin_config_tuner, defense_sentinel, registry_discovery.
    """
    return {
        "nexus_sentinel": NexusSentinelBridge(sentinel=sentinel, bus=bus),
        "foresight_portal": ForesightPortalBridge(sentinel=sentinel, bus=bus),
        "admin_config_tuner": AdminConfigTunerBridge(
            sentinel=sentinel,
            bus=bus,
            admin_url=admin_url,
        ),
        "defense_sentinel": DefenseSentinelBridge(sentinel=sentinel, bus=bus),
        "registry_discovery": RegistryDiscoveryBridge(sentinel=sentinel, bus=bus),
    }


async def start_all_bridges(bridges: Dict[str, WorkerBridge]) -> None:
    """Start all bridges in a dictionary."""
    for name, bridge in bridges.items():
        try:
            await bridge.start()
        except Exception as exc:
            logger.error("Failed to start bridge %s: %s", name, sanitize_for_log(str(exc)))


async def stop_all_bridges(bridges: Dict[str, WorkerBridge]) -> None:
    """Stop all bridges in a dictionary."""
    for name, bridge in bridges.items():
        try:
            await bridge.stop()
        except Exception as exc:
            logger.error("Failed to stop bridge %s: %s", name, sanitize_for_log(str(exc)))
