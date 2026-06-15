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
    from api.models import DeepHealthResponse, HealthResponse
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


@router.get("/health", response_model=HealthResponse)
async def health() -> dict[str, Any]:
    """Shallow liveness probe."""
    return {
        "status": "ok",
        "timestamp": time.time(),
        "version": _VERSION,
    }


@router.get("/health/deep", response_model=DeepHealthResponse)
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

    import asyncio

    async def _probe(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, dict]:
        try:
            resp = await client.get(url)
            status = "ok" if resp.status_code < 300 else "degraded"
            return name, {"status": status, "http_status": resp.status_code}
        except Exception:
            return name, {"status": "unreachable", "error": "probe_failed"}

    async with httpx.AsyncClient(timeout=3.0) as client:
        probes = await asyncio.gather(
            *(_probe(client, name, url) for name, url in _P0_WORKERS.items())
        )
        for name, res in probes:
            results[name] = res
            if res["status"] != "ok":
                overall = "degraded"

    return {
        "status": overall,
        "timestamp": time.time(),
        "version": _VERSION,
        "workers": results,
    }
