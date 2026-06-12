"""Adaptive rate limiter — RSK-007 (DDoS mitigation).

Extends token-bucket rate limiting with adaptive thresholds that tighten
automatically under load. Provides FastAPI middleware and standalone client.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_ADAPTIVE_THRESHOLD = 0.8  # tighten when >80% of capacity used


@dataclass
class TokenBucket:
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
    """Rate limiter with adaptive capacity reduction under sustained load."""

    def __init__(
        self,
        default_rpm: int = 120,
        burst_multiplier: float = 1.5,
        adaptive: bool = True,
    ) -> None:
        self.default_rpm = default_rpm
        self.burst_multiplier = burst_multiplier
        self.adaptive = adaptive
        self._buckets: dict[str, TokenBucket] = {}
        self._request_times: dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))
        self._blocked_ips: dict[str, float] = {}  # ip -> block_until timestamp
        self._global_load: deque = deque(maxlen=10000)

    def _get_bucket(self, key: str) -> TokenBucket:
        if key not in self._buckets:
            capacity = self.default_rpm * self.burst_multiplier
            rate = self.default_rpm / 60.0
            self._buckets[key] = TokenBucket(capacity=capacity, refill_rate=rate)
        return self._buckets[key]

    def _is_ip_blocked(self, ip: str) -> bool:
        until = self._blocked_ips.get(ip)
        if until and time.monotonic() < until:
            return True
        self._blocked_ips.pop(ip, None)
        return False

    def _global_utilization(self) -> float:
        now = time.monotonic()
        recent = sum(1 for t in self._global_load if now - t < _WINDOW_SECONDS)
        total_capacity = self.default_rpm * max(1, len(self._buckets))
        return recent / total_capacity if total_capacity > 0 else 0.0

    def check(self, key: str, ip: str | None = None) -> tuple[bool, dict]:
        """Returns (allowed, metadata). Thread-safe for asyncio usage."""
        if ip and self._is_ip_blocked(ip):
            return False, {"reason": "ip_blocked", "retry_after": 60}

        bucket = self._get_bucket(key)

        # Adaptive: reduce effective capacity under global load
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

            # Block IPs making >500 requests in 60s (aggressive pattern)
            recent = sum(1 for t in self._request_times[ip] if now - t < 60)
            if recent > 500:
                self._blocked_ips[ip] = now + 300  # 5-minute block
                logger.warning("DDoS pattern detected from %s — blocked 5min", ip)

        metadata = {
            "allowed": allowed,
            "utilization": round(bucket.utilization, 3),
            "global_load": round(self._global_utilization(), 3),
            "tokens_remaining": round(bucket.tokens, 1),
        }
        return allowed, metadata

    def stats(self) -> dict:
        now = time.monotonic()
        return {
            "active_keys": len(self._buckets),
            "blocked_ips": len(self._blocked_ips),
            "global_rps": sum(1 for t in self._global_load if now - t < 1),
            "global_rpm": sum(1 for t in self._global_load if now - t < 60),
        }


class AdaptiveRateLimiterMiddleware(BaseHTTPMiddleware):
    """FastAPI/Starlette middleware wrapping AdaptiveRateLimiter."""

    def __init__(self, app, default_rpm: int = 120, **kwargs) -> None:
        super().__init__(app)
        self._limiter = AdaptiveRateLimiter(default_rpm=default_rpm, **kwargs)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        # Key by IP + path prefix to separate API endpoints
        path_prefix = "/" + request.url.path.strip("/").split("/")[0]
        key = f"{client_ip}:{path_prefix}"

        allowed, meta = self._limiter.check(key, ip=client_ip)
        if not allowed:
            logger.warning("Rate limit exceeded: %s path=%s util=%.2f", client_ip, path_prefix, meta.get("utilization", 0))
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


_limiter: AdaptiveRateLimiter | None = None


def get_limiter() -> AdaptiveRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = AdaptiveRateLimiter()
    return _limiter
