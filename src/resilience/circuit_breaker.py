# src/resilience/circuit_breaker.py
# Circuit breaker and bulkhead patterns for nanoservice resilience

import asyncio
import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing — reject requests
    HALF_OPEN = "half_open" # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


class CircuitBreaker:
    """
    Circuit breaker for protecting services from cascading failures.
    Tracks failure rates and opens the circuit when threshold is exceeded.
    Automatically attempts recovery after a timeout period.
    """

    def __init__(
        self,
        name: str,
        config: Optional[CircuitBreakerConfig] = None,
    ):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._total_calls = 0
        self._total_failures = 0

    def can_execute(self) -> bool:
        """Check if a request can be executed"""
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            # Check if recovery timeout has elapsed
            if self._last_failure_time and (
                time.time() - self._last_failure_time >= self.config.recovery_timeout
            ):
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
                logger.info(f"Circuit {self.name}: OPEN → HALF_OPEN")
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_calls < self.config.half_open_max_calls:
                self._half_open_calls += 1
                return True
            return False

        return False

    def record_success(self) -> None:
        """Record a successful call"""
        self._total_calls += 1

        if self.state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info(f"Circuit {self.name}: HALF_OPEN → CLOSED")
        else:
            self._failure_count = max(0, self._failure_count - 1)

    def record_failure(self) -> None:
        """Record a failed call"""
        self._total_calls += 1
        self._total_failures += 1
        self._failure_count += 1
        self._last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            logger.warning(f"Circuit {self.name}: HALF_OPEN → OPEN (failed during test)")
        elif self._failure_count >= self.config.failure_threshold:
            self.state = CircuitState.OPEN
            logger.warning(
                f"Circuit {self.name}: CLOSED → OPEN "
                f"({self._failure_count} failures >= {self.config.failure_threshold})"
            )

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Execute a function with circuit breaker protection"""
        if not self.can_execute():
            raise RuntimeError(
                f"Circuit breaker '{self.name}' is OPEN — requests rejected"
            )

        try:
            result = await fn(*args, **kwargs) if asyncio.iscoroutinefunction(fn) else fn(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

    @property
    def stats(self) -> Dict[str, Any]:
        """Get circuit breaker statistics"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "total_calls": self._total_calls,
            "total_failures": self._total_failures,
            "failure_rate": (
                self._total_failures / self._total_calls if self._total_calls > 0 else 0.0
            ),
        }


class Bulkhead:
    """
    Bulkhead pattern — limit concurrent calls to a service.
    Prevents resource exhaustion by capping parallelism.
    """

    def __init__(self, name: str, max_concurrent: int = 10, max_queue: int = 20):
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_semaphore = asyncio.Semaphore(max_concurrent + max_queue)
        self._active = 0
        self._queued = 0
        self._rejected = 0

    async def acquire(self) -> bool:
        """Acquire a slot. Returns False if queue is full."""
        if not self._queue_semaphore.locked():
            try:
                self._queued += 1
                await self._queue_semaphore.acquire()
                self._queued -= 1
                await self._semaphore.acquire()
                self._active += 1
                return True
            except Exception:
                self._rejected += 1
                return False
        else:
            self._rejected += 1
            return False

    def release(self) -> None:
        """Release a slot"""
        self._semaphore.release()
        self._queue_semaphore.release()
        self._active -= 1

    @property
    def stats(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "active": self._active,
            "queued": self._queued,
            "rejected": self._rejected,
        }


class ResilienceManager:
    """
    Manages circuit breakers and bulkheads for all services.
    Provides a unified interface for resilience patterns.
    """

    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._bulkheads: Dict[str, Bulkhead] = {}

    def get_breaker(self, name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        """Get or create a circuit breaker"""
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(name, config)
        return self._breakers[name]

    def get_bulkhead(self, name: str, max_concurrent: int = 10, max_queue: int = 20) -> Bulkhead:
        """Get or create a bulkhead"""
        if name not in self._bulkheads:
            self._bulkheads[name] = Bulkhead(name, max_concurrent, max_queue)
        return self._bulkheads[name]

    def health(self) -> Dict[str, Any]:
        """Get health status of all resilience components"""
        return {
            "circuit_breakers": {n: b.stats for n, b in self._breakers.items()},
            "bulkheads": {n: b.stats for n, b in self._bulkheads.items()},
        }


# Singleton
resilience = ResilienceManager()