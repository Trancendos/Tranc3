"""Predictive Scaling Engine — Phase 12

Anticipatory resource provisioning using time-series forecasting
and load pattern recognition. Zero-cost implementation using
double exponential smoothing and seasonal decomposition.
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ScalingDirection(Enum):
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    HOLD = "hold"


class ScalingReason(Enum):
    LOAD_FORECAST = "load_forecast"
    SCHEDULE_PATTERN = "schedule_pattern"
    ANOMALY_PREDICTED = "anomaly_predicted"
    COST_OPTIMIZATION = "cost_optimization"
    MANUAL_OVERRIDE = "manual_override"


class ResourceType(Enum):
    CPU = "cpu"
    MEMORY = "memory"
    INSTANCES = "instances"
    CONNECTIONS = "connections"
    QUEUE_WORKERS = "queue_workers"
    GPU = "gpu"


@dataclass
class LoadObservation:
    timestamp: float = field(default_factory=time.time)
    resource_type: ResourceType = ResourceType.CPU
    value: float = 0.0
    service_name: str = ""


@dataclass
class ScalingDecision:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    direction: ScalingDirection = ScalingDirection.HOLD
    reason: ScalingReason = ScalingReason.LOAD_FORECAST
    resource_type: ResourceType = ResourceType.CPU
    service_name: str = ""
    current_value: float = 0.0
    target_value: float = 0.0
    confidence: float = 0.0
    forecast_horizon_seconds: float = 300.0
    created_at: float = field(default_factory=time.time)
    executed: bool = False


@dataclass
class ScalingPolicy:
    service_name: str
    resource_type: ResourceType
    min_value: float = 1.0
    max_value: float = 100.0
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    cooldown_seconds: float = 120.0
    forecast_window_seconds: float = 300.0


class DoubleExponentialSmoother:
    """Holt's double exponential smoothing for trend detection."""

    def __init__(self, alpha: float = 0.3, beta: float = 0.1):
        self._alpha = alpha
        self._beta = beta
        self._level: Optional[float] = None
        self._trend: Optional[float] = None
        self._count: int = 0

    def update(self, value: float) -> None:
        if self._level is None:
            self._level = value
            self._trend = 0.0
        else:
            new_level = self._alpha * value + (1 - self._alpha) * (self._level + self._trend)
            new_trend = self._beta * (new_level - self._level) + (1 - self._beta) * self._trend
            self._level = new_level
            self._trend = new_trend
        self._count += 1

    def forecast(self, steps: int = 1) -> float:
        if self._level is None or self._trend is None:
            return 0.0
        return self._level + steps * self._trend

    @property
    def is_ready(self) -> bool:
        return self._count >= 3

    @property
    def trend(self) -> float:
        return self._trend if self._trend is not None else 0.0


class SeasonalPatternDetector:
    """Detects daily/weekly seasonal patterns using period averages."""

    def __init__(self, period_seconds: float = 86400.0, buckets: int = 24):
        self._period = period_seconds
        self._buckets = buckets
        self._bucket_sums: Dict[int, float] = {}
        self._bucket_counts: Dict[int, int] = {}
        self._observations: List[LoadObservation] = []

    def observe(self, obs: LoadObservation) -> None:
        self._observations.append(obs)
        bucket = self._time_to_bucket(obs.timestamp)
        self._bucket_sums[bucket] = self._bucket_sums.get(bucket, 0.0) + obs.value
        self._bucket_counts[bucket] = self._bucket_counts.get(bucket, 0) + 1

    def _time_to_bucket(self, timestamp: float) -> int:
        phase = (timestamp % self._period) / self._period
        return int(phase * self._buckets) % self._buckets

    def get_seasonal_factor(self, timestamp: float) -> float:
        bucket = self._time_to_bucket(timestamp)
        if bucket not in self._bucket_sums or self._bucket_counts.get(bucket, 0) < 3:
            return 1.0
        avg = self._bucket_sums[bucket] / self._bucket_counts[bucket]
        total_avg = sum(self._bucket_sums.values()) / max(1, sum(self._bucket_counts.values()))
        if total_avg < 1e-10:
            return 1.0
        return avg / total_avg

    @property
    def is_ready(self) -> bool:
        return sum(self._bucket_counts.values()) >= self._buckets * 3


class PredictiveScalingEngine:
    """Main engine: forecasts load and generates scaling decisions."""

    def __init__(self, forecast_horizon: float = 300.0):
        self._forecast_horizon = forecast_horizon
        self._smoothers: Dict[str, DoubleExponentialSmoother] = {}
        self._seasonal: Dict[str, SeasonalPatternDetector] = {}
        self._policies: Dict[str, ScalingPolicy] = {}
        self._decisions: List[ScalingDecision] = []
        self._last_scaling_time: Dict[str, float] = {}

    def add_policy(self, policy: ScalingPolicy) -> None:
        key = f"{policy.service_name}:{policy.resource_type.value}"
        self._policies[key] = policy
        smoother_key = f"{policy.service_name}:{policy.resource_type.value}"
        if smoother_key not in self._smoothers:
            self._smoothers[smoother_key] = DoubleExponentialSmoother()
        if smoother_key not in self._seasonal:
            self._seasonal[smoother_key] = SeasonalPatternDetector()

    def observe_load(self, obs: LoadObservation) -> Optional[ScalingDecision]:
        smoother_key = f"{obs.service_name}:{obs.resource_type.value}"
        if smoother_key not in self._smoothers:
            self._smoothers[smoother_key] = DoubleExponentialSmoother()
        if smoother_key not in self._seasonal:
            self._seasonal[smoother_key] = SeasonalPatternDetector()

        self._smoothers[smoother_key].update(obs.value)
        self._seasonal[smoother_key].observe(obs)

        policy_key = smoother_key
        if policy_key in self._policies:
            return self._evaluate_scaling(obs, smoother_key)

        return None

    def _evaluate_scaling(self, obs: LoadObservation, key: str) -> Optional[ScalingDecision]:
        policy = self._policies.get(key)
        smoother = self._smoothers[key]
        seasonal = self._seasonal[key]

        if not smoother.is_ready:
            return None

        if policy is None:
            return None

        # Cooldown check
        last_time = self._last_scaling_time.get(key, 0.0)
        if time.time() - last_time < policy.cooldown_seconds:
            return None

        # Forecast future load
        steps = max(1, int(self._forecast_horizon / 60))
        base_forecast = smoother.forecast(steps)
        seasonal_factor = (
            seasonal.get_seasonal_factor(time.time() + self._forecast_horizon)
            if seasonal.is_ready
            else 1.0
        )
        forecast = base_forecast * seasonal_factor

        # Normalize to 0-1 utilization
        utilization = min(1.0, max(0.0, forecast / policy.max_value))

        direction = ScalingDirection.HOLD
        reason = ScalingReason.LOAD_FORECAST

        if utilization > policy.scale_up_threshold:
            direction = ScalingDirection.SCALE_UP
            target = min(policy.max_value, obs.value * 1.5)
        elif utilization < policy.scale_down_threshold:
            direction = ScalingDirection.SCALE_DOWN
            target = max(policy.min_value, obs.value * 0.7)
            reason = ScalingReason.COST_OPTIMIZATION
        else:
            return None

        confidence = min(1.0, abs(smoother.trend) * 10) if smoother.is_ready else 0.0

        decision = ScalingDecision(
            direction=direction,
            reason=reason,
            resource_type=obs.resource_type,
            service_name=obs.service_name,
            current_value=obs.value,
            target_value=target,
            confidence=confidence,
            forecast_horizon_seconds=self._forecast_horizon,
        )
        self._decisions.append(decision)
        self._last_scaling_time[key] = time.time()

        logger.info(
            "Scaling decision: %s %s for %s — current=%.1f target=%.1f confidence=%.2f",
            direction.value,
            obs.resource_type.value,
            obs.service_name,
            obs.value,
            target,
            confidence,
        )
        return decision

    def get_forecast(
        self, service_name: str, resource_type: ResourceType, steps: int = 5
    ) -> List[float]:
        key = f"{service_name}:{resource_type.value}"
        smoother = self._smoothers.get(key)
        if not smoother or not smoother.is_ready:
            return []
        seasonal = self._seasonal.get(key)
        forecasts = []
        for i in range(1, steps + 1):
            base = smoother.forecast(i)
            factor = (
                seasonal.get_seasonal_factor(time.time() + i * 60)
                if seasonal and seasonal.is_ready
                else 1.0
            )
            forecasts.append(base * factor)
        return forecasts

    def get_decisions(self, limit: int = 50) -> List[ScalingDecision]:
        return self._decisions[-limit:]

    def get_trend(self, service_name: str, resource_type: ResourceType) -> float:
        key = f"{service_name}:{resource_type.value}"
        smoother = self._smoothers.get(key)
        return smoother.trend if smoother and smoother.is_ready else 0.0
