"""
NSA Registry — Nanoservice Discovery & Health Monitoring
=========================================================
Central registry for nanoservice discovery, health monitoring,
and capability-based routing. Works alongside the NSA Broker
to provide service mesh intelligence.

Architecture:
  - Capability-based discovery: find services by what they DO, not just name
  - Health monitoring: track service liveness, latency, error rates
  - Load-aware routing: direct requests to least-loaded instances
  - Tier-aware: respects the Tranc3 tier hierarchy (1-5)
  - Zero-cost: pure Python, no external dependencies beyond stdlib
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set


class ServiceTier(int, Enum):
    """Tranc3 entity tier hierarchy."""

    TIER_1_SENTINEL = 1
    TIER_2_INFRASTRUCTURE = 2
    TIER_3_INTELLIGENCE = 3
    TIER_4_NEXUS = 4
    TIER_5_HIVE = 5


class ServiceStatus(str, Enum):
    STARTING = "starting"
    READY = "ready"
    BUSY = "busy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    DRAINING = "draining"


@dataclass
class Capability:
    """Describes a nanoservice capability."""

    name: str
    version: str = "1.0.0"
    input_schema: Optional[Dict[str, Any]] = None
    output_schema: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "input_schema": self.input_schema,
            "output_schema": self.output_schema,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Capability":
        return cls(
            name=data["name"],
            version=data.get("version", "1.0.0"),
            input_schema=data.get("input_schema"),
            output_schema=data.get("output_schema"),
            metadata=data.get("metadata", {}),
        )


@dataclass
class HealthReport:
    """Health status for a registered nanoservice."""

    service_id: str
    status: ServiceStatus
    latency_ms: float = 0.0
    error_rate: float = 0.0
    request_count: int = 0
    last_heartbeat: float = 0.0
    uptime_seconds: float = 0.0
    memory_usage_mb: float = 0.0
    cpu_percent: float = 0.0
    custom_metrics: Dict[str, float] = field(default_factory=dict)

    def is_healthy(self, max_latency_ms: float = 500.0, max_error_rate: float = 0.1) -> bool:
        if self.status in (ServiceStatus.OFFLINE, ServiceStatus.DRAINING):
            return False
        if self.latency_ms > max_latency_ms:
            return False
        if self.error_rate > max_error_rate:
            return False
        return True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "status": self.status.value,
            "latency_ms": self.latency_ms,
            "error_rate": self.error_rate,
            "request_count": self.request_count,
            "last_heartbeat": self.last_heartbeat,
            "uptime_seconds": self.uptime_seconds,
            "memory_usage_mb": self.memory_usage_mb,
            "cpu_percent": self.cpu_percent,
            "custom_metrics": self.custom_metrics,
        }


@dataclass
class RegisteredService:
    """A fully registered nanoservice with all metadata."""

    id: str
    name: str
    tier: ServiceTier
    capabilities: List[Capability]
    shm_segment: str
    pid: int
    endpoint: str
    registered_at: float = field(default_factory=time.time)
    health: Optional[HealthReport] = None
    tags: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "tier": self.tier.value,
            "capabilities": [c.to_dict() for c in self.capabilities],
            "shm_segment": self.shm_segment,
            "pid": self.pid,
            "endpoint": self.endpoint,
            "registered_at": self.registered_at,
            "health": self.health.to_dict() if self.health else None,
            "tags": list(self.tags),
            "metadata": self.metadata,
        }


class NSARegistry:
    """
    NSA Registry — capability-based service discovery and health monitoring.

    Usage:
        registry = NSARegistry()
        await registry.start()

        # Register a service
        svc = await registry.register(
            name="shi_gateway",
            tier=ServiceTier.TIER_3_INTELLIGENCE,
            capabilities=[Capability(name="inference", version="1.0")],
            shm_segment="nsa_shi_gateway",
            pid=12345,
            endpoint="http://localhost:7781",
            tags={"inference", "ollama", "vllm"}
        )

        # Discover by capability
        services = await registry.discover(capability="inference")

        # Get healthiest instance
        best = await registry.get_healthiest(capability="inference")
    """

    def __init__(
        self,
        heartbeat_timeout_s: float = 30.0,
        health_check_interval_s: float = 10.0,
        broker_url: str = "http://localhost:7780",
    ):
        self._services: Dict[str, RegisteredService] = {}
        self._capability_index: Dict[str, Set[str]] = {}  # cap_name -> {service_ids}
        self._tag_index: Dict[str, Set[str]] = {}  # tag -> {service_ids}
        self._heartbeat_timeout_s = heartbeat_timeout_s
        self._health_check_interval_s = health_check_interval_s
        self._broker_url = broker_url
        self._event_handlers: Dict[str, List[Callable]] = {}
        self._running = False
        self._health_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the registry health monitor."""
        self._running = True
        self._health_task = asyncio.create_task(self._health_monitor_loop())

    async def stop(self) -> None:
        """Stop the registry."""
        self._running = False
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass

    async def register(
        self,
        name: str,
        tier: ServiceTier,
        capabilities: List[Capability],
        shm_segment: str,
        pid: int,
        endpoint: str,
        tags: Optional[Set[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RegisteredService:
        """Register a new nanoservice."""
        async with self._lock:
            svc_id = f"{name}_{uuid.uuid4().hex[:8]}"
            svc = RegisteredService(
                id=svc_id,
                name=name,
                tier=tier,
                capabilities=capabilities,
                shm_segment=shm_segment,
                pid=pid,
                endpoint=endpoint,
                tags=tags or set(),
                metadata=metadata or {},
            )
            svc.health = HealthReport(
                service_id=svc_id,
                status=ServiceStatus.STARTING,
                last_heartbeat=time.time(),
            )
            self._services[svc_id] = svc

            # Update capability index
            for cap in capabilities:
                if cap.name not in self._capability_index:
                    self._capability_index[cap.name] = set()
                self._capability_index[cap.name].add(svc_id)

            # Update tag index
            for tag in svc.tags:
                if tag not in self._tag_index:
                    self._tag_index[tag] = set()
                self._tag_index[tag].add(svc_id)

            await self._emit("registered", svc)
            return svc

    async def deregister(self, service_id: str) -> bool:
        """Remove a nanoservice from the registry."""
        async with self._lock:
            svc = self._services.pop(service_id, None)
            if not svc:
                return False

            # Clean capability index
            for cap in svc.capabilities:
                if cap.name in self._capability_index:
                    self._capability_index[cap.name].discard(service_id)
                    if not self._capability_index[cap.name]:
                        del self._capability_index[cap.name]

            # Clean tag index
            for tag in svc.tags:
                if tag in self._tag_index:
                    self._tag_index[tag].discard(service_id)
                    if not self._tag_index[tag]:
                        del self._tag_index[tag]

            await self._emit("deregistered", svc)
            return True

    async def discover(
        self,
        capability: Optional[str] = None,
        tier: Optional[ServiceTier] = None,
        tag: Optional[str] = None,
        status: Optional[ServiceStatus] = None,
        min_tier: Optional[ServiceTier] = None,
        max_tier: Optional[ServiceTier] = None,
    ) -> List[RegisteredService]:
        """Discover services matching criteria."""
        async with self._lock:
            candidates = set(self._services.keys())

            if capability:
                cap_ids = self._capability_index.get(capability, set())
                candidates &= cap_ids

            if tag:
                tag_ids = self._tag_index.get(tag, set())
                candidates &= tag_ids

            results = []
            for sid in candidates:
                svc = self._services[sid]
                if tier and svc.tier != tier:
                    continue
                if min_tier and svc.tier < min_tier:
                    continue
                if max_tier and svc.tier > max_tier:
                    continue
                if status and svc.health and svc.health.status != status:
                    continue
                results.append(svc)

            return results

    async def get_healthiest(
        self,
        capability: Optional[str] = None,
        tier: Optional[ServiceTier] = None,
        max_latency_ms: float = 500.0,
        max_error_rate: float = 0.1,
    ) -> Optional[RegisteredService]:
        """Get the healthiest service matching criteria."""
        services = await self.discover(capability=capability, tier=tier)
        healthy = [
            s for s in services if s.health and s.health.is_healthy(max_latency_ms, max_error_rate)
        ]
        if not healthy:
            return None
        # Sort by: lowest error rate, then lowest latency, then lowest request count
        healthy.sort(
            key=lambda s: (
                s.health.error_rate,  # type: ignore[union-attr]
                s.health.latency_ms,  # type: ignore[union-attr]
                s.health.request_count,  # type: ignore[union-attr]
            )
        )
        return healthy[0]

    async def update_health(self, service_id: str, report: HealthReport) -> bool:
        """Update health report for a service."""
        async with self._lock:
            svc = self._services.get(service_id)
            if not svc:
                return False
            old_status = svc.health.status if svc.health else None
            svc.health = report
            report.last_heartbeat = time.time()

            if old_status != report.status:
                await self._emit("status_change", svc, old_status, report.status)

            return True

    async def heartbeat(self, service_id: str, metrics: Optional[Dict[str, float]] = None) -> bool:
        """Record a heartbeat from a service."""
        async with self._lock:
            svc = self._services.get(service_id)
            if not svc:
                return False
            if svc.health:
                svc.health.last_heartbeat = time.time()
                svc.health.uptime_seconds = time.time() - svc.registered_at
                if metrics:
                    svc.health.custom_metrics.update(metrics)
                if svc.health.status == ServiceStatus.STARTING:
                    svc.health.status = ServiceStatus.READY
            return True

    async def record_request(self, service_id: str, latency_ms: float, success: bool) -> None:
        """Record a request result for load/health tracking."""
        async with self._lock:
            svc = self._services.get(service_id)
            if not svc or not svc.health:
                return
            h = svc.health
            h.request_count += 1
            # Exponential moving average for latency
            alpha = 0.3
            h.latency_ms = alpha * latency_ms + (1 - alpha) * h.latency_ms
            # Rolling error rate
            if not success:
                h.error_rate = alpha * 1.0 + (1 - alpha) * h.error_rate
            else:
                h.error_rate = (1 - alpha) * h.error_rate

    async def get(self, service_id: str) -> Optional[RegisteredService]:
        """Get a service by ID."""
        return self._services.get(service_id)

    async def list_all(self) -> List[RegisteredService]:
        """List all registered services."""
        return list(self._services.values())

    async def list_capabilities(self) -> Dict[str, int]:
        """List all capabilities and how many services provide each."""
        return {cap: len(ids) for cap, ids in self._capability_index.items()}

    async def list_tags(self) -> Dict[str, int]:
        """List all tags and how many services have each."""
        return {tag: len(ids) for tag, ids in self._tag_index.items()}

    def on(self, event: str, handler: Callable) -> None:
        """Register an event handler."""
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    async def _emit(self, event: str, *args: Any) -> None:
        """Emit an event to registered handlers."""
        for handler in self._event_handlers.get(event, []):
            if asyncio.iscoroutinefunction(handler):
                await handler(*args)
            else:
                handler(*args)

    async def _health_monitor_loop(self) -> None:
        """Periodic health check — mark services as OFFLINE if heartbeat times out."""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval_s)
                now = time.time()
                async with self._lock:
                    for svc in self._services.values():
                        if not svc.health:
                            continue
                        elapsed = now - svc.health.last_heartbeat
                        if elapsed > self._heartbeat_timeout_s:
                            if svc.health.status != ServiceStatus.OFFLINE:
                                old = svc.health.status
                                svc.health.status = ServiceStatus.OFFLINE
                                await self._emit("status_change", svc, old, ServiceStatus.OFFLINE)
                        elif elapsed > self._heartbeat_timeout_s * 0.7:
                            if svc.health.status == ServiceStatus.READY:
                                old = svc.health.status
                                svc.health.status = ServiceStatus.DEGRADED
                                await self._emit("status_change", svc, old, ServiceStatus.DEGRADED)
            except asyncio.CancelledError:
                break
            except Exception:  # noqa: S110
                pass  # graceful degradation

    def stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        status_counts: Dict[str, int] = {}
        tier_counts: Dict[int, int] = {}
        for svc in self._services.values():
            s = svc.health.status.value if svc.health else "unknown"
            status_counts[s] = status_counts.get(s, 0) + 1
            tier_counts[svc.tier.value] = tier_counts.get(svc.tier.value, 0) + 1
        return {
            "total_services": len(self._services),
            "by_status": status_counts,
            "by_tier": tier_counts,
            "capabilities": len(self._capability_index),
            "tags": len(self._tag_index),
        }
