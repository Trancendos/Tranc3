"""P0 workers must expose Prometheus /metrics (mount helper or InfinityWorkerKit)."""

from __future__ import annotations

from pathlib import Path

from tests._repo_io import read_repo_text

ROOT = Path(__file__).resolve().parents[1]

P0_WORKERS = [
    "workers/infinity-ws/worker.py",
    "workers/api-gateway/worker.py",
    "workers/tranc3-ai/worker.py",
    "workers/infinity-void/worker.py",
    "workers/users-service/worker.py",
    "workers/products-service/worker.py",
    "workers/orders-service/worker.py",
    "workers/payments-service/worker.py",
    "workers/notifications/worker.py",
    "workers/infinity-ai/worker.py",
    "workers/monitoring/worker.py",
    "workers/infinity-auth/worker.py",
]

METRICS_MARKERS = (
    '"/metrics"',
    "mount_prometheus_endpoint",
    "InfinityWorkerKit",
    "_mount_endpoints",
)


def test_p0_workers_declare_metrics_endpoint():
    missing = []
    for rel in P0_WORKERS:
        text = read_repo_text(ROOT / rel)
        if not any(m in text for m in METRICS_MARKERS):
            missing.append(rel)
    assert not missing, f"P0 workers missing /metrics wiring: {missing}"
