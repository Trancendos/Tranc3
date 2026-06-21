"""
Rate Limiter — Unified adaptive rate limiting for the Trancendos platform
=========================================================================
Consolidates all rate-limiting strategies into one canonical module:

  • TokenBucketLimiter     — continuous token refill, burst-friendly
  • SlidingWindowLimiter   — precise per-window tracking
  • FixedWindowLimiter     — lightweight counter, resets on window edge
  • AdaptiveRateLimiter    — IAM-tier-aware, DDoS-aware, self-tuning
  • RateLimitMiddleware     — FastAPI middleware with X-RateLimit-* headers
  • AdaptiveRateLimiterMiddleware — lightweight DDoS-oriented middleware
  • get_limiter()           — module-level singleton

Ported from:
  • @trancendos/kernel resilience/rate-limiter.ts (infinity-adminOS)
  • the-citadel/src/middleware/resilience-layer.ts
  • RSK-007 DDoS mitigation spec

Zero-cost: pure Python stdlib + starlette (already required by FastAPI).
No Redis, no external store.
"""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable, Dict, Literal, Optional, Tuple

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Shared result type
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RateLimitResult:
    allowed: bool
    remaining: int
    reset_ms: int  # ms until current window resets
    retry_after_ms: int  # ms to wait before retrying (0 if allowed)


# ─────────────────────────────────────────────────────────────────────────────
# Basic strategy limiters (thread-safe, sync)
# ─────────────────────────────────────────────────────────────────────────────


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
    entries on each call. Provides precise per-window rate limiting.
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

    Simple counter that resets when the window expires. Lightweight but
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


# ─────────────────────────────────────────────────────────────────────────────
# Factory
# ─────────────────────────────────────────────────────────────────────────────

_StrategyType = Literal["token-bucket", "sliding-window", "fixed-window"]


def create_rate_limiter(
    strategy: _StrategyType,
    name: str,
    max_requests: int,
    window_ms: int,
    burst_capacity: int | None = None,
) -> TokenBucketLimiter | SlidingWindowLimiter | FixedWindowLimiter:
    """Factory for creating a rate limiter with the given *strategy*."""
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


# ─────────────────────────────────────────────────────────────────────────────
# Self-tuning per-tenant bucket (from src/core/adaptive_rate_limiter.py)
# ─────────────────────────────────────────────────────────────────────────────


class _TenantBucket:
    """
    Token bucket + sliding window for a single tenant with self-tuning.

    Auto-tunes the effective rate:
      - Tightens 20% when error_rate > 10%
      - Loosens 10% when error_rate < 1% (after 5min grace)
    """

    def __init__(self, rate: int, window_seconds: int, burst_multiplier: float) -> None:
        self.rate = rate
        self.window_seconds = window_seconds
        self.burst_multiplier = burst_multiplier

        self._tokens = float(rate)
        self._max_tokens = rate * burst_multiplier
        self._last_refill = time.monotonic()

        self._window: deque = deque()
        self._errors: deque = deque()
        self._successes: deque = deque()

        self._effective_rate = float(rate)
        self._last_tune = time.monotonic()
        self._tune_interval = 60.0

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        refill = elapsed * (self._effective_rate / self.window_seconds)
        self._tokens = min(self._max_tokens, self._tokens + refill)
        self._last_refill = now

    def _prune(self, now: float) -> None:
        cutoff = now - self.window_seconds
        while self._window and self._window[0] < cutoff:
            self._window.popleft()
        while self._errors and self._errors[0] < cutoff:
            self._errors.popleft()
        while self._successes and self._successes[0] < cutoff:
            self._successes.popleft()

    def allow(self) -> bool:
        now = time.monotonic()
        self._refill()
        self._prune(now)
        if self._tokens >= 1.0 and len(self._window) < int(self._effective_rate):
            self._tokens -= 1.0
            self._window.append(now)
            return True
        return False

    def record_error(self) -> None:
        self._errors.append(time.monotonic())
        self._maybe_tune()

    def record_success(self) -> None:
        self._successes.append(time.monotonic())
        self._maybe_tune()

    def _maybe_tune(self) -> None:
        now = time.monotonic()
        if now - self._last_tune < self._tune_interval:
            return
        self._last_tune = now
        self._adjust()

    def _adjust(self) -> None:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        error_count = sum(1 for t in self._errors if t > cutoff)
        success_count = sum(1 for t in self._successes if t > cutoff)
        total = error_count + success_count
        if total == 0:
            return
        error_rate = error_count / total
        if error_rate > 0.10:
            self._effective_rate = max(1.0, self._effective_rate * 0.80)
        elif error_rate < 0.01 and now - self._last_tune >= 300:
            max_rate = self.rate * 2.0
            self._effective_rate = min(max_rate, self._effective_rate * 1.10)

    def stats(self) -> Dict:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        return {
            "effective_rate": self._effective_rate,
            "tokens": self._tokens,
            "window_count": len(self._window),
            "error_count": sum(1 for t in self._errors if t > cutoff),
            "success_count": sum(1 for t in self._successes if t > cutoff),
        }


# ─────────────────────────────────────────────────────────────────────────────
# RateLimitConfig — IAM-tier multipliers (from shared_core/middleware)
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RateLimitConfig:
    """Configuration for the adaptive rate limiter."""

    window_seconds: int = 60
    max_requests: int = 100
    tier_multipliers: Dict[str, float] = field(
        default_factory=lambda: {
            "free": 1.0,
            "pro": 2.5,
            "prime": 5.0,
            "admin": 10.0,
            "service": 20.0,
        }
    )
    key_strategy: str = "jwt_sub_with_ip_fallback"
    cleanup_interval: int = 300
    max_entries: int = 100_000


# ─────────────────────────────────────────────────────────────────────────────
# Unified AdaptiveRateLimiter
# ─────────────────────────────────────────────────────────────────────────────

_DDOS_WINDOW_SECONDS = 60
_ADAPTIVE_THRESHOLD = 0.8  # tighten capacity when >80% global utilization


@dataclass
class _TokenBucket:
    """Simple token bucket used by the security/DDoS path."""

    capacity: float
    refill_rate: float  # tokens per second
    tokens: float = field(init=False)
    last_refill: float = field(init=False)

    def __post_init__(self) -> None:
        self.tokens = self.capacity
        self.last_refill = time.monotonic()

    def consume(self, tokens: float = 1.0) -> bool:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)
        self.last_refill = now
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    @property
    def utilization(self) -> float:
        return 1.0 - (self.tokens / self.capacity)


class AdaptiveRateLimiter:
    """
    Unified adaptive rate limiter combining:

    1. **Per-tenant self-tuning** — each tenant gets a ``_TenantBucket`` that
       auto-adjusts its effective rate based on observed error rates
       (tightens on >10% errors, loosens on <1% after a 5-min grace).

    2. **IAM-tier-aware limits** — ``check_request()`` reads the request's
       JWT state and applies tier multipliers (free/pro/prime/admin/service).

    3. **DDoS / IP blocking** — ``check()`` tracks global load and blocks IPs
       making >500 requests in 60s for 5 minutes.

    4. **Async-native request checking** — ``check_async()`` is safe for use
       inside FastAPI async request handlers.

    Usage:
        limiter = AdaptiveRateLimiter()
        allowed = limiter.check("user-123")              # tenant-based
        allowed, meta = limiter.check_ddos("key", ip)   # DDoS-aware
        allowed, remaining, limit, retry = await limiter.check_request(request)
    """

    def __init__(
        self,
        base_rate: int = 100,
        window_seconds: int = 60,
        burst_multiplier: float = 1.5,
        adaptive: bool = True,
        config: Optional[RateLimitConfig] = None,
    ) -> None:
        # Tenant self-tuning state
        self._base_rate = base_rate
        self._window = window_seconds
        self._burst = burst_multiplier
        self._tenant_buckets: Dict[str, _TenantBucket] = {}
        self._tenant_lock = threading.Lock()

        # DDoS / global load state
        self.default_rpm = base_rate
        self.adaptive = adaptive
        self._ddos_buckets: dict[str, _TokenBucket] = {}
        self._request_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._blocked_ips: dict[str, float] = {}
        self._global_load: deque = deque(maxlen=10000)

        # IAM-tier async state
        self._config = config or RateLimitConfig(
            window_seconds=window_seconds,
            max_requests=base_rate,
        )
        self._iam_store: Dict[str, "RateLimitEntry"] = {}
        self._iam_lock = asyncio.Lock() if asyncio._get_running_loop() is not None else None  # type: ignore[attr-defined]
        self._last_cleanup = time.time()

    # ── Tenant self-tuning API ────────────────────────────────────────────────

    def _get_tenant_bucket(self, tenant_id: str) -> _TenantBucket:
        with self._tenant_lock:
            if tenant_id not in self._tenant_buckets:
                self._tenant_buckets[tenant_id] = _TenantBucket(
                    self._base_rate, self._window, self._burst
                )
            return self._tenant_buckets[tenant_id]

    def check(self, tenant_id: str = "global") -> bool:
        """Returns True if the request is allowed (tenant-based, thread-safe)."""
        bucket = self._get_tenant_bucket(tenant_id)
        with self._tenant_lock:
            return bucket.allow()

    def record_error(self, tenant_id: str = "global") -> None:
        self._get_tenant_bucket(tenant_id).record_error()
        with self._tenant_lock:
            for b in self._tenant_buckets.values():
                b._adjust()

    def record_success(self, tenant_id: str = "global") -> None:
        self._get_tenant_bucket(tenant_id).record_success()

    def get_stats(self) -> Dict:
        with self._tenant_lock:
            return {tid: b.stats() for tid, b in self._tenant_buckets.items()}

    def reset(self, tenant_id: str = "global") -> None:
        with self._tenant_lock:
            self._tenant_buckets.pop(tenant_id, None)

    # ── DDoS / IP-aware API ──────────────────────────────────────────────────

    def _get_ddos_bucket(self, key: str) -> _TokenBucket:
        if key not in self._ddos_buckets:
            capacity = self.default_rpm * self._burst
            rate = self.default_rpm / 60.0
            self._ddos_buckets[key] = _TokenBucket(capacity=capacity, refill_rate=rate)
        return self._ddos_buckets[key]

    def _is_ip_blocked(self, ip: str) -> bool:
        until = self._blocked_ips.get(ip)
        if until and time.monotonic() < until:
            return True
        self._blocked_ips.pop(ip, None)
        return False

    def _global_utilization(self) -> float:
        now = time.monotonic()
        recent = sum(1 for t in self._global_load if now - t < _DDOS_WINDOW_SECONDS)
        total_capacity = self.default_rpm * max(1, len(self._ddos_buckets))
        return recent / total_capacity if total_capacity > 0 else 0.0

    def check_ddos(self, key: str, ip: str | None = None) -> tuple[bool, dict]:
        """DDoS-aware check. Returns (allowed, metadata)."""
        if ip and self._is_ip_blocked(ip):
            return False, {"reason": "ip_blocked", "retry_after": 60}

        bucket = self._get_ddos_bucket(key)
        effective_tokens = 1.0
        if self.adaptive:
            gl = self._global_utilization()
            if gl > _ADAPTIVE_THRESHOLD:
                effective_tokens = 1.0 + (gl - _ADAPTIVE_THRESHOLD) * 5

        allowed = bucket.consume(effective_tokens)
        now = time.monotonic()
        self._global_load.append(now)

        if ip:
            self._request_times[ip].append(now)
            recent = sum(1 for t in self._request_times[ip] if now - t < 60)
            if recent > 500:
                self._blocked_ips[ip] = now + 300
                logger.warning("DDoS pattern detected from %s — blocked 5min", ip)

        return allowed, {
            "allowed": allowed,
            "utilization": round(bucket.utilization, 3),
            "global_load": round(self._global_utilization(), 3),
            "tokens_remaining": round(bucket.tokens, 1),
        }

    def ddos_stats(self) -> dict:
        now = time.monotonic()
        return {
            "active_keys": len(self._ddos_buckets),
            "blocked_ips": len(self._blocked_ips),
            "global_rps": sum(1 for t in self._global_load if now - t < 1),
            "global_rpm": sum(1 for t in self._global_load if now - t < 60),
        }

    # ── IAM-tier async API ───────────────────────────────────────────────────

    def _get_client_key(self, request: "Request") -> str:  # type: ignore[name-defined]
        if self._config.key_strategy in ("jwt_sub", "jwt_sub_with_ip_fallback"):
            user = getattr(request.state, "user", None)
            if user and isinstance(user, dict) and user.get("sub"):
                return f"jwt:{user['sub']}"
        if self._config.key_strategy == "jwt_sub":
            return "anon"
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    def _get_user_tier(self, request: "Request") -> str:  # type: ignore[name-defined]
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict):
            return user.get("tier", "free")
        return "free"

    def _get_effective_limit(self, request: "Request") -> int:  # type: ignore[name-defined]
        tier = self._get_user_tier(request)
        multiplier = self._config.tier_multipliers.get(tier, 1.0)
        return int(self._config.max_requests * multiplier)

    async def _ensure_iam_lock(self) -> asyncio.Lock:
        if self._iam_lock is None:
            self._iam_lock = asyncio.Lock()
        return self._iam_lock

    async def check_request(self, request: "Request") -> Tuple[bool, int, int, int]:  # type: ignore[name-defined]
        """
        IAM-tier-aware async check for a FastAPI Request.

        Returns (allowed, remaining, limit, retry_after).
        """
        now = time.time()
        key = self._get_client_key(request)
        effective_limit = self._get_effective_limit(request)
        window_start = now - (now % self._config.window_seconds)

        lock = await self._ensure_iam_lock()
        async with lock:
            entry = self._iam_store.get(key)
            if not entry or entry.window_start != window_start:
                entry = RateLimitEntry(count=0, window_start=window_start)
                self._iam_store[key] = entry

            entry.count += 1

            if len(self._iam_store) > self._config.max_entries:
                sorted_keys = sorted(
                    self._iam_store.keys(), key=lambda k: self._iam_store[k].window_start
                )
                for k in sorted_keys[: len(sorted_keys) // 10]:
                    del self._iam_store[k]

            remaining = max(0, effective_limit - entry.count)
            window_ends_at = window_start + self._config.window_seconds
            retry_after = max(0, int(window_ends_at - now)) if entry.count > effective_limit else 0

            if now - self._last_cleanup >= self._config.cleanup_interval:
                cutoff = now - self._config.window_seconds
                stale = [k for k, v in self._iam_store.items() if v.window_start < cutoff]
                for k in stale:
                    del self._iam_store[k]
                self._last_cleanup = now

        return entry.count <= effective_limit, remaining, effective_limit, retry_after


# ─────────────────────────────────────────────────────────────────────────────
# Supplementary dataclass for IAM store entries
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class RateLimitEntry:
    count: int = 0
    window_start: float = 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Middleware
# ─────────────────────────────────────────────────────────────────────────────

try:
    from fastapi import HTTPException
    from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.types import ASGIApp

    class RateLimitMiddleware(BaseHTTPMiddleware):
        """
        FastAPI/Starlette middleware enforcing IAM-tier-aware rate limiting.

        Adds X-RateLimit-Limit, X-RateLimit-Remaining, X-RateLimit-Window headers.
        Skips /health, /metrics, /api/ecosystem/health.
        """

        _SKIP_PATHS = frozenset({"/health", "/metrics", "/api/ecosystem/health"})

        def __init__(self, app: "ASGIApp", config: Optional[RateLimitConfig] = None) -> None:
            super().__init__(app)
            self._limiter = AdaptiveRateLimiter(config=config)

        async def dispatch(
            self, request: "Request", call_next: "RequestResponseEndpoint"
        ) -> "Response":
            if request.url.path in self._SKIP_PATHS:
                return await call_next(request)

            allowed, remaining, limit, retry_after = await self._limiter.check_request(request)

            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "retry_after": retry_after,
                        "limit": limit,
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(remaining)
            response.headers["X-RateLimit-Window"] = str(self._limiter._config.window_seconds)
            return response

    class AdaptiveRateLimiterMiddleware(BaseHTTPMiddleware):
        """
        Lightweight DDoS-oriented middleware wrapping AdaptiveRateLimiter.check_ddos().

        Adds X-RateLimit-Utilization header and blocks on IP-level abuse.
        """

        def __init__(self, app: "ASGIApp", default_rpm: int = 120, **kwargs) -> None:
            super().__init__(app)
            self._limiter = AdaptiveRateLimiter(base_rate=default_rpm, **kwargs)

        async def dispatch(self, request: "Request", call_next: "Callable") -> "Response":
            client_ip = request.client.host if request.client else "unknown"
            path_prefix = "/" + request.url.path.strip("/").split("/")[0]
            key = f"{client_ip}:{path_prefix}"

            allowed, meta = self._limiter.check_ddos(key, ip=client_ip)
            if not allowed:
                logger.warning(
                    "Rate limit exceeded: %s path=%s util=%.2f",
                    client_ip,
                    path_prefix,
                    meta.get("utilization", 0),
                )
                return Response(
                    content='{"error":"rate_limit_exceeded","retry_after":60}',
                    status_code=429,
                    headers={
                        "Content-Type": "application/json",
                        "Retry-After": "60",
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Utilization"] = str(round(meta.get("utilization", 0), 3))
            return response

except ImportError:
    # FastAPI/Starlette not available in this environment — middleware skipped
    pass


# ─────────────────────────────────────────────────────────────────────────────
# Module-level singleton
# ─────────────────────────────────────────────────────────────────────────────

_limiter: AdaptiveRateLimiter | None = None


def get_limiter() -> AdaptiveRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = AdaptiveRateLimiter()
    return _limiter


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Basic strategy limiters
    "FixedWindowLimiter",
    "RateLimitResult",
    "SlidingWindowLimiter",
    "TokenBucketLimiter",
    "create_rate_limiter",
    # Config
    "RateLimitConfig",
    "RateLimitEntry",
    # Unified adaptive limiter
    "AdaptiveRateLimiter",
    # Middleware (only available when FastAPI/Starlette installed)
    "AdaptiveRateLimiterMiddleware",
    "RateLimitMiddleware",
    # Singleton
    "get_limiter",
]
