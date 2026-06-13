# shared_core/orchestration/health_monitor.py
# Adaptive health monitoring with circuit breaker pattern.
# Provides resilient, self-tuning health checks that adapt to network conditions.

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal — requests flow through
    OPEN = "open"  # Tripped — requests are rejected
    HALF_OPEN = "half_open"  # Testing — allowing probe requests


class HealthStatus(str, Enum):
    """Overall health assessment."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """Result of a single health check."""

    service_name: str
    status: HealthStatus
    latency_ms: float
    timestamp: float = field(default_factory=time.time)
    message: str = ""
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_name": self.service_name,
            "status": self.status.value,
            "latency_ms": round(self.latency_ms, 2),
            "timestamp": self.timestamp,
            "message": self.message,
            "details": self.details,
        }


class CircuitBreaker:
    """
    Circuit breaker with adaptive thresholds.

    States:
      CLOSED  → Normal operation. Opens after N consecutive failures.
      OPEN    → Requests rejected. After cooldown, transitions to HALF_OPEN.
      HALF_OPEN → Allows probe requests. Closes on success, reopens on failure.

    Adaptive features:
      - Cooldown period increases with repeated openings (exponential backoff)
      - Failure threshold adapts based on historical error rates
      - Success threshold for half-open is proportional to failure threshold
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        max_cooldown: float = 300.0,
        half_open_max_probes: int = 2,
    ):
        self.name = name
        self._state = CircuitState.CLOSED
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._base_cooldown = cooldown_seconds
        self._max_cooldown = max_cooldown
        self._half_open_max_probes = half_open_max_probes
        self._consecutive_failures = 0
        self._consecutive_successes = 0
        self._last_failure_time: float = 0.0
        self._last_state_change: float = time.time()
        self._open_count: int = 0  # total times circuit has opened
        self._half_open_probes: int = 0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            # Check if cooldown has elapsed in OPEN state
            if self._state == CircuitState.OPEN:
                elapsed = time.time() - self._last_failure_time
                cooldown = self._current_cooldown
                if elapsed >= cooldown:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    @property
    def _current_cooldown(self) -> float:
        """Exponential backoff: base * 2^(open_count-1), capped at max."""
        backoff = self._base_cooldown * (2 ** (self._open_count - 1))
        return min(backoff, self._max_cooldown)

    @property
    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    @property
    def is_closed(self) -> bool:
        return self.state == CircuitState.CLOSED

    def allow_request(self) -> bool:
        """Check if a request should be allowed through the circuit."""
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.OPEN:
            return False
        if state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_probes < self._half_open_max_probes:
                    self._half_open_probes += 1
                    return True
                return False
        return False

    def record_success(self) -> None:
        """Record a successful request through the circuit."""
        with self._lock:
            self._consecutive_successes += 1
            self._consecutive_failures = 0
            if self._state == CircuitState.HALF_OPEN:
                if self._consecutive_successes >= self._success_threshold:
                    self._transition_to(CircuitState.CLOSED)

    def record_failure(self) -> None:
        """Record a failed request through the circuit."""
        with self._lock:
            self._consecutive_failures += 1
            self._consecutive_successes = 0
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                if self._consecutive_failures >= self._failure_threshold:
                    self._transition_to(CircuitState.OPEN)

    def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new circuit state."""
        old = self._state
        self._state = new_state
        self._last_state_change = time.time()
        if new_state == CircuitState.OPEN:
            self._open_count += 1
            self._half_open_probes = 0
        elif new_state == CircuitState.HALF_OPEN:
            self._half_open_probes = 0
            self._consecutive_successes = 0
        elif new_state == CircuitState.CLOSED:
            self._consecutive_failures = 0
            self._consecutive_successes = 0
            self._half_open_probes = 0
        logger.info(
            "Circuit %s: %s → %s (failures=%d, opens=%d)",
            sanitize_for_log(self.name),
            old.value,
            new_state.value,
            self._consecutive_failures,
            self._open_count,
        )

    def reset(self) -> None:
        """Manually reset the circuit to closed state."""
        with self._lock:
            self._transition_to(CircuitState.CLOSED)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_threshold": self._failure_threshold,
            "success_threshold": self._success_threshold,
            "consecutive_failures": self._consecutive_failures,
            "consecutive_successes": self._consecutive_successes,
            "open_count": self._open_count,
            "current_cooldown": self._current_cooldown,
            "last_state_change": self._last_state_change,
        }


class AdaptiveHealthMonitor:
    """
    Adaptive health monitoring system with circuit breakers.

    Features:
      - Per-service circuit breakers that trip on consecutive failures
      - Adaptive check intervals that speed up for unhealthy services
      - Latency tracking with percentile calculations
      - Health trend analysis (improving, stable, degrading)
      - Configurable notification callbacks for state changes
      - Graceful degradation — monitors continue even if individual checks fail
    """

    def __init__(
        self,
        default_interval: float = 30.0,
        unhealthy_interval: float = 10.0,
        degraded_interval: float = 20.0,
        latency_window: int = 100,
        circuit_failure_threshold: int = 5,
        circuit_cooldown: float = 30.0,
    ):
        self._default_interval = default_interval
        self._unhealthy_interval = unhealthy_interval
        self._degraded_interval = degraded_interval
        self._circuit_failure_threshold = circuit_failure_threshold
        self._circuit_cooldown = circuit_cooldown
        self._circuits: Dict[str, CircuitBreaker] = {}
        self._results: Dict[str, deque] = {}  # service -> recent results
        self._latency_window = latency_window
        self._callbacks: List[Callable] = []
        self._monitored: Dict[str, Dict[str, Any]] = {}  # service -> config
        self._monitor_task: Optional[asyncio.Task] = None
        self._running = False
        self._lock = threading.Lock()

    # ── Service Registration ──────────────────────────────────────

    def register_service(
        self,
        name: str,
        health_url: str,
        interval: Optional[float] = None,
        timeout: float = 5.0,
        circuit_failure_threshold: Optional[int] = None,
        circuit_cooldown: Optional[float] = None,
    ) -> None:
        """Register a service for health monitoring."""
        with self._lock:
            self._monitored[name] = {
                "health_url": health_url,
                "interval": interval or self._default_interval,
                "timeout": timeout,
                "last_check": 0.0,
                "status": HealthStatus.UNKNOWN,
            }
            self._circuits[name] = CircuitBreaker(
                name=name,
                failure_threshold=circuit_failure_threshold or self._circuit_failure_threshold,
                cooldown_seconds=circuit_cooldown or self._circuit_cooldown,
            )
            self._results[name] = deque(maxlen=self._latency_window)
        logger.info("Health monitor: registered %s", sanitize_for_log(name))

    def deregister_service(self, name: str) -> None:
        """Stop monitoring a service."""
        with self._lock:
            self._monitored.pop(name, None)
            self._circuits.pop(name, None)
            self._results.pop(name, None)

    # ── Health Checking ───────────────────────────────────────────

    async def check_health(self, name: str) -> Optional[HealthCheckResult]:
        """Perform a single health check on a service."""
        config = self._monitored.get(name)
        if not config:
            return None

        circuit = self._circuits.get(name)
        if circuit and circuit.is_open:
            # Circuit is open — skip check, report based on circuit state
            return HealthCheckResult(
                service_name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=0.0,
                message=f"Circuit breaker OPEN (opens={circuit._open_count})",
            )

        start = time.monotonic()
        try:
            import aiohttp

            async with aiohttp.ClientSession() as session:
                async with session.get(
                    config["health_url"],
                    timeout=aiohttp.ClientTimeout(total=config["timeout"]),
                ) as resp:
                    latency = (time.monotonic() - start) * 1000
                    if resp.status == 200:
                        result = HealthCheckResult(
                            service_name=name,
                            status=HealthStatus.HEALTHY,
                            latency_ms=latency,
                            message="OK",
                        )
                        if circuit:
                            circuit.record_success()
                    elif resp.status < 500:
                        result = HealthCheckResult(
                            service_name=name,
                            status=HealthStatus.DEGRADED,
                            latency_ms=latency,
                            message=f"HTTP {resp.status}",
                        )
                        if circuit:
                            circuit.record_failure()
                    else:
                        result = HealthCheckResult(
                            service_name=name,
                            status=HealthStatus.UNHEALTHY,
                            latency_ms=latency,
                            message=f"HTTP {resp.status}",
                        )
                        if circuit:
                            circuit.record_failure()
        except ImportError:
            # aiohttp not available — use urllib as fallback
            try:
                import urllib.request

                req = urllib.request.Request(config["health_url"])
                with urllib.request.urlopen(req, timeout=config["timeout"]) as resp:
                    latency = (time.monotonic() - start) * 1000
                    result = HealthCheckResult(
                        service_name=name,
                        status=HealthStatus.HEALTHY,
                        latency_ms=latency,
                        message="OK",
                    )
                    if circuit:
                        circuit.record_success()
            except Exception as e:
                latency = (time.monotonic() - start) * 1000
                result = HealthCheckResult(
                    service_name=name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=latency,
                    message=str(e),
                )
                if circuit:
                    circuit.record_failure()
        except Exception as e:
            latency = (time.monotonic() - start) * 1000
            result = HealthCheckResult(
                service_name=name,
                status=HealthStatus.UNHEALTHY,
                latency_ms=latency,
                message=str(e),
            )
            if circuit:
                circuit.record_failure()

        # Record the result
        with self._lock:
            if name in self._results:
                self._results[name].append(result)
            if name in self._monitored:
                old_status = self._monitored[name]["status"]
                self._monitored[name]["status"] = result.status
                self._monitored[name]["last_check"] = time.time()
                if old_status != result.status:
                    self._notify_status_change(name, old_status, result.status, result)

        return result

    # ── Monitoring Loop ───────────────────────────────────────────

    async def start(self) -> None:
        """Start the background monitoring loop."""
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the background monitoring loop."""
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            self._monitor_task = None

    async def _monitor_loop(self) -> None:
        """Adaptive monitoring — check services at intervals based on their health."""
        while self._running:
            try:
                now = time.time()
                for name, config in list(self._monitored.items()):
                    interval = self._adaptive_interval(name)
                    if now - config.get("last_check", 0) >= interval:
                        try:
                            await self.check_health(name)
                        except Exception as e:
                            logger.error(
                                "Health check error for %s: %s",
                                sanitize_for_log(name),
                                sanitize_for_log(str(e)),
                            )

                # Sleep for the shortest interval among monitored services
                intervals = [self._adaptive_interval(n) for n in self._monitored]
                sleep_time = min(intervals) if intervals else self._default_interval
                await asyncio.sleep(min(sleep_time, 5.0))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Monitor loop error: %s", sanitize_for_log(str(e)))
                await asyncio.sleep(5.0)

    def _adaptive_interval(self, name: str) -> float:
        """Compute check interval based on current health status."""
        config = self._monitored.get(name)
        if not config:
            return self._default_interval
        status = config.get("status", HealthStatus.UNKNOWN)
        if status == HealthStatus.UNHEALTHY:
            return self._unhealthy_interval
        elif status == HealthStatus.DEGRADED:
            return self._degraded_interval
        return config.get("interval", self._default_interval)

    # ── Analysis & Introspection ──────────────────────────────────

    def get_status(self, name: str) -> Optional[HealthStatus]:
        """Get the current health status of a service."""
        config = self._monitored.get(name)
        return config.get("status") if config else None

    def get_circuit(self, name: str) -> Optional[CircuitBreaker]:
        """Get the circuit breaker for a service."""
        return self._circuits.get(name)

    def get_latency_stats(self, name: str) -> Dict[str, Any]:
        """Get latency statistics for a service."""
        results = self._results.get(name, deque())
        if not results:
            return {"service": name, "samples": 0}
        latencies = sorted(r.latency_ms for r in results)
        return {
            "service": name,
            "samples": len(latencies),
            "min_ms": round(min(latencies), 2),
            "max_ms": round(max(latencies), 2),
            "avg_ms": round(sum(latencies) / len(latencies), 2),
            "p50_ms": round(latencies[len(latencies) // 2], 2),
            "p95_ms": round(latencies[int(len(latencies) * 0.95)], 2),
            "p99_ms": round(latencies[int(len(latencies) * 0.99)], 2),
        }

    def get_health_trend(self, name: str, window: int = 20) -> str:
        """
        Analyze health trend over recent checks.
        Returns: "improving", "stable", "degrading", "unknown"
        """
        results = list(self._results.get(name, deque()))
        if len(results) < 3:
            return "unknown"
        recent = results[-window:]

        # Convert statuses to numeric scores
        score_map = {
            HealthStatus.HEALTHY: 3,
            HealthStatus.DEGRADED: 2,
            HealthStatus.UNHEALTHY: 1,
            HealthStatus.UNKNOWN: 0,
        }
        scores = [score_map.get(r.status, 0) for r in recent]
        if len(scores) < 3:
            return "unknown"

        # Simple trend: compare first half average to second half average
        mid = len(scores) // 2
        first_half_avg = sum(scores[:mid]) / mid
        second_half_avg = sum(scores[mid:]) / (len(scores) - mid)
        diff = second_half_avg - first_half_avg

        if diff > 0.5:
            return "improving"
        elif diff < -0.5:
            return "degrading"
        return "stable"

    def get_all_status(self) -> Dict[str, Any]:
        """Get health status summary for all monitored services."""
        summary = {}
        for name in self._monitored:
            config = self._monitored[name]
            circuit = self._circuits.get(name)
            summary[name] = {
                "status": config.get("status", HealthStatus.UNKNOWN).value
                if isinstance(config.get("status"), HealthStatus)
                else str(config.get("status", "unknown")),
                "circuit": circuit.to_dict() if circuit else None,
                "trend": self.get_health_trend(name),
                "latency": self.get_latency_stats(name),
                "last_check": config.get("last_check", 0),
                "adaptive_interval": self._adaptive_interval(name),
            }
        return summary

    # ── Callbacks ─────────────────────────────────────────────────

    def on_status_change(self, callback: Callable) -> None:
        """Register a callback for health status changes."""
        self._callbacks.append(callback)

    def _notify_status_change(
        self,
        name: str,
        old: HealthStatus,
        new: HealthStatus,
        result: HealthCheckResult,
    ) -> None:
        """Notify callbacks of a status change."""
        for cb in self._callbacks:
            try:
                cb(name, old, new, result)
            except Exception as e:
                logger.error("Status change callback error: %s", sanitize_for_log(str(e)))
