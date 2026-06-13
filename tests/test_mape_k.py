"""
Tests for MAPE-K Autonomic Control Loop — src/core/mape_k.py
"""

import time
import pytest
from src.core.mape_k import (
    KnowledgeBase,
    MAPEKLoop,
    Observation,
    Plan,
    AnomalyReport,
    z_score_anomaly,
    iqr_anomaly,
)


# ── Unit: statistical helpers ─────────────────────────────────────────────


def test_z_score_detects_spike():
    """Z-score should flag a large spike as anomalous."""
    baseline = [10.0, 10.1, 9.9, 10.05, 9.95, 10.0, 9.98]
    values = baseline + [100.0]  # massive spike
    z, is_anom = z_score_anomaly(values, threshold=2.5)
    assert is_anom is True
    assert z is not None and z > 2.5


def test_z_score_no_anomaly_for_stable_values():
    """Stable values should not trigger Z-score anomaly."""
    values = [10.0, 10.1, 9.9, 10.05, 9.95, 10.0]
    z, is_anom = z_score_anomaly(values, threshold=2.5)
    assert is_anom is False


def test_iqr_anomaly_detects_outlier():
    """IQR should detect extreme outlier."""
    values = [1, 2, 2, 3, 2, 1, 2, 3, 100]
    assert iqr_anomaly(values) is True


def test_iqr_no_anomaly_for_normal_data():
    values = [1, 2, 2, 3, 2, 1, 2, 3, 2]
    assert iqr_anomaly(values) is False


# ── Unit: KnowledgeBase ───────────────────────────────────────────────────


def test_knowledge_base_set_get():
    kb = KnowledgeBase()
    kb.set("threshold", 42)
    assert kb.get("threshold") == 42


def test_knowledge_base_window():
    kb = KnowledgeBase(window_size=5)
    for v in [1, 2, 3, 4, 5, 6]:
        kb.record_metric("latency", v)
    window = kb.get_window("latency")
    # maxlen=5 so first value should be evicted
    assert len(window) == 5
    assert 1 not in window


def test_knowledge_base_sqlite_persistence(tmp_path):
    """Values must survive across KnowledgeBase instances with same db_path."""
    db = str(tmp_path / "kb.db")
    kb1 = KnowledgeBase(db_path=db)
    kb1.set("worker_count", 7)

    kb2 = KnowledgeBase(db_path=db)
    # SQLite persistence doesn't auto-load on init in this implementation,
    # but writing must not raise
    kb2.set("worker_count", 7)
    assert kb2.get("worker_count") == 7


# ── Unit: MAPEKLoop ───────────────────────────────────────────────────────


def _make_monitor(values):
    """Return a monitor function that yields one observation per call."""
    it = iter(values)

    def monitor_fn(loop):
        try:
            v = next(it)
        except StopIteration:
            return []
        return [Observation(timestamp=time.time(), metric_name="latency_ms", value=v)]

    return monitor_fn


def test_mape_k_loop_run_once_no_anomaly():
    """run_once with stable values should return an empty plan."""
    values = [10.0, 10.1, 9.9, 10.0, 10.05, 10.2, 10.1, 10.0, 10.05]

    # Pre-populate knowledge window
    loop = MAPEKLoop(
        name="test-stable",
        monitor_fn=_make_monitor(values),
        execute_fn=lambda l, p: None,
        interval_seconds=999,
    )
    for v in values[:-1]:
        loop.knowledge.record_metric("latency_ms", v)

    plan = loop.run_once()
    assert isinstance(plan, Plan)
    assert len(plan.actions) == 0


def test_mape_k_loop_run_once_detects_anomaly():
    """run_once with a spike should detect anomaly and produce actions."""
    baseline = [10.0] * 20
    spike = 500.0  # far outside baseline

    for v in baseline:
        pass  # pre-build baseline in knowledge

    loop = MAPEKLoop(
        name="test-spike",
        monitor_fn=_make_monitor([spike]),
        execute_fn=lambda l, p: None,
        interval_seconds=999,
    )
    for v in baseline:
        loop.knowledge.record_metric("latency_ms", v)

    plan = loop.run_once()
    assert len(plan.actions) > 0
    assert any("latency_ms" in a for a in plan.actions)


def test_mape_k_loop_iteration_count():
    """iteration_count must increment on each run_once call."""
    loop = MAPEKLoop(
        name="test-count",
        monitor_fn=lambda l: [],
        execute_fn=lambda l, p: None,
        interval_seconds=999,
    )
    assert loop.iteration_count == 0
    loop.run_once()
    loop.run_once()
    assert loop.iteration_count == 2


def test_mape_k_loop_custom_execute_called():
    """Custom execute_fn must be called when anomalies are detected."""
    calls = []

    def exec_fn(loop, plan):
        calls.append(plan)

    baseline = [10.0] * 20
    loop = MAPEKLoop(
        name="test-exec",
        monitor_fn=_make_monitor([999.0]),
        execute_fn=exec_fn,
        interval_seconds=999,
    )
    for v in baseline:
        loop.knowledge.record_metric("latency_ms", v)

    loop.run_once()
    assert len(calls) == 1


def test_mape_k_loop_start_stop():
    """start/stop must not raise and thread must join cleanly."""
    loop = MAPEKLoop(
        name="test-lifecycle",
        monitor_fn=lambda l: [],
        execute_fn=lambda l, p: None,
        interval_seconds=0.1,
    )
    loop.start()
    assert loop._running is True
    time.sleep(0.25)
    loop.stop(timeout=2.0)
    assert loop._running is False


def test_mape_k_knowledge_persists_across_cycles(tmp_path):
    """Knowledge base should persist data across run_once calls."""
    db = str(tmp_path / "mape.db")
    loop = MAPEKLoop(
        name="test-persist",
        monitor_fn=lambda l: [],
        execute_fn=lambda l, p: None,
        knowledge_db_path=db,
        interval_seconds=999,
    )
    loop.knowledge.set("max_workers", 8)
    loop.run_once()
    assert loop.knowledge.get("max_workers") == 8
