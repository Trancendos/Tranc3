# shared_core/middleware/telemetry.py — Request Telemetry & Trace Propagation
# Ported from the-citadel/src/middleware/resilience-layer.ts (SmartTelemetry + telemetryMiddleware)
#
# Features:
#   - Prometheus-compatible metrics collection
#   - Distributed trace propagation (X-Trace-Id)
#   - Request latency tracking with percentile calculations (p50, p95, p99)
#   - Error rate monitoring
#   - Memory and uptime tracking
#   - /metrics endpoint for Prometheus scraping
#   - Zero external dependencies (no OTel collector needed for basic metrics)

from __future__ import annotations

import logging
import os
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


@dataclass
class RequestRecord:
    """Record of a single request for metrics calculation."""

    timestamp: float
    latency_ms: float
    status_code: int
    method: str
    path: str


class TelemetryCollector:
    """
    Prometheus-compatible telemetry collector with request tracing.

    Ported from the-citadel's SmartTelemetry class.
    Collects request metrics and exposes them for Prometheus scraping.
    All metrics are stored in-memory (zero-cost, no external dependencies).

    Metrics tracked:
    - http_requests_total (counter)
    - http_errors_total (counter)
    - http_request_duration_seconds (histogram)
    - requests_per_second (gauge, 1-min window)
    - error_rate (gauge)
    - memory_usage_bytes (gauge)
    - uptime_seconds (gauge)
    """

    _instance: Optional[TelemetryCollector] = None

    @classmethod
    def get_instance(cls) -> TelemetryCollector:
        if cls._instance is None:
            cls._instance = TelemetryCollector()
        return cls._instance

    def __init__(self):
        self._counters: Dict[str, float] = defaultdict(float)
        self._gauges: Dict[str, float] = defaultdict(float)
        self._histograms: Dict[str, List[float]] = defaultdict(list)
        self._request_records: List[RequestRecord] = []
        self._start_time = time.time()
        self._window_seconds = 60  # sliding window for RPS calculation
        self._max_records = 10_000  # prevent unbounded memory growth

    def increment(self, name: str, value: float = 1.0) -> None:
        self._counters[name] += value

    def gauge(self, name: str, value: float) -> None:
        self._gauges[name] = value

    def observe(self, name: str, value: float) -> None:
        hist = self._histograms[name]
        hist.append(value)
        if len(hist) > self._max_records:
            self._histograms[name] = hist[-self._max_records :]

    def record_request(
        self,
        latency_ms: float,
        status_code: int,
        method: str = "",
        path: str = "",
        is_error: bool = False,
    ) -> None:
        now = time.time()
        self._request_records.append(
            RequestRecord(
                timestamp=now,
                latency_ms=latency_ms,
                status_code=status_code,
                method=method,
                path=path,
            )
        )
        # Trim old records
        if len(self._request_records) > self._max_records:
            self._request_records = self._request_records[-self._max_records :]

        self.observe("http_request_duration_ms", latency_ms)
        self.increment("http_requests_total")
        if is_error:
            self.increment("http_errors_total")

    def _clean_window(self) -> None:
        """Remove records outside the sliding window."""
        cutoff = time.time() - self._window_seconds
        self._request_records = [r for r in self._request_records if r.timestamp > cutoff]

    def get_rps(self) -> float:
        self._clean_window()
        return len(self._request_records) / max(self._window_seconds, 1)

    def get_error_rate(self) -> float:
        self._clean_window()
        if not self._request_records:
            return 0.0
        errors = sum(1 for r in self._request_records if r.status_code >= 400)
        return errors / len(self._request_records)

    def get_percentile(self, name: str, p: float) -> float:
        """Get the p-th percentile for a histogram."""
        values = self._histograms.get(name, [])
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * p / 100)))
        return sorted_vals[idx]

    def get_metrics(self) -> Dict[str, Any]:
        """Get all current metrics as a dictionary."""
        try:
            import resource

            memory_mb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        except Exception:
            memory_mb = 0.0

        return {
            "service": os.getenv("SERVICE_NAME", "tranc3-api"),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "requests_total": int(self._counters.get("http_requests_total", 0)),
            "requests_per_second": round(self.get_rps(), 2),
            "errors_total": int(self._counters.get("http_errors_total", 0)),
            "error_rate": round(self.get_error_rate(), 4),
            "latency_p50_ms": round(self.get_percentile("http_request_duration_ms", 50), 2),
            "latency_p95_ms": round(self.get_percentile("http_request_duration_ms", 95), 2),
            "latency_p99_ms": round(self.get_percentile("http_request_duration_ms", 99), 2),
            "memory_mb": round(memory_mb, 2),
            "uptime_seconds": int(time.time() - self._start_time),
        }

    def to_prometheus(self) -> str:
        """Export metrics in Prometheus exposition format."""
        svc = os.getenv("SERVICE_NAME", "tranc3-api")
        lines: List[str] = []

        # Counters
        for name, value in self._counters.items():
            prom_name = name.replace(".", "_")
            lines.append(f"# TYPE {prom_name} counter")
            lines.append(f'{prom_name}{{service="{svc}"}} {int(value)}')

        # Gauges
        for name, value in self._gauges.items():
            prom_name = name.replace(".", "_")
            lines.append(f"# TYPE {prom_name} gauge")
            lines.append(f'{prom_name}{{service="{svc}"}} {value}')

        # Histograms — summary format
        for name, values in self._histograms.items():
            if not values:
                continue
            prom_name = name.replace(".", "_")
            sorted_vals = sorted(values)
            for p in [50, 95, 99]:
                idx = max(0, min(len(sorted_vals) - 1, int(len(sorted_vals) * p / 100)))
                lines.append(
                    f'{prom_name}{{service="{svc}",quantile="0.{p:02d}"}} {sorted_vals[idx]:.2f}'
                )
            lines.append(f'{prom_name}_count{{service="{svc}"}} {len(values)}')
            lines.append(f'{prom_name}_sum{{service="{svc}"}} {sum(values):.2f}')

        # Built-in gauges
        metrics = self.get_metrics()
        lines.append(
            f'tranc3_requests_per_second{{service="{svc}"}} {metrics["requests_per_second"]}'
        )
        lines.append(f'tranc3_error_rate{{service="{svc}"}} {metrics["error_rate"]}')
        lines.append(f'tranc3_uptime_seconds{{service="{svc}"}} {metrics["uptime_seconds"]}')

        return "\n".join(lines) + "\n"


class TelemetryMiddleware(BaseHTTPMiddleware):
    """
    FastAPI/Starlette middleware for request telemetry and trace propagation.

    Ported from the-citadel's telemetryMiddleware.
    Adds X-Trace-Id, X-Trancendos-Service, and X-Trancendos-Version headers.
    Records request latency and error rates for Prometheus scraping.

    Usage:
        app.add_middleware(TelemetryMiddleware)
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._telemetry = TelemetryCollector.get_instance()

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.time()

        # Propagate or create trace ID
        trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
        request.state.trace_id = trace_id

        # Process request
        response = await call_next(request)

        # Calculate latency
        latency_ms = (time.time() - start) * 1000
        status_code = response.status_code
        is_error = status_code >= 400

        # Record metrics
        self._telemetry.record_request(
            latency_ms=latency_ms,
            status_code=status_code,
            method=request.method,
            path=request.url.path,
            is_error=is_error,
        )

        # Set response headers
        response.headers["X-Trace-Id"] = trace_id
        response.headers["X-Trancendos-Service"] = os.getenv("SERVICE_NAME", "tranc3-api")
        response.headers["X-Trancendos-Version"] = os.getenv("SERVICE_VERSION", "1.0.0")
        response.headers["X-Trancendos-Mesh-Protocol"] = os.getenv(
            "MESH_ROUTING_PROTOCOL", "static_port"
        )
        response.headers["X-Response-Time-Ms"] = f"{latency_ms:.2f}"

        return response
