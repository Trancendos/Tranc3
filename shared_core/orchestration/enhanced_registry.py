# shared_core/orchestration/enhanced_registry.py
# Enhanced ServiceRegistry with auto-discovery, capability-based routing,
# load-aware selection, and proactive rebalancing.

import asyncio
import hashlib
import json
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class RoutingStrategy(str, Enum):
    """Strategy for selecting among multiple capable services."""
    ROUND_ROBIN = "round_robin"
    LEAST_LOADED = "least_loaded"
    WEIGHTED_HEALTH = "weighted_health"
    RANDOM = "random"
    CAPABILITY_SCORE = "capability_score"


@dataclass
class ServiceDiscoveryEvent:
    """Event emitted when a service is discovered or changes state."""
    event_type: str  # "discovered", "lost", "health_change", "capability_change"
    service_name: str
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type,
            "service_name": self.service_name,
            "timestamp": self.timestamp,
            "details": self.details,
        }


@dataclass
class _ServiceMetrics:
    """Internal tracking metrics for a registered service."""
    request_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    last_request_time: float = 0.0
    active_connections: int = 0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    uptime_seconds: float = 0.0
    registered_at: float = field(default_factory=time.time)
    weight: float = 1.0  # adaptive weight for routing

    @property
    def error_rate(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.error_count / self.request_count

    @property
    def avg_latency_ms(self) -> float:
        if self.request_count == 0:
            return 0.0
        return self.total_latency_ms / self.request_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": round(self.error_rate, 4),
            "avg_latency_ms": round(self.avg_latency_ms, 2),
            "active_connections": self.active_connections,
            "consecutive_failures": self.consecutive_failures,
            "consecutive_successes": self.consecutive_successes,
            "weight": round(self.weight, 4),
        }


class EnhancedServiceRegistry:
    """
    Enhanced service registry with auto-discovery, capability-based routing,
    and adaptive load balancing.

    Wraps and extends the base ServiceRegistry with:
    - Auto-discovery via probing and heartbeat tracking
    - Multiple routing strategies (round-robin, least-loaded, weighted-health)
    - Per-service metrics collection and adaptive weight adjustment
    - Event-driven notifications for discovery, loss, and changes
    - Proactive rebalancing when service health degrades
    """

    def __init__(
        self,
        routing_strategy: RoutingStrategy = RoutingStrategy.WEIGHTED_HEALTH,
        discovery_interval: float = 60.0,
        heartbeat_timeout: float = 90.0,
        weight_adaptation_rate: float = 0.1,
        min_weight: float = 0.01,
        max_weight: float = 10.0,
    ):
        self._services: Dict[str, Any] = {}  # name -> service info dict
        self._capabilities: Dict[str, List[str]] = defaultdict(list)  # cap -> [names]
        self._metrics: Dict[str, _ServiceMetrics] = {}
        self._watchers: List[Callable] = []
        self._discovery_watchers: List[Callable] = []
        self._routing_strategy = routing_strategy
        self._discovery_interval = discovery_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._weight_adaptation_rate = weight_adaptation_rate
        self._min_weight = min_weight
        self._max_weight = max_weight
        self._rr_counters: Dict[str, int] = defaultdict(int)  # capability -> round-robin idx
        self._discovery_task: Optional[asyncio.Task] = None
        self._rebalance_task: Optional[asyncio.Task] = None
        self._event_log: List[ServiceDiscoveryEvent] = []

    # ── Registration ──────────────────────────────────────────────

    def register(
        self,
        name: str,
        endpoint: str,
        health_url: str,
        capabilities: List[Dict[str, Any]],
        version: str = "1.0.0",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Register a service with its capabilities and endpoint info."""
        service_data = {
            "name": name,
            "version": version,
            "endpoint": endpoint,
            "health_url": health_url,
            "capabilities": capabilities,
            "health": "unknown",
            "last_seen": time.time(),
            "metadata": metadata or {},
        }
        self._services[name] = service_data
        self._metrics[name] = _ServiceMetrics()

        # Build capability index
        for cap in capabilities:
            cap_name = cap.get("name", cap) if isinstance(cap, dict) else cap
            if name not in self._capabilities[cap_name]:
                self._capabilities[cap_name].append(name)

        logger.info("Registered service: %s @ %s", sanitize_for_log(name), sanitize_for_log(endpoint))
        self._emit_discovery_event("discovered", name, {"endpoint": endpoint, "capabilities": [c if isinstance(c, str) else c.get("name") for c in capabilities]})

    def deregister(self, name: str) -> Optional[Dict[str, Any]]:
        """Remove a service from the registry."""
        service = self._services.pop(name, None)
        if service:
            self._metrics.pop(name, None)
            # Clean capability index
            for cap_list in self._capabilities.values():
                if name in cap_list:
                    cap_list.remove(name)
            # Clean round-robin counters
            for cap_name in list(self._rr_counters.keys()):
                if name in self._capabilities.get(cap_name, []):
                    pass  # counter will naturally adjust
            logger.info("Deregistered service: %s", sanitize_for_log(name))
            self._emit_discovery_event("lost", name, {"endpoint": service.get("endpoint")})
        return service

    # ── Capability-Based Routing ─────────────────────────────────

    def resolve(self, capability: str, strategy: Optional[RoutingStrategy] = None) -> Optional[Dict[str, Any]]:
        """
        Resolve the best service endpoint for a given capability.
        Uses the configured routing strategy or an override.
        """
        strat = strategy or self._routing_strategy
        candidates = self._get_healthy_candidates(capability)

        if not candidates:
            logger.warning("No healthy service found for capability: %s", sanitize_for_log(capability))
            return None

        if len(candidates) == 1:
            selected = candidates[0]
        elif strat == RoutingStrategy.ROUND_ROBIN:
            selected = self._select_round_robin(capability, candidates)
        elif strat == RoutingStrategy.LEAST_LOADED:
            selected = self._select_least_loaded(candidates)
        elif strat == RoutingStrategy.WEIGHTED_HEALTH:
            selected = self._select_weighted_health(candidates)
        elif strat == RoutingStrategy.CAPABILITY_SCORE:
            selected = self._select_capability_score(capability, candidates)
        else:  # RANDOM
            import random
            selected = random.choice(candidates)

        # Record the request
        name = selected["name"]
        self._metrics[name].request_count += 1
        self._metrics[name].last_request_time = time.time()
        self._metrics[name].active_connections += 1

        return selected

    def _get_healthy_candidates(self, capability: str) -> List[Dict[str, Any]]:
        """Get healthy or degraded services offering a capability."""
        names = self._capabilities.get(capability, [])
        candidates = []
        for name in names:
            svc = self._services.get(name)
            if svc and svc.get("health") != "unhealthy":
                candidates.append(svc)
        return candidates

    def _select_round_robin(self, capability: str, candidates: List[Dict]) -> Dict:
        """Round-robin selection among candidates."""
        idx = self._rr_counters[capability] % len(candidates)
        self._rr_counters[capability] = idx + 1
        return candidates[idx]

    def _select_least_loaded(self, candidates: List[Dict]) -> Dict:
        """Select the service with the fewest active connections."""
        return min(candidates, key=lambda s: self._metrics[s["name"]].active_connections)

    def _select_weighted_health(self, candidates: List[Dict]) -> Dict:
        """Select using adaptive weights that reflect health, latency, and error rate."""
        import random
        weights = []
        for svc in candidates:
            m = self._metrics[svc["name"]]
            # Health multiplier
            health_mult = 1.0 if svc.get("health") == "healthy" else 0.5 if svc.get("health") == "degraded" else 0.1
            # Latency factor (lower is better, invert)
            latency_factor = 1.0 / (1.0 + m.avg_latency_ms / 1000.0)
            # Error rate penalty
            error_penalty = 1.0 - min(m.error_rate, 0.99)
            # Combined weight
            w = m.weight * health_mult * latency_factor * error_penalty
            weights.append(max(w, 0.001))

        total = sum(weights)
        if total == 0:
            return candidates[0]
        r = random.random() * total
        cumulative = 0.0
        for i, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                return candidates[i]
        return candidates[-1]

    def _select_capability_score(self, capability: str, candidates: List[Dict]) -> Dict:
        """Score candidates based on capability version match and metadata."""
        best = None
        best_score = -1.0
        for svc in candidates:
            score = self._compute_capability_score(capability, svc)
            if score > best_score:
                best_score = score
                best = svc
        return best or candidates[0]

    def _compute_capability_score(self, capability: str, svc: Dict) -> float:
        """Compute a 0-1 score for how well a service matches a capability request."""
        base = self._metrics[svc["name"]].weight
        # Check capability metadata for version match
        for cap in svc.get("capabilities", []):
            cap_name = cap.get("name", cap) if isinstance(cap, dict) else cap
            if cap_name == capability and isinstance(cap, dict):
                # Higher version = higher score
                version = cap.get("version", "1.0.0")
                try:
                    parts = version.split(".")
                    version_score = sum(int(p) * (0.1 ** i) for i, p in enumerate(parts[:3]))
                except (ValueError, IndexError):
                    version_score = 1.0
                base *= (0.5 + version_score * 0.5)
        return base

    # ── Metrics & Adaptive Weight ─────────────────────────────────

    def record_success(self, service_name: str, latency_ms: float = 0.0) -> None:
        """Record a successful request to a service."""
        m = self._metrics.get(service_name)
        if not m:
            return
        m.consecutive_successes += 1
        m.consecutive_failures = 0
        m.total_latency_ms += latency_ms
        m.active_connections = max(0, m.active_connections - 1)
        # Adaptive: increase weight on success
        m.weight = min(self._max_weight, m.weight * (1.0 + self._weight_adaptation_rate))

    def record_failure(self, service_name: str, error: Optional[str] = None) -> None:
        """Record a failed request to a service."""
        m = self._metrics.get(service_name)
        if not m:
            return
        m.error_count += 1
        m.consecutive_failures += 1
        m.consecutive_successes = 0
        m.active_connections = max(0, m.active_connections - 1)
        # Adaptive: decrease weight on failure
        penalty = 1.0 - self._weight_adaptation_rate * (1.0 + m.consecutive_failures * 0.5)
        m.weight = max(self._min_weight, m.weight * penalty)
        logger.warning("Service %s failure #%d (weight→%.3f): %s",
                       sanitize_for_log(service_name), m.consecutive_failures,
                       m.weight, sanitize_for_log(error or "unknown"))

    def update_health(self, name: str, health: str) -> None:
        """Update a service's health status."""
        svc = self._services.get(name)
        if svc and svc.get("health") != health:
            old_health = svc.get("health", "unknown")
            svc["health"] = health
            svc["last_seen"] = time.time()
            logger.info("Service %s: %s → %s", sanitize_for_log(name), old_health, health)
            self._emit_discovery_event("health_change", name, {"from": old_health, "to": health})
            self._notify_watchers("health_change", name)

            # Adaptive weight adjustment on health change
            m = self._metrics.get(name)
            if m:
                if health == "healthy":
                    m.weight = min(self._max_weight, m.weight * 1.5)
                elif health == "degraded":
                    m.weight = max(self._min_weight, m.weight * 0.7)
                elif health == "unhealthy":
                    m.weight = self._min_weight

    # ── Auto-Discovery ────────────────────────────────────────────

    async def start_discovery(self) -> None:
        """Start the auto-discovery and rebalancing loops."""
        self._discovery_task = asyncio.create_task(self._discovery_loop())
        self._rebalance_task = asyncio.create_task(self._rebalance_loop())

    async def stop_discovery(self) -> None:
        """Stop the auto-discovery and rebalancing loops."""
        for task in [self._discovery_task, self._rebalance_task]:
            if task:
                task.cancel()
        self._discovery_task = None
        self._rebalance_task = None

    async def _discovery_loop(self) -> None:
        """Periodically probe services and detect stale registrations."""
        while True:
            try:
                await asyncio.sleep(self._discovery_interval)
                now = time.time()
                stale = []
                for name, svc in list(self._services.items()):
                    elapsed = now - svc.get("last_seen", 0)
                    if elapsed > self._heartbeat_timeout:
                        stale.append(name)
                    elif elapsed > self._heartbeat_timeout * 0.75:
                        # Approaching timeout — degrade health
                        if svc.get("health") != "degraded":
                            self.update_health(name, "degraded")

                for name in stale:
                    logger.warning("Service %s heartbeat timeout — marking unhealthy", sanitize_for_log(name))
                    self.update_health(name, "unhealthy")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Discovery loop error: %s", sanitize_for_log(str(e)))

    async def _rebalance_loop(self) -> None:
        """Periodically rebalance weights based on recent performance."""
        while True:
            try:
                await asyncio.sleep(self._discovery_interval * 2)
                self._rebalance_weights()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Rebalance loop error: %s", sanitize_for_log(str(e)))

    def _rebalance_weights(self) -> None:
        """Adjust weights toward 1.0 baseline, rewarding good performance."""
        for name, m in self._metrics.items():
            svc = self._services.get(name)
            if not svc:
                continue
            # Slowly drift weight toward 1.0
            m.weight = m.weight + (1.0 - m.weight) * self._weight_adaptation_rate * 0.1
            # Boost if consistently successful
            if m.consecutive_successes > 10:
                m.weight = min(self._max_weight, m.weight * 1.05)
            # Clamp
            m.weight = max(self._min_weight, min(self._max_weight, m.weight))

    # ── Query & Introspection ─────────────────────────────────────

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        """Look up a service by name."""
        return self._services.get(name)

    def find_by_capability(self, capability: str) -> List[Dict[str, Any]]:
        """Find all services offering a capability (excluding unhealthy)."""
        return self._get_healthy_candidates(capability)

    def list_all(self) -> List[Dict[str, Any]]:
        """List all registered services with their metrics."""
        result = []
        for name, svc in self._services.items():
            entry = dict(svc)
            entry["metrics"] = self._metrics[name].to_dict() if name in self._metrics else {}
            result.append(entry)
        return result

    def get_metrics(self, name: str) -> Optional[Dict[str, Any]]:
        """Get metrics for a specific service."""
        m = self._metrics.get(name)
        return m.to_dict() if m else None

    def get_routing_topology(self) -> Dict[str, Any]:
        """Get the current routing topology — capabilities → services → weights."""
        topology = {}
        for cap, names in self._capabilities.items():
            topology[cap] = [
                {
                    "name": n,
                    "health": self._services[n].get("health", "unknown") if n in self._services else "unknown",
                    "weight": round(self._metrics[n].weight, 4) if n in self._metrics else 0.0,
                    "active": self._metrics[n].active_connections if n in self._metrics else 0,
                }
                for n in names
                if n in self._services
            ]
        return topology

    # ── Event System ──────────────────────────────────────────────

    def add_watcher(self, callback: Callable) -> None:
        """Register a callback for registry change events."""
        self._watchers.append(callback)

    def add_discovery_watcher(self, callback: Callable) -> None:
        """Register a callback for discovery events."""
        self._discovery_watchers.append(callback)

    def _notify_watchers(self, event: str, service_name: str) -> None:
        """Notify all watchers of a registry change."""
        for watcher in self._watchers:
            try:
                watcher(event, service_name)
            except Exception as e:
                logger.error("Watcher error: %s", sanitize_for_log(str(e)))

    def _emit_discovery_event(self, event_type: str, service_name: str, details: Dict[str, Any] = None) -> None:
        """Emit a discovery event to watchers and log."""
        event = ServiceDiscoveryEvent(
            event_type=event_type,
            service_name=service_name,
            details=details or {},
        )
        self._event_log.append(event)
        # Keep only last 1000 events
        if len(self._event_log) > 1000:
            self._event_log = self._event_log[-500:]
        for watcher in self._discovery_watchers:
            try:
                watcher(event)
            except Exception as e:
                logger.error("Discovery watcher error: %s", sanitize_for_log(str(e)))

    def get_event_log(self, since: float = 0.0, event_type: Optional[str] = None) -> List[Dict]:
        """Query discovery events."""
        events = self._event_log
        if since:
            events = [e for e in events if e.timestamp >= since]
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        return [e.to_dict() for e in events]
