"""
Circuit Breaker — Failure detection and recovery
==================================================
Ported from @trancendos/service-mesh CircuitBreaker class.

Implements the circuit breaker pattern with three states:
- CLOSED: Normal operation — requests flow through
- OPEN: Failures detected — requests are rejected
- HALF_OPEN: Testing recovery — limited requests allowed

Zero-cost: Pure Python, no external dependencies.
"""

from __future__ import annotations

import logging
import random
from datetime import datetime, timezone

from src.mesh.types import (
    CircuitBreakerConfig,
    CircuitBreakerState,
    CircuitState,
    DEFAULT_CIRCUIT_BREAKER_CONFIG,
)

logger = logging.getLogger("tranc3.mesh.circuit_breaker")


class CircuitBreaker:
    """
    Circuit breaker for a single service.

    Tracks successes and failures, automatically opens when failures
    exceed the threshold, and allows controlled recovery through
    the half-open state.

    Usage:
        cb = CircuitBreaker("auth-api")
        if cb.can_execute():
            try:
                result = await call_service()
                cb.record_success()
            except Exception:
                cb.record_failure()
    """

    def __init__(
        self,
        service_name: str,
        config: CircuitBreakerConfig | None = None,
    ) -> None:
        self.service_name = service_name
        self.config = config or DEFAULT_CIRCUIT_BREAKER_CONFIG
        self._state = CircuitBreakerState()

    @property
    def state(self) -> CircuitState:
        """Current circuit state (auto-transitions open → half-open if timeout elapsed)."""
        if self._state.state == CircuitState.OPEN:
            if self._should_transition_to_half_open():
                self._transition(CircuitState.HALF_OPEN)
        return self._state.state

    def can_execute(self) -> bool:
        """Check if a request is allowed through the circuit breaker."""
        current = self.state  # Access via property to trigger auto-transition

        if current == CircuitState.CLOSED:
            return True

        if current == CircuitState.OPEN:
            return False

        if current == CircuitState.HALF_OPEN:
            # Allow a percentage of requests through
            return random.random() * 100 < self.config.half_open_request_percentage

        return False

    def record_success(self) -> None:
        """Record a successful execution."""
        self._state.success_count += 1
        self._state.last_success_at = datetime.now(timezone.utc)

        if self._state.state == CircuitState.HALF_OPEN:
            self._state.half_open_attempts += 1
            if self._state.half_open_attempts >= self.config.half_open_success_threshold:
                self._transition(CircuitState.CLOSED)
        elif self._state.state == CircuitState.CLOSED:
            # Reset failure count on success
            self._state.failure_count = 0

    def record_failure(self) -> None:
        """Record a failed execution."""
        self._state.failure_count += 1
        self._state.last_failure_at = datetime.now(timezone.utc)

        if self._state.state == CircuitState.HALF_OPEN:
            # Any failure in half-open goes back to open
            self._transition(CircuitState.OPEN)
        elif self._state.state == CircuitState.CLOSED:
            if self._state.failure_count >= self.config.failure_threshold:
                self._transition(CircuitState.OPEN)

    def get_state(self) -> CircuitBreakerState:
        """Get current circuit breaker state (snapshot)."""
        # Trigger auto-transition check
        _ = self.state
        return self._state.model_copy()

    def reset(self) -> None:
        """Force reset to closed state."""
        self._transition(CircuitState.CLOSED)
        self._state.failure_count = 0
        self._state.success_count = 0
        self._state.half_open_attempts = 0

    # ── Private ──────────────────────────────────────────────

    def _should_transition_to_half_open(self) -> bool:
        """Check if an open circuit should transition to half-open."""
        if self._state.opened_at is None:
            return False
        now = datetime.now(timezone.utc)
        elapsed_ms = (now - self._state.opened_at).total_seconds() * 1000
        return elapsed_ms >= self.config.reset_timeout_ms

    def _transition(self, new_state: CircuitState) -> None:
        """Transition to a new circuit state."""
        old_state = self._state.state
        self._state.state = new_state

        if new_state == CircuitState.OPEN:
            self._state.opened_at = datetime.now(timezone.utc)
            self._state.half_open_attempts = 0
        elif new_state == CircuitState.CLOSED:
            self._state.failure_count = 0
            self._state.half_open_attempts = 0
            self._state.opened_at = None
        elif new_state == CircuitState.HALF_OPEN:
            self._state.half_open_attempts = 0

        logger.info(
            "circuit_breaker_state_transition",
            extra={
                "service": self.service_name,
                "from_state": old_state.value,
                "to_state": new_state.value,
            },
        )
