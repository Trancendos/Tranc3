"""
Worker Intelligence — Predictive Health Tracking
=================================================
Tracks health scores (0-100) for platform workers based on response
time, error rate, and availability. Integrates with CircuitBreaker
from src/mesh/ and uses linear trend analysis to warn before failure.

Zero-cost: Pure Python stdlib only.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Deque, Dict, List, Tuple

logger = logging.getLogger("tranc3.core.worker_intelligence")


# ── Data classes ──────────────────────────────────────────────────────────


@dataclass
class HealthSample:
    """One health data point for a worker."""
    timestamp: float
    response_time_ms: float
    is_error: bool
    is_available: bool


@dataclass
class WorkerHealthReport:
    """Snapshot health report for a worker."""
    worker_id: str
    health_score: float          # 0-100
    trend: str                   # "stable" | "improving" | "degrading"
    trend_slope: float           # positive = improving, negative = degrading
    predicted_score_1m: float    # predicted score in 1 minute
    warning: bool                # True if predicted failure within threshold
    error_rate: float
    avg_response_ms: float
    p95_response_ms: float
    availability: float          # fraction 0..1
    circuit_state: str           # "closed" | "open" | "half-open" | "unknown"
    sample_count: int


# ── Worker tracker ────────────────────────────────────────────────────────


class _WorkerState:
    """Internal state for a single tracked worker."""

    def __init__(self, worker_id: str, window_size: int = 200) -> None:
        self.worker_id = worker_id
        self.samples: Deque[HealthSample] = deque(maxlen=window_size)
        self.circuit_breaker: Any = None  # Optional CircuitBreaker reference
        self.custom_weight: float = 1.0

    def add_sample(
        self,
        response_time_ms: float,
        is_error: bool = False,
        is_available: bool = True,
    ) -> None:
        self.samples.append(
            HealthSample(
                timestamp=time.monotonic(),
                response_time_ms=response_time_ms,
                is_error=is_error,
                is_available=is_available,
            )
        )

    def recent_samples(self, window_s: float = 60.0) -> List[HealthSample]:
        now = time.monotonic()
        return [s for s in self.samples if now - s.timestamp <= window_s]


# ── WorkerIntelligence ────────────────────────────────────────────────────


class WorkerIntelligence:
    """
    Health-score engine for a fleet of platform workers.

    Health score formula (0-100):
      score = 40 * availability
            + 40 * (1 - error_rate)
            + 20 * latency_score

    where latency_score = 1.0 when avg_ms <= target_ms,
    decays toward 0 as avg_ms approaches ceiling_ms.

    Usage::

        wi = WorkerIntelligence()
        wi.register("inference-worker-1")
        wi.record("inference-worker-1", response_ms=120.0, is_error=False)
        report = wi.health_report("inference-worker-1")
        if report.warning:
            # scale up or reroute traffic
    """

    def __init__(
        self,
        target_latency_ms: float = 300.0,
        ceiling_latency_ms: float = 5000.0,
        window_s: float = 60.0,
        warning_score_threshold: float = 40.0,
        prediction_horizon_s: float = 60.0,
        sample_window: int = 200,
    ) -> None:
        self._lock = threading.RLock()
        self._workers: Dict[str, _WorkerState] = {}
        self._target_ms = target_latency_ms
        self._ceiling_ms = ceiling_latency_ms
        self._window_s = window_s
        self._warning_threshold = warning_score_threshold
        self._prediction_horizon_s = prediction_horizon_s
        self._sample_window = sample_window

    # ── Registration ──────────────────────────────────────────────────────

    def register(
        self,
        worker_id: str,
        circuit_breaker: Any = None,
    ) -> "WorkerIntelligence":
        """Register a worker for health tracking."""
        with self._lock:
            if worker_id not in self._workers:
                state = _WorkerState(worker_id, window_size=self._sample_window)
                state.circuit_breaker = circuit_breaker
                self._workers[worker_id] = state
        return self

    def attach_circuit_breaker(self, worker_id: str, cb: Any) -> None:
        """Attach a CircuitBreaker instance post-registration."""
        with self._lock:
            state = self._get_state(worker_id)
            state.circuit_breaker = cb

    # ── Data ingestion ────────────────────────────────────────────────────

    def record(
        self,
        worker_id: str,
        response_ms: float,
        is_error: bool = False,
        is_available: bool = True,
    ) -> None:
        """Record one response observation for *worker_id*."""
        with self._lock:
            state = self._get_state(worker_id)
            state.add_sample(response_ms, is_error, is_available)
            # Mirror into circuit breaker if attached
            if state.circuit_breaker is not None:
                try:
                    if is_error:
                        state.circuit_breaker.record_failure()
                    else:
                        state.circuit_breaker.record_success()
                except Exception:
                    pass

    # ── Reporting ─────────────────────────────────────────────────────────

    def health_score(self, worker_id: str) -> float:
        """Return current health score (0-100) for *worker_id*."""
        return self.health_report(worker_id).health_score

    def health_report(self, worker_id: str) -> WorkerHealthReport:
        """Full health report for *worker_id*."""
        with self._lock:
            state = self._get_state(worker_id)
            samples = state.recent_samples(self._window_s)
            score, err_rate, avg_ms, p95_ms, avail = self._compute_score(samples)
            trend, slope = self._compute_trend(state)
            predicted = self._predict(score, slope)
            warning = predicted < self._warning_threshold
            cb_state = self._get_cb_state(state)

            return WorkerHealthReport(
                worker_id=worker_id,
                health_score=score,
                trend=trend,
                trend_slope=slope,
                predicted_score_1m=predicted,
                warning=warning,
                error_rate=err_rate,
                avg_response_ms=avg_ms,
                p95_response_ms=p95_ms,
                availability=avail,
                circuit_state=cb_state,
                sample_count=len(samples),
            )

    def all_reports(self) -> Dict[str, WorkerHealthReport]:
        """Return health reports for all registered workers."""
        with self._lock:
            ids = list(self._workers.keys())
        return {wid: self.health_report(wid) for wid in ids}

    def list_workers(self) -> List[str]:
        with self._lock:
            return list(self._workers.keys())

    # ── Internal helpers ──────────────────────────────────────────────────

    def _get_state(self, worker_id: str) -> _WorkerState:
        if worker_id not in self._workers:
            self._workers[worker_id] = _WorkerState(
                worker_id, window_size=self._sample_window
            )
        return self._workers[worker_id]

    def _compute_score(
        self, samples: List[HealthSample]
    ) -> Tuple[float, float, float, float, float]:
        if not samples:
            return 50.0, 0.0, 0.0, 0.0, 1.0

        total = len(samples)
        errors = sum(1 for s in samples if s.is_error)
        unavail = sum(1 for s in samples if not s.is_available)
        error_rate = errors / total
        availability = 1.0 - (unavail / total)
        latencies = [s.response_time_ms for s in samples]
        avg_ms = sum(latencies) / len(latencies)
        p95_ms = sorted(latencies)[int(len(latencies) * 0.95)]

        # Latency score: 1.0 at target, approaches 0 at ceiling
        if avg_ms <= self._target_ms:
            lat_score = 1.0
        elif avg_ms >= self._ceiling_ms:
            lat_score = 0.0
        else:
            lat_score = 1.0 - (avg_ms - self._target_ms) / (
                self._ceiling_ms - self._target_ms
            )

        score = (
            40.0 * availability
            + 40.0 * (1.0 - error_rate)
            + 20.0 * lat_score
        )
        return max(0.0, min(100.0, score)), error_rate, avg_ms, p95_ms, availability

    def _compute_trend(self, state: _WorkerState) -> Tuple[str, float]:
        """Compute linear regression slope over recent health score approximations."""
        # Use last 10 non-overlapping windows to build a time series of scores
        all_samples = list(state.samples)
        if len(all_samples) < 10:
            return "stable", 0.0

        # Split into 5 equal segments
        chunk = max(1, len(all_samples) // 5)
        points: List[Tuple[float, float]] = []
        for i in range(5):
            seg = all_samples[i * chunk : (i + 1) * chunk]
            if seg:
                score, *_ = self._compute_score(seg)
                t = seg[-1].timestamp
                points.append((t, score))

        if len(points) < 2:
            return "stable", 0.0

        slope = self._linear_slope(points)

        if slope > 0.5:
            return "improving", slope
        elif slope < -0.5:
            return "degrading", slope
        return "stable", slope

    def _predict(self, current_score: float, slope: float) -> float:
        """Predict health score after prediction_horizon_s seconds."""
        # slope is in score units per second (approximate)
        predicted = current_score + slope * self._prediction_horizon_s
        return max(0.0, min(100.0, predicted))

    @staticmethod
    def _linear_slope(points: List[Tuple[float, float]]) -> float:
        """Least-squares slope of (x, y) pairs."""
        n = len(points)
        if n < 2:
            return 0.0
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        mx = sum(xs) / n
        my = sum(ys) / n
        num = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=False))
        den = sum((x - mx) ** 2 for x in xs)
        return num / den if den != 0 else 0.0

    def _get_cb_state(self, state: _WorkerState) -> str:
        if state.circuit_breaker is None:
            return "unknown"
        try:
            cb_state = state.circuit_breaker.state
            return str(cb_state.value) if hasattr(cb_state, "value") else str(cb_state)
        except Exception:
            return "unknown"
