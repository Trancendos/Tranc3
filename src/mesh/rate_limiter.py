"""
Rate Limiter — Three strategies for request throttling
=======================================================
Provides multiple rate limiting strategies that are thread-safe and
suitable for cross-thread use in FastAPI / concurrent workloads.

Ported from: @trancendos/kernel resilience/rate-limiter.ts (infinity-adminOS)
Zero-cost: Pure Python stdlib. No external dependencies.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Literal


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_ms: int  # ms until current window resets
    retry_after_ms: int  # ms to wait before retrying (0 if allowed)


class TokenBucketLimiter:
    """
    Token-bucket rate limiter.

    Tokens refill continuously at ``max_requests / window_ms`` tokens/ms.
    An optional ``burst_capacity`` lets the bucket hold more tokens than
    the per-window limit (default: same as ``max_requests``).
    """

    def __init__(
        self,
        name: str,
        max_requests: int,
        window_ms: int,
        burst_capacity: int | None = None,
    ) -> None:
        self.name = name
        self.max_requests = max_requests
        self.window_ms = window_ms
        self.burst_capacity = burst_capacity if burst_capacity is not None else max_requests
        self._buckets: dict[str, dict] = {}
        self._lock = threading.Lock()

    def consume(self, key: str = "default", tokens: int = 1) -> RateLimitResult:
        now_ms = int(time.monotonic() * 1000)
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = {"tokens": float(self.burst_capacity), "last_refill": now_ms}
                self._buckets[key] = bucket

            elapsed = now_ms - bucket["last_refill"]
            refill_rate = self.max_requests / self.window_ms  # tokens per ms
            bucket["tokens"] = min(
                float(self.burst_capacity),
                bucket["tokens"] + elapsed * refill_rate,
            )
            bucket["last_refill"] = now_ms

            allowed = bucket["tokens"] >= tokens
            if allowed:
                bucket["tokens"] -= tokens
                retry_after = 0
            else:
                deficit = tokens - bucket["tokens"]
                retry_after = int(deficit / refill_rate) if refill_rate > 0 else self.window_ms

            remaining = max(0, int(bucket["tokens"]))
            return RateLimitResult(
                allowed=allowed,
                remaining=remaining,
                reset_ms=0,  # token bucket has no hard reset
                retry_after_ms=retry_after if not allowed else 0,
            )

    def reset(self, key: str = "default") -> None:
        with self._lock:
            self._buckets.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._buckets.clear()


class SlidingWindowLimiter:
    """
    Sliding-window rate limiter.

    Tracks individual request timestamps in a deque and evicts expired
    entries on each call.  Provides precise per-window rate limiting.
    """

    def __init__(self, name: str, max_requests: int, window_ms: int) -> None:
        self.name = name
        self.max_requests = max_requests
        self.window_ms = window_ms
        self._windows: dict[str, deque] = {}
        self._lock = threading.Lock()

    def consume(self, key: str = "default") -> RateLimitResult:
        now_ms = int(time.monotonic() * 1000)
        window_start = now_ms - self.window_ms

        with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()
            ts_deque = self._windows[key]

            # Evict expired timestamps
            while ts_deque and ts_deque[0] <= window_start:
                ts_deque.popleft()

            allowed = len(ts_deque) < self.max_requests
            if allowed:
                ts_deque.append(now_ms)

            remaining = max(0, self.max_requests - len(ts_deque))
            oldest = ts_deque[0] if ts_deque else now_ms
            reset_ms = max(0, oldest + self.window_ms - now_ms)
            retry_after_ms = reset_ms if not allowed else 0

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_ms=reset_ms,
            retry_after_ms=retry_after_ms,
        )

    def reset(self, key: str = "default") -> None:
        with self._lock:
            self._windows.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._windows.clear()


class FixedWindowLimiter:
    """
    Fixed-window rate limiter.

    Simple counter that resets when the window expires.  Lightweight but
    susceptible to boundary bursts (requests pile up at window edges).
    """

    def __init__(self, name: str, max_requests: int, window_ms: int) -> None:
        self.name = name
        self.max_requests = max_requests
        self.window_ms = window_ms
        self._counters: dict[str, dict] = {}
        self._lock = threading.Lock()

    def consume(self, key: str = "default") -> RateLimitResult:
        now_ms = int(time.monotonic() * 1000)

        with self._lock:
            counter = self._counters.get(key)
            if counter is None or now_ms - counter["window_start"] >= self.window_ms:
                counter = {"count": 0, "window_start": now_ms}
                self._counters[key] = counter

            allowed = counter["count"] < self.max_requests
            if allowed:
                counter["count"] += 1

            remaining = max(0, self.max_requests - counter["count"])
            reset_ms = max(0, counter["window_start"] + self.window_ms - now_ms)
            retry_after_ms = reset_ms if not allowed else 0

        return RateLimitResult(
            allowed=allowed,
            remaining=remaining,
            reset_ms=reset_ms,
            retry_after_ms=retry_after_ms,
        )

    def reset(self, key: str = "default") -> None:
        with self._lock:
            self._counters.pop(key, None)

    def reset_all(self) -> None:
        with self._lock:
            self._counters.clear()


# ── Factory ──────────────────────────────────────────────────────────────────

_StrategyType = Literal["token-bucket", "sliding-window", "fixed-window"]


def create_rate_limiter(
    strategy: _StrategyType,
    name: str,
    max_requests: int,
    window_ms: int,
    burst_capacity: int | None = None,
) -> TokenBucketLimiter | SlidingWindowLimiter | FixedWindowLimiter:
    """
    Factory for creating a rate limiter with the given *strategy*.

    Args:
        strategy: One of ``'token-bucket'``, ``'sliding-window'``, ``'fixed-window'``.
        name: Logical name used in metrics and logs.
        max_requests: Maximum requests per *window_ms*.
        window_ms: Window duration in milliseconds.
        burst_capacity: Only used by ``'token-bucket'`` — max bucket size.
    """
    if strategy == "token-bucket":
        return TokenBucketLimiter(
            name=name,
            max_requests=max_requests,
            window_ms=window_ms,
            burst_capacity=burst_capacity,
        )
    if strategy == "sliding-window":
        return SlidingWindowLimiter(name=name, max_requests=max_requests, window_ms=window_ms)
    if strategy == "fixed-window":
        return FixedWindowLimiter(name=name, max_requests=max_requests, window_ms=window_ms)
    raise ValueError(f"Unknown rate limiter strategy: {strategy!r}")


__all__ = [
    "FixedWindowLimiter",
    "RateLimitResult",
    "SlidingWindowLimiter",
    "TokenBucketLimiter",
    "create_rate_limiter",
]
