"""
src/core/resource_limits.py
─────────────────────────────────────────────────────────────────────────────
Standardised resource-exhaustion prevention configuration (REQ-SA-005).

Provides a single source of truth for timeouts, connection-pool sizes,
rate-limit tokens and circuit-breaker thresholds used across all workers
and the main FastAPI application.

All values are env-overridable so they can be tuned per environment without
code changes.

Usage:
    from src.core.resource_limits import LIMITS

    async with httpx.AsyncClient(timeout=LIMITS.http_timeout) as client:
        ...
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(key: str, default: int) -> int:
    return int(os.getenv(key, str(default)))


def _float(key: str, default: float) -> float:
    return float(os.getenv(key, str(default)))


@dataclass(frozen=True)
class ResourceLimits:
    # ── HTTP client timeouts (seconds) ────────────────────────────────────────
    http_connect_timeout: float = _float("LIMIT_HTTP_CONNECT_TIMEOUT", 5.0)
    http_read_timeout: float = _float("LIMIT_HTTP_READ_TIMEOUT", 30.0)
    http_write_timeout: float = _float("LIMIT_HTTP_WRITE_TIMEOUT", 10.0)
    http_pool_timeout: float = _float("LIMIT_HTTP_POOL_TIMEOUT", 5.0)

    # ── Connection pool ───────────────────────────────────────────────────────
    http_max_connections: int = _int("LIMIT_HTTP_MAX_CONNECTIONS", 100)
    http_max_keepalive: int = _int("LIMIT_HTTP_MAX_KEEPALIVE", 20)

    # ── AI inference timeouts ─────────────────────────────────────────────────
    inference_timeout: float = _float("LIMIT_INFERENCE_TIMEOUT", 60.0)
    inference_stream_timeout: float = _float("LIMIT_INFERENCE_STREAM_TIMEOUT", 120.0)

    # ── API request limits ────────────────────────────────────────────────────
    max_request_body_bytes: int = _int("LIMIT_MAX_REQUEST_BODY_BYTES", 1_048_576)  # 1 MB
    max_prompt_tokens: int = _int("LIMIT_MAX_PROMPT_TOKENS", 4096)
    max_response_tokens: int = _int("LIMIT_MAX_RESPONSE_TOKENS", 2048)

    # ── Rate limiting (in-memory token bucket) ────────────────────────────────
    rate_free_rpm: int = _int("LIMIT_RATE_FREE_RPM", 100)
    rate_pro_rpm: int = _int("LIMIT_RATE_PRO_RPM", 1000)
    rate_business_rpm: int = _int("LIMIT_RATE_BUSINESS_RPM", 10000)

    # ── Circuit breaker ───────────────────────────────────────────────────────
    cb_failure_threshold: int = _int("LIMIT_CB_FAILURE_THRESHOLD", 5)
    cb_recovery_timeout: float = _float("LIMIT_CB_RECOVERY_TIMEOUT", 30.0)
    cb_half_open_max_calls: int = _int("LIMIT_CB_HALF_OPEN_MAX_CALLS", 3)

    # ── Background workers ────────────────────────────────────────────────────
    worker_queue_max_size: int = _int("LIMIT_WORKER_QUEUE_MAX_SIZE", 500)
    worker_task_timeout: float = _float("LIMIT_WORKER_TASK_TIMEOUT", 90.0)

    # ── Database ──────────────────────────────────────────────────────────────
    db_pool_size: int = _int("LIMIT_DB_POOL_SIZE", 10)
    db_max_overflow: int = _int("LIMIT_DB_MAX_OVERFLOW", 20)
    db_pool_timeout: float = _float("LIMIT_DB_POOL_TIMEOUT", 30.0)
    db_statement_timeout_ms: int = _int("LIMIT_DB_STATEMENT_TIMEOUT_MS", 10_000)

    def httpx_timeout(self):
        """Return an httpx.Timeout object from these limits."""
        try:
            import httpx

            return httpx.Timeout(
                connect=self.http_connect_timeout,
                read=self.http_read_timeout,
                write=self.http_write_timeout,
                pool=self.http_pool_timeout,
            )
        except ImportError:
            return None

    def httpx_limits(self):
        """Return an httpx.Limits object from these limits."""
        try:
            import httpx

            return httpx.Limits(
                max_connections=self.http_max_connections,
                max_keepalive_connections=self.http_max_keepalive,
            )
        except ImportError:
            return None


# Module-level singleton — import and use directly
LIMITS = ResourceLimits()
