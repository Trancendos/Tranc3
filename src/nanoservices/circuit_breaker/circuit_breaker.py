"""Circuit Breaker Mesh — Phase 12

Inter-service fault tolerance with circuit breaker pattern,
bulkhead isolation, and adaptive threshold management.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"          # Normal operation
    OPEN = "open"              # Failing — reject requests
    HALF_OPEN = "half_open"    # Testing recovery


class FailureType(Enum):
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    SERVICE_ERROR = "service_error"
    RATE_LIMIT = "rate_limit"
    CIRCUIT_OPEN = "circuit_open"


@dataclass
class CircuitConfig:
    service_name: str
    failure_threshold: int = 5
    success_threshold: int = 3
    timeout_seconds: float = 30.0
    half_open_max_calls: int = 3
    window_seconds: float = 60.0
    slow_call_duration_seconds: float = 5.0
    slow_call_rate_threshold: float = 0.5


@dataclass
class CircuitMetrics:
    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    slow_calls: int = 0
    rejected_calls: int = 0
    last_failure_time: float = 0.0
    last_success_time: float = 0.0
    consecutive_failures: int = 0
    consecutive_successes: int = 0
    window_start: float = field(default_factory=time.time)
    window_failures: int = 0


class CircuitBreaker:
    """Individual circuit breaker for a single service dependency."""

    def __init__(self, config: CircuitConfig):
        self._config = config
        self._state = CircuitState.CLOSED
        self._metrics = CircuitMetrics()
        self._state_changed_at: float = time.time()
        self._half_open_calls: int = 0
        self._fallback: Optional[Callable] = None
        self._listeners: List[Callable[[CircuitState, CircuitState], None]] = []

    @property
    def state(self) -> CircuitState:
        # Auto-transition from OPEN to HALF_OPEN after timeout
        if self._state == CircuitState.OPEN:
            if time.time() - self._state_changed_at >= self._config.timeout_seconds:
                self._transition(CircuitState.HALF_OPEN)
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        return self._metrics

    @property
    def service_name(self) -> str:
        return self._config.service_name

    def set_fallback(self, fallback: Callable) -> None:
        self._fallback = fallback

    def add_state_listener(self, listener: Callable[[CircuitState, CircuitState], None]) -> None:
        self._listeners.append(listener)

    def allow_request(self) -> bool:
        current = self.state
        if current == CircuitState.CLOSED:
            return True
        if current == CircuitState.HALF_OPEN:
            if self._half_open_calls < self._config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False
        # OPEN — reject
        self._metrics.rejected_calls += 1
        return False

    def record_success(self, duration: float = 0.0) -> None:
        self._metrics.total_calls += 1
        self._metrics.successful_calls += 1
        self._metrics.consecutive_failures = 0
        self._metrics.consecutive_successes += 1
        self._metrics.last_success_time = time.time()

        if duration > self._config.slow_call_duration_seconds:
            self._metrics.slow_calls += 1

        if self._state == CircuitState.HALF_OPEN:
            if self._metrics.consecutive_successes >= self._config.success_threshold:
                self._transition(CircuitState.CLOSED)

        self._check_window()

    def record_failure(self, failure_type: FailureType = FailureType.SERVICE_ERROR) -> None:
        self._metrics.total_calls += 1
        self._metrics.failed_calls += 1
        self._metrics.consecutive_successes = 0
        self._metrics.consecutive_failures += 1
        self._metrics.last_failure_time = time.time()
        self._metrics.window_failures += 1

        if self._state == CircuitState.HALF_OPEN:
            self._transition(CircuitState.OPEN)
        elif self._state == CircuitState.CLOSED:
            if self._metrics.consecutive_failures >= self._config.failure_threshold:
                self._transition(CircuitState.OPEN)

        self._check_window()

    def _check_window(self) -> None:
        now = time.time()
        if now - self._metrics.window_start > self._config.window_seconds:
            # Check slow call rate
            if self._metrics.total_calls > 0:
                slow_rate = self._metrics.slow_calls / self._metrics.total_calls
                if slow_rate > self._config.slow_call_rate_threshold and self._state == CircuitState.CLOSED:
                    self._transition(CircuitState.OPEN)
            # Reset window
            self._metrics.window_start = now
            self._metrics.window_failures = 0
            self._metrics.slow_calls = 0

    def _transition(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        self._state_changed_at = time.time()
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._metrics.consecutive_successes = 0

        logger.info("Circuit %s: %s → %s", self._config.service_name, old_state.value, new_state.value)
        for listener in self._listeners:
            try:
                listener(old_state, new_state)
            except Exception:
                pass

    def execute(self, func: Callable, *args: Any, **kwargs: Any) -> Any:
        if not self.allow_request():
            if self._fallback:
                return self._fallback(*args, **kwargs)
            raise Exception(f"Circuit open for {self._config.service_name}")

        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start
            self.record_success(duration)
            return result
        except Exception:
            self.record_failure()
            if self._fallback:
                return self._fallback(*args, **kwargs)
            raise


class CircuitBreakerMesh:
    """Mesh of circuit breakers managing inter-service communication."""

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._global_listeners: List[Callable] = []

    def register(self, config: CircuitConfig) -> CircuitBreaker:
        if config.service_name in self._breakers:
            return self._breakers[config.service_name]
        breaker = CircuitBreaker(config)
        self._breakers[config.service_name] = breaker
        breaker.add_state_listener(self._on_state_change)
        logger.info("Registered circuit breaker for %s", config.service_name)
        return breaker

    def get(self, service_name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(service_name)

    def get_or_create(self, service_name: str) -> CircuitBreaker:
        if service_name not in self._breakers:
            self.register(CircuitConfig(service_name=service_name))
        return self._breakers[service_name]

    def _on_state_change(self, old: CircuitState, new: CircuitState) -> None:
        for listener in self._global_listeners:
            try:
                listener(old, new)
            except Exception:
                pass

    def get_mesh_status(self) -> Dict[str, Dict[str, Any]]:
        status = {}
        for name, breaker in self._breakers.items():
            m = breaker.metrics
            status[name] = {
                "state": breaker.state.value,
                "total_calls": m.total_calls,
                "successful_calls": m.successful_calls,
                "failed_calls": m.failed_calls,
                "rejected_calls": m.rejected_calls,
                "consecutive_failures": m.consecutive_failures,
            }
        return status

    def reset_all(self) -> None:
        for breaker in self._breakers.values():
            if breaker.state != CircuitState.CLOSED:
                breaker._transition(CircuitState.CLOSED)
        logger.info("All circuits reset to CLOSED")

    def trip(self, service_name: str) -> bool:
        breaker = self._breakers.get(service_name)
        if breaker:
            breaker._transition(CircuitState.OPEN)
            return True
        return False
