"""
The Nexus — AI, Agent, and Bot Traffic Coordination
=====================================================
The Nexus is the dedicated routing and coordination system for AI, Agent,
and Bot traffic (Tier 3–5) within the Tranc3 platform. It is ONE of the
three bridges that route traffic through Sentinel Station:

    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus      : AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE       : Data movement and swarm system coordination

The Nexus provides:
    - Causal event ordering for AI/Agent/Bot events (vector clocks)
    - Tier-aware access control for AI/Agent/Bot resources
    - Real-time health aggregation for AI/Agent/Bot services
    - Cross-Nexus event routing via Sentinel channels
    - Topology mapping of AI/Agent/Bot service connections
    - WebSocket dashboard for live Nexus event streaming

Tier Hierarchy (Mandatory Custom Definitions):
    Tier 0: HUMAN — Override authority, maximum access
    Tier 1: ORCHESTRATOR — System-level coordination
    Tier 2: PRIME — Strategic decision-making
    Tier 3: AI — The overarching ML/LLM Complex
    Tier 4: AGENT — Lower-level autonomous AI
    Tier 5: BOT — Stateless service worker/function

IMPORTANT: The Nexus is NOT a general coordinator. It is specifically for
AI, Agent, and Bot traffic. User traffic uses InfinityBridge. Data traffic
uses The HIVE. The Dimensional package provides core/shared services that
all three bridges can use, but Dimensional and Nexus are separate concepts.

"DimensionalNexus" is only valid when referring to both the Dimensional
package AND The Nexus in conjunction — NOT as a merged system.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import sqlite3
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from Dimensional.infinity.nomenclature import InfinityRole, SentinelChannel, Tier
from Dimensional.infinity.rbac import RBACEngine, Permission
from Dimensional.infinity.abac import ABACEngine, Policy, PolicyEffect

logger = logging.getLogger("nexus")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NEXUS_DB_PATH = os.environ.get("NEXUS_DB_PATH", "data/nexus.db")
NEXUS_PORT = int(os.environ.get("NEXUS_PORT", "8050"))
NEXUS_HEALTH_INTERVAL = int(os.environ.get("NEXUS_HEALTH_INTERVAL", "30"))  # seconds
NEXUS_EVENT_BUFFER_SIZE = int(os.environ.get("NEXUS_EVENT_BUFFER_SIZE", "10000"))

# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


class NexusServiceHealth(BaseModel):
    """Health status of a single AI/Agent/Bot service in the Nexus."""
    service_id: str
    service_name: str
    pillar: str
    tier_requirement: int
    status: str = "unknown"  # healthy, degraded, unhealthy, unknown
    uptime_seconds: float = 0.0
    last_heartbeat: Optional[str] = None
    response_time_ms: Optional[float] = None
    error_count: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NexusHealthSummary(BaseModel):
    """Aggregated health across all AI/Agent/Bot services in the Nexus."""
    total_services: int = 0
    healthy: int = 0
    degraded: int = 0
    unhealthy: int = 0
    unknown: int = 0
    overall_status: str = "unknown"
    pillar_health: Dict[str, Dict[str, int]] = Field(default_factory=dict)
    tier_coverage: Dict[int, List[str]] = Field(default_factory=dict)
    last_updated: str = ""


class NexusAccessDecision(BaseModel):
    """Result of a tier-aware access control decision for Nexus traffic."""
    allowed: bool
    reason: str = ""
    matched_policy: Optional[str] = None
    tier_valid: bool = True
    rbac_result: Optional[bool] = None
    abac_result: Optional[bool] = None
    effective_tier: int = 5
    required_tier: int = 5
    constraints: List[str] = Field(default_factory=list)


class NexusEvent(BaseModel):
    """An event in the Nexus — AI/Agent/Bot traffic with causal ordering.

    Events flowing through the Nexus represent AI, Agent, and Bot
    movement, coordination, and traffic. They are NOT general platform
    events — those flow through the HIVE or Sentinel Station directly.
    """
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: str  # SentinelChannel name
    source_dimension: str  # Which AI/Agent/Bot service emitted this
    source_tier: int  # Must be Tier 3 (AI), 4 (Agent), or 5 (Bot)
    event_type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    vector_clock: Dict[str, int] = Field(default_factory=dict)
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    correlation_id: Optional[str] = None
    causality_hash: Optional[str] = None


class NexusTopologyNode(BaseModel):
    """A node in the Nexus topology graph — an AI/Agent/Bot service."""
    node_id: str
    node_type: str  # ai_complex, agent, bot, gateway, coordinator
    tier: int
    pillar: str
    connections: List[str] = Field(default_factory=list)
    health_status: str = "unknown"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class NexusTopologyEdge(BaseModel):
    """An edge in the Nexus topology — traffic flow between AI/Agent/Bot services."""
    source: str
    target: str
    edge_type: str  # task_dispatch, inference_route, data_flow, coordination
    sentinel_channel: Optional[str] = None
    bandwidth: Optional[float] = None
    latency_ms: Optional[float] = None


# ---------------------------------------------------------------------------
# Causal Ordering Engine
# ---------------------------------------------------------------------------


class CausalOrderingEngine:
    """
    Vector-clock based causal ordering for Nexus events.

    Implements a distributed vector clock that tracks causality across
    all AI/Agent/Bot services in the Nexus. Events are ordered by their
    vector clocks, ensuring timeline consistency even in the presence of
    network delays and concurrent AI/Agent/Bot operations.
    """

    def __init__(self, node_id: str, known_nodes: Optional[Set[str]] = None,
                 buffer_size: Optional[int] = None):
        self.node_id = node_id
        self.clock: Dict[str, int] = {node_id: 0}
        self.known_nodes: Set[str] = known_nodes or {node_id}
        self._buffer_size = buffer_size or int(os.environ.get("NEXUS_EVENT_BUFFER_SIZE", "10000"))
        self._event_buffer: List[NexusEvent] = []
        self._lock = asyncio.Lock()

    def increment(self) -> Dict[str, int]:
        """Increment the local clock and return the new vector clock."""
        self.clock[self.node_id] = self.clock.get(self.node_id, 0) + 1
        return dict(self.clock)

    def merge(self, incoming_clock: Dict[str, int]) -> Dict[str, int]:
        """Merge an incoming vector clock (happens-before relation)."""
        for node, ts in incoming_clock.items():
            self.known_nodes.add(node)
            current = self.clock.get(node, 0)
            self.clock[node] = max(current, ts)
        self.clock[self.node_id] = self.clock.get(self.node_id, 0) + 1
        return dict(self.clock)

    def happened_before(self, clock_a: Dict[str, int], clock_b: Dict[str, int]) -> bool:
        """Check if clock_a happened before clock_b (strict partial order)."""
        all_nodes = set(clock_a.keys()) | set(clock_b.keys())
        at_least_one_less = False
        for node in all_nodes:
            a_val = clock_a.get(node, 0)
            b_val = clock_b.get(node, 0)
            if a_val > b_val:
                return False
            if a_val < b_val:
                at_least_one_less = True
        return at_least_one_less

    def concurrent(self, clock_a: Dict[str, int], clock_b: Dict[str, int]) -> bool:
        """Check if two events are concurrent (no causal relationship)."""
        return not self.happened_before(clock_a, clock_b) and not self.happened_before(clock_b, clock_a)

    def compute_causality_hash(self, event: NexusEvent) -> str:
        """Compute a deterministic hash for causal chain verification."""
        vc_str = json.dumps(event.vector_clock, sort_keys=True)
        content = f"{event.source_dimension}:{event.event_type}:{vc_str}:{event.timestamp}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    async def record_event(self, event: NexusEvent) -> NexusEvent:
        """Record an event and update causal ordering."""
        async with self._lock:
            if event.source_dimension == self.node_id:
                event.vector_clock = self.increment()
            else:
                event.vector_clock = self.merge(event.vector_clock)
            event.causality_hash = self.compute_causality_hash(event)
            self._event_buffer.append(event)
            if len(self._event_buffer) > self._buffer_size:
                self._event_buffer = self._event_buffer[-self._buffer_size:]
        return event

    async def get_ordered_events(
        self, channel: Optional[str] = None, limit: int = 100
    ) -> List[NexusEvent]:
        """Get events in causal order, optionally filtered by channel."""
        async with self._lock:
            events = list(self._event_buffer)
        if channel:
            events = [e for e in events if e.channel == channel]
        events.sort(key=lambda e: json.dumps(e.vector_clock, sort_keys=True))
        return events[-limit:]


# ---------------------------------------------------------------------------
# Tier Access Bridge — Unified RBAC + ABAC with Tier Hierarchy
# ---------------------------------------------------------------------------


class TierAccessBridge:
    """
    Unified access control bridge that combines RBAC and ABAC with
    the Tier hierarchy for AI/Agent/Bot traffic in the Nexus.

    The bridge enforces the mandatory custom definition hierarchy:
        - AI (Tier 3): The overarching ML/LLM Complex
        - Agent (Tier 4): Lower-level autonomous AI
        - Bot (Tier 5): Stateless service worker/function

    Access decisions are made by:
    1. Checking tier requirements (minimum tier for the resource)
    2. Applying RBAC permissions (role-based)
    3. Applying ABAC policies (attribute-based)
    4. Combining results with AND logic (both must allow)

    If either RBAC or ABAC is not configured, the other acts as
    the sole decision maker. If neither is configured, tier check
    alone determines access.
    """

    def __init__(
        self,
        rbac_engine: Optional[RBACEngine] = None,
        abac_engine: Optional[ABACEngine] = None,
    ):
        self.rbac = rbac_engine
        self.abac = abac_engine
        self._tier_overrides: Dict[str, int] = {}  # resource → min_tier
        self._deny_list: Set[str] = set()  # explicitly denied resources

    def set_tier_requirement(self, resource: str, min_tier: int) -> None:
        """Set the minimum tier required to access a resource."""
        self._tier_overrides[resource] = min_tier

    def add_deny(self, resource: str) -> None:
        """Explicitly deny access to a resource regardless of other checks."""
        self._deny_list.add(resource)

    def remove_deny(self, resource: str) -> None:
        """Remove an explicit deny."""
        self._deny_list.discard(resource)

    def check_access(
        self,
        subject: str,
        resource: str,
        action: str,
        subject_tier: int,
        subject_role: Optional[str] = None,
        subject_attributes: Optional[Dict[str, Any]] = None,
        resource_attributes: Optional[Dict[str, Any]] = None,
        environment: Optional[Dict[str, Any]] = None,
    ) -> NexusAccessDecision:
        """
        Perform a complete tier-aware access control check.

        The decision process:
        1. Check explicit deny list → immediate deny
        2. Check tier requirement → deny if tier insufficient
        3. Check RBAC if configured → deny if role lacks permission
        4. Check ABAC if configured → deny if no policy allows
        5. If both RBAC and ABAC configured → both must allow
        6. If neither configured → tier check alone suffices
        """
        # Step 1: Explicit deny
        if resource in self._deny_list:
            return NexusAccessDecision(
                allowed=False,
                reason=f"Resource '{resource}' is explicitly denied",
                tier_valid=True,
                effective_tier=subject_tier,
                required_tier=self._tier_overrides.get(resource, 5),
                constraints=["explicit_deny"],
            )

        # Step 2: Tier check
        required_tier = self._tier_overrides.get(resource, 5)
        tier_valid = subject_tier <= required_tier  # Lower tier number = higher access

        if not tier_valid:
            return NexusAccessDecision(
                allowed=False,
                reason=f"Tier {subject_tier} insufficient for resource requiring tier {required_tier}",
                tier_valid=False,
                effective_tier=subject_tier,
                required_tier=required_tier,
                constraints=["insufficient_tier"],
            )

        # Step 3: RBAC check
        rbac_result = None
        if self.rbac and subject_role:
            try:
                rbac_result = self.rbac.check_permission(subject_role, resource, action)
            except Exception:
                rbac_result = None  # RBAC not authoritative if misconfigured

        # Step 4: ABAC check
        abac_result = None
        if self.abac:
            try:
                abac_result = self.abac.evaluate(
                    subject_attributes or {},
                    resource_attributes or {},
                    action,
                    environment or {},
                )
            except Exception:
                abac_result = None  # ABAC not authoritative if misconfigured

        # Step 5: Combine results
        matched_policy = None
        constraints = []

        if rbac_result is not None and abac_result is not None:
            # Both configured → both must allow
            allowed = rbac_result and abac_result
            if not allowed:
                if not rbac_result:
                    constraints.append("rbac_denied")
                if not abac_result:
                    constraints.append("abac_denied")
            matched_policy = "rbac+abac"
        elif rbac_result is not None:
            allowed = rbac_result
            matched_policy = "rbac"
            if not allowed:
                constraints.append("rbac_denied")
        elif abac_result is not None:
            allowed = abac_result
            matched_policy = "abac"
            if not allowed:
                constraints.append("abac_denied")
        else:
            # Neither configured → tier check alone
            allowed = tier_valid
            matched_policy = "tier_only"

        reason = ""
        if not allowed:
            reason = f"Access denied by {matched_policy}"
            if constraints:
                reason += f" ({', '.join(constraints)})"

        return NexusAccessDecision(
            allowed=allowed,
            reason=reason,
            matched_policy=matched_policy,
            tier_valid=tier_valid,
            rbac_result=rbac_result,
            abac_result=abac_result,
            effective_tier=subject_tier,
            required_tier=required_tier,
            constraints=constraints,
        )


# ---------------------------------------------------------------------------
# Health Aggregator
# ---------------------------------------------------------------------------


class HealthAggregator:
    """
    Real-time health aggregation for AI/Agent/Bot services in the Nexus.

    Collects heartbeat signals from AI/Agent/Bot services and maintains
    a comprehensive health view organized by pillar, tier, and status.
    Supports configurable health thresholds and anomaly detection.
    """

    def __init__(self, db_path: str = NEXUS_DB_PATH):
        self.db_path = db_path
        self._services: Dict[str, NexusServiceHealth] = {}
        self._health_history: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        self._thresholds = {
            "response_time_ms": 1000.0,
            "error_rate": 0.1,
            "heartbeat_timeout_seconds": 90,
        }
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        """Initialize the health database."""
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS service_health (
                service_id TEXT PRIMARY KEY,
                service_name TEXT NOT NULL,
                pillar TEXT NOT NULL,
                tier_requirement INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'unknown',
                uptime_seconds REAL DEFAULT 0.0,
                last_heartbeat TEXT,
                response_time_ms REAL,
                error_count INTEGER DEFAULT 0,
                metadata TEXT DEFAULT '{}',
                updated_at TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS health_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id TEXT NOT NULL,
                status TEXT NOT NULL,
                response_time_ms REAL,
                timestamp TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (service_id) REFERENCES service_health(service_id)
            );
            CREATE INDEX IF NOT EXISTS idx_health_history_service
                ON health_history(service_id, timestamp);
        """)
        conn.commit()
        conn.close()

    async def register_service(self, health: NexusServiceHealth) -> None:
        """Register an AI/Agent/Bot service for health tracking in the Nexus."""
        async with self._lock:
            self._services[health.service_id] = health
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """INSERT OR REPLACE INTO service_health
               (service_id, service_name, pillar, tier_requirement, status,
                uptime_seconds, last_heartbeat, response_time_ms, error_count, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                health.service_id,
                health.service_name,
                health.pillar,
                health.tier_requirement,
                health.status,
                health.uptime_seconds,
                health.last_heartbeat,
                health.response_time_ms,
                health.error_count,
                json.dumps(health.metadata),
            ),
        )
        conn.commit()
        conn.close()

    async def update_heartbeat(
        self,
        service_id: str,
        status: str = "healthy",
        response_time_ms: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update the heartbeat for an AI/Agent/Bot service in the Nexus."""
        async with self._lock:
            if service_id not in self._services:
                return
            svc = self._services[service_id]
            svc.status = status
            svc.last_heartbeat = datetime.now(timezone.utc).isoformat()
            if response_time_ms is not None:
                svc.response_time_ms = response_time_ms
            if status == "unhealthy":
                svc.error_count += 1
            if metadata:
                svc.metadata.update(metadata)

        conn = sqlite3.connect(self.db_path)
        conn.execute(
            """UPDATE service_health
               SET status=?, last_heartbeat=?, response_time_ms=?, error_count=?, metadata=?
               WHERE service_id=?""",
            (status, datetime.now(timezone.utc).isoformat(),
             response_time_ms, self._services.get(service_id, NexusServiceHealth(
                 service_id=service_id, service_name="", pillar="",
                 tier_requirement=5)).error_count,
             json.dumps(metadata or {}),
             service_id),
        )
        conn.execute(
            """INSERT INTO health_history (service_id, status, response_time_ms)
               VALUES (?, ?, ?)""",
            (service_id, status, response_time_ms),
        )
        conn.commit()
        conn.close()

    async def get_summary(self) -> NexusHealthSummary:
        """Get the aggregated health summary for Nexus services."""
        async with self._lock:
            services = list(self._services.values())

        summary = NexusHealthSummary(
            total_services=len(services),
            last_updated=datetime.now(timezone.utc).isoformat(),
        )

        pillar_health: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        tier_coverage: Dict[int, List[str]] = defaultdict(list)

        for svc in services:
            if svc.status == "healthy":
                summary.healthy += 1
            elif svc.status == "degraded":
                summary.degraded += 1
            elif svc.status == "unhealthy":
                summary.unhealthy += 1
            else:
                summary.unknown += 1

            pillar_health[svc.pillar][svc.status] += 1
            tier_coverage[svc.tier_requirement].append(svc.service_name)

        summary.pillar_health = dict(pillar_health)
        summary.tier_coverage = dict(tier_coverage)

        # Overall status determination
        if summary.total_services == 0:
            summary.overall_status = "unknown"
        elif summary.unhealthy > 0:
            summary.overall_status = "critical"
        elif summary.degraded > summary.healthy:
            summary.overall_status = "degraded"
        elif summary.degraded > 0:
            summary.overall_status = "warning"
        else:
            summary.overall_status = "healthy"

        return summary

    async def detect_anomalies(self) -> List[Dict[str, Any]]:
        """Detect health anomalies across AI/Agent/Bot services in the Nexus."""
        anomalies = []
        now = time.time()

        async with self._lock:
            services = list(self._services.values())

        for svc in services:
            # Check heartbeat timeout
            if svc.last_heartbeat:
                try:
                    hb_time = datetime.fromisoformat(svc.last_heartbeat).timestamp()
                    elapsed = now - hb_time
                    if elapsed > self._thresholds["heartbeat_timeout_seconds"]:
                        anomalies.append({
                            "type": "heartbeat_timeout",
                            "service_id": svc.service_id,
                            "service_name": svc.service_name,
                            "elapsed_seconds": round(elapsed, 1),
                            "threshold": self._thresholds["heartbeat_timeout_seconds"],
                            "severity": "high",
                        })
                except (ValueError, TypeError):
                    pass

            # Check response time
            if svc.response_time_ms and svc.response_time_ms > self._thresholds["response_time_ms"]:
                anomalies.append({
                    "type": "high_response_time",
                    "service_id": svc.service_id,
                    "service_name": svc.service_name,
                    "response_time_ms": svc.response_time_ms,
                    "threshold_ms": self._thresholds["response_time_ms"],
                    "severity": "medium",
                })

            # Check error rate
            if svc.error_count > 10:
                anomalies.append({
                    "type": "high_error_count",
                    "service_id": svc.service_id,
                    "service_name": svc.service_name,
                    "error_count": svc.error_count,
                    "severity": "high",
                })

        return anomalies


# ---------------------------------------------------------------------------
# Event Router — Cross-Nexus Sentinel Event Distribution
# ---------------------------------------------------------------------------


class EventRouter:
    """
    Cross-Nexus event routing with Sentinel channel distribution.

    Routes events between AI/Agent/Bot services based on Sentinel channel
    subscriptions. Supports fan-out, point-to-point, and channel-based
    routing with causal ordering guarantees.
    """

    def __init__(self, causal_engine: CausalOrderingEngine):
        self.causal_engine = causal_engine
        self._subscriptions: Dict[str, Set[str]] = defaultdict(set)  # channel → set of service_ids
        self._event_handlers: Dict[str, List[callable]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, channel: str, service_id: str) -> None:
        """Subscribe an AI/Agent/Bot service to a Sentinel channel."""
        async with self._lock:
            self._subscriptions[channel].add(service_id)

    async def unsubscribe(self, channel: str, service_id: str) -> None:
        """Unsubscribe an AI/Agent/Bot service from a Sentinel channel."""
        async with self._lock:
            self._subscriptions[channel].discard(service_id)

    async def register_handler(self, channel: str, handler: callable) -> None:
        """Register an async handler for events on a channel."""
        async with self._lock:
            self._event_handlers[channel].append(handler)

    async def publish(self, event: NexusEvent) -> List[str]:
        """
        Publish an event to all subscribers on its channel.
        Returns list of service IDs that were notified.
        """
        # Record event with causal ordering
        event = await self.causal_engine.record_event(event)

        async with self._lock:
            subscribers = list(self._subscriptions.get(event.channel, set()))
            handlers = list(self._event_handlers.get(event.channel, []))

        # Invoke handlers
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(event)
                else:
                    handler(event)
            except Exception as e:
                logger.error(f"Event handler error on channel {event.channel}: {e}")

        return subscribers

    async def get_subscriptions(self, service_id: Optional[str] = None) -> Dict[str, List[str]]:
        """Get current subscriptions, optionally filtered by service."""
        async with self._lock:
            if service_id:
                return {
                    ch: [s for s in subs if s == service_id]
                    for ch, subs in self._subscriptions.items()
                    if service_id in subs
                }
            return {ch: list(subs) for ch, subs in self._subscriptions.items()}

    async def get_routing_table(self) -> Dict[str, Any]:
        """Get the complete routing table for topology visualization."""
        async with self._lock:
            return {
                "channels": {
                    ch: list(subs) for ch, subs in self._subscriptions.items()
                },
                "total_channels": len(self._subscriptions),
                "total_subscriptions": sum(
                    len(subs) for subs in self._subscriptions.values()
                ),
            }


# ---------------------------------------------------------------------------
# The Nexus — AI/Agent/Bot Traffic Coordinator
# ---------------------------------------------------------------------------


class Nexus:
    """
    The Nexus — dedicated coordinator for AI, Agent, and Bot traffic.

    The Nexus is ONE of the three bridges through Sentinel Station:
        - InfinityBridge: User context / human traffic
        - The Nexus (THIS): AI, Agent, and Bot movement and traffic
        - The HIVE: Data movement and swarm system coordination

    The Nexus provides a unified API surface for AI/Agent/Bot services:
    - Health aggregation and monitoring for AI/Agent/Bot services
    - Tier-aware access control (RBAC + ABAC bridge) for AI/Agent/Bot resources
    - Cross-Nexus event routing with causal ordering for AI/Agent/Bot events
    - Topology mapping of AI/Agent/Bot service connections
    - Service registration and discovery for AI/Agent/Bot entities

    IMPORTANT: The Nexus is NOT a general coordinator. It is specifically
    and exclusively for AI (Tier 3), Agent (Tier 4), and Bot (Tier 5) traffic.
    """

    def __init__(self, db_path: str = NEXUS_DB_PATH):
        self.node_id = f"nexus-{uuid.uuid4().hex[:8]}"
        self.db_path = db_path
        self.causal_engine = CausalOrderingEngine(self.node_id)
        self.health_aggregator = HealthAggregator(db_path)
        self.access_bridge = TierAccessBridge()
        self.event_router = EventRouter(self.causal_engine)
        self._topology_nodes: Dict[str, NexusTopologyNode] = {}
        self._topology_edges: List[NexusTopologyEdge] = []
        self._started_at = time.time()
        self._lock = asyncio.Lock()
        logger.info(f"Nexus initialized: {self.node_id}")

    async def register_service(
        self,
        service_id: str,
        service_name: str,
        pillar: str,
        tier_requirement: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> NexusServiceHealth:
        """Register an AI/Agent/Bot service with the Nexus."""
        health = NexusServiceHealth(
            service_id=service_id,
            service_name=service_name,
            pillar=pillar,
            tier_requirement=tier_requirement,
            status="unknown",
            metadata=metadata or {},
        )
        await self.health_aggregator.register_service(health)

        # Add to topology
        node = NexusTopologyNode(
            node_id=service_id,
            node_type="dimension",
            tier=tier_requirement,
            pillar=pillar,
            health_status="unknown",
            metadata=metadata or {},
        )
        async with self._lock:
            self._topology_nodes[service_id] = node

        # Subscribe to all Sentinel channels by default
        for channel in SentinelChannel:
            await self.event_router.subscribe(channel.value, service_id)

        logger.info(f"Registered Nexus service: {service_name} ({service_id})")
        return health

    async def add_topology_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        sentinel_channel: Optional[str] = None,
    ) -> None:
        """Add a traffic flow edge to the Nexus topology."""
        edge = NexusTopologyEdge(
            source=source,
            target=target,
            edge_type=edge_type,
            sentinel_channel=sentinel_channel,
        )
        async with self._lock:
            self._topology_edges.append(edge)
            if source in self._topology_nodes:
                if target not in self._topology_nodes[source].connections:
                    self._topology_nodes[source].connections.append(target)

    async def emit_event(
        self,
        channel: str,
        source_dimension: str,
        source_tier: int,
        event_type: str,
        payload: Optional[Dict[str, Any]] = None,
        correlation_id: Optional[str] = None,
    ) -> NexusEvent:
        """Emit an AI/Agent/Bot traffic event through the Nexus."""
        event = NexusEvent(
            channel=channel,
            source_dimension=source_dimension,
            source_tier=source_tier,
            event_type=event_type,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        subscribers = await self.event_router.publish(event)
        # Broadcast to WebSocket dashboards
        await _ws_manager.broadcast(event)
        logger.info(
            f"Nexus event: {event_type} on {channel} "
            f"from {source_dimension} → {len(subscribers)} subscribers"
        )
        return event

    async def check_access(
        self,
        subject: str,
        resource: str,
        action: str,
        subject_tier: int,
        **kwargs,
    ) -> NexusAccessDecision:
        """Perform a tier-aware access control check for Nexus traffic."""
        return self.access_bridge.check_access(
            subject=subject,
            resource=resource,
            action=action,
            subject_tier=subject_tier,
            **kwargs,
        )

    async def get_topology(self) -> Dict[str, Any]:
        """Get the complete Nexus topology graph."""
        async with self._lock:
            return {
                "nodes": [n.model_dump() for n in self._topology_nodes.values()],
                "edges": [e.model_dump() for e in self._topology_edges],
                "node_count": len(self._topology_nodes),
                "edge_count": len(self._topology_edges),
            }

    async def get_status(self) -> Dict[str, Any]:
        """Get the comprehensive Nexus status."""
        health_summary = await self.health_aggregator.get_summary()
        routing_table = await self.event_router.get_routing_table()
        return {
            "nexus_id": self.node_id,
            "bridge_type": "nexus",
            "description": "AI, Agent, and Bot traffic coordination",
            "uptime_seconds": round(time.time() - self._started_at, 1),
            "health": health_summary.model_dump(),
            "event_routing": routing_table,
            "topology_nodes": len(self._topology_nodes),
            "topology_edges": len(self._topology_edges),
            "causal_clock": dict(self.causal_engine.clock),
            "tier_hierarchy": {
                "HUMAN": 0,
                "ORCHESTRATOR": 1,
                "PRIME": 2,
                "AI": 3,
                "AGENT": 4,
                "BOT": 5,
            },
            "three_bridges": {
                "infinity_bridge": {
                    "name": "InfinityBridge",
                    "role": "User Context & Human Traffic",
                    "description": "User Context & Human Traffic (Light Bridge)",
                    "status": "see_infinity_bridge_status",
                    "bridge_type": "infinity",
                },
                "nexus": {
                    "name": "The Nexus",
                    "role": "AI, Agent, and Bot Traffic",
                    "description": "AI, Agent, and Bot Traffic Coordination",
                    "status": "active",
                    "bridge_type": "nexus",
                },
                "hive": {
                    "name": "The HIVE",
                    "role": "Data Movement & Swarm Coordination",
                    "description": "Data Movement & Swarm System Coordination",
                    "status": "see_hive_status",
                    "bridge_type": "hive",
                },
            },
            "sentinel_channels": [ch.value for ch in SentinelChannel],
        }


# Backward-compatible alias — only valid when referring to both Dimensional
# AND Nexus in conjunction. For the Nexus specifically, use the Nexus class.
DimensionalNexus = Nexus


# ---------------------------------------------------------------------------
# Singleton Nexus Instance
# ---------------------------------------------------------------------------

_nexus_instance: Optional[Nexus] = None


def get_nexus() -> Nexus:
    """Get or create the singleton Nexus instance."""
    global _nexus_instance
    if _nexus_instance is None:
        _nexus_instance = Nexus()
    return _nexus_instance


# ---------------------------------------------------------------------------
# WebSocket Connection Manager
# ---------------------------------------------------------------------------


class NexusWSManager:
    """Manages WebSocket connections for live Nexus event streaming to dashboards."""

    def __init__(self):
        self._connections: List[WebSocket] = []
        self._channel_subs: Dict[str, List[WebSocket]] = defaultdict(list)

    async def connect(self, ws: WebSocket, channels: Optional[List[str]] = None):
        await ws.accept()
        self._connections.append(ws)
        if channels:
            for ch in channels:
                self._channel_subs[ch].append(ws)
        logger.info(f"Nexus Dashboard WebSocket connected (total: {len(self._connections)})")

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        for ch_conns in self._channel_subs.values():
            if ws in ch_conns:
                ch_conns.remove(ws)
        logger.info(f"Nexus Dashboard WebSocket disconnected (total: {len(self._connections)})")

    async def broadcast(self, event: NexusEvent):
        msg = event.model_dump_json()
        # Broadcast to all connections
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)
        # Broadcast to channel subscribers
        ch = event.channel.value if isinstance(event.channel, SentinelChannel) else str(event.channel)
        dead = []
        for ws in self._channel_subs.get(ch, []):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


_ws_manager = NexusWSManager()


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------


def create_nexus_app() -> FastAPI:
    """Create the Nexus FastAPI application — AI/Agent/Bot traffic coordination."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        nexus = get_nexus()
        logger.info(f"Nexus starting: {nexus.node_id}")
        yield
        logger.info("Nexus shutting down")

    app = FastAPI(
        title="Tranc3 Nexus",
        description="The Nexus — AI, Agent, and Bot Traffic Coordination (Bridge 2 of 3)",
        version="0.2.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Health Endpoints ---

    @app.get("/health", response_model=NexusHealthSummary)
    async def health_summary():
        """Get aggregated health across all AI/Agent/Bot services in the Nexus."""
        nexus = get_nexus()
        return await nexus.health_aggregator.get_summary()

    @app.get("/health/anomalies")
    async def health_anomalies():
        """Detect health anomalies across AI/Agent/Bot services in the Nexus."""
        nexus = get_nexus()
        return await nexus.health_aggregator.detect_anomalies()

    @app.get("/health/service/{service_id}", response_model=NexusServiceHealth)
    async def service_health(service_id: str):
        """Get health for a specific AI/Agent/Bot service in the Nexus."""
        nexus = get_nexus()
        if service_id in nexus.health_aggregator._services:
            return nexus.health_aggregator._services[service_id]
        raise HTTPException(status_code=404, detail=f"Service {service_id} not found")

    # --- Access Control Endpoints ---

    @app.post("/access/check", response_model=NexusAccessDecision)
    async def check_access(request: Request):
        """Perform a tier-aware access control check for Nexus traffic."""
        body = await request.json()
        nexus = get_nexus()
        return await nexus.check_access(**body)

    @app.get("/access/tiers")
    async def get_tier_hierarchy():
        """Get the tier hierarchy definition for AI/Agent/Bot access control."""
        return {
            "0": "HUMAN — Override authority, maximum access",
            "1": "ORCHESTRATOR — System-level coordination",
            "2": "PRIME — Strategic decision-making",
            "3": "AI — The overarching ML/LLM Complex",
            "4": "AGENT — Lower-level autonomous AI",
            "5": "BOT — Stateless service worker/function",
        }

    # --- Event Endpoints ---

    @app.post("/events/emit", response_model=NexusEvent)
    async def emit_event(request: Request):
        """Emit an AI/Agent/Bot traffic event through the Nexus."""
        body = await request.json()
        nexus = get_nexus()
        return await nexus.emit_event(**body)

    @app.get("/events/recent")
    async def recent_events(channel: Optional[str] = None, limit: int = 100):
        """Get recent Nexus events in causal order."""
        nexus = get_nexus()
        return [
            e.model_dump()
            for e in await nexus.causal_engine.get_ordered_events(channel, limit)
        ]

    @app.get("/events/routing")
    async def event_routing():
        """Get the current Nexus event routing table."""
        nexus = get_nexus()
        return await nexus.event_router.get_routing_table()

    # --- Topology Endpoints ---

    @app.get("/topology")
    async def get_topology():
        """Get the Nexus topology graph of AI/Agent/Bot services."""
        nexus = get_nexus()
        return await nexus.get_topology()

    @app.get("/topology/nodes")
    async def get_topology_nodes():
        """Get all AI/Agent/Bot service nodes in the Nexus topology."""
        nexus = get_nexus()
        async with nexus._lock:
            return [n.model_dump() for n in nexus._topology_nodes.values()]

    @app.get("/topology/edges")
    async def get_topology_edges():
        """Get all traffic flow edges in the Nexus topology."""
        nexus = get_nexus()
        async with nexus._lock:
            return [e.model_dump() for e in nexus._topology_edges]

    # --- Service Registration ---

    @app.post("/services/register", response_model=NexusServiceHealth)
    async def register_service(request: Request):
        """Register an AI/Agent/Bot service with the Nexus."""
        body = await request.json()
        nexus = get_nexus()
        return await nexus.register_service(**body)

    @app.post("/services/heartbeat")
    async def service_heartbeat(request: Request):
        """Submit a heartbeat for an AI/Agent/Bot service in the Nexus."""
        body = await request.json()
        nexus = get_nexus()
        await nexus.health_aggregator.update_heartbeat(**body)
        return {"status": "acknowledged"}

    # --- Nexus Status ---

    @app.get("/status")
    async def nexus_status():
        """Get the comprehensive Nexus status."""
        nexus = get_nexus()
        return await nexus.get_status()

    @app.get("/")
    async def root():
        """Nexus root endpoint."""
        return {
            "service": "Tranc3 Nexus",
            "version": "0.2.0",
            "bridge_type": "nexus",
            "description": "The Nexus — AI, Agent, and Bot Traffic Coordination",
            "three_bridges": {
                "infinity_bridge": {
                    "name": "InfinityBridge",
                    "role": "User Context & Human Traffic",
                    "description": "User Context & Human Traffic (Light Bridge)",
                    "status": "see_infinity_bridge_status",
                    "bridge_type": "infinity",
                },
                "nexus": {
                    "name": "The Nexus",
                    "role": "AI, Agent, and Bot Traffic",
                    "description": "AI, Agent, and Bot Traffic Coordination",
                    "status": "active",
                    "bridge_type": "nexus",
                },
                "hive": {
                    "name": "The HIVE",
                    "role": "Data Movement & Swarm Coordination",
                    "description": "Data Movement & Swarm System Coordination",
                    "status": "see_hive_status",
                    "bridge_type": "hive",
                },
            },
            "tier_hierarchy": "HUMAN(0) → ORCHESTRATOR(1) → PRIME(2) → AI(3) → AGENT(4) → BOT(5)",
            "channels": [ch.value for ch in SentinelChannel],
            "endpoints": [
                "/health", "/health/anomalies", "/health/service/{id}",
                "/access/check", "/access/tiers",
                "/events/emit", "/events/recent", "/events/routing",
                "/topology", "/topology/nodes", "/topology/edges",
                "/services/register", "/services/heartbeat",
                "/status",
                "/ws/events (WebSocket)",
                "/dashboard",
            ],
        }

    # --- Phase 28: Nexus Cluster (Raft Consensus) Endpoints ---

    @app.get("/cluster/status", tags=["cluster"])
    async def cluster_status():
        """Get the Nexus Cluster status with Raft consensus information."""
        from Dimensional.nexus.raft.raft_core import get_nexus_cluster
        cluster = get_nexus_cluster()
        return cluster.get_cluster_status()

    @app.post("/cluster/nodes/{node_id}", tags=["cluster"])
    async def cluster_add_node(node_id: str):
        """Add a node to the Nexus Cluster."""
        from Dimensional.nexus.raft.raft_core import get_nexus_cluster
        cluster = get_nexus_cluster()
        await cluster.add_node(node_id)
        return {"action": "add_node", "node_id": node_id, "status": "added"}

    @app.delete("/cluster/nodes/{node_id}", tags=["cluster"])
    async def cluster_remove_node(node_id: str):
        """Remove a node from the Nexus Cluster."""
        from Dimensional.nexus.raft.raft_core import get_nexus_cluster
        cluster = get_nexus_cluster()
        await cluster.remove_node(node_id)
        return {"action": "remove_node", "node_id": node_id, "status": "removed"}

    @app.post("/cluster/propose", tags=["cluster"])
    async def cluster_propose(request: Request):
        """Propose a command to the Nexus Cluster via Raft consensus."""
        from Dimensional.nexus.raft.raft_core import get_nexus_cluster
        body = await request.json()
        cluster = get_nexus_cluster()
        result = await cluster.propose(body.get("command", {}))
        return {"action": "propose", "result": result}

    # --- Phase 28: Pillar Entity Endpoints ---

    @app.get("/pillars/locations", tags=["pillars"])
    async def pillar_locations():
        """Get all pillar entity locations and their configurations."""
        from Dimensional.pillars.entities import get_pillar_registry
        registry = get_pillar_registry()
        return registry.get_full_summary()

    @app.get("/pillars/locations/{location}", tags=["pillars"])
    async def pillar_location_detail(location: str):
        """Get pillar entities for a specific location."""
        from Dimensional.pillars.entities import get_pillar_registry, PillarLocation
        registry = get_pillar_registry()
        entities = registry.get_by_location(location)
        return {
            "location": location,
            "entity_count": len(entities),
            "entities": [e.model_dump() for e in entities],
        }

    @app.get("/pillars/tiers", tags=["pillars"])
    async def pillar_tiers():
        """Get pillar entities grouped by tier."""
        from Dimensional.pillars.entities import get_pillar_registry, EntityTier
        registry = get_pillar_registry()
        result = {}
        for tier in EntityTier:
            entities = registry.get_by_tier(tier)
            result[tier.name] = [e.model_dump() for e in entities]
        return result

    # --- WebSocket Endpoint ---

    @app.websocket("/ws/events")
    async def ws_events(ws: WebSocket):
        """WebSocket endpoint for live Nexus event streaming to dashboards."""
        await _ws_manager.connect(ws)
        try:
            while True:
                data = await ws.receive_text()
                # Client can send channel subscription messages
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "subscribe" and "channel" in msg:
                        _ws_manager._channel_subs[msg["channel"]].append(ws)
                        await ws.send_text(json.dumps({"type": "subscribed", "channel": msg["channel"]}))
                except (json.JSONDecodeError, KeyError):
                    pass
        except WebSocketDisconnect:
            _ws_manager.disconnect(ws)

    # --- Dashboard UI ---

    @app.get("/dashboard", response_class=HTMLResponse)
    async def dashboard():
        """Serve the Nexus Dashboard web UI."""
        dashboard_path = Path(__file__).parent / "dashboard.html"
        if dashboard_path.exists():
            return dashboard_path.read_text(encoding="utf-8")
        return HTMLResponse(
            "<h1>Dashboard not found</h1><p>Place dashboard.html in the nexus package directory.</p>",
            status_code=404,
        )

    return app


# Create the default app instance
app = create_nexus_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=NEXUS_PORT)
