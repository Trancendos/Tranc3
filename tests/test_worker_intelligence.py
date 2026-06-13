"""
Tests for WorkerIntelligence — src/core/worker_intelligence.py
"""

from src.core.worker_intelligence import WorkerHealthReport, WorkerIntelligence

# ── Helpers ───────────────────────────────────────────────────────────────


def _populate(
    wi: WorkerIntelligence,
    worker_id: str,
    n: int = 30,
    response_ms: float = 100.0,
    error: bool = False,
) -> None:
    for _ in range(n):
        wi.record(worker_id, response_ms=response_ms, is_error=error)


# ── Tests ─────────────────────────────────────────────────────────────────


def test_health_score_healthy_worker():
    """A worker with low latency and zero errors should score ~100."""
    wi = WorkerIntelligence(target_latency_ms=300.0)
    wi.register("fast-worker")
    _populate(wi, "fast-worker", response_ms=50.0, error=False)
    score = wi.health_score("fast-worker")
    assert score >= 90.0, f"Expected score >= 90, got {score}"


def test_health_score_degrades_on_errors():
    """High error rate should pull health score down."""
    wi = WorkerIntelligence()
    wi.register("flaky-worker")
    # 50% error rate
    for _ in range(20):
        wi.record("flaky-worker", response_ms=100.0, is_error=True)
        wi.record("flaky-worker", response_ms=100.0, is_error=False)
    score = wi.health_score("flaky-worker")
    assert score < 85.0, f"Expected score < 85 with 50% errors, got {score}"


def test_health_score_degrades_on_high_latency():
    """Latency above ceiling should reduce health score."""
    wi = WorkerIntelligence(
        target_latency_ms=100.0,
        ceiling_latency_ms=1000.0,
    )
    wi.register("slow-worker")
    _populate(wi, "slow-worker", response_ms=2000.0, error=False)
    score = wi.health_score("slow-worker")
    assert score < 90.0, f"Expected reduced score for high latency, got {score}"


def test_report_fields_complete():
    """WorkerHealthReport must expose all documented fields."""
    wi = WorkerIntelligence()
    wi.register("report-worker")
    _populate(wi, "report-worker", n=10, response_ms=80.0)
    report = wi.health_report("report-worker")

    assert isinstance(report, WorkerHealthReport)
    assert report.worker_id == "report-worker"
    assert 0.0 <= report.health_score <= 100.0
    assert report.trend in ("stable", "improving", "degrading")
    assert report.circuit_state == "unknown"  # no CB attached
    assert report.sample_count > 0


def test_auto_register_on_record():
    """Recording to an unregistered worker should auto-create it."""
    wi = WorkerIntelligence()
    wi.record("new-worker", response_ms=100.0)
    assert "new-worker" in wi.list_workers()


def test_list_workers():
    wi = WorkerIntelligence()
    wi.register("w1")
    wi.register("w2")
    workers = wi.list_workers()
    assert "w1" in workers
    assert "w2" in workers


def test_all_reports():
    wi = WorkerIntelligence()
    wi.register("wa")
    wi.register("wb")
    _populate(wi, "wa")
    _populate(wi, "wb")
    reports = wi.all_reports()
    assert len(reports) == 2
    assert "wa" in reports and "wb" in reports


def test_warning_flag_when_predicted_low():
    """Warning should be True when predicted score drops below threshold."""
    wi = WorkerIntelligence(warning_score_threshold=50.0, prediction_horizon_s=5.0)
    wi.register("dying-worker")
    # 100% errors → score will be very low
    for _ in range(40):
        wi.record("dying-worker", response_ms=5000.0, is_error=True, is_available=False)
    report = wi.health_report("dying-worker")
    assert report.warning is True


def test_circuit_breaker_integration():
    """CircuitBreaker state should appear in report when attached."""

    class MockCB:
        class _state:
            value = "closed"

        state = _state()

    wi = WorkerIntelligence()
    wi.register("cb-worker", circuit_breaker=MockCB())
    report = wi.health_report("cb-worker")
    assert report.circuit_state == "closed"
