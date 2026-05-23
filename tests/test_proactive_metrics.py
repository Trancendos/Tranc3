"""
Tests for shared_core.architecture.proactive_metrics.

Covers: MetricType, HealthTrend, SubsystemMetrics, SystemVitals,
MetricsSnapshot, ProactiveMetricsCollector.
"""

from __future__ import annotations

import time


from shared_core.architecture.proactive_metrics import (
    HealthTrend,
    MetricsSnapshot,
    MetricType,
    ProactiveMetricsCollector,
    SubsystemMetrics,
    SystemVitals,
)


# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------

class TestMetricType:
    """Tests for MetricType enum."""

    def test_metric_types_exist(self):
        expected = ["COUNTER", "GAUGE", "HISTOGRAM", "SUMMARY"]
        for name in expected:
            assert hasattr(MetricType, name), f"Missing MetricType.{name}"

    def test_metric_type_values(self):
        assert MetricType.COUNTER.value == "counter"
        assert MetricType.GAUGE.value == "gauge"


class TestHealthTrend:
    """Tests for HealthTrend enum."""

    def test_all_trends_exist(self):
        expected = ["IMPROVING", "STABLE", "DEGRADING", "CRITICAL", "UNKNOWN"]
        for name in expected:
            assert hasattr(HealthTrend, name), f"Missing HealthTrend.{name}"

    def test_trend_values(self):
        assert HealthTrend.IMPROVING.value == "improving"
        assert HealthTrend.STABLE.value == "stable"
        assert HealthTrend.CRITICAL.value == "critical"
        assert HealthTrend.UNKNOWN.value == "unknown"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------

class TestSubsystemMetrics:
    """Tests for SubsystemMetrics dataclass."""

    def test_create_subsystem_metrics(self):
        sm = SubsystemMetrics(
            name="storage",
            health_score=0.9,
            status="healthy",
            events_processed=100,
            actions_dispatched=5,
            errors=0,
            uptime_seconds=86400.0,
            last_activity=time.time(),
        )
        assert sm.name == "storage"
        assert sm.health_score == 0.9
        assert sm.status == "healthy"
        assert sm.events_processed == 100
        assert sm.actions_dispatched == 5
        assert sm.errors == 0

    def test_custom_metrics(self):
        sm = SubsystemMetrics(
            name="test",
            custom_metrics={"latency_p99": 42.5},
        )
        assert sm.custom_metrics["latency_p99"] == 42.5


class TestSystemVitals:
    """Tests for SystemVitals dataclass."""

    def test_create_system_vitals(self):
        vitals = SystemVitals(
            timestamp=time.time(),
            composite_health=0.85,
            subsystem_health={"storage": 0.9, "registry": 0.8},
            health_trend=HealthTrend.STABLE,
            orchestrator_mode="observe",
            pulse_mode="steady",
            zero_cost_compliant=True,
            active_actions=2,
            pending_actions=1,
            healing_active=False,
            scaling_direction="maintain",
            storage_tiers_healthy=3,
            storage_tiers_total=3,
            services_healthy=5,
            services_total=5,
            circuits_open=0,
            circuits_total=3,
            threat_level="low",
            config_profile="default",
            predictions_degrading=0,
            uptime_seconds=3600.0,
        )
        assert vitals.composite_health == 0.85
        assert vitals.health_trend == HealthTrend.STABLE
        assert vitals.zero_cost_compliant is True
        assert vitals.active_actions == 2
        assert vitals.pending_actions == 1

    def test_system_vitals_all_fields(self):
        ts = time.time()
        vitals = SystemVitals(
            timestamp=ts,
            composite_health=0.5,
            subsystem_health={},
            health_trend=HealthTrend.DEGRADING,
            orchestrator_mode="autonomous",
            pulse_mode="accelerated",
            zero_cost_compliant=False,
            active_actions=5,
            pending_actions=3,
            healing_active=True,
            scaling_direction="up",
            storage_tiers_healthy=1,
            storage_tiers_total=3,
            services_healthy=3,
            services_total=5,
            circuits_open=1,
            circuits_total=3,
            threat_level="medium",
            config_profile="production",
            predictions_degrading=2,
            uptime_seconds=7200.0,
        )
        assert vitals.uptime_seconds == 7200.0
        assert vitals.healing_active is True
        assert vitals.services_healthy == 3


class TestMetricsSnapshot:
    """Tests for MetricsSnapshot dataclass."""

    def test_create_metrics_snapshot(self):
        vitals = SystemVitals(
            timestamp=time.time(),
            composite_health=0.8,
            subsystem_health={},
            health_trend=HealthTrend.STABLE,
            orchestrator_mode="observe",
            pulse_mode="steady",
            zero_cost_compliant=True,
            active_actions=0,
            pending_actions=0,
            healing_active=False,
            scaling_direction="maintain",
            storage_tiers_healthy=0,
            storage_tiers_total=0,
            services_healthy=0,
            services_total=0,
            circuits_open=0,
            circuits_total=0,
            threat_level="none",
            config_profile="default",
            predictions_degrading=0,
            uptime_seconds=0.0,
        )
        snapshot = MetricsSnapshot(
            timestamp=time.time(),
            vitals=vitals,
            subsystems={},
            action_stats={},
            zero_cost_details={},
            pulse_details={},
            scaler_details={},
        )
        assert isinstance(snapshot.vitals, SystemVitals)
        assert isinstance(snapshot.subsystems, dict)


# ---------------------------------------------------------------------------
# ProactiveMetricsCollector tests
# ---------------------------------------------------------------------------

class TestProactiveMetricsCollector:
    """Tests for the ProactiveMetricsCollector."""

    def setup_method(self):
        self.collector = ProactiveMetricsCollector()

    def test_collect_returns_snapshot(self):
        snapshot = self.collector.collect()
        assert isinstance(snapshot, MetricsSnapshot)

    def test_get_vitals(self):
        vitals = self.collector.get_vitals()
        assert isinstance(vitals, SystemVitals)

    def test_export_prometheus(self):
        output = self.collector.export_prometheus()
        assert isinstance(output, str)

    def test_attach_orchestrator(self):
        # Should not raise even with None
        self.collector.attach_orchestrator(None)

    def test_attach_pulse(self):
        self.collector.attach_pulse(None)

    def test_attach_config(self):
        self.collector.attach_config(None)

    def test_attach_scaler(self):
        self.collector.attach_scaler(None)

    def test_register_custom_collector(self):
        def my_collector():
            return {"custom_metric": 42.0}
        self.collector.register_custom_collector("custom", my_collector)

    def test_collect_with_subsystems(self):
        snapshot = self.collector.collect()
        assert isinstance(snapshot.subsystems, dict)

    def test_history_size_param(self):
        collector = ProactiveMetricsCollector(history_size=50)
        assert collector is not None

    def test_prometheus_prefix_param(self):
        collector = ProactiveMetricsCollector(prometheus_prefix="tranc3")
        output = collector.export_prometheus()
        assert isinstance(output, str)
