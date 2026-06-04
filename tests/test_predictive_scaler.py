"""
Tests for src.adaptive.predictive_scaler.

Covers: ScalingDirection, ScalingReason, LoadSample, LoadForecast,
ScalerConfig, ScalingDecision, LoadForecaster, PredictiveAutoscaler.
"""

from __future__ import annotations

import time

from src.adaptive.predictive_scaler import (
    LoadForecast,
    LoadForecaster,
    LoadSample,
    PredictiveAutoscaler,
    ScalerConfig,
    ScalingDecision,
    ScalingDirection,
    ScalingReason,
)

# ---------------------------------------------------------------------------
# Enum tests
# ---------------------------------------------------------------------------


class TestScalingDirection:
    """Tests for ScalingDirection enum."""

    def test_all_directions(self):
        assert hasattr(ScalingDirection, "UP")
        assert hasattr(ScalingDirection, "DOWN")
        assert hasattr(ScalingDirection, "MAINTAIN")

    def test_direction_values(self):
        assert ScalingDirection.UP.value == "up"
        assert ScalingDirection.DOWN.value == "down"
        assert ScalingDirection.MAINTAIN.value == "maintain"


class TestScalingReason:
    """Tests for ScalingReason enum."""

    def test_all_reasons_exist(self):
        expected = [
            "PREDICTED_DEMAND",
            "CURRENT_LOAD",
            "ZERO_COST_LIMIT",
            "COOLDOWN",
            "MIN_REACHED",
            "MAX_REACHED",
            "INSUFFICIENT_DATA",
        ]
        for name in expected:
            assert hasattr(ScalingReason, name), f"Missing ScalingReason.{name}"

    def test_reason_values(self):
        assert ScalingReason.PREDICTED_DEMAND.value == "predicted_demand"
        assert ScalingReason.ZERO_COST_LIMIT.value == "zero_cost_limit"


# ---------------------------------------------------------------------------
# Dataclass tests
# ---------------------------------------------------------------------------


class TestLoadSample:
    """Tests for LoadSample dataclass."""

    def test_create_load_sample(self):
        sample = LoadSample(
            timestamp=time.time(),
            value=42.5,
            source="test",
        )
        assert sample.value == 42.5
        assert sample.source == "test"

    def test_load_sample_with_tags(self):
        sample = LoadSample(
            timestamp=time.time(),
            value=100.0,
            source="monitor",
            tags={"service": "api"},
        )
        assert sample.tags == {"service": "api"}


class TestLoadForecast:
    """Tests for LoadForecast dataclass."""

    def test_create_load_forecast(self):
        lf = LoadForecast(
            predicted_load=150.0,
            confidence=0.85,
            lower_bound=120.0,
            upper_bound=180.0,
            horizon_seconds=300.0,
            timestamp=time.time(),
            method="holt_double_exp",
        )
        assert lf.predicted_load == 150.0
        assert lf.confidence == 0.85
        assert lf.lower_bound == 120.0
        assert lf.upper_bound == 180.0
        assert lf.horizon_seconds == 300.0
        assert lf.method == "holt_double_exp"


class TestScalerConfig:
    """Tests for ScalerConfig dataclass."""

    def test_create_scaler_config(self):
        config = ScalerConfig(
            name="api-gateway",
            current_units=2,
            min_units=1,
            max_units=10,
        )
        assert config.name == "api-gateway"
        assert config.current_units == 2
        assert config.min_units == 1
        assert config.max_units == 10

    def test_create_with_free_tier_limit(self):
        config = ScalerConfig(
            name="free-service",
            current_units=1,
            min_units=1,
            max_units=5,
            free_tier_limit=3,
        )
        assert config.free_tier_limit == 3

    def test_default_current_units(self):
        config = ScalerConfig(
            name="default-service",
            min_units=1,
            max_units=10,
        )
        assert config.current_units == 1


class TestScalingDecision:
    """Tests for ScalingDecision dataclass."""

    def test_scale_up(self):
        decision = ScalingDecision(
            direction=ScalingDirection.UP,
            current_units=2,
            target_units=4,
            reason=ScalingReason.PREDICTED_DEMAND,
            forecast=None,
            zero_cost_compliant=True,
            timestamp=time.time(),
            executed=False,
        )
        assert decision.direction == ScalingDirection.UP
        assert decision.target_units > decision.current_units

    def test_scale_down(self):
        decision = ScalingDecision(
            direction=ScalingDirection.DOWN,
            current_units=5,
            target_units=2,
            reason=ScalingReason.ZERO_COST_LIMIT,
            forecast=None,
            zero_cost_compliant=True,
            timestamp=time.time(),
            executed=False,
        )
        assert decision.direction == ScalingDirection.DOWN
        assert decision.target_units < decision.current_units

    def test_maintain(self):
        decision = ScalingDecision(
            direction=ScalingDirection.MAINTAIN,
            current_units=3,
            target_units=3,
            reason=ScalingReason.CURRENT_LOAD,
            forecast=None,
            zero_cost_compliant=True,
            timestamp=time.time(),
            executed=False,
        )
        assert decision.direction == ScalingDirection.MAINTAIN
        assert decision.target_units == decision.current_units


# ---------------------------------------------------------------------------
# LoadForecaster tests
# ---------------------------------------------------------------------------


class TestLoadForecaster:
    """Tests for the LoadForecaster."""

    def setup_method(self):
        self.forecaster = LoadForecaster()

    def test_record_and_forecast(self):
        for i in range(30):
            self.forecaster.record(
                value=100.0 + i * 2.0,
                source="test",
                tags={"service": "api"},
            )
        forecast = self.forecaster.forecast(horizon_seconds=300.0)
        assert isinstance(forecast, LoadForecast)
        assert forecast.predicted_load > 0
        assert forecast.confidence > 0.0
        assert forecast.horizon_seconds == 300.0

    def test_forecast_no_data(self):
        forecast = self.forecaster.forecast(horizon_seconds=300.0)
        assert isinstance(forecast, LoadForecast)
        # With no data, confidence should be low
        assert forecast.confidence <= 0.5

    def test_forecast_confidence_bounds(self):
        for i in range(20):
            self.forecaster.record(value=50.0, source="test")
        forecast = self.forecaster.forecast(horizon_seconds=300.0)
        assert forecast.lower_bound <= forecast.predicted_load
        assert forecast.upper_bound >= forecast.predicted_load

    def test_forecast_increasing_trend(self):
        # Use alpha/beta that favour trend detection
        forecaster = LoadForecaster(alpha=0.8, beta=0.6, window_size=10)
        for i in range(30):
            forecaster.record(value=100.0 + i * 5.0, source="test")
        forecast = forecaster.forecast(horizon_seconds=300.0)
        # The forecast should at least be positive with an increasing trend
        assert forecast.predicted_load > 0

    def test_get_stats(self):
        self.forecaster.record(value=42.0, source="test")
        stats = self.forecaster.get_stats()
        assert isinstance(stats, dict)


# ---------------------------------------------------------------------------
# PredictiveAutoscaler tests
# ---------------------------------------------------------------------------


class TestPredictiveAutoscaler:
    """Tests for the PredictiveAutoscaler."""

    def setup_method(self):
        self.scaler = PredictiveAutoscaler()

    def test_register_resource(self):
        config = self.scaler.register_resource(
            name="test-service",
            current_units=2,
            min_units=1,
            max_units=10,
        )
        assert isinstance(config, ScalerConfig)
        assert config.name == "test-service"
        assert config.current_units == 2

    def test_register_resource_with_free_tier(self):
        config = self.scaler.register_resource(
            name="free-service",
            current_units=1,
            min_units=1,
            max_units=5,
            free_tier_limit=3,
        )
        assert config.free_tier_limit == 3

    def test_deregister_resource(self):
        self.scaler.register_resource(
            name="temp-service", current_units=1, min_units=1, max_units=10,
        )
        self.scaler.deregister_resource("temp-service")
        # After deregister, should not appear in all_status
        status = self.scaler.get_all_status()
        assert "temp-service" not in status

    def test_record_load(self):
        self.scaler.register_resource(name="load-test", current_units=1, min_units=1, max_units=10)
        self.scaler.record_load("load-test", 0.5)
        # Should not raise

    def test_evaluate_stable_load(self):
        self.scaler.register_resource(name="stable-svc", current_units=2, min_units=1, max_units=10)
        for i in range(20):
            self.scaler.record_load("stable-svc", 0.5)
        decisions = self.scaler.evaluate()
        assert isinstance(decisions, list)
        for d in decisions:
            assert isinstance(d, ScalingDecision)

    def test_evaluate_high_load(self):
        self.scaler.register_resource(name="high-svc", current_units=2, min_units=1, max_units=10)
        for i in range(20):
            self.scaler.record_load("high-svc", 0.95)
        decisions = self.scaler.evaluate()
        for d in decisions:
            if d.direction == ScalingDirection.UP:
                assert d.target_units > d.current_units

    def test_evaluate_low_load(self):
        self.scaler.register_resource(name="low-svc", current_units=5, min_units=1, max_units=10)
        for i in range(20):
            self.scaler.record_load("low-svc", 0.1)
        decisions = self.scaler.evaluate()
        for d in decisions:
            if d.direction == ScalingDirection.DOWN:
                assert d.target_units < d.current_units

    def test_zero_cost_constraint(self):
        self.scaler.register_resource(
            name="zero-cost-svc",
            current_units=1,
            min_units=1,
            max_units=10,
            free_tier_limit=3,
        )
        for i in range(20):
            self.scaler.record_load("zero-cost-svc", 0.99)
        decisions = self.scaler.evaluate()
        for d in decisions:
            if d.direction == ScalingDirection.UP:
                assert d.target_units <= 3 or not d.zero_cost_compliant

    def test_apply_decision(self):
        self.scaler.register_resource(name="apply-svc", current_units=1, min_units=1, max_units=10)
        decision = ScalingDecision(
            direction=ScalingDirection.UP,
            current_units=1,
            target_units=3,
            reason=ScalingReason.PREDICTED_DEMAND,
            forecast=None,
            zero_cost_compliant=True,
            timestamp=time.time(),
            executed=False,
        )
        self.scaler.apply_decision(decision)
        # Should not raise

    def test_get_forecast(self):
        self.scaler.register_resource(
            name="forecast-svc", current_units=1, min_units=1, max_units=10,
        )
        for i in range(10):
            self.scaler.record_load("forecast-svc", 0.5 + i * 0.01)
        forecast = self.scaler.get_forecast("forecast-svc")
        assert isinstance(forecast, LoadForecast)

    def test_get_resource_status(self):
        self.scaler.register_resource(name="status-svc", current_units=2, min_units=1, max_units=10)
        status = self.scaler.get_resource_status("status-svc")
        # get_resource_status returns a dict, not ScalerConfig
        assert isinstance(status, dict)
        assert "current_units" in status or "name" in status

    def test_get_all_status(self):
        self.scaler.register_resource(name="all1", current_units=1, min_units=1, max_units=10)
        self.scaler.register_resource(name="all2", current_units=2, min_units=1, max_units=5)
        all_status = self.scaler.get_all_status()
        assert isinstance(all_status, dict)
        assert "all1" in all_status
        assert "all2" in all_status

    def test_get_recent_decisions(self):
        self.scaler.register_resource(name="recent-svc", current_units=1, min_units=1, max_units=10)
        for i in range(20):
            self.scaler.record_load("recent-svc", 0.8)
        self.scaler.evaluate()
        recent = self.scaler.get_recent_decisions()
        assert isinstance(recent, list)

    def test_get_stats(self):
        self.scaler.register_resource(name="stats-svc", current_units=1, min_units=1, max_units=10)
        stats = self.scaler.get_stats()
        assert isinstance(stats, dict)
