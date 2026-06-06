"""Mount a minimal Prometheus /metrics endpoint on FastAPI workers."""

from __future__ import annotations

from typing import Any

_REGISTERED: set[str] = set()


def _route_exists(app: Any, path: str) -> bool:
    for route in getattr(app, "routes", []):
        if getattr(route, "path", None) == path:
            return True
    return False


_worker_up_gauge = None


def _ensure_worker_info_metric(service_name: str) -> None:
    global _worker_up_gauge
    if service_name in _REGISTERED:
        return
    try:
        from prometheus_client import Gauge, REGISTRY

        if "tranc3_worker_up" in REGISTRY._names_to_collectors:
            REGISTRY.unregister(REGISTRY._names_to_collectors["tranc3_worker_up"])

        if _worker_up_gauge is None:
            _worker_up_gauge = Gauge(
                "tranc3_worker_up",
                "Worker process is serving metrics",
                ["service"],
            )
        _worker_up_gauge.labels(service=service_name).set(1)
        _REGISTERED.add(service_name)
    except Exception:
        pass


def mount_prometheus_endpoint(app: Any, service_name: str) -> None:
    """Register GET /metrics if not already present (InfinityWorkerKit-safe)."""
    if _route_exists(app, "/metrics"):
        return

    _ensure_worker_info_metric(service_name)

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics():
        from fastapi.responses import PlainTextResponse

        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

            return PlainTextResponse(
                content=generate_latest(),
                media_type=CONTENT_TYPE_LATEST,
            )
        except ImportError:
            return PlainTextResponse(
                content=f"# prometheus_client not installed\n# service={service_name}\n",
                media_type="text/plain; version=0.0.4",
            )
