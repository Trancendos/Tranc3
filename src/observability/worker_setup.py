"""Shared one-call observability setup for every Tranc3 FastAPI worker.

Usage (in any worker's startup section):
    from src.observability.worker_setup import instrument_worker
    instrument_worker(app, service_name="tranc3.my-service", worker_port=8010)

What it wires up:
  1. prometheus-fastapi-instrumentator — auto-instruments every route with:
       http_requests_total{method, handler, status}
       http_request_duration_seconds{method, handler}
     and mounts a /metrics endpoint served by prometheus_client REGISTRY.
  2. OpenTelemetry SDK + FastAPI instrumentation — traces every request;
     exports via OTLP gRPC to otel-collector:4317 (configurable via env).
  3. OTel Redis instrumentation (if redis is installed).
  4. OTel aiohttp instrumentation (if aiohttp is installed).

All components degrade gracefully to no-ops if their packages are absent —
workers run without any monitoring package installed.

Zero-cost: prometheus_client + opentelemetry are MIT/Apache 2.0.
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI

logger = logging.getLogger(__name__)


def instrument_worker(
    app: "FastAPI",
    service_name: str,
    worker_port: int | None = None,
    enable_prometheus: bool = True,
    enable_otel: bool = True,
    metrics_path: str = "/metrics",
    exclude_paths: list[str] | None = None,
) -> None:
    """Wire Prometheus + OTel instrumentation onto a FastAPI app.

    Safe to call multiple times — subsequent calls for the same app are no-ops.
    """
    if getattr(app.state, "_tranc3_instrumented", False):
        return

    _excluded = set(exclude_paths or []) | {metrics_path, "/health", "/ready", "/favicon.ico"}

    # ── 1. Prometheus FastAPI Instrumentator ─────────────────────────────────
    if enable_prometheus and os.getenv("PROMETHEUS_ENABLED", "true").lower() not in ("false", "0"):
        try:
            from prometheus_fastapi_instrumentator import Instrumentator

            instrumentator = Instrumentator(
                should_group_status_codes=False,
                should_ignore_untemplated=True,
                should_respect_env_var=False,
                should_instrument_requests_inprogress=True,
                excluded_handlers=[p for p in _excluded],
                inprogress_name=f"{_sanitise(service_name)}_inprogress_requests",
                inprogress_labels=True,
            )
            instrumentator.instrument(app)
            instrumentator.expose(app, endpoint=metrics_path, include_in_schema=False)
            logger.info("Prometheus instrumentation active for %s → %s", service_name, metrics_path)
        except ImportError:
            logger.debug("prometheus-fastapi-instrumentator not installed — metrics passive")
        except Exception as exc:
            logger.warning("Prometheus instrumentator setup failed: %s", exc)

    # ── 2. OpenTelemetry SDK ──────────────────────────────────────────────────
    if enable_otel and os.getenv("OTEL_ENABLED", "true").lower() not in ("false", "0"):
        try:
            from src.observability.otel import init_otel

            init_otel(service_name=service_name)
        except ImportError:
            logger.debug("src.observability.otel not available — skipping OTel init")
        except Exception as exc:
            logger.warning("OTel init_otel failed: %s", exc)

        # FastAPI auto-instrumentation
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(
                app,
                excluded_urls=",".join(_excluded),
                tracer_provider=None,  # uses global provider set by init_otel
            )
            logger.debug("OTel FastAPI instrumentation active for %s", service_name)
        except ImportError:
            logger.debug("opentelemetry-instrumentation-fastapi not installed")
        except Exception as exc:
            logger.warning("OTel FastAPI instrumentor failed: %s", exc)

        # Redis auto-instrumentation
        try:
            from opentelemetry.instrumentation.redis import RedisInstrumentor

            RedisInstrumentor().instrument()
            logger.debug("OTel Redis instrumentation active")
        except (ImportError, Exception):
            pass

        # aiohttp auto-instrumentation
        try:
            from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

            AioHttpClientInstrumentor().instrument()
            logger.debug("OTel aiohttp-client instrumentation active")
        except (ImportError, Exception):
            pass

    app.state._tranc3_instrumented = True
    app.state._tranc3_service_name = service_name
    if worker_port:
        app.state._tranc3_worker_port = worker_port


def _sanitise(name: str) -> str:
    """Convert service name to a valid Prometheus metric name prefix."""
    return name.replace(".", "_").replace("-", "_").replace("/", "_")
