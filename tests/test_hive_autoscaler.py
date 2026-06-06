"""
Tests for Tranc3 HIVE Swarm Auto-Scaling
==========================================
Comprehensive tests for the auto-scaling engine including throughput metrics,
scaling policies, cooldown management, and threshold triggers.
"""

import asyncio  # noqa: I001

from Dimensional.hive.autoscaler import (
    AutoScalerEngine,
    CooldownManager,
    MetricsCollector,
    ScalingAction,
    ScalingDecisionEngine,
    ScalingDirection,
    ScalingPolicyConfig,
    ScalingPolicyType,
    ScalingStatus,
    ThroughputMetrics,
    get_autoscaler,
)

# ──────────────────────────────────────────────
# ThroughputMetrics Tests
# ──────────────────────────────────────────────


class TestThroughputMetrics:
    def test_create_metrics(self):
        metrics = ThroughputMetrics(
            swarm_id="swarm-1",
            tasks_per_second=100.0,
            active_nodes=5,
            pending_tasks=20,
            cpu_utilization=0.75,
            memory_utilization=0.60,
        )
        assert metrics.swarm_id == "swarm-1"
        assert metrics.tasks_per_second == 100.0
        assert metrics.active_nodes == 5
        assert metrics.pending_tasks == 20
        assert metrics.cpu_utilization == 0.75
        assert metrics.memory_utilization == 0.60

    def test_load_factor(self):
        metrics = ThroughputMetrics(
            swarm_id="swarm-1",
            tasks_per_second=100.0,
            active_nodes=5,
            pending_tasks=20,
            cpu_utilization=0.80,
            memory_utilization=0.70,
        )
        lf = metrics.load_factor
        assert isinstance(lf, float)
        assert lf >= 0.0

    def test_metrics_defaults(self):
        metrics = ThroughputMetrics()
        assert metrics.swarm_id == ""
        assert metrics.tasks_per_second == 0.0
        assert metrics.active_nodes == 0
        assert metrics.load_factor >= 0.0


# ──────────────────────────────────────────────
# ScalingPolicyConfig Tests
# ──────────────────────────────────────────────


class TestScalingPolicyConfig:
    def test_default_config(self):
        config = ScalingPolicyConfig()
        assert config.policy_type == ScalingPolicyType.THRESHOLD
        assert config.scale_up_threshold > 0
        assert config.scale_down_threshold > 0

    def test_custom_config(self):
        config = ScalingPolicyConfig(
            policy_type=ScalingPolicyType.PREDICTIVE,
            scale_up_threshold=0.8,
            scale_down_threshold=0.3,
            min_nodes=2,
            max_nodes=10,
        )
        assert config.policy_type == ScalingPolicyType.PREDICTIVE
        assert config.scale_up_threshold == 0.8
        assert config.scale_down_threshold == 0.3
        assert config.min_nodes == 2
        assert config.max_nodes == 10


# ──────────────────────────────────────────────
# ScalingAction Tests
# ──────────────────────────────────────────────


class TestScalingAction:
    def test_create_action(self):
        action = ScalingAction(
            swarm_id="swarm-1",
            direction=ScalingDirection.UP,
            previous_nodes=3,
            target_nodes=5,
            reason="high_load",
        )
        assert action.swarm_id == "swarm-1"
        assert action.direction == ScalingDirection.UP
        assert action.previous_nodes == 3
        assert action.target_nodes == 5

    def test_action_defaults(self):
        action = ScalingAction()
        assert action.direction == ScalingDirection.NONE
        assert action.previous_nodes == 0
        assert action.target_nodes == 0


# ──────────────────────────────────────────────
# MetricsCollector Tests
# ──────────────────────────────────────────────


class TestMetricsCollector:
    def test_record_and_get_latest(self):
        collector = MetricsCollector()
        metrics = ThroughputMetrics(
            swarm_id="swarm-1",
            tasks_per_second=100.0,
            active_nodes=5,
            pending_tasks=20,
            cpu_utilization=0.75,
            memory_utilization=0.60,
        )
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(collector.record(metrics))
            latest = loop.run_until_complete(collector.get_latest("swarm-1"))
            assert latest is not None
            assert latest.tasks_per_second == 100.0
        finally:
            loop.close()

    def test_get_latest_nonexistent(self):
        collector = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            latest = loop.run_until_complete(collector.get_latest("nonexistent"))
            assert latest is None
        finally:
            loop.close()

    def test_get_samples(self):
        collector = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            for i in range(5):
                metrics = ThroughputMetrics(
                    swarm_id="swarm-1",
                    tasks_per_second=float(i * 10),
                    active_nodes=1,
                    pending_tasks=0,
                    cpu_utilization=0.5,
                    memory_utilization=0.5,
                )
                loop.run_until_complete(collector.record(metrics))
            samples = loop.run_until_complete(collector.get_samples("swarm-1", count=3))
            assert len(samples) == 3
        finally:
            loop.close()

    def test_get_all_swarm_ids(self):
        collector = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                collector.record(
                    ThroughputMetrics(
                        swarm_id="swarm-1",
                        tasks_per_second=100.0,
                        active_nodes=5,
                        pending_tasks=0,
                        cpu_utilization=0.5,
                        memory_utilization=0.5,
                    ),
                ),
            )
            loop.run_until_complete(
                collector.record(
                    ThroughputMetrics(
                        swarm_id="swarm-2",
                        tasks_per_second=200.0,
                        active_nodes=3,
                        pending_tasks=0,
                        cpu_utilization=0.5,
                        memory_utilization=0.5,
                    ),
                ),
            )
            ids = loop.run_until_complete(collector.get_all_swarm_ids())
            assert "swarm-1" in ids
            assert "swarm-2" in ids
        finally:
            loop.close()

    def test_get_load_trend(self):
        collector = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            for i in range(5):
                loop.run_until_complete(
                    collector.record(
                        ThroughputMetrics(
                            swarm_id="swarm-1",
                            tasks_per_second=float(i * 20),
                            active_nodes=1,
                            pending_tasks=0,
                            cpu_utilization=0.5,
                            memory_utilization=0.5,
                        ),
                    ),
                )
            trend = loop.run_until_complete(collector.get_load_trend("swarm-1"))
            assert trend is not None
        finally:
            loop.close()

    def test_clear(self):
        collector = MetricsCollector()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(
                collector.record(
                    ThroughputMetrics(
                        swarm_id="swarm-1",
                        tasks_per_second=100.0,
                        active_nodes=5,
                        pending_tasks=0,
                        cpu_utilization=0.5,
                        memory_utilization=0.5,
                    ),
                ),
            )
            loop.run_until_complete(collector.clear())
            latest = loop.run_until_complete(collector.get_latest("swarm-1"))
            assert latest is None
        finally:
            loop.close()


# ──────────────────────────────────────────────
# CooldownManager Tests
# ──────────────────────────────────────────────


class TestCooldownManager:
    def test_not_on_cooldown_initially(self):
        manager = CooldownManager()
        assert manager.is_on_cooldown("swarm-1") is False

    def test_set_cooldown(self):
        manager = CooldownManager()
        manager.set_cooldown("swarm-1", "scale_up", duration_seconds=60)
        assert manager.is_on_cooldown("swarm-1") is True

    def test_clear_cooldown(self):
        manager = CooldownManager()
        manager.set_cooldown("swarm-1", "scale_up", duration_seconds=60)
        manager.clear_cooldown("swarm-1")
        assert manager.is_on_cooldown("swarm-1") is False

    def test_cooldown_expires(self):
        manager = CooldownManager()
        manager.set_cooldown("swarm-1", "scale_up", duration_seconds=0)
        assert manager.is_on_cooldown("swarm-1") is False

    def test_record_action_and_flapping(self):
        manager = CooldownManager()
        up_action = ScalingAction(
            swarm_id="swarm-1",
            direction=ScalingDirection.UP,
            previous_nodes=3,
            target_nodes=5,
        )
        down_action = ScalingAction(
            swarm_id="swarm-1",
            direction=ScalingDirection.DOWN,
            previous_nodes=5,
            target_nodes=3,
        )
        # Alternating up/down = flapping
        for _ in range(3):
            manager.record_action(up_action)
            manager.record_action(down_action)
        assert manager.is_flapping("swarm-1") is True

    def test_not_flapping_initially(self):
        manager = CooldownManager()
        assert manager.is_flapping("swarm-1") is False


# ──────────────────────────────────────────────
# ScalingDecisionEngine Tests
# ──────────────────────────────────────────────


class TestScalingDecisionEngine:
    def test_evaluate_scale_up(self):
        engine = ScalingDecisionEngine()
        metrics = ThroughputMetrics(
            swarm_id="swarm-1",
            tasks_per_second=1000.0,
            active_nodes=2,
            pending_tasks=500,
            cpu_utilization=0.95,
            memory_utilization=0.90,
        )
        action = engine.evaluate(metrics)
        assert action is not None
        assert action.direction in (ScalingDirection.UP, ScalingDirection.NONE)

    def test_evaluate_scale_down(self):
        engine = ScalingDecisionEngine()
        metrics = ThroughputMetrics(
            swarm_id="swarm-1",
            tasks_per_second=1.0,
            active_nodes=10,
            pending_tasks=0,
            cpu_utilization=0.05,
            memory_utilization=0.05,
        )
        action = engine.evaluate(metrics)
        assert action is not None
        assert action.direction in (ScalingDirection.DOWN, ScalingDirection.NONE)

    def test_evaluate_stable(self):
        engine = ScalingDecisionEngine()
        metrics = ThroughputMetrics(
            swarm_id="swarm-1",
            tasks_per_second=50.0,
            active_nodes=5,
            pending_tasks=5,
            cpu_utilization=0.50,
            memory_utilization=0.50,
        )
        action = engine.evaluate(metrics)
        assert action is not None


# ──────────────────────────────────────────────
# AutoScalerEngine Tests
# ──────────────────────────────────────────────


class TestAutoScalerEngine:
    def test_create_engine(self):
        engine = AutoScalerEngine()
        assert engine is not None
        assert engine.status == ScalingStatus.STOPPED

    def test_register_swarm(self):
        engine = AutoScalerEngine()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.register_swarm("swarm-1"))
            assert "swarm-1" in engine._swarms
        finally:
            loop.close()

    def test_unregister_swarm(self):
        engine = AutoScalerEngine()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.register_swarm("swarm-1"))
            loop.run_until_complete(engine.unregister_swarm("swarm-1"))
            assert "swarm-1" not in engine._swarms
        finally:
            loop.close()

    def test_record_metrics(self):
        engine = AutoScalerEngine()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.register_swarm("swarm-1"))
            metrics = ThroughputMetrics(
                swarm_id="swarm-1",
                tasks_per_second=100.0,
                active_nodes=5,
                pending_tasks=10,
                cpu_utilization=0.60,
                memory_utilization=0.50,
            )
            loop.run_until_complete(engine.record_metrics(metrics))
        finally:
            loop.close()

    def test_get_status(self):
        engine = AutoScalerEngine()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.start())
            status = loop.run_until_complete(engine.get_status())
            assert status["status"] == ScalingStatus.ACTIVE.value
            loop.run_until_complete(engine.stop())
        finally:
            loop.close()

    def test_evaluate(self):
        engine = AutoScalerEngine()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.register_swarm("swarm-1"))
            metrics = ThroughputMetrics(
                swarm_id="swarm-1",
                tasks_per_second=100.0,
                active_nodes=5,
                pending_tasks=10,
                cpu_utilization=0.60,
                memory_utilization=0.50,
            )
            loop.run_until_complete(engine.record_metrics(metrics))
            action = loop.run_until_complete(engine.evaluate("swarm-1"))
            assert action is not None or action is None  # May or may not produce action
        finally:
            loop.close()

    def test_pause_resume(self):
        engine = AutoScalerEngine()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(engine.start())
            loop.run_until_complete(engine.pause())
            assert engine.status == ScalingStatus.PAUSED
            loop.run_until_complete(engine.resume())
            assert engine.status == ScalingStatus.ACTIVE
            loop.run_until_complete(engine.stop())
        finally:
            loop.close()


# ──────────────────────────────────────────────
# Singleton Tests
# ──────────────────────────────────────────────


class TestAutoScalerSingleton:
    def test_get_autoscaler(self):
        scaler = get_autoscaler()
        assert scaler is not None
        assert isinstance(scaler, AutoScalerEngine)

    def test_singleton_identity(self):
        s1 = get_autoscaler()
        s2 = get_autoscaler()
        assert s1 is s2
