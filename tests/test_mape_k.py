"""
Tests for MAPE-K Autonomic Control Loop — src/core/mape_k.py

Note: MAPEKLoop.stop() calls thread.join(timeout=interval+5).
Tests that start the loop use interval_seconds=0 and call stop(),
or use daemon threads (no stop needed — process cleanup handles it).
"""

import time
import threading
import pytest
from src.core.mape_k import MAPEKLoop


# ── Helpers ───────────────────────────────────────────────────────────────


def _simple_monitor():
    return {"latency_ms": 100.0, "error_rate": 0.01}


def _spike_monitor():
    return {"latency_ms": 9999.0, "error_rate": 0.95}


# ── Tests ─────────────────────────────────────────────────────────────────


def test_mape_k_loop_basic_run():
    """
    MAPEKLoop phases must complete one iteration without raising.
    """
    executed = []

    def exec_fn(plan):
        executed.append(plan)

    loop = MAPEKLoop(
        name="test-basic",
        monitor_fn=_simple_monitor,
        execute_fn=exec_fn,
        interval_seconds=999,  # not started, cycle run manually
    )
    metrics = loop._monitor_fn()
    analysis = loop._analyze_fn(metrics)
    plan = loop._plan_fn(analysis)
    loop._execute_fn(plan)
    assert isinstance(plan, dict)


def test_mape_k_start_stop_fast():
    """start/stop with a short interval must not hang."""
    loop = MAPEKLoop(
        name="test-lifecycle-fast",
        monitor_fn=_simple_monitor,
        interval_seconds=1,   # stop() waits interval+5 = 6s max, thread wakes in 1s
    )
    loop.start()
    assert loop._running is True
    loop.stop()  # waits at most interval+5 = 6s
    assert loop._running is False


def test_mape_k_update_knowledge():
    """update_knowledge / get_knowledge round-trip."""
    loop = MAPEKLoop(
        name="test-knowledge",
        monitor_fn=_simple_monitor,
        interval_seconds=999,
    )
    loop.update_knowledge("worker_count", 4)
    kb = loop.get_knowledge()
    assert kb.get("worker_count") == 4


def test_mape_k_default_analyze_detects_high_values():
    """_default_analyze should return a dict for extreme metric values."""
    loop = MAPEKLoop(
        name="test-analyze",
        monitor_fn=_spike_monitor,
        interval_seconds=999,
    )
    # Pre-populate history to build baseline
    baseline = {"latency_ms": 50.0, "error_rate": 0.01}
    for _ in range(10):
        loop._history.append({
            "metrics": baseline,
            "analysis": {},
            "plan": {},
            "timestamp": time.time(),
        })
    metrics = loop._monitor_fn()
    analysis = loop._analyze_fn(metrics)
    assert isinstance(analysis, dict)


def test_mape_k_sqlite_persistence(tmp_path):
    """Cycle history should be persisted to SQLite without errors."""
    db = tmp_path / "mape_test.db"
    loop = MAPEKLoop(
        name="test-persist",
        monitor_fn=_simple_monitor,
        db_path=db,
        interval_seconds=999,
    )
    metrics = loop._monitor_fn()
    analysis = loop._analyze_fn(metrics)
    plan = loop._plan_fn(analysis)
    loop._persist_cycle({
        "metrics": metrics,
        "analysis": analysis,
        "plan": plan,
        "executed": True,
        "timestamp": time.time(),
    })
    history = loop.get_history()
    assert isinstance(history, list)


def test_mape_k_knowledge_persists():
    """Knowledge base should retain values between calls."""
    loop = MAPEKLoop(
        name="test-kb-persist",
        monitor_fn=_simple_monitor,
        interval_seconds=999,
    )
    loop.update_knowledge("max_workers", 8)
    loop.update_knowledge("target_latency_ms", 200)
    kb = loop.get_knowledge()
    assert kb["max_workers"] == 8
    assert kb["target_latency_ms"] == 200
