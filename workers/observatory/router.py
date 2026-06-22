"""Observatory — FastAPI routes."""

from __future__ import annotations

import time
from typing import Optional

import service
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from models import SignalType

import config


def _make_observatory_router() -> APIRouter:
    async def _auth(
        x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
    ) -> None:
        if not config.INTERNAL_SECRET:
            return
        if x_internal_secret != config.INTERNAL_SECRET:
            raise HTTPException(401, "Invalid or missing X-Internal-Secret header")

    router = APIRouter(dependencies=[Depends(_auth)])

    # ── Backend status ─────────────────────────────────────────────────────────

    @router.get("/backends")
    async def list_backends():
        """Return pheromone + health status for all 7 observability backends."""
        statuses = await service.backend_statuses()
        return {"backends": [s.model_dump() for s in statuses]}

    # ── Traces ─────────────────────────────────────────────────────────────────

    @router.get("/traces")
    async def query_traces(
        service_name: Optional[str] = Query(None, alias="service"),
        limit: int = Query(20, ge=1, le=200),
        lookback_hours: int = Query(1, ge=1, le=168),
    ):
        """Query distributed traces — Tempo primary, Jaeger fallback."""
        result = await service.query_traces(service_name, limit, lookback_hours)
        return result.model_dump()

    # ── Metrics ────────────────────────────────────────────────────────────────

    @router.get("/metrics")
    async def query_metrics(
        promql: str = Query(..., description="PromQL expression"),
        step: str = Query("60s", description="Query step interval"),
    ):
        """Execute PromQL — VictoriaMetrics primary, Prometheus fallback."""
        result = await service.query_metrics(promql, step)
        return result.model_dump()

    # ── Logs ───────────────────────────────────────────────────────────────────

    @router.get("/logs")
    async def query_logs(
        logql: str = Query(..., description="LogQL expression"),
        limit: int = Query(100, ge=1, le=5000),
    ):
        """Query logs via Loki."""
        result = await service.query_logs(logql, limit)
        return result.model_dump()

    # ── Node metrics ───────────────────────────────────────────────────────────

    @router.get("/node")
    async def node_metrics():
        """Real-time host metrics — Netdata primary, VictoriaMetrics PromQL fallback."""
        summary = await service.query_node_metrics()
        return summary.model_dump()

    # ── Dashboard ──────────────────────────────────────────────────────────────

    @router.get("/dashboard")
    async def dashboard():
        """Aggregated platform health overview — all signals in one call."""
        t0 = time.monotonic()
        import asyncio

        backends_task = asyncio.create_task(service.backend_statuses())
        node_task = asyncio.create_task(service.query_node_metrics())

        backends, node = await asyncio.gather(backends_task, node_task)

        healthy = [b for b in backends if b.healthy]
        signals: dict = {
            SignalType.traces: next(
                (b.url for b in backends if b.healthy and b.backend.value in ("tempo", "jaeger")),
                "offline",
            ),
            SignalType.metrics: next(
                (
                    b.url
                    for b in backends
                    if b.healthy and b.backend.value in ("victoriametrics", "prometheus")
                ),
                "offline",
            ),
            SignalType.logs: next(
                (b.url for b in backends if b.healthy and b.backend.value == "loki"),
                "offline",
            ),
            SignalType.node: node.source,
        }

        return {
            "healthy_backends": len(healthy),
            "total_backends": len(backends),
            "backends": [b.model_dump() for b in backends],
            "node": node.model_dump(),
            "active_signals": {k.value: v for k, v in signals.items()},
            "latency_ms": round((time.monotonic() - t0) * 1000, 1),
        }

    return router
