"""Chaos Party Observatory trend regression contracts (no external services)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from tests._worker_import_utils import import_worker

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "workers" / "chaos-party" / "observatory_bridge.py"


def _history(*, baseline: list[str], recent: list[str]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute(
        "CREATE TABLE test_runs (id INTEGER PRIMARY KEY, name TEXT, status TEXT)"
    )
    # Trend queries order by descending ID: baseline must precede recent.
    conn.executemany(
        "INSERT INTO test_runs (name, status) VALUES (?, ?)",
        [("example", status) for status in baseline + recent],
    )
    return conn


def test_all_skipped_recent_window_reports_no_prediction_or_regression():
    bridge = import_worker("chaos_trend_skips", BRIDGE)
    conn = _history(baseline=["pass"] * 10, recent=["skip"] * 10)
    try:
        result = bridge.analyse_trend(conn, "example")
    finally:
        conn.close()
    assert result["recent_pass_rate"] is None
    assert result["baseline_pass_rate"] == 1.0
    assert result["predicted_next_fail"] is None
    assert result["confidence_floor"] is None
    assert result["regression"] is False
    assert result["trend"] == "insufficient_data"


def test_all_skipped_history_never_predicts_failure():
    bridge = import_worker("chaos_trend_only_skips", BRIDGE)
    conn = _history(baseline=[], recent=["skip"] * 12)
    try:
        result = bridge.analyse_trend(conn, "example")
    finally:
        conn.close()
    assert result["trend"] == "insufficient_data"
    assert result["predicted_next_fail"] is None
    assert result["regression"] is False


def test_genuine_pass_to_fail_regression_remains_detected():
    bridge = import_worker("chaos_trend_real_failure", BRIDGE)
    conn = _history(baseline=["pass"] * 10, recent=["fail"] * 10)
    try:
        result = bridge.analyse_trend(conn, "example")
    finally:
        conn.close()
    assert result["baseline_pass_rate"] == 1.0
    assert result["recent_pass_rate"] == 0.0
    assert result["predicted_next_fail"] == 1.0
    assert result["regression"] is True
    assert result["trend"] == "regression"
