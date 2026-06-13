"""OpenTelemetry instrumentation helpers — zero-cost, self-hosted Tempo/Collector.

Usage:
    from src.observability.otel import instrument, get_tracer, trace_span

    @instrument("my_operation")
    async def my_handler(request):
        async with trace_span("db_query") as span:
            span.set_attribute("db.table", "users")
            ...

Zero-dep fallback: if opentelemetry packages are absent, all calls become no-ops
so workers function without the optional dependency installed.
"""

from __future__ import annotations

import functools
import logging
import os
import time
from contextlib import asynccontextmanager, contextmanager
from typing import Any, AsyncGenerator, Callable, Generator

logger = logging.getLogger(__name__)

OTEL_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")
SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "tranc3")
_ENABLED = os.getenv("OTEL_ENABLED", "true").lower() not in ("false", "0", "no")

# ── Try to load real OpenTelemetry SDK ────────────────────────────────────────
_tracer = None
_meter = None

try:
    if _ENABLED:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": SERVICE_NAME,
                "service.namespace": "tranc3",
                "deployment.environment": os.getenv("ENVIRONMENT", "production"),
            }
        )

        _tp = TracerProvider(resource=resource)
        _tp.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=OTEL_ENDPOINT),
                max_queue_size=2048,
                max_export_batch_size=512,
                export_timeout_millis=10_000,
            )
        )
        trace.set_tracer_provider(_tp)
        _tracer = trace.get_tracer(SERVICE_NAME)

        _reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=OTEL_ENDPOINT),
            export_interval_millis=60_000,
        )
        _mp = MeterProvider(resource=resource, metric_readers=[_reader])
        otel_metrics.set_meter_provider(_mp)
        _meter = otel_metrics.get_meter(SERVICE_NAME)

        logger.info("OpenTelemetry SDK initialised → %s", OTEL_ENDPOINT)

except ImportError:
    logger.debug("opentelemetry packages not installed — tracing disabled (no-op mode)")
except Exception as exc:
    logger.warning("OpenTelemetry init failed: %s — falling back to no-op", exc)


# ── Public API ────────────────────────────────────────────────────────────────


def init_otel(service_name: str | None = None) -> None:
    """Initialise OpenTelemetry for the calling worker.

    Call this once at startup, before ``FastAPIInstrumentor.instrument_app(app)``.
    If ``service_name`` is provided it overrides the ``OTEL_SERVICE_NAME`` env var
    for the lifetime of this process.  Safe to call multiple times — subsequent
    calls are no-ops when OTel is already initialised.
    """
    global _tracer, _meter

    if not _ENABLED:
        return

    effective_name = service_name or SERVICE_NAME

    # Already initialised — nothing to do
    if _tracer is not None:
        return

    try:
        from opentelemetry import metrics as otel_metrics
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                "service.name": effective_name,
                "service.namespace": "tranc3",
                "deployment.environment": os.getenv("ENVIRONMENT", "production"),
            }
        )

        tp = TracerProvider(resource=resource)
        tp.add_span_processor(
            BatchSpanProcessor(
                OTLPSpanExporter(endpoint=OTEL_ENDPOINT),
                max_queue_size=2048,
                max_export_batch_size=512,
                export_timeout_millis=10_000,
            )
        )
        trace.set_tracer_provider(tp)
        _tracer = trace.get_tracer(effective_name)

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=OTEL_ENDPOINT),
            export_interval_millis=60_000,
        )
        mp = MeterProvider(resource=resource, metric_readers=[reader])
        otel_metrics.set_meter_provider(mp)
        _meter = otel_metrics.get_meter(effective_name)

        logger.info("OpenTelemetry SDK initialised for %s → %s", effective_name, OTEL_ENDPOINT)

    except ImportError:
        logger.debug("opentelemetry packages not installed — tracing disabled (no-op mode)")
    except Exception as exc:
        logger.warning("OpenTelemetry init_otel failed for %s: %s — no-op", effective_name, exc)


def get_tracer():
    return _tracer


def get_meter():
    return _meter


@contextmanager
def trace_span(name: str, attributes: dict[str, Any] | None = None) -> Generator:
    """Synchronous context manager that wraps a code block in an OTEL span."""
    if _tracer is None:
        yield _NullSpan()
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


@asynccontextmanager
async def async_trace_span(name: str, attributes: dict[str, Any] | None = None) -> AsyncGenerator:
    """Async context manager that wraps an async block in an OTEL span."""
    if _tracer is None:
        yield _NullSpan()
        return
    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        yield span


def instrument(operation_name: str | None = None, record_exception: bool = True):
    """Decorator that wraps a sync or async function in an OTEL span.

    @instrument("llm.generate")
    async def generate(prompt: str): ...
    """

    def decorator(fn: Callable) -> Callable:
        span_name = operation_name or f"{fn.__module__}.{fn.__qualname__}"

        if _is_async(fn):

            @functools.wraps(fn)
            async def async_wrapper(*args, **kwargs):
                if _tracer is None:
                    return await fn(*args, **kwargs)
                with _tracer.start_as_current_span(span_name) as span:
                    t0 = time.perf_counter()
                    try:
                        result = await fn(*args, **kwargs)
                        span.set_attribute("success", True)
                        return result
                    except Exception as exc:
                        span.set_attribute("success", False)
                        span.set_attribute("error.type", type(exc).__name__)
                        if record_exception:
                            span.record_exception(exc)
                        raise
                    finally:
                        span.set_attribute(
                            "duration_ms", round((time.perf_counter() - t0) * 1000, 2)
                        )

            return async_wrapper
        else:

            @functools.wraps(fn)
            def sync_wrapper(*args, **kwargs):
                if _tracer is None:
                    return fn(*args, **kwargs)
                with _tracer.start_as_current_span(span_name) as span:
                    t0 = time.perf_counter()
                    try:
                        result = fn(*args, **kwargs)
                        span.set_attribute("success", True)
                        return result
                    except Exception as exc:
                        span.set_attribute("success", False)
                        span.set_attribute("error.type", type(exc).__name__)
                        if record_exception:
                            span.record_exception(exc)
                        raise
                    finally:
                        span.set_attribute(
                            "duration_ms", round((time.perf_counter() - t0) * 1000, 2)
                        )

            return sync_wrapper

    return decorator


def extract_trace_context(headers: dict) -> dict:
    """Extract W3C traceparent/tracestate from incoming HTTP headers."""
    return {
        "traceparent": headers.get("traceparent", ""),
        "tracestate": headers.get("tracestate", ""),
    }


def inject_trace_context(headers: dict | None = None) -> dict:
    """Inject current span context as W3C traceparent into outgoing headers."""
    out = dict(headers or {})
    if _tracer is None:
        return out
    try:
        from opentelemetry.propagate import inject

        inject(out)
    except Exception:
        pass
    return out


# ── Counter / gauge helpers (work even when meter is None) ────────────────────


class _NullCounter:
    def add(self, *a, **kw):
        pass

    def record(self, *a, **kw):
        pass


class _NullSpan:
    def set_attribute(self, *a, **kw):
        pass

    def record_exception(self, *a, **kw):
        pass

    def set_status(self, *a, **kw):
        pass


def counter(name: str, description: str = "", unit: str = "1"):
    if _meter is None:
        return _NullCounter()
    return _meter.create_counter(name, description=description, unit=unit)


def histogram(name: str, description: str = "", unit: str = "ms"):
    if _meter is None:
        return _NullCounter()
    return _meter.create_histogram(name, description=description, unit=unit)


def _is_async(fn: Callable) -> bool:
    import asyncio
    import inspect

    return asyncio.iscoroutinefunction(fn) or inspect.iscoroutinefunction(fn)
