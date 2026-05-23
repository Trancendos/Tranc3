# shared_core/middleware/rate_limiter.py — Adaptive Rate Limiting for FastAPI
# Ported from the-citadel/src/middleware/resilience-layer.ts (TypeScript → Python)
#
# Features:
#   - IAM-level aware rate limiting (higher-tier users get more capacity)
#   - Sliding window with configurable duration and max requests
#   - Per-client tracking using JWT sub or IP address
#   - X-RateLimit-* response headers
#   - Zero external dependencies (no Redis needed)

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


@dataclass
class RateLimitEntry:
    """Tracks request count within a sliding window for a single client."""
    count: int = 0
    window_start: float = 0.0


@dataclass
class RateLimitConfig:
    """Configuration for the adaptive rate limiter."""
    window_seconds: int = 60
    max_requests: int = 100
    # IAM tier multipliers — higher tier = more requests allowed
    tier_multipliers: Dict[str, float] = field(default_factory=lambda: {
        "free": 1.0,
        "pro": 2.5,
        "prime": 5.0,
        "admin": 10.0,
        "service": 20.0,  # internal service accounts
    })
    # Key extraction: "ip", "jwt_sub", or "jwt_sub_with_ip_fallback"
    key_strategy: str = "jwt_sub_with_ip_fallback"
    cleanup_interval: int = 300  # seconds between stale entry cleanup
    max_entries: int = 100_000  # max tracked clients


class AdaptiveRateLimiter:
    """
    Adaptive rate limiter with IAM-level aware capacity allocation.

    Ported from the-citadel's adaptiveRateLimitMiddleware.
    Instead of a simple counter, this adjusts the allowed request count
    based on the user's IAM tier, giving premium users proportionally
    more capacity while still enforcing reasonable limits.

    Zero-cost: no Redis, no external store — all in-memory with
    periodic cleanup to prevent memory leaks.
    """

    def __init__(self, config: Optional[RateLimitConfig] = None):
        self._config = config or RateLimitConfig()
        self._store: Dict[str, RateLimitEntry] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = time.time()

    def _get_client_key(self, request: Request) -> str:
        """Extract client identity from request for rate limit tracking."""
        if self._config.key_strategy in ("jwt_sub", "jwt_sub_with_ip_fallback"):
            # Try to get JWT subject from state (set by auth middleware)
            user = getattr(request.state, "user", None)
            if user and isinstance(user, dict) and user.get("sub"):
                return f"jwt:{user['sub']}"

        if self._config.key_strategy == "jwt_sub":
            # Strict mode — if no JWT, use a shared "anonymous" bucket
            return "anon"

        # Fallback to IP
        client_ip = request.client.host if request.client else "unknown"
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            client_ip = forwarded.split(",")[0].strip()
        return f"ip:{client_ip}"

    def _get_user_tier(self, request: Request) -> str:
        """Get the IAM tier for the current request."""
        user = getattr(request.state, "user", None)
        if user and isinstance(user, dict):
            return user.get("tier", "free")
        return "free"

    def _get_effective_limit(self, request: Request) -> int:
        """Calculate the effective rate limit for this request's tier."""
        tier = self._get_user_tier(request)
        multiplier = self._config.tier_multipliers.get(tier, 1.0)
        return int(self._config.max_requests * multiplier)

    async def _cleanup_stale(self) -> None:
        """Remove entries with expired windows to prevent memory leaks."""
        now = time.time()
        if now - self._last_cleanup < self._config.cleanup_interval:
            return
        cutoff = now - self._config.window_seconds
        stale_keys = [k for k, v in self._store.items() if v.window_start < cutoff]
        for k in stale_keys:
            del self._store[k]
        self._last_cleanup = now
        if stale_keys:
            logger.debug("Cleaned up %d stale rate limit entries", len(stale_keys))

    async def check(self, request: Request) -> Tuple[bool, int, int, int]:
        """
        Check if the request is within rate limits.

        Returns:
            (allowed, remaining, limit, retry_after)
            - allowed: True if request is permitted
            - remaining: Number of requests remaining in this window
            - limit: The effective limit for this client's tier
            - retry_after: Seconds until the window resets (0 if allowed)
        """
        now = time.time()
        key = self._get_client_key(request)
        effective_limit = self._get_effective_limit(request)
        window_start = now - (now % self._config.window_seconds)

        async with self._lock:
            entry = self._store.get(key)
            if not entry or entry.window_start != window_start:
                entry = RateLimitEntry(count=0, window_start=window_start)
                self._store[key] = entry

            entry.count += 1

            # Enforce max entries to prevent memory exhaustion
            if len(self._store) > self._config.max_entries:
                # Remove oldest 10%
                sorted_keys = sorted(self._store.keys(),
                                     key=lambda k: self._store[k].window_start)
                for k in sorted_keys[:len(sorted_keys) // 10]:
                    del self._store[k]

            remaining = max(0, effective_limit - entry.count)
            window_ends_at = window_start + self._config.window_seconds
            retry_after = max(0, int(window_ends_at - now)) if entry.count > effective_limit else 0

            await self._cleanup_stale()

        allowed = entry.count <= effective_limit
        return allowed, remaining, effective_limit, retry_after


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware that enforces adaptive rate limiting.

    Usage:
        app.add_middleware(RateLimitMiddleware, config=RateLimitConfig(max_requests=100))

    Ported from the-citadel's adaptiveRateLimitMiddleware.
    Adds X-RateLimit-Limit, X-RateLimit-Remaining, and X-RateLimit-Reset headers.
    """

    def __init__(self, app: ASGIApp, config: Optional[RateLimitConfig] = None):
        super().__init__(app)
        self._limiter = AdaptiveRateLimiter(config)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health checks and internal metrics
        path = request.url.path
        if path in ("/health", "/metrics", "/api/ecosystem/health"):
            return await call_next(request)

        allowed, remaining, limit, retry_after = await self._limiter.check(request)

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

        # Add rate limit headers
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Window"] = str(self._limiter._config.window_seconds)

        return response
