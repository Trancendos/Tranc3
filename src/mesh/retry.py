"""
Retry with Exponential Backoff — Resilient execution with configurable retry logic
==================================================================================
Provides configurable retry logic with exponential backoff, jitter,
and customisable retry conditions for both async and sync callers.

Ported from: @trancendos/kernel resilience/retry.ts (infinity-adminOS)
Zero-cost: Pure Python stdlib. No external dependencies.
"""

from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted."""

    def __init__(self, message: str, last_error: Exception, attempts: int) -> None:
        super().__init__(message)
        self.last_error = last_error
        self.attempts = attempts


@dataclass
class RetryPolicy:
    """Configuration for retry behaviour.

    Attributes:
        max_attempts: Total attempts (first try + retries). Default 3.
        initial_delay_ms: Base delay before first retry in ms. Default 100.
        max_delay_ms: Cap on computed delay in ms. Default 30 000.
        backoff_multiplier: Exponential growth factor. Default 2.0.
        jitter: Full jitter — randomise delay in [0, computed_delay]. Default True.
        retryable_exceptions: Only retry on these exception types. Default (Exception,).
        on_retry: Optional callback(attempt, exc, delay_s) called before each retry.
    """

    max_attempts: int = 3
    initial_delay_ms: float = 100.0
    max_delay_ms: float = 30_000.0
    backoff_multiplier: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple = field(default_factory=lambda: (Exception,))
    on_retry: Optional[Callable[[int, Exception, float], None]] = None

    def _compute_delay(self, attempt: int) -> float:
        """Return delay in seconds for the given attempt index (0-based)."""
        delay_ms = self.initial_delay_ms * (self.backoff_multiplier**attempt)
        delay_ms = min(delay_ms, self.max_delay_ms)
        if self.jitter:
            delay_ms = random.uniform(0, delay_ms)
        return delay_ms / 1000.0


async def with_retry(coro_fn: Callable[[], Any], policy: RetryPolicy) -> Any:
    """Execute *coro_fn()* with retry logic defined by *policy*.

    ``coro_fn`` must be a zero-argument callable that returns a coroutine.

    Raises:
        RetryExhaustedError: when all attempts are exhausted.
        Exception: immediately if the exception is not in ``retryable_exceptions``.
    """
    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(policy.max_attempts):
        try:
            return await coro_fn()
        except policy.retryable_exceptions as exc:
            last_error = exc
            if attempt >= policy.max_attempts - 1:
                break
            delay = policy._compute_delay(attempt)
            if policy.on_retry:
                policy.on_retry(attempt + 1, exc, delay)
            await asyncio.sleep(delay)
        except Exception:
            raise  # Non-retryable exception — propagate immediately

    raise RetryExhaustedError(
        f"All {policy.max_attempts} attempt(s) exhausted",
        last_error=last_error,
        attempts=policy.max_attempts,
    )


def with_retry_sync(fn: Callable[[], Any], policy: RetryPolicy) -> Any:
    """Synchronous version of :func:`with_retry`.

    ``fn`` must be a zero-argument callable.

    Raises:
        RetryExhaustedError: when all attempts are exhausted.
        Exception: immediately if the exception is not in ``retryable_exceptions``.
    """
    last_error: Exception = RuntimeError("No attempts made")

    for attempt in range(policy.max_attempts):
        try:
            return fn()
        except policy.retryable_exceptions as exc:
            last_error = exc
            if attempt >= policy.max_attempts - 1:
                break
            delay = policy._compute_delay(attempt)
            if policy.on_retry:
                policy.on_retry(attempt + 1, exc, delay)
            time.sleep(delay)
        except Exception:
            raise

    raise RetryExhaustedError(
        f"All {policy.max_attempts} attempt(s) exhausted",
        last_error=last_error,
        attempts=policy.max_attempts,
    )


__all__ = [
    "RetryExhaustedError",
    "RetryPolicy",
    "with_retry",
    "with_retry_sync",
]
