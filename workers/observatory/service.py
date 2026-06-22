"""Observatory service — ACO pheromone routing across 7 free observability backends.

Signal routing:
  Traces  : Tempo → Jaeger (fan-out write; adaptive read)
  Metrics : VictoriaMetrics → Prometheus (adaptive fallback)
  Logs    : Loki
  Node    : Netdata → VictoriaMetrics/Prometheus (Netdata Prom endpoint)
  APM     : SigNoz (full unified view — traces + metrics + logs)
"""
from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from typing import Any, Dict, List, Optional, Tuple

import httpx

from .config import (
    ACO_DECAY,
    JAEGER_URL,
    LOG_BACKENDS,
    LOKI_URL,
    METRICS_BACKENDS,
    NETDATA_URL,
    PROMETHEUS_URL,
    SIGNOZ_URL,
    TEMPO_URL,
    THRESHOLD_JAEGER,
    THRESHOLD_LOKI,
    THRESHOLD_NETDATA,
    THRESHOLD_PROMETHEUS,
    THRESHOLD_SIGNOZ,
    THRESHOLD_TEMPO,
    THRESHOLD_VICTORIA,
    THRESHOLD_WINDOW_SECONDS,
    TRACE_BACKENDS,
    VICTORIAMETRICS_URL,
)
from .models import BackendStatus, BackendType, NodeMetricSummary, QueryResult, SignalType

logger = logging.getLogger("observatory.service")


# ── ThresholdGuard ────────────────────────────────────────────────────────────

class ThresholdGuard:
    def __init__(self, limit: int, window_seconds: int = THRESHOLD_WINDOW_SECONDS) -> None:
        self.limit = limit
        self.window = window_seconds
        self._timestamps: deque[float] = deque()

    def check(self) -> bool:
        """Returns True if request is allowed; side-effect: records timestamp."""
        now = time.monotonic()
        cutoff = now - self.window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        if len(self._timestamps) >= self.limit:
            return False
        self._timestamps.append(now)
        return True

    @property
    def current_count(self) -> int:
        now = time.monotonic()
        cutoff = now - self.window
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()
        return len(self._timestamps)


# ── Pheromone state ───────────────────────────────────────────────────────────

class PheromoneState:
    def __init__(self, initial: float = 0.8) -> None:
        self.value = initial

    def success(self, boost: float = 0.05) -> None:
        self.value = min(1.0, self.value + boost)

    def failure(self, penalty: float = 0.2) -> None:
        self.value = max(0.0, self.value - penalty)

    def decay(self, factor: float = ACO_DECAY) -> None:
        self.value = self.value * factor + (1 - factor) * 0.5


# ── Per-backend registry ──────────────────────────────────────────────────────

_BACKEND_CONFIG: Dict[BackendType, Tuple[str, int]] = {
    BackendType.signoz:         (SIGNOZ_URL,          THRESHOLD_SIGNOZ),
    BackendType.jaeger:         (JAEGER_URL,          THRESHOLD_JAEGER),
    BackendType.tempo:          (TEMPO_URL,            THRESHOLD_TEMPO),
    BackendType.victoriametrics:(VICTORIAMETRICS_URL,  THRESHOLD_VICTORIA),
    BackendType.prometheus:     (PROMETHEUS_URL,       THRESHOLD_PROMETHEUS),
    BackendType.loki:           (LOKI_URL,             THRESHOLD_LOKI),
    BackendType.netdata:        (NETDATA_URL,          THRESHOLD_NETDATA),
}

_guards: Dict[BackendType, ThresholdGuard] = {
    bt: ThresholdGuard(limit) for bt, (_, limit) in _BACKEND_CONFIG.items()
}
_pheromones: Dict[BackendType, PheromoneState] = {
    bt: PheromoneState() for bt in BackendType
}


async def _probe(url: str, path: str = "/", timeout: float = 3.0) -> Tuple[bool, float]:
    """Returns (reachable, latency_ms)."""
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            r = await client.get(f"{url.rstrip('/')}{path}")
            latency_ms = (time.monotonic() - t0) * 1000
            return r.status_code < 500, latency_ms
    except Exception:
        return False, (time.monotonic() - t0) * 1000


async def backend_statuses() -> List[BackendStatus]:
    probes = {
        BackendType.signoz:          ("/api/v1/health", SIGNOZ_URL),
        BackendType.jaeger:          ("/",               JAEGER_URL),
        BackendType.tempo:           ("/ready",          TEMPO_URL),
        BackendType.victoriametrics: ("/health",         VICTORIAMETRICS_URL),
        BackendType.prometheus:      ("/-/healthy",      PROMETHEUS_URL),
        BackendType.loki:            ("/ready",          LOKI_URL),
        BackendType.netdata:         ("/api/v1/info",    NETDATA_URL),
    }
    tasks = {bt: _probe(url, path) for bt, (path, url) in probes.items()}
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    out = []
    for (bt, _), result in zip(tasks.items(), results):
        url, _ = _BACKEND_CONFIG[bt]
        if isinstance(result, Exception):
            healthy, latency_ms = False, 0.0
        else:
            healthy, latency_ms = result
        guard = _guards[bt]
        ph = _pheromones[bt]
        if healthy:
            ph.success(0.02)
        else:
            ph.failure(0.1)
        out.append(BackendStatus(
            backend=bt,
            url=url,
            healthy=healthy,
            pheromone=round(ph.value, 4),
            requests_in_window=guard.current_count,
            threshold=guard.limit,
            blocked=guard.current_count >= guard.limit,
            latency_ms=round(latency_ms, 1),
        ))
    return out


# ── Adaptive query helpers ────────────────────────────────────────────────────

async def _query_with_fallback(
    backends: List[str],
    backend_types: List[BackendType],
    make_request,
) -> Tuple[Any, str, int]:
    """Try each backend in order; return (data, backend_url_used, fallbacks_count)."""
    fallbacks = 0
    for url, bt in zip(backends, backend_types):
        guard = _guards[bt]
        if not guard.check():
            logger.warning("Observatory: %s threshold reached — skipping", bt.value)
            fallbacks += 1
            continue
        try:
            data = await make_request(url)
            _pheromones[bt].success()
            return data, url, fallbacks
        except Exception as exc:
            _pheromones[bt].failure()
            logger.warning("Observatory: %s failed (%s) — trying fallback", bt.value, exc)
            fallbacks += 1
    return {"error": "all_backends_exhausted"}, "offline", fallbacks


async def query_traces(service: Optional[str], limit: int = 20, lookback_hours: int = 1) -> QueryResult:
    t0 = time.monotonic()
    end_us = int(time.time() * 1_000_000)
    start_us = end_us - lookback_hours * 3600 * 1_000_000
    backend_types = [
        BackendType.tempo if "tempo" in u else BackendType.jaeger
        for u in TRACE_BACKENDS
    ]

    async def _request(url: str) -> Any:
        async with httpx.AsyncClient(timeout=10) as client:
            if "tempo" in url:
                params = {"limit": limit, "start": start_us, "end": end_us}
                if service:
                    params["tags"] = f"service.name={service}"
                r = await client.get(f"{url}/api/search", params=params)
                r.raise_for_status()
                return r.json()
            else:
                params = {"limit": limit, "lookback": f"{lookback_hours}h"}
                if service:
                    params["service"] = service
                r = await client.get(f"{url}/api/traces", params=params)
                r.raise_for_status()
                return r.json()

    data, backend, fallbacks = await _query_with_fallback(TRACE_BACKENDS, backend_types, _request)
    return QueryResult(
        signal=SignalType.traces,
        backend_used=backend,
        data=data,
        latency_ms=round((time.monotonic() - t0) * 1000, 1),
        fallbacks_attempted=fallbacks,
    )


async def query_metrics(promql: str, step: str = "60s") -> QueryResult:
    t0 = time.monotonic()
    backend_types = [
        BackendType.victoriametrics if "victoria" in u else BackendType.prometheus
        for u in METRICS_BACKENDS
    ]

    async def _request(url: str) -> Any:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{url}/api/v1/query",
                params={"query": promql},
            )
            r.raise_for_status()
            return r.json()

    data, backend, fallbacks = await _query_with_fallback(METRICS_BACKENDS, backend_types, _request)
    return QueryResult(
        signal=SignalType.metrics,
        backend_used=backend,
        data=data,
        latency_ms=round((time.monotonic() - t0) * 1000, 1),
        fallbacks_attempted=fallbacks,
    )


async def query_logs(logql: str, limit: int = 100) -> QueryResult:
    t0 = time.monotonic()
    backends = LOG_BACKENDS
    backend_types = [BackendType.loki] * len(backends)

    async def _request(url: str) -> Any:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                f"{url}/loki/api/v1/query_range",
                params={"query": logql, "limit": limit, "direction": "backward"},
            )
            r.raise_for_status()
            return r.json()

    data, backend, fallbacks = await _query_with_fallback(backends, backend_types, _request)
    return QueryResult(
        signal=SignalType.logs,
        backend_used=backend,
        data=data,
        latency_ms=round((time.monotonic() - t0) * 1000, 1),
        fallbacks_attempted=fallbacks,
    )


async def query_node_metrics() -> NodeMetricSummary:
    """Pull host metrics from Netdata API; fall back to VictoriaMetrics PromQL."""
    guard = _guards[BackendType.netdata]
    if guard.check():
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                r = await client.get(
                    f"{NETDATA_URL}/api/v1/data",
                    params={"chart": "system.cpu", "points": 1, "format": "json"},
                )
                r.raise_for_status()
                cpu_data = r.json()
                cpu_pct = 100 - cpu_data.get("data", [[None, None]])[-1][-1] if cpu_data.get("data") else None

                r2 = await client.get(
                    f"{NETDATA_URL}/api/v1/data",
                    params={"chart": "system.ram", "points": 1, "format": "json"},
                )
                r2.raise_for_status()
                ram_data = r2.json()
                ram_vals = ram_data.get("data", [None])[-1] if ram_data.get("data") else None
            _pheromones[BackendType.netdata].success()
            return NodeMetricSummary(
                cpu_usage_pct=round(cpu_pct, 2) if cpu_pct is not None else None,
                ram_used_mb=round(ram_vals[1] / 1024, 1) if ram_vals and len(ram_vals) > 1 else None,
                source="netdata",
            )
        except Exception as exc:
            _pheromones[BackendType.netdata].failure()
            logger.warning("Netdata node query failed: %s — falling back to VictoriaMetrics", exc)

    # Fallback: PromQL via VictoriaMetrics/Prometheus
    try:
        result = await query_metrics('100 - (avg by(instance)(irate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)')
        cpu = None
        if result.data and result.data.get("status") == "success":
            data_list = result.data.get("data", {}).get("result", [])
            if data_list:
                cpu = float(data_list[0]["value"][1])
        return NodeMetricSummary(cpu_usage_pct=round(cpu, 2) if cpu else None, source="victoriametrics")
    except Exception:
        return NodeMetricSummary(source="offline")
