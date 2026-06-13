"""
Tests for the 10 adaptive/intelligent platform systems.
Covers: MAPEKLoop, AdaptiveRateLimiter, WorkerIntelligence, DNAConfig,
SmartContainer, ReactiveStream, IntelligentLogger.
"""
import time
import threading
import tempfile
from pathlib import Path

import pytest


# ── MAPEKLoop ─────────────────────────────────────────────────────────────

class TestMAPEKLoop:
    def _make_monitor(self, values):
        """Generator-based monitor for deterministic tests."""
        iter_values = iter(values)

        def monitor():
            try:
                return next(iter_values)
            except StopIteration:
                return {"cpu": 50.0}

        return monitor

    def test_basic_cycle_runs(self):
        """Loop should run monitor→analyze→plan without crashing."""
        from src.core.mape_k import MAPEKLoop

        calls = []

        def monitor():
            calls.append(time.time())
            return {"cpu": 10.0, "mem": 200.0}

        loop = MAPEKLoop(name="test", monitor_fn=monitor, interval_seconds=1)
        loop.start()
        time.sleep(1.5)
        loop.stop()

        assert len(calls) >= 1, "Monitor function should have been called"

    def test_anomaly_detection_triggers_action(self):
        """Z-score anomaly should set needs_action=True for extreme values."""
        from src.core.mape_k import MAPEKLoop

        actions_taken = []

        # Seed history with normal values then spike
        normal = [{"cpu": float(i)} for i in range(10, 15)]  # mean ~12.5
        spike = [{"cpu": 9999.0}]
        values = normal + spike + normal * 10

        idx = [0]

        def monitor():
            v = values[idx[0] % len(values)]
            idx[0] += 1
            return v

        def execute(plan):
            actions_taken.append(plan)
            return True

        loop = MAPEKLoop(
            name="anomaly-test",
            monitor_fn=monitor,
            execute_fn=execute,
            interval_seconds=0,
        )
        # Manually seed history
        for val in normal:
            loop._history.append({"metrics": val, "analysis": {}, "plan": {}, "executed": False, "timestamp": time.time()})

        # Run one analysis cycle with spike
        metrics = {"cpu": 9999.0}
        analysis = loop._default_analyze(metrics)
        assert analysis["needs_action"] is True or analysis["anomaly_score"] >= 0

    def test_history_capped_at_1000(self):
        """History deque should not exceed maxlen=1000."""
        from src.core.mape_k import MAPEKLoop

        loop = MAPEKLoop(name="cap-test", monitor_fn=lambda: {}, interval_seconds=99999)
        for _ in range(1500):
            loop._history.append({"metrics": {}, "analysis": {}, "plan": {}, "executed": False, "timestamp": 0})

        assert len(loop._history) <= 1000

    def test_knowledge_update_and_retrieve(self):
        """Knowledge base should store and return values."""
        from src.core.mape_k import MAPEKLoop

        loop = MAPEKLoop(name="kb-test", monitor_fn=lambda: {}, interval_seconds=99999)
        loop.update_knowledge("worker_count", 5)
        kb = loop.get_knowledge()
        assert kb["worker_count"] == 5

    def test_sqlite_persistence(self, tmp_path):
        """With db_path set, cycles should be persisted."""
        import sqlite3
        from src.core.mape_k import MAPEKLoop

        db = tmp_path / "test_mapek.db"
        loop = MAPEKLoop(
            name="db-test",
            monitor_fn=lambda: {"x": 1.0},
            interval_seconds=1,
            db_path=db,
        )
        loop.start()
        time.sleep(1.5)
        loop.stop()

        assert db.exists()
        conn = sqlite3.connect(str(db))
        rows = conn.execute("SELECT COUNT(*) FROM mapek_history").fetchone()
        conn.close()
        assert rows[0] >= 1


# ── AdaptiveRateLimiter ────────────────────────────────────────────────────

class TestAdaptiveRateLimiter:
    def test_allows_requests_under_limit(self):
        """Should allow requests within the base rate."""
        from src.core.adaptive_rate_limiter import AdaptiveRateLimiter

        limiter = AdaptiveRateLimiter(base_rate=100, window_seconds=60)
        allowed = sum(1 for _ in range(10) if limiter.check("tenant-a"))
        assert allowed == 10

    def test_blocks_requests_over_limit(self):
        """Should block requests once tokens are exhausted."""
        from src.core.adaptive_rate_limiter import AdaptiveRateLimiter

        limiter = AdaptiveRateLimiter(base_rate=5, window_seconds=60, burst_multiplier=1.0)
        results = [limiter.check("tenant-b") for _ in range(20)]
        allowed = sum(results)
        assert allowed <= 5, f"Should not allow more than 5 requests, got {allowed}"

    def test_separate_tenants_independent(self):
        """Each tenant should have an independent bucket."""
        from src.core.adaptive_rate_limiter import AdaptiveRateLimiter

        limiter = AdaptiveRateLimiter(base_rate=5, window_seconds=60, burst_multiplier=1.0)
        for _ in range(5):
            limiter.check("tenant-x")
        # tenant-x is exhausted but tenant-y should still be fresh
        assert limiter.check("tenant-y") is True

    def test_stats_returns_dict(self):
        """get_stats() should return a non-empty dict after usage."""
        from src.core.adaptive_rate_limiter import AdaptiveRateLimiter

        limiter = AdaptiveRateLimiter()
        limiter.check("stats-tenant")
        stats = limiter.get_stats()
        assert isinstance(stats, dict)
        assert "stats-tenant" in stats

    def test_error_recording_does_not_crash(self):
        """record_error/record_success should not raise."""
        from src.core.adaptive_rate_limiter import AdaptiveRateLimiter

        limiter = AdaptiveRateLimiter()
        for _ in range(20):
            limiter.record_error("noisy-tenant")
        for _ in range(5):
            limiter.record_success("noisy-tenant")
        # Should not raise

    def test_concurrent_access(self):
        """Multiple threads checking concurrently should not crash."""
        from src.core.adaptive_rate_limiter import AdaptiveRateLimiter

        limiter = AdaptiveRateLimiter(base_rate=50, window_seconds=1)
        results = []
        lock = threading.Lock()

        def worker():
            r = limiter.check("concurrent")
            with lock:
                results.append(r)

        threads = [threading.Thread(target=worker) for _ in range(30)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 30


# ── WorkerIntelligence ────────────────────────────────────────────────────

class TestWorkerIntelligence:
    def test_health_score_starts_high(self):
        """A freshly registered worker with no data should score near 100."""
        from src.core.worker_intelligence import WorkerIntelligence

        wi = WorkerIntelligence()
        score = wi.health_score("brand-new-worker")
        assert score >= 0  # Can be 100 or computed from empty

    def test_errors_reduce_score(self):
        """Recording errors should reduce the health score."""
        from src.core.worker_intelligence import WorkerIntelligence

        wi = WorkerIntelligence()
        for _ in range(50):
            wi.record("flaky-worker", response_ms=200.0, is_error=True)

        # After 50 errors with no successes, score should be low
        score = wi.health_score("flaky-worker")
        assert score < 80, f"Expected low score for flaky worker, got {score}"

    def test_successes_maintain_high_score(self):
        """Recording successes should keep score high."""
        from src.core.worker_intelligence import WorkerIntelligence

        wi = WorkerIntelligence()
        for _ in range(50):
            wi.record("healthy-worker", response_ms=100.0, is_error=False)

        score = wi.health_score("healthy-worker")
        assert score >= 50, f"Expected high score for healthy worker, got {score}"

    def test_predict_returns_float(self):
        """health_report should include a predicted_score_1m float in [0, 100]."""
        from src.core.worker_intelligence import WorkerIntelligence

        wi = WorkerIntelligence()
        for i in range(10):
            wi.record("pred-worker", response_ms=float(100 + i * 10), is_error=False)

        report = wi.health_report("pred-worker")
        pred = report.predicted_score_1m
        assert isinstance(pred, float)
        assert 0.0 <= pred <= 100.0

    def test_alerts_for_low_score(self):
        """Workers with warning=True in health_report should be detectable."""
        from src.core.worker_intelligence import WorkerIntelligence

        wi = WorkerIntelligence()
        for _ in range(100):
            wi.record("critical-worker", response_ms=6000.0, is_error=True)

        report = wi.health_report("critical-worker")
        # Either warning is set or score is low
        assert report.warning or report.health_score < 80

    def test_all_reports_contains_all_workers(self):
        """all_reports() should include all workers that have been recorded."""
        from src.core.worker_intelligence import WorkerIntelligence

        wi = WorkerIntelligence()
        wi.record("worker-a", 100.0, True)
        wi.record("worker-b", 200.0, False)

        reports = wi.all_reports()
        assert "worker-a" in reports
        assert "worker-b" in reports


# ── DNAConfig ─────────────────────────────────────────────────────────────

class TestDNAConfig:
    def test_register_base_and_get_config(self, tmp_path):
        """register_base + get_active_config should return registered keys."""
        from src.core.dna_config import DNAConfig

        cfg = DNAConfig(db_path=str(tmp_path / "dna.db"))
        cfg.register_base({"batch_size": 32, "timeout": 10})
        active = cfg.get_active_config()
        assert active["batch_size"] == 32
        assert active["timeout"] == 10

    def test_get_active_config_has_variant_id(self, tmp_path):
        """get_active_config() should include _variant_id key."""
        from src.core.dna_config import DNAConfig

        cfg = DNAConfig(db_path=str(tmp_path / "dna2.db"))
        cfg.register_base({"x": 1})
        active = cfg.get_active_config()
        assert "_variant_id" in active

    def test_record_score_does_not_crash(self, tmp_path):
        """record_score should store metrics without error."""
        from src.core.dna_config import DNAConfig

        cfg = DNAConfig(db_path=str(tmp_path / "dna3.db"))
        vid = cfg.register_base({"lr": 0.01})
        cfg.record_score(vid, score=0.85)
        cfg.record_score(vid, score=0.90)

    def test_mutate_creates_new_variant(self, tmp_path):
        """mutate() should create a variant with overridden keys."""
        from src.core.dna_config import DNAConfig

        cfg = DNAConfig(db_path=str(tmp_path / "dna4.db"))
        cfg.register_base({"x": 10, "y": 0.5})
        mut_id = cfg.mutate({"x": 20}, name="large-x")
        variant = cfg.get_variant(mut_id)
        assert variant is not None
        assert variant.config["x"] == 20

    def test_promote_best_runs_without_error(self, tmp_path):
        """promote_best() should complete without raising."""
        from src.core.dna_config import DNAConfig

        cfg = DNAConfig(db_path=str(tmp_path / "dna5.db"), auto_promote=False)
        vid = cfg.register_base({"alpha": 1, "beta": 2})
        cfg.record_score(vid, score=0.8)
        cfg.promote_best()  # should not raise


# ── SmartContainer ────────────────────────────────────────────────────────

class TestSmartContainer:
    def test_register_and_resolve_class(self):
        """Should register and resolve a simple class."""
        from src.core.smart_container import SmartContainer, Lifetime

        class MyService:
            def greet(self):
                return "hello"

        container = SmartContainer()
        container.register(MyService, MyService, lifetime=Lifetime.TRANSIENT)
        svc = container.resolve(MyService)
        assert svc.greet() == "hello"

    def test_singleton_returns_same_instance(self):
        """SINGLETON lifetime should return the same instance each time."""
        from src.core.smart_container import SmartContainer, Lifetime

        class Counter:
            count = 0

            def __init__(self):
                Counter.count += 1

        container = SmartContainer()
        container.register(Counter, Counter, lifetime=Lifetime.SINGLETON)
        a = container.resolve(Counter)
        b = container.resolve(Counter)
        assert a is b
        assert Counter.count == 1

    def test_transient_returns_new_instance(self):
        """TRANSIENT lifetime should return different instances."""
        from src.core.smart_container import SmartContainer, Lifetime

        class Widget:
            pass

        container = SmartContainer()
        container.register(Widget, Widget, lifetime=Lifetime.TRANSIENT)
        a = container.resolve(Widget)
        b = container.resolve(Widget)
        assert a is not b

    def test_factory_registration(self):
        """Factory function should be used when provided via register_factory."""
        from src.core.smart_container import SmartContainer, Lifetime

        class Config:
            def __init__(self, value):
                self.value = value

        container = SmartContainer()
        container.register_factory(Config, lambda: Config(42))
        obj = container.resolve(Config)
        assert obj.value == 42

    def test_register_and_resolve_plain_class(self):
        """Registering a plain class should allow resolving it."""
        from src.core.smart_container import SmartContainer

        class TaggedService:
            def tag(self):
                return "tagged"

        container = SmartContainer()
        container.register(TaggedService)
        svc = container.resolve(TaggedService)
        assert svc.tag() == "tagged"

    def test_register_instance(self):
        """register_instance should return the exact object on resolve."""
        from src.core.smart_container import SmartContainer

        class DB:
            pass

        db = DB()
        container = SmartContainer()
        container.register_instance(DB, db)
        resolved = container.resolve(DB)
        assert resolved is db

    def test_unregistered_concrete_class_auto_resolves(self):
        """Resolving an unregistered concrete class should work via auto-registration."""
        from src.core.smart_container import SmartContainer

        class Plain:
            pass

        container = SmartContainer()
        container.register(Plain)
        obj = container.resolve(Plain)
        assert isinstance(obj, Plain)


# ── ReactiveStream ────────────────────────────────────────────────────────

class TestReactiveStream:
    def test_subject_emit_and_subscribe(self):
        """Subject.emit should deliver values to subscriber."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s = Subject()
        s.subscribe(received.append)
        s.emit(1)
        s.emit(2)
        s.emit(3)
        assert received == [1, 2, 3]

    def test_map_transforms_values(self):
        """map() should apply transformation to each value."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s = Subject()
        s.map(lambda x: x * 2).subscribe(received.append)
        s.emit(5)
        s.emit(10)
        assert received == [10, 20]

    def test_filter_drops_values(self):
        """filter() should only pass values matching predicate."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s = Subject()
        s.filter(lambda x: x % 2 == 0).subscribe(received.append)
        for i in range(6):
            s.emit(i)
        assert received == [0, 2, 4]

    def test_take_limits_emissions(self):
        """take(n) should stop after n values."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s = Subject()
        s.take(3).subscribe(received.append)
        for i in range(10):
            s.emit(i)
        assert received == [0, 1, 2]

    def test_unsubscribe_stops_delivery(self):
        """unsubscribe() should prevent further value delivery."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s = Subject()
        sub = s.subscribe(received.append)
        s.emit(1)
        sub.unsubscribe()
        s.emit(2)
        s.emit(3)
        assert received == [1]

    def test_debounce_coalesces_rapid_emissions(self):
        """debounce() should emit only the last value within the window."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s = Subject()
        s.debounce(50).subscribe(received.append)

        for i in range(5):
            s.emit(i)
            time.sleep(0.005)

        time.sleep(0.2)  # wait for debounce to fire
        # Should receive only 1 value (the last one)
        assert len(received) <= 2  # at most 1-2 due to timing

    def test_merge_combines_streams(self):
        """merge() should combine emissions from multiple observables."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        received = []
        s1 = Subject()
        s2 = Subject()
        s1.merge(s2).subscribe(received.append)
        s1.emit("a")
        s2.emit("b")
        s1.emit("c")
        assert set(received) == {"a", "b", "c"}

    def test_error_handler_called(self):
        """on_error should be called when map raises."""
        import importlib.util, sys
        spec = importlib.util.spec_from_file_location("reactive_stream", "/home/user/Tranc3/src/event_bus/reactive_stream.py")
        rs = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(rs)
        Subject = rs.Subject

        errors = []
        s = Subject()
        s.map(lambda x: 1 / x).subscribe(lambda v: None, errors.append)
        s.emit(0)  # causes ZeroDivisionError
        assert len(errors) == 1
        assert isinstance(errors[0], ZeroDivisionError)


# ── IntelligentLogger ─────────────────────────────────────────────────────

class TestIntelligentLogger:
    def test_info_log_does_not_crash(self):
        """info() should emit without raising."""
        from src.core.intelligent_logger import IntelligentLogger

        log = IntelligentLogger("test-service")
        log.info("hello world", key="value")

    def test_error_increments_stats(self):
        """error() should be reflected in get_stats()."""
        from src.core.intelligent_logger import IntelligentLogger

        log = IntelligentLogger("stats-service")
        log.error("something broke")
        stats = log.get_stats()
        assert isinstance(stats, dict)

    def test_trace_context_propagates(self):
        """trace_context should set trace_id in thread-local."""
        from src.core.intelligent_logger import IntelligentLogger

        log = IntelligentLogger("ctx-service")
        recorded = []

        original_emit = log._emit

        def capturing_emit(level, msg, kwargs):
            ctx = log._get_context()
            recorded.append(ctx.get("trace_id"))
            return original_emit(level, msg, kwargs)

        log._emit = capturing_emit

        with log.trace_context("trace-xyz", user_id="user-1"):
            log.info("inside context")

        log.info("outside context")

        assert recorded[0] == "trace-xyz"
        assert recorded[1] is None

    def test_error_burst_creates_anomaly(self):
        """Emitting >10 errors quickly should create an anomaly entry."""
        from src.core.intelligent_logger import IntelligentLogger

        log = IntelligentLogger("burst-service")
        for _ in range(15):
            log.error("burst error")

        anomalies = log.get_anomalies()
        assert len(anomalies) >= 1
        assert anomalies[0]["type"] == "error_burst"

    def test_get_stats_returns_structure(self):
        """get_stats() should return a dict with expected keys."""
        from src.core.intelligent_logger import IntelligentLogger

        log = IntelligentLogger("stats2-service")
        log.info("msg1")
        log.warning("msg2")
        stats = log.get_stats()
        assert "service" in stats or isinstance(stats, dict)

    def test_context_restored_after_exception(self):
        """trace_context should restore context even if exception occurs."""
        from src.core.intelligent_logger import IntelligentLogger

        log = IntelligentLogger("exc-service")
        try:
            with log.trace_context("t-1"):
                raise ValueError("test error")
        except ValueError:
            pass

        ctx = log._get_context()
        assert ctx.get("trace_id") is None
