"""Optional Services Health Monitor — Port 8039.

Polls each optional service's health endpoint, aggregates status,
and reports to The Observatory (port 8007). Exposes a unified
/health endpoint for Traefik and Prometheus scraping.
"""
from __future__ import annotations

import asyncio
import os
import time
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Optional Services Health", version="1.0.0")

PORT = int(os.getenv("PORT", "8039"))
OBSERVATORY_URL = os.getenv("OBSERVATORY_URL", "http://localhost:8007")

# Parse SERVICES env: "name:url, name2:url2, ..."
_raw = os.getenv(
    "SERVICES",
    "library:http://the-library:3000/_health,"
    "documents:http://docutari:8000/api/,"
    "design:http://fabulousa-frontend/,"
    "workshop:http://the-workshop:3000/-/health,"
    "scheduling:http://chronossphere:3000/api/health,"
    "registry:http://the-artifactory:5000/v2/,"
    "sandbox:http://the-ice-box:8090/health",
)

SERVICE_URLS: dict[str, str] = {}
for entry in _raw.replace("\n", "").split(","):
    entry = entry.strip()
    if ":" in entry:
        name, _, url = entry.partition(":")
        SERVICE_URLS[name.strip()] = url.strip() if url.startswith("http") else f"http:{url.strip()}"

_cache: dict[str, dict[str, Any]] = {}
_last_poll: float = 0.0
POLL_INTERVAL = 30  # seconds


async def poll_service(client: httpx.AsyncClient, name: str, url: str) -> dict[str, Any]:
    start = time.monotonic()
    try:
        r = await client.get(url, timeout=5.0)
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "name": name,
            "url": url,
            "status": "healthy" if r.status_code < 400 else "degraded",
            "http_status": r.status_code,
            "latency_ms": latency_ms,
            "checked_at": time.time(),
        }
    except Exception as exc:
        latency_ms = int((time.monotonic() - start) * 1000)
        return {
            "name": name,
            "url": url,
            "status": "unreachable",
            "error": str(exc)[:120],
            "latency_ms": latency_ms,
            "checked_at": time.time(),
        }


async def refresh_cache() -> None:
    global _last_poll
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(
            *[poll_service(client, name, url) for name, url in SERVICE_URLS.items()]
        )
    for r in results:
        _cache[r["name"]] = r
    _last_poll = time.time()

    # Report to The Observatory
    try:
        async with httpx.AsyncClient(timeout=3.0) as obs:
            await obs.post(
                f"{OBSERVATORY_URL}/events",
                json={
                    "source": "optional-services-health",
                    "event": "health_poll",
                    "services": list(_cache.values()),
                },
            )
    except Exception:
        pass  # Observatory may not be running; non-fatal


@app.on_event("startup")
async def startup() -> None:
    await refresh_cache()
    asyncio.create_task(_background_poll())


async def _background_poll() -> None:
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        await refresh_cache()


@app.get("/health")
async def health() -> JSONResponse:
    if time.time() - _last_poll > POLL_INTERVAL * 2:
        await refresh_cache()
    statuses = list(_cache.values())
    overall = "healthy"
    for s in statuses:
        if s["status"] == "unreachable":
            overall = "degraded"
            break
        if s["status"] == "degraded":
            overall = "degraded"
    return JSONResponse(
        {
            "service": "optional-services-health",
            "overall": overall,
            "services": statuses,
            "last_poll": _last_poll,
        },
        status_code=200 if overall == "healthy" else 207,
    )


@app.get("/metrics")
async def metrics() -> JSONResponse:
    """Prometheus-compatible JSON metrics."""
    return JSONResponse(
        {
            "optional_services_total": len(_cache),
            "optional_services_healthy": sum(1 for s in _cache.values() if s["status"] == "healthy"),
            "optional_services_unreachable": sum(1 for s in _cache.values() if s["status"] == "unreachable"),
            "services": {
                name: {
                    "status": info["status"],
                    "latency_ms": info.get("latency_ms", 0),
                }
                for name, info in _cache.items()
            },
        }
    )


@app.get("/services/{name}")
async def service_detail(name: str) -> JSONResponse:
    if name not in _cache:
        return JSONResponse({"error": "unknown service"}, status_code=404)
    return JSONResponse(_cache[name])


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
