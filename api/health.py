"""Health check router — shallow and deep probes."""

from __future__ import annotations

import time
from typing import Any

try:
    from fastapi import APIRouter
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("fastapi required") from exc

try:
    import httpx

    _HTTPX_AVAILABLE = True
except ImportError:
    _HTTPX_AVAILABLE = False

try:
    from api.models import DeepHealthResponse, HealthResponse  # noqa: F401
except ImportError:
    HealthResponse = dict  # type: ignore[misc,assignment]
    DeepHealthResponse = dict  # type: ignore[misc,assignment]

router = APIRouter(tags=["health"])

_VERSION = "1.0.0"

# P0 workers that must be reachable for the platform to function.
_P0_WORKERS: dict[str, str] = {
    "infinity-ws": "http://localhost:8004/health",
    "infinity-auth": "http://localhost:8005/health",
}


@router.get("/health")
async def health() -> dict[str, Any]:
    """Shallow liveness probe."""
    return {
        "status": "ok",
        "timestamp": time.time(),
        "version": _VERSION,
    }


@router.get("/health/deep")
async def deep_health() -> dict[str, Any]:
    """Deep readiness probe — checks all P0 workers."""
    results: dict[str, Any] = {}
    overall = "ok"

    if not _HTTPX_AVAILABLE:
        return {
            "status": "degraded",
            "reason": "httpx not installed; cannot probe P0 workers",
            "timestamp": time.time(),
        }

    async with httpx.AsyncClient(timeout=3.0) as client:
        for name, url in _P0_WORKERS.items():
            try:
                resp = await client.get(url)
                results[name] = {
                    "status": "ok" if resp.status_code < 300 else "degraded",
                    "http_status": resp.status_code,
                }
                if resp.status_code >= 300:
                    overall = "degraded"
            except Exception as exc:
                results[name] = {"status": "unreachable", "error": str(exc)}
                overall = "degraded"

    return {
        "status": overall,
        "timestamp": time.time(),
        "version": _VERSION,
        "workers": results,
    }
