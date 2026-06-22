"""Observatory worker configuration — The Observatory (Norman Hawkins)."""

from __future__ import annotations

import os

WORKER_NAME = "observatory"
WORKER_PORT = int(os.environ.get("OBSERVATORY_PORT", "8040"))
DB_PATH = os.environ.get("OBSERVATORY_DB_PATH", "/data/observatory.db")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

# ── Backend endpoints (all free/self-hosted) ──────────────────────────────────
SIGNOZ_URL = os.environ.get("SIGNOZ_URL", "http://signoz-query-service:8080")
JAEGER_URL = os.environ.get("JAEGER_URL", "http://jaeger:16686")
TEMPO_URL = os.environ.get("TEMPO_URL", "http://tempo:3200")
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
VICTORIAMETRICS_URL = os.environ.get("VICTORIAMETRICS_URL", "http://victoriametrics:8428")
LOKI_URL = os.environ.get("LOKI_URL", "http://loki:3100")
NETDATA_URL = os.environ.get("NETDATA_URL", "http://netdata:19999")
GRAFANA_URL = os.environ.get("GRAFANA_URL", "http://grafana:3000")

# ── OTel push endpoint (our own collector) ───────────────────────────────────
OTEL_ENDPOINT = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "http://otel-collector:4317")

# ── Adaptive rotation: ordered list of metrics query backends ────────────────
# System tries each in order; falls back on connection error.
METRICS_BACKENDS = [
    b.strip()
    for b in os.environ.get(
        "OBSERVATORY_METRICS_BACKENDS",
        f"{VICTORIAMETRICS_URL},{PROMETHEUS_URL}",
    ).split(",")
    if b.strip()
]

# ── Adaptive rotation: ordered list of trace query backends ─────────────────
TRACE_BACKENDS = [
    b.strip()
    for b in os.environ.get(
        "OBSERVATORY_TRACE_BACKENDS",
        f"{TEMPO_URL},{JAEGER_URL}",
    ).split(",")
    if b.strip()
]

# ── Adaptive rotation: ordered list of log query backends ────────────────────
LOG_BACKENDS = [
    b.strip()
    for b in os.environ.get(
        "OBSERVATORY_LOG_BACKENDS",
        LOKI_URL,
    ).split(",")
    if b.strip()
]

# ── ThresholdGuard limits (requests per hour) ─────────────────────────────────
THRESHOLD_SIGNOZ = int(os.environ.get("THRESHOLD_SIGNOZ", "1000"))
THRESHOLD_JAEGER = int(os.environ.get("THRESHOLD_JAEGER", "2000"))
THRESHOLD_TEMPO = int(os.environ.get("THRESHOLD_TEMPO", "2000"))
THRESHOLD_VICTORIA = int(os.environ.get("THRESHOLD_VICTORIA", "5000"))
THRESHOLD_PROMETHEUS = int(os.environ.get("THRESHOLD_PROMETHEUS", "5000"))
THRESHOLD_LOKI = int(os.environ.get("THRESHOLD_LOKI", "2000"))
THRESHOLD_NETDATA = int(os.environ.get("THRESHOLD_NETDATA", "3000"))
THRESHOLD_WINDOW_SECONDS = int(os.environ.get("THRESHOLD_WINDOW_SECONDS", "3600"))
ACO_DECAY = float(os.environ.get("ACO_DECAY", "0.95"))
