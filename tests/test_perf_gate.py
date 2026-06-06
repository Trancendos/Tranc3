"""
REQ-QA-007: Performance regression gate — unit tests.

Tests:
- Gate passes on first run (seeds baseline)
- Gate passes when results meet thresholds
- Gate fails when RPS drops below 85% of baseline
- Gate fails when P99 exceeds 120% of baseline
- --update flag refreshes baseline and exits 0
- All benchmark subjects return valid BenchResult
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


def _import_gate(tmp_baseline: Path):
    """Re-import perf_gate with a patched BASELINE_PATH."""
    for k in list(sys.modules):
        if "perf_gate" in k:
            del sys.modules[k]
    import src.benchmark.perf_gate as mod

    mod.BASELINE_PATH = tmp_baseline
    return mod


def _fake_results(rps=1000.0, p99=5.0):
    from src.benchmark.perf_gate import BenchResult

    return [BenchResult("bench_a", rps, p99 * 0.5, p99, 0.0)]


def test_first_run_seeds_baseline(tmp_path):
    baseline = tmp_path / "baseline.json"
    mod = _import_gate(baseline)
    with patch.object(mod, "_build_suite", return_value=_fake_results()):
        rc = mod.run_gate()
    assert rc == 0
    assert baseline.exists()
    data = json.loads(baseline.read_text())
    assert "bench_a" in data


def test_gate_passes_within_threshold(tmp_path):
    baseline = tmp_path / "baseline.json"
    mod = _import_gate(baseline)
    with patch.object(mod, "_build_suite", return_value=_fake_results(1000, 5)):
        mod.run_gate()  # seed
    with patch.object(mod, "_build_suite", return_value=_fake_results(950, 5.5)):
        rc = mod.run_gate()
    assert rc == 0


def test_gate_fails_rps_regression(tmp_path):
    baseline = tmp_path / "baseline.json"
    mod = _import_gate(baseline)
    with patch.object(mod, "_build_suite", return_value=_fake_results(1000, 5)):
        mod.run_gate()  # seed
    # 800 < 1000 * 0.85 = 850 → regression
    with patch.object(mod, "_build_suite", return_value=_fake_results(800, 5)):
        rc = mod.run_gate()
    assert rc == 1


def test_gate_fails_p99_regression(tmp_path):
    baseline = tmp_path / "baseline.json"
    mod = _import_gate(baseline)
    with patch.object(mod, "_build_suite", return_value=_fake_results(1000, 5)):
        mod.run_gate()  # seed
    # 7 > 5 * 1.20 = 6 → regression
    with patch.object(mod, "_build_suite", return_value=_fake_results(1000, 7)):
        rc = mod.run_gate()
    assert rc == 1


def test_update_refreshes_baseline(tmp_path):
    baseline = tmp_path / "baseline.json"
    mod = _import_gate(baseline)
    with patch.object(mod, "_build_suite", return_value=_fake_results(1000, 5)):
        mod.run_gate()
    with patch.object(mod, "_build_suite", return_value=_fake_results(2000, 2)):
        rc = mod.run_gate(update=True)
    assert rc == 0
    data = json.loads(baseline.read_text())
    assert data["bench_a"]["rps"] == pytest.approx(2000.0)


def test_benchmark_suite_runs():
    """Verify _build_suite returns results without crashing."""
    from src.benchmark.perf_gate import _build_suite

    results = _build_suite()
    assert len(results) >= 1
    for r in results:
        assert r.p99_ms >= 0
        assert r.rps >= 0
        assert 0.0 <= r.error_rate <= 1.0


def test_report_mode_emits_json(tmp_path, capsys):
    baseline = tmp_path / "baseline.json"
    mod = _import_gate(baseline)
    with patch.object(mod, "_build_suite", return_value=_fake_results()):
        mod.run_gate(report=True)
    captured = capsys.readouterr()
    # stdout should contain a JSON array line
    assert any(line.strip().startswith("[") for line in captured.out.splitlines())
