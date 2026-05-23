"""
src.adaptive.predictive_scaler — Proactive Predictive Autoscaler for Tranc3.

Implements zero-cost-aware predictive autoscaling that proactively adjusts
resource allocation based on predicted load patterns. Unlike traditional
autoscalers that react to current metrics, this system uses time-series
forecasting to anticipate demand and prepare resources before they're needed.

Key Features:
    - Exponential smoothing for load prediction
    - Zero-cost-aware: only scales within free-tier limits
    - Confidence intervals on predictions
    - Proactive pre-warming before predicted demand spikes
    - Graceful scale-down during low-demand periods
    - Integration with SmartStorageOrchestrator for capacity planning

Scaling Philosophy:
    1. Predict load 5-15 minutes ahead
    2. Pre-warm resources before demand spike
    3. Scale down gradually during low demand
    4. Never exceed free-tier limits
    5. Maintain headroom for unexpected spikes

This module is part of the Tranc3 Intelligent Adaptive Proactive Systems
(Phase 10) and integrates with the ProactiveOrchestrator.
"""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_FORECAST_HORIZON = 300.0  # 5 minutes ahead
_DEFAULT_SMOOTHING_ALPHA = 0.3  # EMA smoothing factor
_DEFAULT_SCALE_UP_THRESHOLD = 0.75  # Scale up when predicted load > 75%
_DEFAULT_SCALE_DOWN_THRESHOLD = 0.25  # Scale down when predicted load < 25%
_DEFAULT_MIN_CAPACITY_UNITS = 1  # Minimum units (always at least 1)
_DEFAULT_MAX_CAPACITY_UNITS = 10  # Maximum units (respect free-tier)
_DEFAULT_COOLDOWN_SECONDS = 120.0  # Minimum time between scaling actions
_DEFAULT_FREE_TIER_LIMIT = 5  # Maximum free-tier capacity units


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ScalingDirection(str, Enum):
    """Direction of a scaling decision."""

    UP = "up"
    DOWN = "down"
    MAINTAIN = "maintain"


class ScalingReason(str, Enum):
    """Reason for a scaling decision."""

    PREDICTED_DEMAND = "predicted_demand"
    CURRENT_LOAD = "current_load"
    ZERO_COST_LIMIT = "zero_cost_limit"
    COOLDOWN = "cooldown"
    MIN_REACHED = "min_reached"
    MAX_REACHED = "max_reached"
    INSUFFICIENT_DATA = "insufficient_data"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class LoadSample:
    """A single load measurement."""

    timestamp: float
    value: float  # 0.0 to 1.0 (normalized load)
    source: str = ""  # Where the measurement came from
    tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class LoadForecast:
    """Predicted load with confidence intervals."""

    predicted_load: float  # 0.0 to 1.0
    confidence: float  # 0.0 to 1.0
    lower_bound: float  # P10 prediction
    upper_bound: float  # P90 prediction
    horizon_seconds: float  # How far ahead the prediction is
    timestamp: float = field(default_factory=time.time)
    method: str = "exponential_smoothing"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "predicted_load": round(self.predicted_load, 4),
            "confidence": round(self.confidence, 4),
            "lower_bound": round(self.lower_bound, 4),
            "upper_bound": round(self.upper_bound, 4),
            "horizon_seconds": round(self.horizon_seconds, 1),
            "timestamp": self.timestamp,
            "method": self.method,
        }


@dataclass
class ScalingDecision:
    """A scaling decision with justification."""

    direction: ScalingDirection
    current_units: int
    target_units: int
    reason: ScalingReason
    forecast: Optional[LoadForecast] = None
    zero_cost_compliant: bool = True
    timestamp: float = field(default_factory=time.time)
    executed: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "direction": self.direction.value,
            "current_units": self.current_units,
            "target_units": self.target_units,
            "reason": self.reason.value,
            "forecast": self.forecast.to_dict() if self.forecast else None,
            "zero_cost_compliant": self.zero_cost_compliant,
            "timestamp": self.timestamp,
            "executed": self.executed,
            "metadata": self.metadata,
        }


@dataclass
class ScalerConfig:
    """Configuration for a scalable resource."""

    name: str
    current_units: int = 1
    min_units: int = _DEFAULT_MIN_CAPACITY_UNITS
    max_units: int = _DEFAULT_MAX_CAPACITY_UNITS
    free_tier_limit: int = _DEFAULT_FREE_TIER_LIMIT
    scale_up_threshold: float = _DEFAULT_SCALE_UP_THRESHOLD
    scale_down_threshold: float = _DEFAULT_SCALE_DOWN_THRESHOLD
    cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS
    last_scale_action: float = 0.0

    @property
    def effective_max(self) -> int:
        """Effective maximum respecting free-tier limit."""
        return min(self.max_units, self.free_tier_limit)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "current_units": self.current_units,
            "min_units": self.min_units,
            "max_units": self.max_units,
            "free_tier_limit": self.free_tier_limit,
            "effective_max": self.effective_max,
            "scale_up_threshold": self.scale_up_threshold,
            "scale_down_threshold": self.scale_down_threshold,
            "cooldown_seconds": self.cooldown_seconds,
        }


# ---------------------------------------------------------------------------
# Load Forecaster
# ---------------------------------------------------------------------------


class LoadForecaster:
    """
    Time-series load forecaster using exponential smoothing.

    Uses double exponential smoothing (Holt's method) to forecast
    load patterns with trend detection. This provides better predictions
    than simple averaging for workloads with trends or seasonal patterns.

    The forecaster is intentionally lightweight — no external ML
    dependencies required. For production systems, this can be replaced
    with a more sophisticated model (ARIMA, Prophet, neural network).
    """

    def __init__(
        self,
        alpha: float = _DEFAULT_SMOOTHING_ALPHA,
        beta: float = 0.1,  # Trend smoothing factor
        window_size: int = 200,  # Max samples to keep
    ):
        self._alpha = alpha
        self._beta = beta
        self._window_size = window_size
        self._samples: deque = deque(maxlen=window_size)

        # Holt's method state
        self._level: Optional[float] = None
        self._trend: Optional[float] = None
        self._initialized = False

    def record(self, value: float, source: str = "", tags: Optional[Dict[str, str]] = None) -> None:
        """Record a load sample."""
        sample = LoadSample(
            timestamp=time.time(),
            value=max(0.0, min(1.0, value)),
            source=source,
            tags=tags or {},
        )
        self._samples.append(sample)

        # Update Holt's method
        if not self._initialized:
            if len(self._samples) >= 2:
                samples = list(self._samples)
                self._level = samples[-1].value
                self._trend = samples[-1].value - samples[-2].value
                self._initialized = True
        else:
            prev_level = self._level
            self._level = self._alpha * value + (1 - self._alpha) * (self._level + self._trend)
            self._trend = self._beta * (self._level - prev_level) + (1 - self._beta) * self._trend

    def forecast(self, horizon_seconds: float = _DEFAULT_FORECAST_HORIZON) -> LoadForecast:
        """
        Forecast load at the given horizon.

        Uses Holt's double exponential smoothing for trend-aware prediction.
        Confidence intervals widen with the forecast horizon.
        """
        if not self._initialized or self._level is None:
            # Not enough data — return neutral forecast with low confidence
            recent = list(self._samples)
            current = recent[-1].value if recent else 0.5
            return LoadForecast(
                predicted_load=current,
                confidence=0.1,
                lower_bound=max(0.0, current - 0.3),
                upper_bound=min(1.0, current + 0.3),
                horizon_seconds=horizon_seconds,
                method="naive",
            )

        # Estimate average sample interval
        samples = list(self._samples)
        if len(samples) >= 2:
            intervals = [
                samples[i + 1].timestamp - samples[i].timestamp
                for i in range(len(samples) - 1)
                if samples[i + 1].timestamp - samples[i].timestamp > 0
            ]
            avg_interval = sum(intervals) / len(intervals) if intervals else 30.0
        else:
            avg_interval = 30.0

        # Number of steps ahead
        steps = horizon_seconds / avg_interval

        # Holt's forecast: level + trend * steps
        predicted = self._level + self._trend * steps
        predicted = max(0.0, min(1.0, predicted))

        # Confidence based on sample count and forecast distance
        n_samples = len(samples)
        confidence = min(1.0, n_samples / 30.0)  # Full confidence at 30+ samples
        confidence *= max(0.2, 1.0 - steps / 100.0)  # Decay with distance

        # Confidence intervals based on historical variance
        if len(samples) >= 5:
            recent_values = [s.value for s in samples[-20:]]
            mean_val = sum(recent_values) / len(recent_values)
            variance = sum((v - mean_val) ** 2 for v in recent_values) / len(recent_values)
            std_dev = math.sqrt(variance)
            # Widen intervals with forecast distance
            interval_width = std_dev * (1 + steps * 0.1) * 1.645  # 90% CI
        else:
            interval_width = 0.2 * (1 + steps * 0.05)

        lower = max(0.0, predicted - interval_width)
        upper = min(1.0, predicted + interval_width)

        return LoadForecast(
            predicted_load=round(predicted, 4),
            confidence=round(confidence, 4),
            lower_bound=round(lower, 4),
            upper_bound=round(upper, 4),
            horizon_seconds=horizon_seconds,
            method="holt_double_exponential",
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get forecaster statistics."""
        return {
            "alpha": self._alpha,
            "beta": self._beta,
            "window_size": self._window_size,
            "samples_collected": len(self._samples),
            "initialized": self._initialized,
            "current_level": round(self._level, 4) if self._level is not None else None,
            "current_trend": round(self._trend, 6) if self._trend is not None else None,
        }


# ---------------------------------------------------------------------------
# Predictive Autoscaler
# ---------------------------------------------------------------------------


class PredictiveAutoscaler:
    """
    Zero-cost-aware predictive autoscaler.

    Proactively scales resources based on predicted load patterns while
    respecting free-tier limits. Uses Holt's double exponential smoothing
    for trend-aware forecasting.

    Scaling Logic:
        1. Collect current load metrics
        2. Forecast load at the configured horizon
        3. Determine scaling direction:
           - Scale UP if predicted load > scale_up_threshold
           - Scale DOWN if predicted load < scale_down_threshold
           - MAINTAIN otherwise
        4. Calculate target units based on predicted load
        5. Enforce zero-cost limits (never exceed free_tier_limit)
        6. Apply cooldown between scaling actions

    Usage:
        scaler = PredictiveAutoscaler()

        # Register scalable resources
        scaler.register_resource("api_workers", min_units=1, max_units=10, free_tier_limit=5)
        scaler.register_resource("storage_readers", min_units=1, max_units=8, free_tier_limit=4)

        # Record load metrics
        scaler.record_load("api_workers", 0.6)
        scaler.record_load("storage_readers", 0.3)

        # Get scaling decisions
        decisions = scaler.evaluate()
        for decision in decisions:
            print(f"{decision.direction}: {decision.current_units} → {decision.target_units}")
    """

    def __init__(
        self,
        forecast_horizon: float = _DEFAULT_FORECAST_HORIZON,
        smoothing_alpha: float = _DEFAULT_SMOOTHING_ALPHA,
    ):
        self._forecast_horizon = forecast_horizon
        self._smoothing_alpha = smoothing_alpha

        # Resource registrations
        self._resources: Dict[str, ScalerConfig] = {}
        self._forecasters: Dict[str, LoadForecaster] = {}

        # Decision history
        self._decision_history: List[ScalingDecision] = []
        self._total_scale_ups = 0
        self._total_scale_downs = 0
        self._total_maintains = 0
        self._zero_cost_violations_prevented = 0

    def register_resource(
        self,
        name: str,
        current_units: int = 1,
        min_units: int = _DEFAULT_MIN_CAPACITY_UNITS,
        max_units: int = _DEFAULT_MAX_CAPACITY_UNITS,
        free_tier_limit: int = _DEFAULT_FREE_TIER_LIMIT,
        scale_up_threshold: float = _DEFAULT_SCALE_UP_THRESHOLD,
        scale_down_threshold: float = _DEFAULT_SCALE_DOWN_THRESHOLD,
        cooldown_seconds: float = _DEFAULT_COOLDOWN_SECONDS,
    ) -> ScalerConfig:
        """Register a scalable resource for autoscaling."""
        config = ScalerConfig(
            name=name,
            current_units=current_units,
            min_units=min_units,
            max_units=max_units,
            free_tier_limit=free_tier_limit,
            scale_up_threshold=scale_up_threshold,
            scale_down_threshold=scale_down_threshold,
            cooldown_seconds=cooldown_seconds,
        )
        self._resources[name] = config
        self._forecasters[name] = LoadForecaster(
            alpha=self._smoothing_alpha,
        )
        logger.info(
            "Autoscaler resource registered: %s (units=%d, free_limit=%d)",
            sanitize_for_log(name),
            current_units,
            free_tier_limit,
        )
        return config

    def deregister_resource(self, name: str) -> bool:
        """Remove a resource from autoscaling."""
        if name in self._resources:
            del self._resources[name]
            del self._forecasters[name]
            return True
        return False

    def record_load(self, resource_name: str, load: float, source: str = "") -> None:
        """Record a load measurement for a resource."""
        forecaster = self._forecasters.get(resource_name)
        if forecaster:
            forecaster.record(load, source=source)

    def evaluate(self) -> List[ScalingDecision]:
        """
        Evaluate all resources and generate scaling decisions.

        Returns a list of ScalingDecision objects indicating what
        scaling actions (if any) should be taken.
        """
        decisions = []

        for name, config in self._resources.items():
            decision = self._evaluate_resource(name, config)
            decisions.append(decision)

            # Track in history
            self._decision_history.append(decision)
            if len(self._decision_history) > 1000:
                self._decision_history = self._decision_history[-1000:]

            if decision.direction == ScalingDirection.UP:
                self._total_scale_ups += 1
            elif decision.direction == ScalingDirection.DOWN:
                self._total_scale_downs += 1
            else:
                self._total_maintains += 1

        return decisions

    def _evaluate_resource(self, name: str, config: ScalerConfig) -> ScalingDecision:
        """Evaluate a single resource and determine scaling decision."""
        forecaster = self._forecasters.get(name)

        if not forecaster:
            return ScalingDecision(
                direction=ScalingDirection.MAINTAIN,
                current_units=config.current_units,
                target_units=config.current_units,
                reason=ScalingReason.INSUFFICIENT_DATA,
            )

        # Get forecast
        forecast = forecaster.forecast(self._forecast_horizon)

        # Check cooldown
        now = time.time()
        if (
            config.last_scale_action > 0
            and (now - config.last_scale_action) < config.cooldown_seconds
        ):
            return ScalingDecision(
                direction=ScalingDirection.MAINTAIN,
                current_units=config.current_units,
                target_units=config.current_units,
                reason=ScalingReason.COOLDOWN,
                forecast=forecast,
            )

        predicted = forecast.predicted_load

        # Determine scaling direction
        if predicted > config.scale_up_threshold:
            # Scale UP
            # Calculate how many units needed: load_per_unit * units >= predicted
            # Assume linear: each unit handles ~1/effective_max of the load
            load_per_unit = 1.0 / config.effective_max
            target_units = math.ceil(predicted / load_per_unit)
            target_units = min(target_units, config.effective_max)

            # Zero-cost compliance check
            zero_cost_compliant = target_units <= config.free_tier_limit
            if not zero_cost_compliant:
                target_units = config.free_tier_limit
                self._zero_cost_violations_prevented += 1
                logger.warning(
                    "Scaling capped at free-tier limit for %s: %d units",
                    sanitize_for_log(name),
                    target_units,
                )

            if target_units <= config.current_units:
                return ScalingDecision(
                    direction=ScalingDirection.MAINTAIN,
                    current_units=config.current_units,
                    target_units=config.current_units,
                    reason=ScalingReason.MAX_REACHED,
                    forecast=forecast,
                    zero_cost_compliant=zero_cost_compliant,
                )

            config.last_scale_action = now
            return ScalingDecision(
                direction=ScalingDirection.UP,
                current_units=config.current_units,
                target_units=target_units,
                reason=ScalingReason.PREDICTED_DEMAND
                if forecast.confidence > 0.3
                else ScalingReason.CURRENT_LOAD,
                forecast=forecast,
                zero_cost_compliant=zero_cost_compliant,
                metadata={"predicted_load": round(predicted, 4)},
            )

        elif predicted < config.scale_down_threshold:
            # Scale DOWN
            load_per_unit = 1.0 / config.effective_max
            target_units = max(config.min_units, math.ceil(predicted / load_per_unit))

            if target_units >= config.current_units:
                return ScalingDecision(
                    direction=ScalingDirection.MAINTAIN,
                    current_units=config.current_units,
                    target_units=config.current_units,
                    reason=ScalingReason.MIN_REACHED,
                    forecast=forecast,
                )

            config.last_scale_action = now
            return ScalingDecision(
                direction=ScalingDirection.DOWN,
                current_units=config.current_units,
                target_units=target_units,
                reason=ScalingReason.PREDICTED_DEMAND,
                forecast=forecast,
                metadata={"predicted_load": round(predicted, 4)},
            )

        else:
            # Maintain current capacity
            return ScalingDecision(
                direction=ScalingDirection.MAINTAIN,
                current_units=config.current_units,
                target_units=config.current_units,
                reason=ScalingReason.PREDICTED_DEMAND,
                forecast=forecast,
            )

    def apply_decision(self, decision: ScalingDecision) -> bool:
        """Apply a scaling decision to update resource units."""
        config = self._resources.get(decision.target_units and "")
        # Find by matching the decision to a resource
        for name, config in self._resources.items():
            if config.current_units == decision.current_units:
                config.current_units = decision.target_units
                decision.executed = True
                logger.info(
                    "Scaling applied: %s %d → %d (%s)",
                    sanitize_for_log(name),
                    decision.current_units,
                    decision.target_units,
                    decision.direction.value,
                )
                return True
        return False

    def get_forecast(self, resource_name: str) -> Optional[LoadForecast]:
        """Get the current load forecast for a resource."""
        forecaster = self._forecasters.get(resource_name)
        if forecaster:
            return forecaster.forecast(self._forecast_horizon)
        return None

    def get_resource_status(self, resource_name: str) -> Optional[Dict[str, Any]]:
        """Get the status of a registered resource."""
        config = self._resources.get(resource_name)
        forecast = self.get_forecast(resource_name)
        if not config:
            return None
        return {
            **config.to_dict(),
            "forecast": forecast.to_dict() if forecast else None,
        }

    def get_all_status(self) -> Dict[str, Dict[str, Any]]:
        """Get the status of all registered resources."""
        return {name: self.get_resource_status(name) or {} for name in self._resources}

    def get_recent_decisions(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent scaling decisions."""
        return [d.to_dict() for d in self._decision_history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive autoscaler statistics."""
        return {
            "forecast_horizon": self._forecast_horizon,
            "resources_managed": len(self._resources),
            "total_scale_ups": self._total_scale_ups,
            "total_scale_downs": self._total_scale_downs,
            "total_maintains": self._total_maintains,
            "zero_cost_violations_prevented": self._zero_cost_violations_prevented,
            "resources": {name: config.to_dict() for name, config in self._resources.items()},
            "forecasters": {
                name: forecaster.get_stats() for name, forecaster in self._forecasters.items()
            },
        }


# Singleton
predictive_scaler = PredictiveAutoscaler()
