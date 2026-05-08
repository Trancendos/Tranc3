# src/observability/metrics.py
# TRANC3 Observability — Prometheus metrics + structured logging

import time
import logging
import structlog
from typing import Optional
from contextlib import contextmanager

# ---------------------------------------------------------------------------
# STRUCTURED LOGGING
# ---------------------------------------------------------------------------
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)

log = structlog.get_logger("tranc3")


# ---------------------------------------------------------------------------
# PROMETHEUS METRICS (lazy import — only if prometheus_client installed)
# ---------------------------------------------------------------------------
try:
    from prometheus_client import Counter, Histogram, Gauge, Summary

    REQUEST_COUNT = Counter(
        "tranc3_requests_total",
        "Total API requests",
        ["endpoint", "method", "status", "tier"],
    )
    REQUEST_LATENCY = Histogram(
        "tranc3_request_duration_seconds",
        "Request latency",
        ["endpoint"],
        buckets=[0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    )
    ACTIVE_USERS = Gauge("tranc3_active_users", "Currently active users")
    PHI_SCORE = Gauge("tranc3_consciousness_phi", "Current consciousness Φ score")
    EMOTION_COUNTER = Counter(
        "tranc3_emotions_total",
        "Detected emotions",
        ["emotion", "language"],
    )
    TOKEN_USAGE = Counter(
        "tranc3_tokens_total",
        "Total tokens processed",
        ["tier", "language"],
    )
    CHURN_RISK = Histogram(
        "tranc3_churn_risk",
        "User churn probability distribution",
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )
    QUALITY_SCORE = Histogram(
        "tranc3_response_quality",
        "Response quality score distribution",
        buckets=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    )
    REVENUE_GAUGE = Gauge("tranc3_revenue_gbp_total", "Total revenue in GBP", ["stream"])

    PROMETHEUS_AVAILABLE = True

except ImportError:
    PROMETHEUS_AVAILABLE = False
    log.warning("prometheus_client not available — metrics disabled")


# ---------------------------------------------------------------------------
# METRIC HELPERS
# ---------------------------------------------------------------------------
def record_request(endpoint: str, method: str, status: int, tier: str, duration_s: float):
    if not PROMETHEUS_AVAILABLE:
        return
    REQUEST_COUNT.labels(endpoint=endpoint, method=method, status=str(status), tier=tier).inc()
    REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration_s)


def record_emotion(emotion: str, language: str):
    if not PROMETHEUS_AVAILABLE:
        return
    EMOTION_COUNTER.labels(emotion=emotion, language=language).inc()


def record_phi(phi: float):
    if not PROMETHEUS_AVAILABLE:
        return
    PHI_SCORE.set(phi)


def record_tokens(count: int, tier: str, language: str):
    if not PROMETHEUS_AVAILABLE:
        return
    TOKEN_USAGE.labels(tier=tier, language=language).inc(count)


def record_churn_risk(probability: float):
    if not PROMETHEUS_AVAILABLE:
        return
    CHURN_RISK.observe(probability)


def record_quality(score: float):
    if not PROMETHEUS_AVAILABLE:
        return
    QUALITY_SCORE.observe(score)


def record_revenue(stream: str, amount: float):
    if not PROMETHEUS_AVAILABLE:
        return
    REVENUE_GAUGE.labels(stream=stream).set(amount)


@contextmanager
def timed_operation(name: str):
    """Context manager to time any operation"""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        log.info("operation_timed", name=name, duration_ms=round(elapsed * 1000, 2))
