"""
Tranc3 Observability Package
=============================
Structured logging, Prometheus metrics, distributed tracing, and health aggregation.
Zero-cost: No external APM services. All data stays in-process and SQLite.
"""

from .health import (
    SERVICE_REGISTRY,
    HealthChecker,
    SystemHealth,
)
from .metrics import (
    PROMETHEUS_AVAILABLE,
    log,
    record_churn_risk,
    record_emotion,
    record_phi,
    record_quality,
    record_request,
    record_revenue,
    record_tokens,
    timed_operation,
)
from .tracing import (
    Span,
    Tracer,
    clear_trace,
    current_span_id,
    current_trace_id,
    extract_trace_context,
    get_tracer,
    init_tracing,
    inject_trace_context,
    new_span_id,
    new_trace_id,
    set_trace,
)

__all__ = [
    # Metrics
    "PROMETHEUS_AVAILABLE",
    "record_request",
    "record_emotion",
    "record_phi",
    "record_tokens",
    "record_churn_risk",
    "record_quality",
    "record_revenue",
    "timed_operation",
    "log",
    # Tracing
    "Tracer",
    "Span",
    "current_trace_id",
    "current_span_id",
    "set_trace",
    "clear_trace",
    "new_trace_id",
    "new_span_id",
    "extract_trace_context",
    "inject_trace_context",
    "init_tracing",
    "get_tracer",
    # Health
    "HealthChecker",
    "SystemHealth",
    "SERVICE_REGISTRY",
]
