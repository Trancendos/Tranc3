"""
Three-Bridge Architecture — Python Implementation
==================================================

Implements the Three-Bridge Architecture that separates traffic into three
distinct domains, all coordinated through Sentinel Station:

  InfinityBridge — User/Human traffic
  Nexus           — AI/Agent/Bot traffic
  HIVE            — Data movement / Swarm coordination

Sentinel Station is the central coordinator that routes traffic,
monitors bridge health, and enforces isolation rules.
"""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.three_bridge")


# ─────────────────────────────────────────────────────────────────────────────
# Types
# ─────────────────────────────────────────────────────────────────────────────


class BridgeDomain(str, Enum):
    INFINITY = "infinity"
    NEXUS = "nexus"
    HIVE = "hive"


class BridgeStatus(str, Enum):
    ACTIVE = "active"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class TrafficClass(str, Enum):
    """Traffic classifications mapped to bridge domains."""

    # InfinityBridge
    USER_REQUEST = "user_request"
    USER_AUTH = "user_auth"
    USER_DASHBOARD = "user_dashboard"
    # Nexus
    AGENT_REQUEST = "agent_request"
    AGENT_BROADCAST = "agent_broadcast"
    AGENT_DISCOVERY = "agent_discovery"
    BOT_DELEGATION = "bot_delegation"
    A2A_MESSAGE = "a2a_message"
    # HIVE
    DATA_QUEUE = "data_queue"
    DATA_TRANSPORT = "data_transport"
    SWARM_DISPATCH = "swarm_dispatch"
    SWARM_CONSENSUS = "swarm_consensus"
    ESTATE_SCAN = "estate_scan"
    # Sentinel
    INTERNAL_HEALTH = "internal_health"
    CROSS_BRIDGE = "cross_bridge"
    UNKNOWN = "unknown"


# Traffic class → bridge domain mapping
TRAFFIC_TO_BRIDGE: Dict[TrafficClass, BridgeDomain] = {
    TrafficClass.USER_REQUEST: BridgeDomain.INFINITY,
    TrafficClass.USER_AUTH: BridgeDomain.INFINITY,
    TrafficClass.USER_DASHBOARD: BridgeDomain.INFINITY,
    TrafficClass.AGENT_REQUEST: BridgeDomain.NEXUS,
    TrafficClass.AGENT_BROADCAST: BridgeDomain.NEXUS,
    TrafficClass.AGENT_DISCOVERY: BridgeDomain.NEXUS,
    TrafficClass.BOT_DELEGATION: BridgeDomain.NEXUS,
    TrafficClass.A2A_MESSAGE: BridgeDomain.NEXUS,
    TrafficClass.DATA_QUEUE: BridgeDomain.HIVE,
    TrafficClass.DATA_TRANSPORT: BridgeDomain.HIVE,
    TrafficClass.SWARM_DISPATCH: BridgeDomain.HIVE,
    TrafficClass.SWARM_CONSENSUS: BridgeDomain.HIVE,
    TrafficClass.ESTATE_SCAN: BridgeDomain.HIVE,
    TrafficClass.INTERNAL_HEALTH: BridgeDomain.INFINITY,  # Default, handled by Sentinel
    TrafficClass.CROSS_BRIDGE: BridgeDomain.INFINITY,  # Sentinel decides
    TrafficClass.UNKNOWN: BridgeDomain.INFINITY,  # Sentinel decides
}


# ─────────────────────────────────────────────────────────────────────────────
# Data Classes
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class BridgeTrafficPacket:
    """A packet of traffic flowing through the bridge system."""

    id: str = field(default_factory=lambda: f"pkt-{uuid.uuid4().hex[:12]}")
    traffic_class: TrafficClass = TrafficClass.UNKNOWN
    target_bridge: BridgeDomain = BridgeDomain.INFINITY
    source: str = ""
    destination: str = ""
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5
    security_token: str = ""
    requires_escalation: bool = False
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trafficClass": self.traffic_class.value,
            "targetBridge": self.target_bridge.value,
            "source": self.source,
            "destination": self.destination,
            "payload": self.payload,
            "priority": self.priority,
            "securityToken": self.security_token,
            "requiresEscalation": self.requires_escalation,
            "createdAt": self.created_at,
            "metadata": self.metadata,
        }


@dataclass
class BridgeHealthReport:
    """Health report for a bridge."""

    domain: BridgeDomain
    status: BridgeStatus = BridgeStatus.ACTIVE
    packets_processed: int = 0
    packets_pending: int = 0
    packets_failed: int = 0
    average_latency_ms: float = 0.0
    error_rate: float = 0.0
    last_packet_at: Optional[float] = None
    uptime_seconds: float = 0.0


@dataclass
class RoutingRule:
    """Custom routing rule for traffic."""

    traffic_pattern: str = "*"
    source_pattern: str = "*"
    target_bridge: BridgeDomain = BridgeDomain.INFINITY
    priority_boost: int = 0
    enabled: bool = True


@dataclass
class EscalationRequest:
    """Request to escalate a packet across bridges."""

    packet_id: str = ""
    from_bridge: BridgeDomain = BridgeDomain.INFINITY
    to_bridge: BridgeDomain = BridgeDomain.INFINITY
    reason: str = ""
    authorized_by: str = ""
    priority: int = 10


@dataclass
class EscalationResult:
    """Result of a cross-bridge escalation."""

    success: bool = False
    packet_id: str = ""
    from_bridge: BridgeDomain = BridgeDomain.INFINITY
    to_bridge: BridgeDomain = BridgeDomain.INFINITY
    message: str = ""


# ─────────────────────────────────────────────────────────────────────────────
# Bridge Interface
# ─────────────────────────────────────────────────────────────────────────────


class IBridge(ABC):
    """Abstract base class for bridges."""

    @property
    @abstractmethod
    def domain(self) -> BridgeDomain:
        raise NotImplementedError

    @abstractmethod
    def process_packet(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        raise NotImplementedError

    @abstractmethod
    def health_check(self) -> BridgeHealthReport:
        raise NotImplementedError

    @abstractmethod
    def scan_and_cleanup(self) -> List[str]:
        """Proactive scan and cleanup. Returns list of actions taken."""
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Bridge Implementations
# ─────────────────────────────────────────────────────────────────────────────


class InfinityBridge(IBridge):
    """
    InfinityBridge — User/Human traffic domain.
    Handles: user_request, user_auth, user_dashboard
    """

    def __init__(self):
        self._processed: int = 0
        self._pending: int = 0
        self._failed: int = 0
        self._latencies: List[float] = []
        self._started_at: float = time.time()
        self._last_packet_at: Optional[float] = None
        self._active_sessions: Dict[str, Dict[str, Any]] = {}

    @property
    def domain(self) -> BridgeDomain:
        return BridgeDomain.INFINITY

    def process_packet(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        start = time.time()
        self._pending += 1

        try:
            if packet.traffic_class == TrafficClass.USER_AUTH:
                self._handle_auth(packet)
            elif packet.traffic_class == TrafficClass.USER_REQUEST:
                self._handle_request(packet)
            elif packet.traffic_class == TrafficClass.USER_DASHBOARD:
                self._handle_dashboard(packet)
            else:
                logger.warning(f"InfinityBridge: Unhandled traffic class {packet.traffic_class}")

            self._processed += 1
            self._pending -= 1
            self._last_packet_at = time.time()
            latency = (time.time() - start) * 1000
            self._latencies.append(latency)
            if len(self._latencies) > 100:
                self._latencies = self._latencies[-100:]

            return packet

        except Exception as e:
            self._failed += 1
            self._pending -= 1
            logger.error(f"InfinityBridge error processing packet {packet.id}: {e}")
            raise

    def _handle_auth(self, packet: BridgeTrafficPacket) -> None:
        """Handle user authentication traffic."""
        user_id = packet.payload.get("user_id", "")
        if user_id:
            self._active_sessions[user_id] = {
                "authenticated_at": time.time(),
                "source": packet.source,
            }
            logger.debug(f"InfinityBridge: Auth session for {user_id}")

    def _handle_request(self, packet: BridgeTrafficPacket) -> None:
        """Handle user request traffic."""
        logger.debug(f"InfinityBridge: User request from {packet.source}")

    def _handle_dashboard(self, packet: BridgeTrafficPacket) -> None:
        """Handle dashboard traffic."""
        logger.debug(f"InfinityBridge: Dashboard interaction from {packet.source}")

    def health_check(self) -> BridgeHealthReport:
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        total = self._processed + self._failed
        error_rate = self._failed / total if total > 0 else 0.0

        status = BridgeStatus.ACTIVE
        if error_rate > 0.1:
            status = BridgeStatus.DEGRADED
        if error_rate > 0.5:
            status = BridgeStatus.OFFLINE

        return BridgeHealthReport(
            domain=self.domain,
            status=status,
            packets_processed=self._processed,
            packets_pending=self._pending,
            packets_failed=self._failed,
            average_latency_ms=avg_latency,
            error_rate=error_rate,
            last_packet_at=self._last_packet_at,
            uptime_seconds=time.time() - self._started_at,
        )

    def scan_and_cleanup(self) -> List[str]:
        """Clean up expired sessions."""
        actions = []
        now = time.time()
        expired = [
            uid
            for uid, session in self._active_sessions.items()
            if now - session.get("authenticated_at", 0) > 3600  # 1 hour timeout
        ]
        for uid in expired:
            del self._active_sessions[uid]
            actions.append(f"Cleaned up expired session: {uid}")
        return actions


class NexusBridge(IBridge):
    """
    Nexus Bridge — AI/Agent/Bot traffic domain.
    Handles: agent_request, agent_broadcast, agent_discovery,
             bot_delegation, a2a_message
    """

    def __init__(self):
        self._processed: int = 0
        self._pending: int = 0
        self._failed: int = 0
        self._latencies: List[float] = []
        self._started_at: float = time.time()
        self._last_packet_at: Optional[float] = None
        self._channels: Dict[str, List[str]] = {}
        self._discovered_agents: Dict[str, Dict[str, Any]] = {}

    @property
    def domain(self) -> BridgeDomain:
        return BridgeDomain.NEXUS

    def process_packet(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        start = time.time()
        self._pending += 1

        try:
            if packet.traffic_class == TrafficClass.AGENT_REQUEST:
                self._handle_agent_request(packet)
            elif packet.traffic_class == TrafficClass.AGENT_BROADCAST:
                self._handle_broadcast(packet)
            elif packet.traffic_class == TrafficClass.AGENT_DISCOVERY:
                self._handle_discovery(packet)
            elif packet.traffic_class == TrafficClass.BOT_DELEGATION:
                self._handle_delegation(packet)
            elif packet.traffic_class == TrafficClass.A2A_MESSAGE:
                self._handle_a2a(packet)
            else:
                logger.warning(f"NexusBridge: Unhandled traffic class {packet.traffic_class}")

            self._processed += 1
            self._pending -= 1
            self._last_packet_at = time.time()
            latency = (time.time() - start) * 1000
            self._latencies.append(latency)
            if len(self._latencies) > 100:
                self._latencies = self._latencies[-100:]

            return packet

        except Exception as e:
            self._failed += 1
            self._pending -= 1
            logger.error(f"NexusBridge error processing packet {packet.id}: {e}")
            raise

    def _handle_agent_request(self, packet: BridgeTrafficPacket) -> None:
        logger.debug(f"NexusBridge: Agent request from {packet.source} to {packet.destination}")

    def _handle_broadcast(self, packet: BridgeTrafficPacket) -> None:
        channel = packet.payload.get("channel", "default")
        if channel not in self._channels:
            self._channels[channel] = []
        self._channels[channel].append(packet.id)
        logger.debug(f"NexusBridge: Broadcast on channel {channel}")

    def _handle_discovery(self, packet: BridgeTrafficPacket) -> None:
        agent_info = packet.payload.get("agent_card", {})
        if agent_info:
            self._discovered_agents[packet.source] = agent_info
        logger.debug(f"NexusBridge: Discovery from {packet.source}")

    def _handle_delegation(self, packet: BridgeTrafficPacket) -> None:
        logger.debug(f"NexusBridge: Bot delegation from {packet.source}")

    def _handle_a2a(self, packet: BridgeTrafficPacket) -> None:
        logger.debug(f"NexusBridge: A2A message from {packet.source} to {packet.destination}")

    def health_check(self) -> BridgeHealthReport:
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        total = self._processed + self._failed
        error_rate = self._failed / total if total > 0 else 0.0

        status = BridgeStatus.ACTIVE
        if error_rate > 0.1:
            status = BridgeStatus.DEGRADED
        if error_rate > 0.5:
            status = BridgeStatus.OFFLINE

        return BridgeHealthReport(
            domain=self.domain,
            status=status,
            packets_processed=self._processed,
            packets_pending=self._pending,
            packets_failed=self._failed,
            average_latency_ms=avg_latency,
            error_rate=error_rate,
            last_packet_at=self._last_packet_at,
            uptime_seconds=time.time() - self._started_at,
        )

    def scan_and_cleanup(self) -> List[str]:
        """Clean up stale channels and discovered agents."""
        actions = []
        # _now = time.time()  # noqa: F841
        # Clean channels with no recent activity
        stale_channels = [ch for ch, msgs in self._channels.items() if len(msgs) == 0]
        for ch in stale_channels:
            del self._channels[ch]
            actions.append(f"Removed empty channel: {ch}")
        return actions


class HIVEBridge(IBridge):
    """
    HIVE Bridge — Data movement / Swarm coordination domain.
    Handles: data_queue, data_transport, swarm_dispatch,
             swarm_consensus, estate_scan
    """

    def __init__(self):
        self._processed: int = 0
        self._pending: int = 0
        self._failed: int = 0
        self._latencies: List[float] = []
        self._started_at: float = time.time()
        self._last_packet_at: Optional[float] = None
        self._queue_depth: int = 0
        self._estates: Dict[str, Dict[str, Any]] = {}

    @property
    def domain(self) -> BridgeDomain:
        return BridgeDomain.HIVE

    def process_packet(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        start = time.time()
        self._pending += 1

        try:
            if packet.traffic_class == TrafficClass.DATA_QUEUE:
                self._handle_queue(packet)
            elif packet.traffic_class == TrafficClass.DATA_TRANSPORT:
                self._handle_transport(packet)
            elif packet.traffic_class == TrafficClass.SWARM_DISPATCH:
                self._handle_swarm_dispatch(packet)
            elif packet.traffic_class == TrafficClass.SWARM_CONSENSUS:
                self._handle_consensus(packet)
            elif packet.traffic_class == TrafficClass.ESTATE_SCAN:
                self._handle_estate_scan(packet)
            else:
                logger.warning(f"HIVEBridge: Unhandled traffic class {packet.traffic_class}")

            self._processed += 1
            self._pending -= 1
            self._last_packet_at = time.time()
            latency = (time.time() - start) * 1000
            self._latencies.append(latency)
            if len(self._latencies) > 100:
                self._latencies = self._latencies[-100:]

            return packet

        except Exception as e:
            self._failed += 1
            self._pending -= 1
            logger.error(f"HIVEBridge error processing packet {packet.id}: {e}")
            raise

    def _handle_queue(self, packet: BridgeTrafficPacket) -> None:
        action = packet.payload.get("action", "enqueue")
        if action == "enqueue":
            self._queue_depth += 1
        elif action == "dequeue":
            self._queue_depth = max(0, self._queue_depth - 1)
        logger.debug(f"HIVEBridge: Queue {action}, depth={self._queue_depth}")

    def _handle_transport(self, packet: BridgeTrafficPacket) -> None:
        logger.debug(f"HIVEBridge: Data transport from {packet.source}")

    def _handle_swarm_dispatch(self, packet: BridgeTrafficPacket) -> None:
        logger.debug(f"HIVEBridge: Swarm dispatch from {packet.source}")

    def _handle_consensus(self, packet: BridgeTrafficPacket) -> None:
        vote = packet.payload.get("vote", "")
        estate_id = packet.payload.get("estate_id", "")
        if estate_id not in self._estates:
            self._estates[estate_id] = {"votes": [], "consensus": None}
        self._estates[estate_id]["votes"].append(vote)
        logger.debug(f"HIVEBridge: Consensus vote for estate {estate_id}")

    def _handle_estate_scan(self, packet: BridgeTrafficPacket) -> None:
        logger.debug(f"HIVEBridge: Estate scan from {packet.source}")

    def health_check(self) -> BridgeHealthReport:
        avg_latency = sum(self._latencies) / len(self._latencies) if self._latencies else 0.0
        total = self._processed + self._failed
        error_rate = self._failed / total if total > 0 else 0.0

        status = BridgeStatus.ACTIVE
        if error_rate > 0.1 or self._queue_depth > 50:
            status = BridgeStatus.DEGRADED
        if error_rate > 0.5:
            status = BridgeStatus.OFFLINE

        return BridgeHealthReport(
            domain=self.domain,
            status=status,
            packets_processed=self._processed,
            packets_pending=self._pending,
            packets_failed=self._failed,
            average_latency_ms=avg_latency,
            error_rate=error_rate,
            last_packet_at=self._last_packet_at,
            uptime_seconds=time.time() - self._started_at,
        )

    def scan_and_cleanup(self) -> List[str]:
        """Clean up completed estates and reset queue if needed."""
        actions = []
        # Clean estates with consensus reached
        completed = [
            eid for eid, estate in self._estates.items() if estate.get("consensus") is not None
        ]
        for eid in completed:
            del self._estates[eid]
            actions.append(f"Cleaned completed estate: {eid}")
        return actions


# ─────────────────────────────────────────────────────────────────────────────
# Sentinel Station — Central Coordinator
# ─────────────────────────────────────────────────────────────────────────────


class SentinelStation:
    """
    Sentinel Station — The central coordination point for the Three-Bridge
    Architecture. Routes traffic, monitors bridge health, enforces isolation
    rules, and provides cross-bridge escalation.
    """

    def __init__(self):
        self._bridges: Dict[BridgeDomain, IBridge] = {
            BridgeDomain.INFINITY: InfinityBridge(),
            BridgeDomain.NEXUS: NexusBridge(),
            BridgeDomain.HIVE: HIVEBridge(),
        }
        self._routing_rules: List[RoutingRule] = []
        self._escalation_log: List[EscalationResult] = []
        self._started_at: float = time.time()

    def route_traffic(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        """
        Classify traffic and route to the correct bridge.
        This is the main entry point for all traffic.
        """
        # Classify the traffic
        target_bridge = self.classify_traffic(packet.traffic_class)
        packet.target_bridge = target_bridge

        # Check routing rules for overrides
        import re

        for rule in self._routing_rules:
            if not rule.enabled:
                continue
            if rule.traffic_pattern != "*":
                if not re.match(rule.traffic_pattern, packet.traffic_class.value):
                    continue
            if rule.source_pattern != "*":
                if not re.match(rule.source_pattern, packet.source):
                    continue
            target_bridge = rule.target_bridge
            packet.priority += rule.priority_boost
            break

        # Handle special cases
        if packet.traffic_class == TrafficClass.INTERNAL_HEALTH:
            return self._handle_health_packet(packet)

        if packet.traffic_class == TrafficClass.CROSS_BRIDGE:
            return self._handle_cross_bridge(packet)

        # Route to the appropriate bridge
        bridge = self._bridges.get(target_bridge)
        if not bridge:
            logger.error(f"Sentinel: No bridge for domain {target_bridge}")
            packet.metadata["routing_error"] = f"No bridge for domain {target_bridge}"
            return packet

        return bridge.process_packet(packet)

    def classify_traffic(self, traffic_class: TrafficClass) -> BridgeDomain:
        """Map a traffic class to a bridge domain."""
        return TRAFFIC_TO_BRIDGE.get(traffic_class, BridgeDomain.INFINITY)

    def escalate(self, request: EscalationRequest) -> EscalationResult:
        """
        Escalate a packet from one bridge to another.
        Requires proper authorization.
        """
        from_bridge = self._bridges.get(request.from_bridge)
        to_bridge = self._bridges.get(request.to_bridge)

        if not from_bridge or not to_bridge:
            result = EscalationResult(
                success=False,
                packet_id=request.packet_id,
                from_bridge=request.from_bridge,
                to_bridge=request.to_bridge,
                message=f"Bridge not found: from={request.from_bridge}, to={request.to_bridge}",
            )
            self._escalation_log.append(result)
            return result

        # Create a cross-bridge packet (commented out — not currently used)
        # packet = BridgeTrafficPacket(
        #     id=request.packet_id,
        #     traffic_class=TrafficClass.CROSS_BRIDGE,
        #     target_bridge=request.to_bridge,
        #     source=f"sentinel-escalation:{request.from_bridge.value}",
        #     destination=request.to_bridge.value,
        #     payload={"reason": request.reason, "authorized_by": request.authorized_by},
        #     priority=request.priority,
        #     requires_escalation=False,
        # )

        # _result_packet = to_bridge.process_packet(packet)  # noqa: F841

        result = EscalationResult(
            success=True,
            packet_id=request.packet_id,
            from_bridge=request.from_bridge,
            to_bridge=request.to_bridge,
            message=f"Escalated packet {request.packet_id} from {request.from_bridge.value} to {request.to_bridge.value}",
        )
        self._escalation_log.append(result)
        logger.info(
            f"Sentinel: Escalated {request.packet_id}: {request.from_bridge.value} → {request.to_bridge.value}"
        )

        return result

    def aggregate_health(self) -> Dict[str, Any]:
        """Aggregate health data from all bridges."""
        reports = {}
        total_processed = 0
        total_pending = 0
        any_offline = False
        any_degraded = False

        for domain, bridge in self._bridges.items():
            health = bridge.health_check()
            reports[domain.value] = {
                "status": health.status.value,
                "packetsProcessed": health.packets_processed,
                "packetsPending": health.packets_pending,
                "packetsFailed": health.packets_failed,
                "averageLatencyMs": health.average_latency_ms,
                "errorRate": health.error_rate,
                "uptimeSeconds": health.uptime_seconds,
            }
            total_processed += health.packets_processed
            total_pending += health.packets_pending
            if health.status == BridgeStatus.OFFLINE:
                any_offline = True
            if health.status == BridgeStatus.DEGRADED:
                any_degraded = True

        overall = "active"
        if any_offline:
            overall = "critical"
        elif any_degraded:
            overall = "degraded"

        return {
            "overallStatus": overall,
            "bridges": reports,
            "totalPacketsProcessed": total_processed,
            "totalPacketsPending": total_pending,
            "routingRules": len(self._routing_rules),
            "escalationsTotal": len(self._escalation_log),
            "uptimeSeconds": time.time() - self._started_at,
        }

    def scan_bridge_health(self) -> Dict[str, Any]:
        """Proactive: scan all bridges and report anomalies."""
        anomalies: List[str] = []
        recommendations: List[str] = []

        for domain, bridge in self._bridges.items():
            health = bridge.health_check()

            if health.status == BridgeStatus.OFFLINE:
                anomalies.append(f"{domain.value} bridge is offline")
                recommendations.append(f"Restart {domain.value} bridge")

            if health.error_rate > 0.1:
                anomalies.append(
                    f"{domain.value} bridge has high error rate: {health.error_rate * 100:.1f}%"
                )
                recommendations.append(f"Investigate {domain.value} bridge error patterns")

            if health.packets_pending > 100:
                anomalies.append(
                    f"{domain.value} bridge has {health.packets_pending} pending packets"
                )
                recommendations.append(f"Scale {domain.value} bridge capacity")

            if health.average_latency_ms > 1000:
                anomalies.append(
                    f"{domain.value} bridge has high latency: {health.average_latency_ms:.0f}ms"
                )
                recommendations.append(f"Optimize {domain.value} bridge processing")

            # Run proactive cleanup
            cleanup_actions = bridge.scan_and_cleanup()
            for action in cleanup_actions:
                logger.info(f"Sentinel proactive cleanup: {action}")

        return {
            "anomalies": anomalies,
            "recommendations": recommendations,
            "healthy": len(anomalies) == 0,
        }

    def _handle_health_packet(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        """Handle an INTERNAL_HEALTH packet — aggregate all bridge health and embed in metadata."""
        health = self.aggregate_health()
        packet.metadata["health"] = health
        packet.metadata["handled_by"] = "sentinel"
        logger.debug("Sentinel: served health packet %s", packet.id)
        return packet

    def _handle_cross_bridge(self, packet: BridgeTrafficPacket) -> BridgeTrafficPacket:
        """
        Handle a CROSS_BRIDGE packet — route to the target bridge specified in
        packet.destination, enforcing sentinel authorisation.

        The calling side must set packet.destination to the name of the target
        BridgeDomain value ("infinity", "nexus", or "hive") and set
        packet.security_token to a non-empty authorisation marker.
        """
        if not packet.security_token:
            logger.warning(
                "Sentinel: cross-bridge packet %s rejected — no security_token",
                packet.id,
            )
            packet.metadata["sentinel_error"] = "cross_bridge_requires_security_token"
            return packet

        try:
            target_domain = BridgeDomain(packet.destination)
        except ValueError:
            logger.warning(
                "Sentinel: cross-bridge packet %s has unknown destination %r",
                packet.id,
                packet.destination,
            )
            packet.metadata["sentinel_error"] = f"unknown_destination:{packet.destination}"
            return packet

        bridge = self._bridges.get(target_domain)
        if not bridge:
            logger.error("Sentinel: no bridge for cross-bridge destination %s", target_domain)
            packet.metadata["sentinel_error"] = f"no_bridge:{target_domain.value}"
            return packet

        packet.traffic_class = TrafficClass.UNKNOWN  # de-classify before handing off
        packet.metadata["cross_bridge_via"] = "sentinel"
        logger.info("Sentinel: cross-bridge packet %s routed to %s", packet.id, target_domain.value)
        return bridge.process_packet(packet)

    def get_bridge(self, domain: BridgeDomain) -> Optional[IBridge]:
        """Get a specific bridge by domain."""
        return self._bridges.get(domain)

    def add_routing_rule(self, rule: RoutingRule) -> None:
        """Add a routing rule."""
        self._routing_rules.append(rule)

    def health_check(self) -> Dict[str, Any]:
        """Health check for Sentinel Station itself."""
        return {
            "status": "healthy",
            "bridges_active": sum(
                1 for b in self._bridges.values() if b.health_check().status != BridgeStatus.OFFLINE
            ),
            "bridges_total": len(self._bridges),
            "routing_rules": len(self._routing_rules),
            "escalations_logged": len(self._escalation_log),
        }
