"""
Tranc3 Three-Bridge Coordinator
================================
Central coordinator that wires the InfinityBridge, Nexus, and HIVE
together through Sentinel Station with proper event forwarding.

Architecture:
    ┌─────────────────┐
    │  Sentinel Station │  ← Central event bus (Redis Pub/Sub or in-process)
    └──┬──────┬──────┬─┘
       │      │      │
    ┌──┴──┐┌──┴──┐┌──┴──┐
    │ IB  ││Nexus││ HIVE │
    │Bridge││ S.B.││ S.B. │
    └──┬──┘└──┬──┘└──┬──┘
       │      │      │
    ┌──┴──┐┌──┴──┐┌──┴──┐
    │ IB  ││Nexus││ HIVE │
    │ Core││Core ││ Core │
    └─────┘└─────┘└─────┘

Three Bridges:
    1. InfinityBridge — User context / human traffic (Light bridges)
    2. The Nexus      — AI, Agent, and Bot traffic ONLY
    3. The HIVE       — Data movement and swarm system coordination

Critical Rules:
    - User traffic stays on InfinityBridge
    - AI/Agent/Bot traffic stays on Nexus
    - Data traffic stays on HIVE
    - Cross-bridge awareness is achieved through Sentinel Station
    - DimensionalNexus is ONLY valid when referring to BOTH Dimensional AND Nexus

Tier System:
    0-HUMAN, 1-ORCHESTRATOR, 2-PRIME, 3-AI, 4-AGENT, 5-BOT

Usage:
    from Dimensional.three_bridge_coordinator import ThreeBridgeCoordinator

    coordinator = ThreeBridgeCoordinator()
    await coordinator.start()

    # All three bridges are now connected through Sentinel Station
    status = await coordinator.get_unified_status()

    await coordinator.stop()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from Dimensional.hive.hive_core import (
    Hive,
    get_hive,
)
from Dimensional.hive.sentinel_bridge import (
    HiveSentinelBridge,
)
from Dimensional.hive.sentinel_bridge import (
    get_bridge as get_hive_sentinel_bridge,
)
from Dimensional.infinity.bridge.bridge_core import (
    InfinityBridge,
    InfinitySentinelBridge,
    get_infinity_bridge,
)
from Dimensional.infinity.bridge.bridge_core import (
    get_sentinel_bridge as get_infinity_sentinel_bridge,
)
from Dimensional.infinity.nomenclature import SentinelChannel, TransferSystem
from Dimensional.nexus.nexus_core import (
    Nexus,
    get_nexus,
)
from Dimensional.nexus.sentinel_bridge import (
    NexusSentinelBridge,
)
from Dimensional.nexus.sentinel_bridge import (
    get_bridge as get_nexus_sentinel_bridge,
)

logger = logging.getLogger(__name__)


class CoordinatorState(str, Enum):
    """State of the Three-Bridge Coordinator."""

    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    DEGRADED = "degraded"
    STOPPING = "stopping"


class BridgeIdentity(str, Enum):
    """Identity of each bridge in the three-bridge architecture."""

    INFINITY_BRIDGE = "infinity"
    NEXUS = "nexus"
    HIVE = "hive"


@dataclass
class BridgeHealth:
    """Health status of a single bridge."""

    bridge_type: str
    healthy: bool
    sentinel_attached: bool
    stats: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None


@dataclass
class CrossBridgeEvent:
    """An event that crosses between bridges through Sentinel Station.

    Cross-bridge events carry metadata about their origin bridge and
    the target bridge(s), ensuring that traffic scoping is maintained
    even when events need to be shared for awareness purposes.
    """

    event_id: str = ""
    source_bridge: str = ""  # BridgeIdentity value
    target_bridges: List[str] = field(default_factory=list)
    sentinel_channel: str = ""
    event_type: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "source_bridge": self.source_bridge,
            "target_bridges": self.target_bridges,
            "sentinel_channel": self.sentinel_channel,
            "event_type": self.event_type,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


class ThreeBridgeCoordinator:
    """Central coordinator that wires the three bridges together.

    The coordinator is responsible for:
    1. Starting the Sentinel Station
    2. Attaching each bridge's sentinel bridge to the station
    3. Managing cross-bridge event forwarding with proper traffic scoping
    4. Providing unified status and health monitoring
    5. Enforcing the three-bridge traffic separation rules

    Traffic Separation Rules (CRITICAL):
        - InfinityBridge events → Sentinel BRIDGE channel
        - Nexus events → Sentinel NEXUS/AGENTS/MODELS channels
        - HIVE events → Sentinel HIVE channel
        - Cross-bridge awareness events are forwarded through Sentinel
          but each bridge only processes events relevant to its domain
    """

    def __init__(
        self,
        infinity_bridge: Optional[InfinityBridge] = None,
        nexus: Optional[Nexus] = None,
        hive: Optional[Hive] = None,
        sentinel_station=None,
    ) -> None:
        # Bridge cores
        self._infinity_bridge = infinity_bridge
        self._nexus = nexus
        self._hive = hive

        # Sentinel bridges
        self._infinity_sentinel: Optional[InfinitySentinelBridge] = None
        self._nexus_sentinel: Optional[NexusSentinelBridge] = None
        self._hive_sentinel: Optional[HiveSentinelBridge] = None

        # Sentinel Station
        self._sentinel_station = sentinel_station

        # State
        self._state = CoordinatorState.STOPPED
        self._started_at: Optional[str] = None

        # Cross-bridge event tracking
        self._cross_bridge_events: List[CrossBridgeEvent] = []
        self._max_tracked_events = 1000

        # Statistics
        self._stats = {
            "total_cross_bridge_events": 0,
            "infinity_to_sentinel": 0,
            "nexus_to_sentinel": 0,
            "hive_to_sentinel": 0,
            "sentinel_to_infinity": 0,
            "sentinel_to_nexus": 0,
            "sentinel_to_hive": 0,
            "start_count": 0,
            "stop_count": 0,
        }

    # ── Properties ────────────────────────────────────────────────────────

    @property
    def state(self) -> CoordinatorState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state in (CoordinatorState.RUNNING, CoordinatorState.DEGRADED)

    @property
    def infinity_bridge(self) -> InfinityBridge:
        if self._infinity_bridge is None:
            self._infinity_bridge = get_infinity_bridge()
        return self._infinity_bridge

    @property
    def nexus(self) -> Nexus:
        if self._nexus is None:
            self._nexus = get_nexus()
        return self._nexus

    @property
    def hive(self) -> Hive:
        if self._hive is None:
            self._hive = get_hive()
        return self._hive

    @property
    def sentinel_station(self):
        if self._sentinel_station is None:
            try:
                from Dimensional.infinity.sentinel_station import get_sentinel_station

                self._sentinel_station = get_sentinel_station()
            except Exception as e:
                logger.warning(f"Could not get Sentinel Station: {e}")
        return self._sentinel_station

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Start the Three-Bridge Coordinator.

        1. Start the Sentinel Station
        2. Create and attach each sentinel bridge
        3. Register cross-bridge event handlers
        4. Transition to RUNNING state
        """
        if self._state in (CoordinatorState.RUNNING, CoordinatorState.DEGRADED):
            logger.warning("Three-Bridge Coordinator already running")
            return

        self._state = CoordinatorState.STARTING
        self._started_at = datetime.now(timezone.utc).isoformat()
        self._stats["start_count"] += 1

        try:
            # Step 1: Start Sentinel Station
            station = self.sentinel_station
            if station is not None:
                try:
                    await station.start()
                    logger.info("Sentinel Station started for Three-Bridge coordination")
                except Exception as e:
                    logger.warning(
                        f"Sentinel Station start failed, bridges run in standalone mode: {e}"
                    )

            # Step 2: Create and attach InfinityBridge sentinel
            self._infinity_sentinel = get_infinity_sentinel_bridge(self._infinity_bridge)
            if station is not None:
                try:
                    await self._infinity_sentinel.attach_sentinel(station)
                    logger.info("InfinityBridge ↔ Sentinel Bridge attached")
                except Exception as e:
                    logger.warning(f"InfinityBridge sentinel attach failed: {e}")

            # Step 3: Create and attach Nexus sentinel
            self._nexus_sentinel = get_nexus_sentinel_bridge(self._nexus)
            if station is not None:
                try:
                    await self._nexus_sentinel.attach_sentinel(station)
                    logger.info("Nexus ↔ Sentinel Bridge attached")
                except Exception as e:
                    logger.warning(f"Nexus sentinel attach failed: {e}")

            # Step 4: Create and attach HIVE sentinel
            self._hive_sentinel = get_hive_sentinel_bridge(self._hive)
            if station is not None:
                try:
                    await self._hive_sentinel.attach_sentinel(station)
                    logger.info("HIVE ↔ Sentinel Bridge attached")
                except Exception as e:
                    logger.warning(f"HIVE sentinel attach failed: {e}")

            # Step 5: Register cross-bridge event handlers on Sentinel Station
            if station is not None:
                try:
                    await station.subscribe(
                        SentinelChannel.BRIDGE.value,
                        self._on_bridge_channel_event,
                    )
                    await station.subscribe(
                        SentinelChannel.NEXUS.value,
                        self._on_nexus_channel_event,
                    )
                    await station.subscribe(
                        SentinelChannel.HIVE.value,
                        self._on_hive_channel_event,
                    )
                    logger.info("Cross-bridge event handlers registered on Sentinel Station")
                except Exception as e:
                    logger.warning(f"Cross-bridge handler registration failed: {e}")

            # Step 6: Start the InfinityBridge
            self.infinity_bridge.start()

            self._state = CoordinatorState.RUNNING
            logger.info(
                "Three-Bridge Coordinator started — "
                "InfinityBridge (user traffic) | "
                "The Nexus (AI/Agent/Bot traffic) | "
                "The HIVE (data traffic)"
            )

        except Exception as e:
            self._state = CoordinatorState.DEGRADED
            logger.error(f"Three-Bridge Coordinator start degraded: {e}")

    async def stop(self) -> None:
        """Stop the Three-Bridge Coordinator gracefully."""
        if self._state == CoordinatorState.STOPPED:
            return

        self._state = CoordinatorState.STOPPING
        self._stats["stop_count"] += 1

        try:
            # Stop the InfinityBridge
            self.infinity_bridge.stop()

            # Stop Sentinel Station
            if self._sentinel_station is not None:
                try:
                    await self._sentinel_station.stop()
                except Exception as e:
                    logger.warning(f"Sentinel Station stop error: {e}")

        except Exception as e:
            logger.error(f"Three-Bridge Coordinator stop error: {e}")

        self._state = CoordinatorState.STOPPED
        logger.info("Three-Bridge Coordinator stopped")

    # ── Cross-Bridge Event Handlers ───────────────────────────────────────

    async def _on_bridge_channel_event(self, event) -> None:
        """Handle events on the BRIDGE channel from Sentinel Station.

        BRIDGE channel events come from InfinityBridge (user/human traffic).
        These are routed to Nexus and HIVE for awareness only — they do NOT
        trigger actions in those bridges.
        """
        try:
            cross_event = CrossBridgeEvent(
                event_id=getattr(event, "id", ""),
                source_bridge=BridgeIdentity.INFINITY_BRIDGE.value,
                target_bridges=[BridgeIdentity.NEXUS.value, BridgeIdentity.HIVE.value],
                sentinel_channel=SentinelChannel.BRIDGE.value,
                event_type=getattr(event, "event_type", "unknown"),
                payload=getattr(event, "payload", {}),
            )
            self._track_cross_bridge_event(cross_event)
            self._stats["sentinel_to_infinity"] += 1
            self._stats["total_cross_bridge_events"] += 1
        except Exception as e:
            logger.debug(f"Error handling BRIDGE channel event: {e}")

    async def _on_nexus_channel_event(self, event) -> None:
        """Handle events on the NEXUS channel from Sentinel Station.

        NEXUS channel events come from The Nexus (AI/Agent/Bot traffic).
        These are routed to InfinityBridge and HIVE for awareness only.
        """
        try:
            cross_event = CrossBridgeEvent(
                event_id=getattr(event, "id", ""),
                source_bridge=BridgeIdentity.NEXUS.value,
                target_bridges=[BridgeIdentity.INFINITY_BRIDGE.value, BridgeIdentity.HIVE.value],
                sentinel_channel=SentinelChannel.NEXUS.value,
                event_type=getattr(event, "event_type", "unknown"),
                payload=getattr(event, "payload", {}),
            )
            self._track_cross_bridge_event(cross_event)
            self._stats["sentinel_to_nexus"] += 1
            self._stats["total_cross_bridge_events"] += 1
        except Exception as e:
            logger.debug(f"Error handling NEXUS channel event: {e}")

    async def _on_hive_channel_event(self, event) -> None:
        """Handle events on the HIVE channel from Sentinel Station.

        HIVE channel events come from The HIVE (data movement/swarm).
        These are routed to InfinityBridge and Nexus for awareness only.
        """
        try:
            cross_event = CrossBridgeEvent(
                event_id=getattr(event, "id", ""),
                source_bridge=BridgeIdentity.HIVE.value,
                target_bridges=[BridgeIdentity.INFINITY_BRIDGE.value, BridgeIdentity.NEXUS.value],
                sentinel_channel=SentinelChannel.HIVE.value,
                event_type=getattr(event, "event_type", "unknown"),
                payload=getattr(event, "payload", {}),
            )
            self._track_cross_bridge_event(cross_event)
            self._stats["sentinel_to_hive"] += 1
            self._stats["total_cross_bridge_events"] += 1
        except Exception as e:
            logger.debug(f"Error handling HIVE channel event: {e}")

    def _track_cross_bridge_event(self, event: CrossBridgeEvent) -> None:
        """Track a cross-bridge event for monitoring and debugging."""
        self._cross_bridge_events.append(event)
        if len(self._cross_bridge_events) > self._max_tracked_events:
            self._cross_bridge_events = self._cross_bridge_events[-self._max_tracked_events :]

    # ── Cross-Bridge Event Publication ────────────────────────────────────

    async def publish_cross_bridge_event(
        self,
        source_bridge: str,
        sentinel_channel: str,
        event_type: str,
        payload: Dict[str, Any],
        target_bridges: Optional[List[str]] = None,
    ) -> CrossBridgeEvent:
        """Publish a cross-bridge event through Sentinel Station.

        This method provides a controlled way for one bridge to send
        awareness events to other bridges. It enforces the rule that
        each bridge only handles its own traffic domain, and cross-bridge
        events are purely for awareness and coordination.

        Args:
            source_bridge: The bridge originating the event (BridgeIdentity value)
            sentinel_channel: The SentinelChannel to publish on
            event_type: Type of cross-bridge event
            payload: Event data
            target_bridges: Optional list of target bridge identities

        Returns:
            The CrossBridgeEvent that was published
        """
        # Determine target bridges based on source (if not specified)
        if target_bridges is None:
            all_bridges = [b.value for b in BridgeIdentity]
            target_bridges = [b for b in all_bridges if b != source_bridge]

        cross_event = CrossBridgeEvent(
            source_bridge=source_bridge,
            target_bridges=target_bridges,
            sentinel_channel=sentinel_channel,
            event_type=event_type,
            payload=payload,
        )

        # Publish through Sentinel Station
        if self._sentinel_station is not None:
            try:
                await self._sentinel_station.publish(
                    channel=sentinel_channel,
                    payload={
                        **payload,
                        "_cross_bridge": True,
                        "_source_bridge": source_bridge,
                        "_target_bridges": target_bridges,
                    },
                    event_type=event_type,
                    source=f"coordinator:{source_bridge}",
                )
            except Exception as e:
                logger.warning(f"Failed to publish cross-bridge event: {e}")

        # Track the event
        self._track_cross_bridge_event(cross_event)
        self._stats["total_cross_bridge_events"] += 1

        # Update source-specific stats
        stat_key = f"{source_bridge}_to_sentinel"
        if stat_key in self._stats:
            self._stats[stat_key] += 1

        return cross_event

    # ── Health & Status ───────────────────────────────────────────────────

    def get_bridge_health(self, bridge_type: str) -> BridgeHealth:
        """Get the health of a specific bridge.

        Args:
            bridge_type: One of 'infinity', 'nexus', 'hive'

        Returns:
            BridgeHealth dataclass with current bridge status
        """
        try:
            if bridge_type == BridgeIdentity.INFINITY_BRIDGE.value:
                health = self.infinity_bridge.get_health()
                sentinel_attached = (
                    self._infinity_sentinel is not None
                    and self._infinity_sentinel._sentinel_station is not None
                )
                return BridgeHealth(
                    bridge_type="infinity",
                    healthy=health.get("healthy", False),
                    sentinel_attached=sentinel_attached,
                    stats=health,
                )

            elif bridge_type == BridgeIdentity.NEXUS.value:
                sentinel_attached = (
                    self._nexus_sentinel is not None
                    and self._nexus_sentinel._sentinel_station is not None
                )
                return BridgeHealth(
                    bridge_type="nexus",
                    healthy=True,  # Nexus is healthy if instantiated
                    sentinel_attached=sentinel_attached,
                    stats={"topology_nodes": 0},  # Sync snapshot
                )

            elif bridge_type == BridgeIdentity.HIVE.value:
                sentinel_attached = (
                    self._hive_sentinel is not None
                    and self._hive_sentinel._sentinel_station is not None
                )
                return BridgeHealth(
                    bridge_type="hive",
                    healthy=True,  # HIVE is healthy if instantiated
                    sentinel_attached=sentinel_attached,
                    stats={"sources": 0, "sinks": 0},  # Sync snapshot
                )

            else:
                return BridgeHealth(
                    bridge_type=bridge_type,
                    healthy=False,
                    sentinel_attached=False,
                    error=f"Unknown bridge type: {bridge_type}",
                )

        except Exception as e:
            return BridgeHealth(
                bridge_type=bridge_type,
                healthy=False,
                sentinel_attached=False,
                error=str(e),
            )

    async def get_unified_status(self) -> Dict[str, Any]:
        """Get the unified status of all three bridges.

        This is the primary status endpoint that shows the health and
        activity of all three bridges through a single response.
        """
        # Gather status from each bridge (handle async)
        ib_status = self.infinity_bridge.get_status()

        nexus_status = {}
        try:
            nexus_status = await self.nexus.get_status()
        except Exception as e:
            nexus_status = {"error": str(e), "bridge_type": "nexus"}

        hive_status = {}
        try:
            hive_status = await self.hive.get_status()
        except Exception as e:
            hive_status = {"error": str(e), "bridge_type": "hive"}

        # Sentinel bridge statuses
        infinity_sb_status = {}
        if self._infinity_sentinel is not None:
            try:
                infinity_sb_status = await self._infinity_sentinel.get_status()
            except Exception as e:
                infinity_sb_status = {"error": str(e)}

        nexus_sb_status = {}
        if self._nexus_sentinel is not None:
            try:
                nexus_sb_status = await self._nexus_sentinel.get_status()
            except Exception as e:
                nexus_sb_status = {"error": str(e)}

        hive_sb_status = {}
        if self._hive_sentinel is not None:
            try:
                hive_sb_status = await self._hive_sentinel.get_status()
            except Exception as e:
                hive_sb_status = {"error": str(e)}

        # Sentinel Station status
        station_status = {}
        if self._sentinel_station is not None:
            try:
                station_status = self._sentinel_station.get_stats()
            except Exception as e:
                station_status = {"error": str(e)}

        return {
            "coordinator": {
                "state": self._state.value,
                "started_at": self._started_at,
                "uptime_seconds": (
                    round(
                        time.time()
                        - time.mktime(datetime.fromisoformat(self._started_at).timetuple()),
                        1,
                    )
                    if self._started_at
                    else 0
                ),
            },
            "three_bridges": {
                "infinity_bridge": {
                    "name": "InfinityBridge",
                    "role": "User Context & Human Traffic",
                    "description": "User Context & Human Traffic (Light Bridge)",
                    "bridge_type": "infinity",
                    "status": ib_status,
                    "sentinel_bridge": infinity_sb_status,
                },
                "nexus": {
                    "name": "The Nexus",
                    "role": "AI, Agent, and Bot Traffic",
                    "description": "AI, Agent, and Bot Traffic Coordination",
                    "bridge_type": "nexus",
                    "status": nexus_status,
                    "sentinel_bridge": nexus_sb_status,
                },
                "hive": {
                    "name": "The HIVE",
                    "role": "Data Movement & Swarm Coordination",
                    "description": "Data Movement & Swarm System Coordination",
                    "bridge_type": "hive",
                    "status": hive_status,
                    "sentinel_bridge": hive_sb_status,
                },
            },
            "sentinel_station": station_status,
            "traffic_separation": {
                "infinity_bridge": "User/human context and navigation ONLY",
                "nexus": "AI, Agent, Bot service registration and events ONLY",
                "hive": "Data sources, sinks, pipelines, and swarm coordination ONLY",
                "cross_bridge": "Awareness events through Sentinel Station (no direct method calls)",
            },
            "cross_bridge_events": {
                "total": self._stats["total_cross_bridge_events"],
                "recent": [e.to_dict() for e in self._cross_bridge_events[-10:]],
            },
            "stats": dict(self._stats),
            "tier_system": {
                "HUMAN": 0,
                "ORCHESTRATOR": 1,
                "PRIME": 2,
                "AI": 3,
                "AGENT": 4,
                "BOT": 5,
            },
            "port_assignments": {
                "nexus": 8050,
                "hive": 8060,
                "infinity_bridge": 8070,
            },
            "transfer_systems": {ts.value: ts.name for ts in TransferSystem},
        }

    async def health_check(self) -> Dict[str, Any]:
        """Perform a quick health check of all three bridges."""
        ib_health = self.get_bridge_health(BridgeIdentity.INFINITY_BRIDGE.value)
        nexus_health = self.get_bridge_health(BridgeIdentity.NEXUS.value)
        hive_health = self.get_bridge_health(BridgeIdentity.HIVE.value)

        all_healthy = ib_health.healthy and nexus_health.healthy and hive_health.healthy
        all_attached = (
            ib_health.sentinel_attached
            and nexus_health.sentinel_attached
            and hive_health.sentinel_attached
        )

        return {
            "status": "healthy" if all_healthy else "degraded",
            "all_bridges_healthy": all_healthy,
            "all_sentinels_attached": all_attached,
            "bridges": {
                "infinity_bridge": {
                    "healthy": ib_health.healthy,
                    "sentinel_attached": ib_health.sentinel_attached,
                    "error": ib_health.error,
                },
                "nexus": {
                    "healthy": nexus_health.healthy,
                    "sentinel_attached": nexus_health.sentinel_attached,
                    "error": nexus_health.error,
                },
                "hive": {
                    "healthy": hive_health.healthy,
                    "sentinel_attached": hive_health.sentinel_attached,
                    "error": hive_health.error,
                },
            },
            "sentinel_station": self._sentinel_station is not None,
            "coordinator_state": self._state.value,
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get coordinator statistics."""
        return dict(self._stats)

    def get_recent_cross_bridge_events(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent cross-bridge events for monitoring."""
        events = self._cross_bridge_events[-limit:]
        return [e.to_dict() for e in events]


# ── Module-level Singleton ──────────────────────────────────────────────────

_coordinator_instance: Optional[ThreeBridgeCoordinator] = None


def get_coordinator() -> ThreeBridgeCoordinator:
    """Get or create the Three-Bridge Coordinator singleton."""
    global _coordinator_instance
    if _coordinator_instance is None:
        _coordinator_instance = ThreeBridgeCoordinator()
    return _coordinator_instance
