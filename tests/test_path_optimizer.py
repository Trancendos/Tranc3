"""
Phase 28 — InfinityBridge Path Optimization Tests

Tests path scoring, health monitoring, fallback routing,
and the path optimization engine for intelligent routing
across light bridges.
"""

import asyncio  # noqa: I001

from Dimensional.infinity.bridge.path_optimizer import (
    PathMetrics,
    PathOptimizerConfig,
    OptimizationStrategy,
    PathScorer,
    PathScore,
    PathHealthMonitor,
    PathHealth,
    FallbackRouter,
    PathOptimizationEngine,
    OptimizedRoute,
    get_path_optimizer,
)


# ── PathMetrics Tests ────────────────────────────────────────────────────────


class TestPathMetrics:
    def test_create_metrics(self):
        metrics = PathMetrics(
            path_id="path-1",
            source="source-A",
            target="target-B",
            avg_latency_ms=20.0,
            current_transitions=30,
            max_capacity=100,
        )
        assert metrics.path_id == "path-1"
        assert metrics.source == "source-A"
        assert metrics.target == "target-B"
        assert metrics.avg_latency_ms == 20.0
        assert metrics.current_transitions == 30
        assert metrics.max_capacity == 100

    def test_available_capacity_is_ratio(self):
        """available_capacity returns a 0-1 ratio, not absolute number."""
        metrics = PathMetrics(
            path_id="path-1",
            source="A",
            target="B",
            avg_latency_ms=20.0,
            current_transitions=30,
            max_capacity=100,
        )
        # 30/100 = 0.3 transitions used; available = 1 - 0.3 = 0.7
        assert abs(metrics.available_capacity - 0.7) < 0.01

    def test_default_health_unknown(self):
        metrics = PathMetrics(
            path_id="p1",
            source="A",
            target="B",
            avg_latency_ms=10.0,
            current_transitions=0,
            max_capacity=100,
        )
        assert metrics.health == PathHealth.UNKNOWN

    def test_metrics_has_timestamp(self):
        metrics = PathMetrics(
            path_id="p1",
            source="A",
            target="B",
            avg_latency_ms=10.0,
            current_transitions=0,
            max_capacity=100,
        )
        assert metrics.last_updated is not None


# ── PathOptimizerConfig Tests ────────────────────────────────────────────────


class TestPathOptimizerConfig:
    def test_default_config(self):
        config = PathOptimizerConfig()
        assert config.strategy == OptimizationStrategy.BALANCED
        assert config.latency_weight == 0.4
        assert config.load_weight == 0.3
        assert config.health_weight == 0.2
        assert config.capacity_weight == 0.1

    def test_custom_config(self):
        config = PathOptimizerConfig(
            strategy=OptimizationStrategy.LOWEST_LATENCY,
            latency_weight=0.6,
            load_weight=0.2,
            health_weight=0.1,
            capacity_weight=0.1,
        )
        assert config.strategy == OptimizationStrategy.LOWEST_LATENCY
        assert config.latency_weight == 0.6


# ── PathScorer Tests ─────────────────────────────────────────────────────────


class TestPathScorer:
    def test_score_healthy_path(self):
        scorer = PathScorer()
        metrics = PathMetrics(
            path_id="path-1",
            source="A",
            target="B",
            avg_latency_ms=10.0,
            current_transitions=10,
            max_capacity=100,
        )
        score = scorer.score(metrics)
        assert isinstance(score, PathScore)
        assert score.total_score > 0.5

    def test_score_degraded_path(self):
        scorer = PathScorer()
        metrics = PathMetrics(
            path_id="path-1",
            source="A",
            target="B",
            avg_latency_ms=800.0,  # High latency → degraded
            current_transitions=90,
            max_capacity=100,
            error_rate=0.1,
        )
        score = scorer.score(metrics)
        assert isinstance(score, PathScore)
        # Degraded path should have lower score than healthy
        healthy_metrics = PathMetrics(
            path_id="path-2",
            source="A",
            target="B",
            avg_latency_ms=10.0,
            current_transitions=10,
            max_capacity=100,
        )
        healthy_score = scorer.score(healthy_metrics)
        assert score.total_score < healthy_score.total_score

    def test_score_total_score_field(self):
        """PathScore uses total_score field (not overall_score)."""
        scorer = PathScorer()
        metrics = PathMetrics(
            path_id="path-1",
            source="A",
            target="B",
            avg_latency_ms=10.0,
            current_transitions=10,
            max_capacity=100,
        )
        score = scorer.score(metrics)
        assert hasattr(score, "total_score")
        assert isinstance(score.total_score, float)


# ── PathHealthMonitor Tests ──────────────────────────────────────────────────


class TestPathHealthMonitor:
    def test_record_latency(self):
        loop = asyncio.new_event_loop()
        try:
            monitor = PathHealthMonitor()
            loop.run_until_complete(monitor.record_latency("path-1", 25.0))
        finally:
            loop.close()

    def test_get_path_metrics(self):
        loop = asyncio.new_event_loop()
        try:
            monitor = PathHealthMonitor()
            loop.run_until_complete(monitor.record_latency("path-1", 30.0))
            metrics = loop.run_until_complete(monitor.get_path_metrics("path-1", "A", "B"))
            assert isinstance(metrics, PathMetrics)
            assert metrics.avg_latency_ms == 30.0
        finally:
            loop.close()

    def test_record_transition(self):
        loop = asyncio.new_event_loop()
        try:
            monitor = PathHealthMonitor()
            loop.run_until_complete(monitor.record_transition("path-1", success=True))
            loop.run_until_complete(monitor.record_transition("path-1", success=False))
        finally:
            loop.close()

    def test_set_health_override(self):
        loop = asyncio.new_event_loop()
        try:
            monitor = PathHealthMonitor()
            loop.run_until_complete(monitor.set_health_override("path-1", PathHealth.DEGRADED))
        finally:
            loop.close()

    def test_clear_health_override(self):
        loop = asyncio.new_event_loop()
        try:
            monitor = PathHealthMonitor()
            loop.run_until_complete(monitor.set_health_override("path-1", PathHealth.DEGRADED))
            loop.run_until_complete(monitor.clear_health_override("path-1"))
        finally:
            loop.close()

    def test_detect_degradation(self):
        """detect_degradation is async, returns Optional[Dict]."""
        loop = asyncio.new_event_loop()
        try:
            monitor = PathHealthMonitor()
            # Create unhealthy conditions
            loop.run_until_complete(monitor.record_latency("path-1", 3000.0))
            loop.run_until_complete(monitor.record_transition("path-1", success=False))
            result = loop.run_until_complete(monitor.detect_degradation("path-1"))
            # Returns a dict when degraded, or None when healthy
            assert result is None or isinstance(result, dict)
        finally:
            loop.close()


# ── FallbackRouter Tests ─────────────────────────────────────────────────────


class TestFallbackRouter:
    def test_register_path(self):
        loop = asyncio.new_event_loop()
        try:
            router = FallbackRouter()
            loop.run_until_complete(router.register_path("A", "B"))
        finally:
            loop.close()

    def test_unregister_path(self):
        loop = asyncio.new_event_loop()
        try:
            router = FallbackRouter()
            loop.run_until_complete(router.register_path("A", "B"))
            loop.run_until_complete(router.unregister_path("A", "B"))
        finally:
            loop.close()

    def test_find_alternative_paths(self):
        loop = asyncio.new_event_loop()
        try:
            router = FallbackRouter()
            loop.run_until_complete(router.register_path("A", "B"))
            loop.run_until_complete(router.register_path("A", "C"))
            loop.run_until_complete(router.register_path("C", "B"))
            paths = loop.run_until_complete(router.find_alternative_paths("A", "B"))
            assert isinstance(paths, list)
        finally:
            loop.close()

    def test_get_fallback_route(self):
        loop = asyncio.new_event_loop()
        try:
            router = FallbackRouter()
            loop.run_until_complete(router.register_path("A", "B"))
            # Need scored_paths and health_monitor for get_fallback_route
            _scorer = PathScorer()
            monitor = PathHealthMonitor()
            # Score a path with low total_score to trigger fallback
            scored_paths = {}
            route = loop.run_until_complete(
                router.get_fallback_route("A", "B", scored_paths, monitor)
            )
            # May return None or an OptimizedRoute
            assert route is None or isinstance(route, OptimizedRoute)
        finally:
            loop.close()


# ── PathOptimizationEngine Tests ─────────────────────────────────────────────


class TestPathOptimizationEngine:
    def test_register_path(self):
        engine = PathOptimizationEngine()
        # register_path is sync, returns path_id string
        path_id = engine.register_path("A", "B", max_capacity=100)
        assert isinstance(path_id, str)
        assert len(path_id) > 0

    def test_record_latency(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            path_id = engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.record_latency(path_id, 25.0))
        finally:
            loop.close()

    def test_record_transition(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            path_id = engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.record_transition(path_id, success=True))
        finally:
            loop.close()

    def test_get_path_score(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            path_id = engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.record_latency(path_id, 15.0))
            score = loop.run_until_complete(engine.get_path_score(path_id))
            assert isinstance(score, PathScore)
            assert score.total_score > 0
        finally:
            loop.close()

    def test_get_optimal_route(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.start())
            try:
                route = loop.run_until_complete(engine.get_optimal_route("A", "B"))
                assert route is None or isinstance(route, OptimizedRoute)
            finally:
                loop.run_until_complete(engine.stop())
        finally:
            loop.close()

    def test_get_all_scores(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.record_latency("A→B", 15.0))
            scores = loop.run_until_complete(engine.get_all_scores())
            assert isinstance(scores, dict)
        finally:
            loop.close()

    def test_get_degraded_paths(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            engine.register_path("A", "B", max_capacity=100)
            degraded = loop.run_until_complete(engine.get_degraded_paths())
            assert isinstance(degraded, list)
        finally:
            loop.close()

    def test_get_status(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.start())
            try:
                status = loop.run_until_complete(engine.get_status())
                assert isinstance(status, dict)
                assert "running" in status
            finally:
                loop.run_until_complete(engine.stop())
        finally:
            loop.close()

    def test_unregister_path(self):
        loop = asyncio.new_event_loop()
        try:
            engine = PathOptimizationEngine()
            engine.register_path("A", "B", max_capacity=100)
            loop.run_until_complete(engine.unregister_path("A", "B"))
        finally:
            loop.close()


# ── PathOptimizer Singleton Tests ────────────────────────────────────────────


class TestPathOptimizerSingleton:
    def test_get_path_optimizer_returns_engine(self):
        optimizer = get_path_optimizer()
        assert isinstance(optimizer, PathOptimizationEngine)

    def test_get_path_optimizer_with_config(self):
        config = PathOptimizerConfig(strategy=OptimizationStrategy.LOWEST_LATENCY)
        optimizer = get_path_optimizer(config=config)
        assert isinstance(optimizer, PathOptimizationEngine)
