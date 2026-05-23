"""
shared_core.orchestration.health_monitor — Adaptive health monitoring with circuit breakers.

Provides circuit-breaker pattern for service resilience, adaptive health
monitoring with configurable check intervals, and health trend detection.

Zero-cost: All monitoring is in-process, no external services required.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional


class CircuitState(str, Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class HealthStatus(str, Enum):
    """Service health statuses."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class CircuitBreaker:
    """Circuit breaker for protecting against cascading failures.

    Implements the circuit-breaker pattern with exponential backoff cooldown.
    Transitions: CLOSED -> OPEN (after N failures) -> HALF_OPEN (after cooldown)
    -> CLOSED (after M successes) or back to OPEN (on failure).

    Args:
        name: Circuit breaker identifier.
        failure_threshold: Consecutive failures before opening.
        cooldown_seconds: Initial cooldown duration.
        success_threshold: Successes needed to close from HALF_OPEN.
        max_cooldown: Maximum cooldown duration.
    """

    def __init__(
        self,
        name: str = "default",
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
        success_threshold: int = 3,
        max_cooldown: float = 300.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.success_threshold = success_threshold
        self.max_cooldown = max_cooldown

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._open_count = 0
        self._current_cooldown = cooldown_seconds
        self._last_failure_time: Optional[float] = None
        self._opened_at: Optional[float] = None
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        """Current circuit state, with automatic HALF_OPEN transition."""
        with self._lock:
            if self._state == CircuitState.OPEN and self._opened_at is not None:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._current_cooldown:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
            return self._state

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """Check if a request should be allowed through."""
        current = self.state
        return current in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Record a successful operation."""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    self._current_cooldown = self.cooldown_seconds

    def record_failure(self) -> None:
        """Record a failed operation."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._open_circuit()
            elif self._failure_count >= self.failure_threshold:
                self._open_circuit()

    def _open_circuit(self) -> None:
        """Open the circuit and apply exponential backoff."""
        self._state = CircuitState.OPEN
        self._opened_at = time.monotonic()
        self._open_count += 1
        self._success_count = 0
        # Exponential backoff
        self._current_cooldown = min(
            self.cooldown_seconds * (2 ** (self._open_count - 1)),
            self.max_cooldown,
        )

    def reset(self) -> None:
        """Manually reset the circuit to CLOSED."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._opened_at = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize circuit breaker state."""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_threshold": self.failure_threshold,
            "failure_count": self._failure_count,
            "open_count": self._open_count,
            "current_cooldown": self._current_cooldown,
        }


@dataclass
class LatencyStats:
    """Latency statistics for a service."""
    samples: int = 0
    avg_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0


class AdaptiveHealthMonitor:
    """Adaptive health monitor for service instances.

    Tracks health status, latency, and circuit-breaker state for registered
    services. Provides health trend detection and adaptive check intervals.

    Args:
        check_interval: Base health check interval in seconds.
        adaptive: Whether to adjust check intervals based on health.
    """

    def __init__(
        self,
        check_interval: float = 30.0,
        adaptive: bool = True,
    ) -> None:
        self._check_interval = check_interval
        self._adaptive = adaptive
        self._services: Dict[str, Dict[str, Any]] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._status_callbacks: List[Callable] = []
        self._lock = threading.Lock()

    def register_service(
        self,
        name: str,
        health_url: str = "",
        check_interval: Optional[float] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
    ) -> None:
        """Register a service for health monitoring.

        Args:
            name: Service name.
            health_url: URL for health check endpoint.
            check_interval: Override check interval for this service.
            circuit_breaker: Optional custom circuit breaker.
        """
        with self._lock:
            self._services[name] = {
                "name": name,
                "health_url": health_url,
                "check_interval": check_interval or self._check_interval,
                "status": HealthStatus.UNKNOWN,
                "latencies": [],
                "last_check": None,
                "consecutive_failures": 0,
                "consecutive_successes": 0,
            }
            self._circuit_breakers[name] = circuit_breaker or CircuitBreaker(
                name=name,
            )

    def deregister_service(self, name: str) -> None:
        """Remove a service from monitoring."""
        with self._lock:
            self._services.pop(name, None)
            self._circuit_breakers.pop(name, None)

    def get_status(self, name: str) -> Optional[HealthStatus]:
        """Get the current health status of a service."""
        with self._lock:
            svc = self._services.get(name)
            return svc["status"] if svc else None

    def get_latency_stats(self, name: str) -> Dict[str, Any]:
        """Get latency statistics for a service."""
        with self._lock:
            svc = self._services.get(name)
            if not svc or not svc["latencies"]:
                return {"samples": 0, "avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0}
            latencies = sorted(svc["latencies"])
            n = len(latencies)
            return {
                "samples": n,
                "avg_ms": sum(latencies) / n,
                "min_ms": latencies[0],
                "max_ms": latencies[-1],
                "p50_ms": latencies[n // 2],
                "p95_ms": latencies[int(n * 0.95)],
                "p99_ms": latencies[int(n * 0.99)] if n > 1 else latencies[-1],
            }

    def get_health_trend(self, name: str) -> str:
        """Get the health trend for a service.

        Returns:
            One of: "improving", "degrading", "stable", "unknown".
        """
        with self._lock:
            svc = self._services.get(name)
            if not svc:
                return "unknown"
            if svc["consecutive_failures"] > 3:
                return "degrading"
            if svc["consecutive_successes"] > 3:
                return "improving"
            if svc["status"] == HealthStatus.UNKNOWN:
                return "unknown"
            return "stable"

    def on_status_change(self, callback: Callable) -> None:
        """Register a callback for status changes.

        Args:
            callback: Callable that receives (service_name, old_status, new_status).
        """
        self._status_callbacks.append(callback)

    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Get the circuit breaker for a service."""
        return self._circuit_breakers.get(name)

    def report_success(self, name: str, latency_ms: float = 0.0) -> None:
        """Report a successful health check.

        Args:
            name: Service name.
            latency_ms: Response latency in milliseconds.
        """
        with self._lock:
            svc = self._services.get(name)
            if not svc:
                return
            old_status = svc["status"]
            svc["consecutive_failures"] = 0
            svc["consecutive_successes"] += 1
            if latency_ms > 0:
                svc["latencies"].append(latency_ms)
                # Keep last 100 samples
                if len(svc["latencies"]) > 100:
                    svc["latencies"] = svc["latencies"][-100:]
            svc["status"] = HealthStatus.HEALTHY
            svc["last_check"] = time.monotonic()

        cb = self._circuit_breakers.get(name)
        if cb:
            cb.record_success()

        if old_status != HealthStatus.HEALTHY and self._status_callbacks:
            for cb_fn in self._status_callbacks:
                try:
                    cb_fn(name, old_status, HealthStatus.HEALTHY)
                except Exception:
                    pass

    def report_failure(self, name: str, error: Optional[str] = None) -> None:
        """Report a failed health check.

        Args:
            name: Service name.
            error: Optional error description.
        """
        with self._lock:
            svc = self._services.get(name)
            if not svc:
                return
            old_status = svc["status"]
            svc["consecutive_failures"] += 1
            svc["consecutive_successes"] = 0
            svc["status"] = HealthStatus.UNHEALTHY
            svc["last_check"] = time.monotonic()

        cb = self._circuit_breakers.get(name)
        if cb:
            cb.record_failure()

        if old_status != HealthStatus.UNHEALTHY and self._status_callbacks:
            for cb_fn in self._status_callbacks:
                try:
                    cb_fn(name, old_status, HealthStatus.UNHEALTHY)
                except Exception:
                    pass
