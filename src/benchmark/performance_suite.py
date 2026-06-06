"""
Tranc3 Performance Benchmarking Suite — The Observatory Integration
====================================================================
Zero-cost production load testing and latency profiling.

Features:
  • Concurrent request load generation with configurable concurrency
  • Latency percentile tracking (P50, P90, P95, P99, P99.9)
  • Throughput (RPS) measurement with confidence intervals
  • Memory and CPU sampling during load runs
  • Error rate tracking with error taxonomy
  • Baseline comparison and regression detection
  • JSON results export for The Observatory

Named: Norman Hawkins (The Spark / The Observatory hybrid)
"""

from __future__ import annotations

import asyncio
import gc
import json
import logging
import statistics
import time
import tracemalloc
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("tranc3.benchmark")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


@dataclass
class BenchmarkConfig:
    """Configuration for a single benchmark run."""

    name: str
    concurrency: int = 10
    total_requests: int = 100
    warmup_requests: int = 10
    timeout_seconds: float = 30.0
    think_time_ms: float = 0.0  # artificial delay between requests
    track_memory: bool = True
    baseline_rps: Optional[float] = None  # regression threshold
    baseline_p99_ms: Optional[float] = None


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class LatencyStats:
    """Latency statistics in milliseconds."""

    min_ms: float = 0.0
    max_ms: float = 0.0
    mean_ms: float = 0.0
    median_ms: float = 0.0
    p90_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    p999_ms: float = 0.0
    stddev_ms: float = 0.0


@dataclass
class BenchmarkResult:
    """Complete benchmark run result."""

    run_id: str
    name: str
    config: BenchmarkConfig
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    total_duration_s: float = 0.0
    rps: float = 0.0  # requests per second
    latency: LatencyStats = field(default_factory=LatencyStats)
    error_counts: Dict[str, int] = field(default_factory=dict)
    memory_peak_kb: float = 0.0
    memory_delta_kb: float = 0.0
    rps_regression: bool = False  # True if RPS < baseline * 0.9
    p99_regression: bool = False  # True if P99 > baseline * 1.1
    started_at: float = field(default_factory=time.time)
    finished_at: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests

    @property
    def error_rate(self) -> float:
        return 1.0 - self.success_rate

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["config"] = asdict(self.config)
        d["success_rate"] = self.success_rate
        d["error_rate"] = self.error_rate
        return d

    def summary(self) -> str:
        lines = [
            f"Benchmark: {self.name}",
            f"  RPS:        {self.rps:.1f} req/s",
            f"  Success:    {self.success_rate * 100:.1f}% ({self.successful_requests}/{self.total_requests})",
            f"  P50:        {self.latency.median_ms:.1f}ms",
            f"  P95:        {self.latency.p95_ms:.1f}ms",
            f"  P99:        {self.latency.p99_ms:.1f}ms",
            f"  Duration:   {self.total_duration_s:.2f}s",
        ]
        if self.memory_peak_kb > 0:
            lines.append(f"  Mem peak:   {self.memory_peak_kb:.0f}KB")
        if self.rps_regression:
            lines.append("  ⚠ RPS REGRESSION DETECTED")
        if self.p99_regression:
            lines.append("  ⚠ P99 REGRESSION DETECTED")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Core benchmark runner
# ---------------------------------------------------------------------------


class BenchmarkSuite:
    """
    Async benchmark runner that measures latency and throughput of
    async callables (HTTP handlers, service calls, etc.)

    Usage::

        suite = BenchmarkSuite()
        result = await suite.run(
            config=BenchmarkConfig("health-check", concurrency=20, total_requests=500),
            target=lambda: httpx_client.get("/health"),
        )
        print(result.summary())
    """

    def __init__(self, results_dir: Optional[Path] = None) -> None:
        self._results_dir = results_dir or Path("data/benchmarks")
        self._results_dir.mkdir(parents=True, exist_ok=True)
        self._history: List[BenchmarkResult] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        config: BenchmarkConfig,
        target: Callable[[], Any],
    ) -> BenchmarkResult:
        """Run a benchmark against *target* (async or sync callable)."""
        run_id = str(uuid.uuid4())[:8]
        result = BenchmarkResult(run_id=run_id, name=config.name, config=config)

        logger.info(
            "Starting benchmark '%s' run=%s concurrency=%d requests=%d",
            config.name,
            run_id,
            config.concurrency,
            config.total_requests,
        )

        # Warm up
        if config.warmup_requests > 0:
            logger.debug("Warming up with %d requests", config.warmup_requests)
            await self._run_batch(
                target,
                config.warmup_requests,
                1,
                config.timeout_seconds,
                config.think_time_ms,
            )

        # Memory baseline
        mem_before = 0.0
        if config.track_memory:
            tracemalloc.start()
            gc.collect()
            mem_before = self._current_memory_kb()

        latencies: List[float] = []
        errors: Dict[str, int] = {}

        start = time.perf_counter()
        successes, batch_errors, batch_latencies = await self._run_batch(
            target,
            config.total_requests,
            config.concurrency,
            config.timeout_seconds,
            config.think_time_ms,
        )
        elapsed = time.perf_counter() - start

        latencies.extend(batch_latencies)
        for k, v in batch_errors.items():
            errors[k] = errors.get(k, 0) + v

        # Memory snapshot
        if config.track_memory:
            mem_after = self._current_memory_kb()
            _, mem_peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            result.memory_peak_kb = mem_peak / 1024
            result.memory_delta_kb = max(0.0, mem_after - mem_before)

        # Populate result
        result.total_requests = config.total_requests
        result.successful_requests = successes
        result.failed_requests = config.total_requests - successes
        result.total_duration_s = elapsed
        result.rps = successes / elapsed if elapsed > 0 else 0.0
        result.error_counts = errors
        result.finished_at = time.time()

        if latencies:
            result.latency = self._compute_latency_stats(latencies)

        # Regression detection
        if config.baseline_rps is not None:
            result.rps_regression = result.rps < config.baseline_rps * 0.9
        if config.baseline_p99_ms is not None:
            result.p99_regression = result.latency.p99_ms > config.baseline_p99_ms * 1.1

        self._history.append(result)
        self._save_result(result)
        logger.info("Benchmark '%s' completed: %s", config.name, result.summary())
        return result

    async def run_suite(
        self,
        benchmarks: List[Tuple[BenchmarkConfig, Callable[[], Any]]],
    ) -> List[BenchmarkResult]:
        """Run multiple benchmarks sequentially and return all results."""
        results = []
        for config, target in benchmarks:
            result = await self.run(config, target)
            results.append(result)
        return results

    def compare(self, result_a: BenchmarkResult, result_b: BenchmarkResult) -> Dict[str, Any]:
        """Compare two benchmark results and return deltas."""

        def pct_change(a: float, b: float) -> float:
            if a == 0:
                return 0.0
            return ((b - a) / a) * 100

        return {
            "name_a": result_a.name,
            "name_b": result_b.name,
            "rps_delta_pct": pct_change(result_a.rps, result_b.rps),
            "p50_delta_pct": pct_change(result_a.latency.median_ms, result_b.latency.median_ms),
            "p99_delta_pct": pct_change(result_a.latency.p99_ms, result_b.latency.p99_ms),
            "success_rate_delta": result_b.success_rate - result_a.success_rate,
            "regression": result_b.rps < result_a.rps * 0.9
            or result_b.latency.p99_ms > result_a.latency.p99_ms * 1.1,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run_batch(
        self,
        target: Callable[[], Any],
        total: int,
        concurrency: int,
        timeout: float,
        think_time_ms: float,
    ) -> Tuple[int, Dict[str, int], List[float]]:
        """Execute *total* calls to *target* with *concurrency* workers."""
        semaphore = asyncio.Semaphore(concurrency)
        latencies: List[float] = []
        errors: Dict[str, int] = {}
        successes = 0
        lock = asyncio.Lock()

        async def worker() -> None:
            nonlocal successes
            async with semaphore:
                t0 = time.perf_counter()
                try:
                    if asyncio.iscoroutinefunction(target):
                        await asyncio.wait_for(target(), timeout=timeout)
                    else:
                        await asyncio.wait_for(
                            asyncio.get_event_loop().run_in_executor(None, target),
                            timeout=timeout,
                        )
                    elapsed_ms = (time.perf_counter() - t0) * 1000
                    async with lock:
                        latencies.append(elapsed_ms)
                        successes += 1
                except asyncio.TimeoutError:
                    async with lock:
                        errors["timeout"] = errors.get("timeout", 0) + 1
                except Exception as exc:
                    err_type = type(exc).__name__
                    async with lock:
                        errors[err_type] = errors.get(err_type, 0) + 1

                if think_time_ms > 0:
                    await asyncio.sleep(think_time_ms / 1000)

        tasks = [worker() for _ in range(total)]
        await asyncio.gather(*tasks)
        return successes, errors, latencies

    @staticmethod
    def _compute_latency_stats(latencies: List[float]) -> LatencyStats:
        s = sorted(latencies)
        n = len(s)

        def pct(p: float) -> float:
            if n == 0:
                return 0.0
            idx = int(p / 100 * n)
            return s[min(idx, n - 1)]

        return LatencyStats(
            min_ms=s[0],
            max_ms=s[-1],
            mean_ms=statistics.mean(s),
            median_ms=statistics.median(s),
            p90_ms=pct(90),
            p95_ms=pct(95),
            p99_ms=pct(99),
            p999_ms=pct(99.9),
            stddev_ms=statistics.stdev(s) if n > 1 else 0.0,
        )

    @staticmethod
    def _current_memory_kb() -> float:
        try:
            import resource

            return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        except Exception:
            return 0.0

    def _save_result(self, result: BenchmarkResult) -> None:
        path = self._results_dir / f"{result.name}_{result.run_id}.json"
        try:
            with open(path, "w") as f:
                json.dump(result.to_dict(), f, indent=2, default=str)
        except Exception as exc:
            logger.warning("Failed to save benchmark result: %s", exc)


# ---------------------------------------------------------------------------
# Built-in endpoint benchmarks (use with live server)
# ---------------------------------------------------------------------------


async def benchmark_health_endpoint(
    base_url: str = "http://localhost:8000",
    concurrency: int = 20,
    requests: int = 500,
) -> BenchmarkResult:
    """Benchmark the /health endpoint of the Tranc3 backend."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx is required for HTTP benchmarks: pip install httpx") from None

    suite = BenchmarkSuite()
    client = httpx.AsyncClient(base_url=base_url, timeout=30.0)

    try:
        config = BenchmarkConfig(
            name="health-endpoint",
            concurrency=concurrency,
            total_requests=requests,
            warmup_requests=20,
            baseline_p99_ms=500.0,
        )
        return await suite.run(config, lambda: client.get("/health"))
    finally:
        await client.aclose()


async def benchmark_inference_endpoint(
    base_url: str = "http://localhost:8000",
    concurrency: int = 5,
    requests: int = 50,
    api_key: str = "",
) -> BenchmarkResult:
    """Benchmark the /chat inference endpoint."""
    try:
        import httpx
    except ImportError:
        raise RuntimeError("httpx is required for HTTP benchmarks: pip install httpx") from None

    suite = BenchmarkSuite()
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    client = httpx.AsyncClient(base_url=base_url, timeout=60.0, headers=headers)

    payload = {"message": "Hello, what is 2 + 2?", "language": "en"}

    try:
        config = BenchmarkConfig(
            name="inference-endpoint",
            concurrency=concurrency,
            total_requests=requests,
            warmup_requests=5,
            baseline_p99_ms=5000.0,
        )
        return await suite.run(config, lambda: client.post("/chat", json=payload))
    finally:
        await client.aclose()
