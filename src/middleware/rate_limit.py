# src/middleware/rate_limit.py
# Production rate limiting middleware.
# Uses Redis when available, falls back to in-memory token bucket.
# Per-user, per-endpoint rate limiting with configurable limits.

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

logger = logging.getLogger(__name__)


# ─── Rate limit tiers ────────────────────────────────────────────

RATE_LIMITS = {
    "free":       {"rpm": 20,  "rpd": 500},    # requests per minute / per day
    "pro":        {"rpm": 60,  "rpd": 5000},
    "enterprise": {"rpm": 200, "rpd": 50000},
    "default":    {"rpm": 10,  "rpd": 200},     # unauthenticated
}


# ─── In-memory token bucket ──────────────────────────────────────

class _InMemoryBucket:
    """Token bucket rate limiter for when Redis is unavailable."""

    def __init__(self):
        self._buckets: Dict[str, Dict[str, float]] = defaultdict(dict)
        self._daily: Dict[str, Dict[str, int]] = defaultdict(dict)

    def check(self, key: str, rpm: int, rpd: int) -> Tuple[bool, Dict[str, int]]:
        """
        Check if the request is within rate limits.
        Returns (allowed, headers) where headers contain remaining counts.
        """
        now = time.monotonic()
        minute_key = f"{key}:{int(now / 60)}"
        day_key = f"{key}:{int(now / 86400)}"

        # Per-minute bucket
        bucket = self._buckets[minute_key]
        tokens = bucket.get("tokens", rpm)
        last_refill = bucket.get("last_refill", now)

        # Refill tokens
        elapsed = now - last_refill
        tokens = min(rpm, tokens + elapsed * (rpm / 60.0))
        bucket["last_refill"] = now

        remaining_min = int(tokens)

        if tokens < 1.0:
            allowed = False
        else:
            tokens -= 1.0
            allowed = True
        bucket["tokens"] = tokens

        # Per-day counter
        day_count = self._daily[day_key].get("count", 0)
        remaining_day = max(0, rpd - day_count)
        if day_count >= rpd:
            allowed = False
        if allowed:
            self._daily[day_key]["count"] = day_count + 1

        # Clean up old entries (keep last 2 minutes and 2 days)
        self._cleanup(now)

        return allowed, {
            "X-RateLimit-Limit": rpm,
            "X-RateLimit-Remaining-Minute": remaining_min,
            "X-RateLimit-Remaining-Day": remaining_day,
        }

    def _cleanup(self, now: float):
        """Remove expired entries to prevent memory leak."""
        current_minute = int(now / 60)
        current_day = int(now / 86400)
        
        keys_to_remove = []
        for key in list(self._buckets.keys()):
            parts = key.rsplit(":", 1)
            if len(parts) == 2:
                try:
                    minute = int(parts[1])
                    if minute < current_minute - 1:
                        keys_to_remove.append(key)
                except ValueError:
                    pass
        for key in keys_to_remove:
            del self._buckets[key]

        day_keys_to_remove = []
        for key in list(self._daily.keys()):
            parts = key.rsplit(":", 1)
            if len(parts) == 2:
                try:
                    day = int(parts[1])
                    if day < current_day - 1:
                        day_keys_to_remove.append(key)
                except ValueError:
                    pass
        for key in day_keys_to_remove:
            del self._daily[key]


# ─── Redis rate limiter ──────────────────────────────────────────

class _RedisRateLimiter:
    """Redis-based rate limiter for distributed deployments."""

    def __init__(self, redis_client):
        self._redis = redis_client

    def check(self, key: str, rpm: int, rpd: int) -> Tuple[bool, Dict[str, int]]:
        """Use Redis INCR + EXPIRE for atomic rate limiting."""
        try:
            pipe = self._redis.pipeline()
            now = int(time.time())
            minute_key = f"rl:min:{key}:{now // 60}"
            day_key = f"rl:day:{key}:{now // 86400}"

            # Increment minute counter
            pipe.incr(minute_key)
            pipe.expire(minute_key, 120)  # 2 minute TTL

            # Increment day counter
            pipe.incr(day_key)
            pipe.expire(day_key, 172800)  # 2 day TTL

            results = pipe.execute()
            minute_count = results[0]
            day_count = results[2]

            allowed = minute_count <= rpm and day_count <= rpd
            return allowed, {
                "X-RateLimit-Limit": rpm,
                "X-RateLimit-Remaining-Minute": max(0, rpm - minute_count),
                "X-RateLimit-Remaining-Day": max(0, rpd - day_count),
            }
        except Exception as e:
            logger.warning("Redis rate limit failed: %s — allowing request", e)
            return True, {"X-RateLimit-Limit": rpm}


# ─── FastAPI Middleware ───────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware for FastAPI.
    Uses Redis when available, falls back to in-memory token bucket.
    Rate limits are per-user (from JWT) or per-IP (unauthenticated).
    """

    # Paths that skip rate limiting
    SKIP_PATHS = {"/health", "/ready", "/metrics", "/docs", "/openapi.json", "/redoc"}

    def __init__(self, app, redis_client=None):
        super().__init__(app)
        if redis_client:
            self._limiter = _RedisRateLimiter(redis_client)
            logger.info("Rate limiting: Redis-backed")
        else:
            self._limiter = _InMemoryBucket()
            logger.info("Rate limiting: In-memory (set REDIS_URL for distributed)")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for health/metrics endpoints
        if request.url.path in self.SKIP_PATHS:
            return await call_next(request)

        # Determine rate limit key and tier
        key, tier = self._get_key_and_tier(request)
        limits = RATE_LIMITS.get(tier, RATE_LIMITS["default"])

        # Check rate limit
        allowed, headers = self._limiter.check(key, limits["rpm"], limits["rpd"])

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down.", "retry_after": 60},
                headers=headers,
            )

        # Process request
        response = await call_next(request)

        # Add rate limit headers to response
        for h, v in headers.items():
            response.headers[h] = str(v)

        return response

    def _get_key_and_tier(self, request: Request) -> Tuple[str, str]:
        """
        Extract rate limit key (user ID or IP) and tier from request.
        Tries JWT first, falls back to client IP.
        """
        # Try to get user from JWT
        try:
            from auth import token_manager
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                payload = token_manager.decode_token(token)
                user_id = payload.get("sub", "anonymous")
                tier = payload.get("tier", "free")
                return f"user:{user_id}", tier
        except Exception:
            pass

        # Fall back to IP
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}", "default"
