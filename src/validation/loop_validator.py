# src/validation/loop_validator.py
# FID: TRANC3-VAL-001 | Version: 1.0.0 | Module: validation
# Loop validation, infinite loop detection, and self-healing circuit breakers

import asyncio
import functools
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict

from shared_core.error_handlers import safe_error_detail
from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ── Circuit Breaker ───────────────────────────────────────────────────────────


class CircuitState:
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing — reject calls
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """
    Circuit breaker pattern — prevents cascade failures.
    Opens after threshold failures, auto-recovers after timeout.
    """

    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    success_threshold: int = 2

    _state: str = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_count: int = field(default=0, init=False)
    _last_failure: float = field(default=0.0, init=False)

    @property
    def state(self) -> str:
        if self._state == CircuitState.OPEN:
            if time.time() - self._last_failure > self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(
                    "Circuit %s: OPEN → HALF_OPEN (testing recovery)", sanitize_for_log(self.name)
                )  # codeql[py/cleartext-logging]
        return self._state

    def call(self, func: Callable, *args, fallback=None, **kwargs):
        if self.state == CircuitState.OPEN:
            logger.warning(
                "Circuit %s OPEN — using fallback", sanitize_for_log(self.name)
            )  # codeql[py/cleartext-logging]  # codeql[py/cleartext-logging]
            return fallback() if callable(fallback) else fallback

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            if callable(fallback):
                return fallback()
            raise
        return None

    async def async_call(self, func: Callable, *args, fallback=None, **kwargs):
        if self.state == CircuitState.OPEN:
            logger.warning("Circuit %s OPEN — using fallback", sanitize_for_log(self.name))
            return (
                await fallback()
                if asyncio.iscoroutinefunction(fallback)
                else (fallback() if callable(fallback) else fallback)
            )

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure(e)
            if asyncio.iscoroutinefunction(fallback):
                return await fallback()
            if callable(fallback):
                return fallback()
            raise
        return None

    def _on_success(self):
        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                self._success_count = 0
                logger.info(
                    "Circuit %s: HALF_OPEN → CLOSED (recovered)", sanitize_for_log(self.name)
                )  # codeql[py/cleartext-logging]
        else:
            self._failure_count = 0

    def _on_failure(self, error: Exception):
        self._failure_count += 1
        self._last_failure = time.time()
        logger.warning(
            "Circuit %s: failure %s/%s — %s",
            sanitize_for_log(self.name),
            sanitize_for_log(self._failure_count),
            sanitize_for_log(self.failure_threshold),
            sanitize_for_log(error),
        )
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.error(
                "Circuit %s: CLOSED → OPEN (too many failures)", sanitize_for_log(self.name)
            )  # codeql[py/cleartext-logging]

    def get_status(self) -> Dict:
        return {
            "name": self.name,
            "state": self.state,
            "failure_count": self._failure_count,
            "last_failure": self._last_failure,
        }


# ── Loop Validator ────────────────────────────────────────────────────────────


class LoopValidator:
    """
    Detects and breaks infinite loops in:
    - Evolution cycles
    - Consciousness stream processing
    - Swarm consensus rounds
    - Retry loops
    """

    def __init__(self):
        self._counters: Dict[str, int] = defaultdict(int)
        self._history: Dict[str, deque] = defaultdict(lambda: deque(maxlen=100))
        self._limits: Dict[str, int] = {
            "evolution_cycle": 1000,
            "consciousness_stream": 10000,
            "swarm_consensus": 50,
            "retry_loop": 10,
            "tokenizer_encode": 5,
            "db_retry": 3,
            "quantum_circuit": 100,
            "default": 500,
        }

    def check(self, loop_id: str, context: str = "default") -> bool:
        """
        Returns True if loop should continue, False if limit exceeded.
        Call at the top of every loop body.
        """
        key = f"{loop_id}:{context}"
        limit = self._limits.get(context, self._limits["default"])
        self._counters[key] += 1
        count = self._counters[key]

        if count > limit:
            logger.error(
                "LOOP_VALIDATOR: Loop '%s' exceeded limit %s — breaking",
                sanitize_for_log(key),
                sanitize_for_log(limit),
            )
            return False

        if count > limit * 0.9:
            logger.warning(
                "LOOP_VALIDATOR: Loop '%s' at %s/%s — approaching limit",
                sanitize_for_log(key),
                sanitize_for_log(count),
                sanitize_for_log(limit),
            )

        return True

    def reset(self, loop_id: str, context: str = "default"):
        key = f"{loop_id}:{context}"
        self._counters[key] = 0

    def record_value(self, loop_id: str, value: Any):
        """Record a value to detect stagnation (same value repeating)."""
        self._history[loop_id].append(str(value)[:64])
        history = list(self._history[loop_id])
        if len(history) >= 10 and len(set(history[-10:])) == 1:
            logger.warning(
                "LOOP_VALIDATOR: Stagnation detected in '%s' — value unchanged for 10 iterations",
                sanitize_for_log(loop_id),
            )
            return False
        return True

    def get_stats(self) -> Dict:
        return {k: v for k, v in self._counters.items() if v > 0}


# ── Retry with Backoff ────────────────────────────────────────────────────────


def with_retry(max_attempts: int = 3, backoff: float = 1.0, exceptions=(Exception,)):
    """Decorator: retry with exponential backoff. Validates loop count."""

    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            validator = LoopValidator()
            for attempt in range(1, max_attempts + 1):
                if not validator.check(func.__name__, "retry_loop"):
                    raise RuntimeError(f"Retry loop exceeded for {func.__name__}")
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts:
                        raise
                    wait = backoff * (2 ** (attempt - 1))
                    logger.warning(
                        "Retry %s/%s for %s: %s — waiting %ss",
                        sanitize_for_log(attempt),
                        sanitize_for_log(max_attempts),
                        sanitize_for_log(func.__name__),
                        sanitize_for_log(e),
                        sanitize_for_log(wait),
                    )
                    time.sleep(wait)

            # Should not reach here — either returned or raised
            return None  # type: ignore[unreachable]

        return wrapper

    return decorator


# ── Self-Healing Actions ──────────────────────────────────────────────────────


class SelfHealer:
    """
    Registers and executes self-healing actions triggered by error codes.
    """

    def __init__(self):
        self._actions: Dict[str, Callable] = {}
        self._history: deque = deque(maxlen=100)

    def register(self, action_name: str, handler: Callable):
        self._actions[action_name] = handler
        logger.info(
            "SelfHealer: registered action '%s'", sanitize_for_log(action_name)
        )  # codeql[py/cleartext-logging]

    def heal(self, action_name: str, context: Dict = None) -> Dict:
        handler = self._actions.get(action_name)
        if not handler:
            return {"healed": False, "reason": f"No handler for '{action_name}'"}
        try:
            result = handler(context or {})
            self._history.append({"action": action_name, "time": time.time(), "result": "success"})
            logger.info(
                "SelfHealer: '%s' executed successfully", sanitize_for_log(action_name)
            )  # codeql[py/cleartext-logging]
            return {"healed": True, "action": action_name, "result": result}
        except Exception as e:
            self._history.append(
                {"action": action_name, "time": time.time(), "result": f"failed: {e}"}
            )
            logger.error(
                "SelfHealer: '%s' failed: %s", sanitize_for_log(action_name), sanitize_for_log(e)
            )  # codeql[py/cleartext-logging]
            return {"healed": False, "action": action_name, "error": safe_error_detail(e, 500)}

    def get_history(self) -> list:
        return list(self._history)


# ── Global Circuit Breakers ───────────────────────────────────────────────────
CIRCUITS: Dict[str, CircuitBreaker] = {
    "model_inference": CircuitBreaker("model_inference", failure_threshold=5, recovery_timeout=30),
    "quantum_attention": CircuitBreaker(
        "quantum_attention", failure_threshold=3, recovery_timeout=10
    ),
    "consciousness_phi": CircuitBreaker(
        "consciousness_phi", failure_threshold=5, recovery_timeout=15
    ),
    "database_write": CircuitBreaker("database_write", failure_threshold=3, recovery_timeout=60),
    "redis_ops": CircuitBreaker("redis_ops", failure_threshold=5, recovery_timeout=30),
    "stripe_api": CircuitBreaker("stripe_api", failure_threshold=3, recovery_timeout=120),
    "evolution_cycle": CircuitBreaker("evolution_cycle", failure_threshold=10, recovery_timeout=60),
}

# Singletons
loop_validator = LoopValidator()
self_healer = SelfHealer()
