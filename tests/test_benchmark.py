"""
Tests for Tranc3 Performance Benchmarking Suite.
Validates the BenchmarkSuite against sync and async targets.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest

from src.benchmark.performance_suite import (
    BenchmarkConfig,
    BenchmarkResult,
    BenchmarkSuite,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_suite(tmp_path: Path) -> BenchmarkSuite:
    return BenchmarkSuite(results_dir=tmp_path / "benchmarks")


# ---------------------------------------------------------------------------
# Unit tests — async target
# ---------------------------------------------------------------------------

class TestBenchmarkSuiteAsync:
    """Test suite with an async target."""

    @pytest.mark.asyncio
    async def test_basic_run_returns_result(self, tmp_suite: BenchmarkSuite) -> None:
        async def fast_target() -> None:
            await asyncio.sleep(0.001)

        config = BenchmarkConfig(
            name="test-async",
            concurrency=5,
            total_requests=20,
            warmup_requests=2,
            track_memory=False,
        )
        result = await tmp_suite.run(config, fast_target)
        assert isinstance(result, BenchmarkResult)
        assert result.name == "test-async"
        assert result.total_requests == 20

    @pytest.mark.asyncio
    async def test_success_rate_all_pass(self, tmp_suite: BenchmarkSuite) -> None:
        async def always_ok() -> str:
            return "ok"

        config = BenchmarkConfig(
            name="all-pass",
            concurrency=3,
            total_requests=15,
            warmup_requests=0,
            track_memory=False,
        )
        result = await tmp_suite.run(config, always_ok)
        assert result.successful_requests == 15
        assert result.failed_requests == 0
        assert result.success_rate == 1.0

    @pytest.mark.asyncio
    async def test_error_tracking(self, tmp_suite: BenchmarkSuite) -> None:
        call_count = {"n": 0}

        async def sometimes_fails() -> None:
            call_count["n"] += 1
            if call_count["n"] % 3 == 0:
                raise ValueError("simulated error")

        config = BenchmarkConfig(
            name="errors",
            concurrency=2,
            total_requests=12,
            warmup_requests=0,
            track_memory=False,
        )
        result = await tmp_suite.run(config, sometimes_fails)
        assert result.failed_requests > 0
        assert "ValueError" in result.error_counts

    @pytest.mark.asyncio
    async def test_latency_stats_computed(self, tmp_suite: BenchmarkSuite) -> None:
        async def variable_latency() -> None:
            import random
            await asyncio.sleep(random.uniform(0.001, 0.005))

        config = BenchmarkConfig(
            name="latency-stats",
            concurrency=5,
            total_requests=30,
            warmup_requests=5,
            track_memory=False,
        )
        result = await tmp_suite.run(config, variable_latency)
        assert result.latency.min_ms > 0
        assert result.latency.max_ms >= result.latency.min_ms
        assert result.latency.p99_ms >= result.latency.p95_ms >= result.latency.p90_ms

    @pytest.mark.asyncio
    async def test_rps_positive(self, tmp_suite: BenchmarkSuite) -> None:
        async def instant() -> None:
            pass

        config = BenchmarkConfig(
            name="rps-test",
            concurrency=10,
            total_requests=50,
            warmup_requests=0,
            track_memory=False,
        )
        result = await tmp_suite.run(config, instant)
        assert result.rps > 0

    @pytest.mark.asyncio
    async def test_regression_detection_rps(self, tmp_suite: BenchmarkSuite) -> None:
        async def slow_target() -> None:
            await asyncio.sleep(0.05)

        config = BenchmarkConfig(
            name="regression",
            concurrency=2,
            total_requests=5,
            warmup_requests=0,
            track_memory=False,
            baseline_rps=10000.0,   # impossibly high baseline → regression
        )
        result = await tmp_suite.run(config, slow_target)
        assert result.rps_regression is True

    @pytest.mark.asyncio
    async def test_no_regression_fast_target(self, tmp_suite: BenchmarkSuite) -> None:
        async def instant() -> None:
            pass

        config = BenchmarkConfig(
            name="no-regression",
            concurrency=5,
            total_requests=20,
            warmup_requests=0,
            track_memory=False,
            baseline_rps=0.001,     # trivially low baseline → no regression
        )
        result = await tmp_suite.run(config, instant)
        assert result.rps_regression is False

    @pytest.mark.asyncio
    async def test_result_saved_to_disk(self, tmp_suite: BenchmarkSuite, tmp_path: Path) -> None:
        async def noop() -> None:
            pass

        config = BenchmarkConfig(
            name="disk-save",
            concurrency=2,
            total_requests=5,
            warmup_requests=0,
            track_memory=False,
        )
        await tmp_suite.run(config, noop)
        saved_files = list((tmp_path / "benchmarks").glob("disk-save_*.json"))
        assert len(saved_files) == 1


# ---------------------------------------------------------------------------
# Unit tests — sync target
# ---------------------------------------------------------------------------

class TestBenchmarkSuiteSync:
    @pytest.mark.asyncio
    async def test_sync_target_runs(self, tmp_suite: BenchmarkSuite) -> None:
        def sync_fn() -> str:
            return "sync result"

        config = BenchmarkConfig(
            name="sync-target",
            concurrency=3,
            total_requests=10,
            warmup_requests=2,
            track_memory=False,
        )
        result = await tmp_suite.run(config, sync_fn)
        assert result.successful_requests == 10


# ---------------------------------------------------------------------------
# Unit tests — compare()
# ---------------------------------------------------------------------------

class TestBenchmarkCompare:
    @pytest.mark.asyncio
    async def test_compare_returns_deltas(self, tmp_suite: BenchmarkSuite) -> None:
        async def fast() -> None:
            await asyncio.sleep(0.001)

        async def slow() -> None:
            await asyncio.sleep(0.01)

        cfg_a = BenchmarkConfig("fast", concurrency=5, total_requests=20, warmup_requests=0, track_memory=False)
        cfg_b = BenchmarkConfig("slow", concurrency=5, total_requests=20, warmup_requests=0, track_memory=False)

        r_a = await tmp_suite.run(cfg_a, fast)
        r_b = await tmp_suite.run(cfg_b, slow)

        cmp = tmp_suite.compare(r_a, r_b)
        assert "rps_delta_pct" in cmp
        assert "p99_delta_pct" in cmp
        assert isinstance(cmp["regression"], bool)

    @pytest.mark.asyncio
    async def test_compare_equal_targets(self, tmp_suite: BenchmarkSuite) -> None:
        async def same() -> None:
            pass

        cfg = BenchmarkConfig("same", concurrency=3, total_requests=10, warmup_requests=0, track_memory=False)
        r1 = await tmp_suite.run(cfg, same)
        r2 = await tmp_suite.run(cfg, same)
        cmp = tmp_suite.compare(r1, r2)
        assert abs(cmp["success_rate_delta"]) < 0.01


# ---------------------------------------------------------------------------
# Unit tests — LatencyStats
# ---------------------------------------------------------------------------

class TestLatencyStats:
    def test_compute_latency_stats(self) -> None:
        latencies = [10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 100.0]
        stats = BenchmarkSuite._compute_latency_stats(latencies)
        assert stats.min_ms == 10.0
        assert stats.max_ms == 100.0
        assert stats.mean_ms == 55.0
        assert stats.p99_ms >= stats.p95_ms

    def test_empty_latencies(self) -> None:
        stats = BenchmarkSuite._compute_latency_stats([1.0])
        assert stats.min_ms == 1.0
        assert stats.max_ms == 1.0

    def test_single_latency(self) -> None:
        stats = BenchmarkSuite._compute_latency_stats([42.0])
        assert stats.median_ms == 42.0
        assert stats.stddev_ms == 0.0


# ---------------------------------------------------------------------------
# BenchmarkResult helpers
# ---------------------------------------------------------------------------

class TestBenchmarkResult:
    def test_success_rate_zero_total(self) -> None:
        config = BenchmarkConfig("test")
        result = BenchmarkResult(run_id="x", name="test", config=config)
        assert result.success_rate == 0.0
        assert result.error_rate == 1.0

    def test_to_dict_serializable(self) -> None:
        import json
        config = BenchmarkConfig("to-dict")
        result = BenchmarkResult(run_id="abc", name="to-dict", config=config)
        result.total_requests = 10
        result.successful_requests = 9
        d = result.to_dict()
        serialized = json.dumps(d, default=str)
        assert "to-dict" in serialized

    def test_summary_includes_rps(self) -> None:
        config = BenchmarkConfig("summary-test")
        result = BenchmarkResult(run_id="y", name="summary-test", config=config)
        result.rps = 123.4
        result.total_requests = 100
        result.successful_requests = 95
        summary = result.summary()
        assert "123.4" in summary
        assert "summary-test" in summary
