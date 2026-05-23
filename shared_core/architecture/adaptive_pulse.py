"""
shared_core.architecture.adaptive_pulse — Dynamic Interval Controller for Tranc3 Daemons.

The AdaptivePulseController dynamically adjusts the check/orchestration intervals
for all long-running daemons and subsystems based on real-time system conditions.
When the system is stable, intervals are stretched to conserve resources. When
degradation is detected, intervals are compressed for faster detection and response.

This ensures the platform is:
    - Efficient:  Minimal resource usage during stable operation
    - Responsive: Rapid detection and response during degradation
    - Adaptive:   Seamless transitions between operational cadences
    - Proactive:  Pre-accelerates based on predicted degradation

Pulse Modes:
    STEADY      — Normal operation, intervals at baseline
    ACCELERATED — Degradation detected, intervals compressed 2-4x
    EMERGENCY   — Critical issues, intervals compressed 10x
    RECOVERY    — System recovering, gradually returning to baseline

Integration Points:
    - Sentinel check_interval
    - EnhancedServiceRegistry discovery_interval
    - ProactiveOrchestrator orchestration_interval
    - SmartStorageOrchestrator capacity check interval
    - DefenseEngine threat scan interval

Architecture:
    ┌─────────────────────────────────────────────────┐
    │          AdaptivePulseController                  │
    │                                                   │
    │  ┌───────────┐  ┌──────────────┐  ┌───────────┐ │
    │  │  System    │  │  Interval    │  │  Backoff   │ │
    │  │  Monitor   │  │  Calculator  │  │  Manager   │ │
    │  └─────┬─────┘  └──────┬───────┘  └─────┬─────┘ │
    │        │               │                 │       │
    │  ┌─────┴───────────────┴─────────────────┴─────┐ │
    │  │              Pulse History                    │ │
    │  │  (adaptive tracking, mode transitions)       │ │
    │  └─────────────────────────────────────────────┘ │
    └─────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
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

_DEFAULT_BASELINE_INTERVAL = 30.0    # seconds — steady-state interval
_DEFAULT_MIN_INTERVAL = 1.0          # seconds — absolute minimum
_DEFAULT_MAX_INTERVAL = 300.0        # seconds — absolute maximum (5 min)
_DEFAULT_ACCELERATION_FACTOR = 3.0   # how much to compress in ACCELERATED
_DEFAULT_EMERGENCY_FACTOR = 10.0     # how much to compress in EMERGENCY
_DEFAULT_RECOVERY_RATE = 0.1         # how quickly to return to baseline
_DEFAULT_HEALTH_THRESHOLD_ACCEL = 0.7  # health score below this → ACCELERATED
_DEFAULT_HEALTH_THRESHOLD_EMERG = 0.4  # health score below this → EMERGENCY


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PulseMode(str, Enum):
    """Operational cadence for daemon intervals."""
    STEADY = "steady"
    ACCELERATED = "accelerated"
    EMERGENCY = "emergency"
    RECOVERY = "recovery"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

@dataclass
class PulseConfig:
    """Configuration for a single daemon's pulse."""
    name: str
    baseline_interval: float = _DEFAULT_BASELINE_INTERVAL
    min_interval: float = _DEFAULT_MIN_INTERVAL
    max_interval: float = _DEFAULT_MAX_INTERVAL
    current_interval: float = 0.0  # 0.0 = use baseline_interval
    pulse_mode: PulseMode = PulseMode.STEADY
    last_fired: float = 0.0
    fire_count: int = 0
    adaptive_enabled: bool = True

    def __post_init__(self):
        if self.current_interval == 0.0:
            self.current_interval = self.baseline_interval

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "baseline_interval": round(self.baseline_interval, 2),
            "current_interval": round(self.current_interval, 2),
            "min_interval": round(self.min_interval, 2),
            "max_interval": round(self.max_interval, 2),
            "pulse_mode": self.pulse_mode.value,
            "last_fired": self.last_fired,
            "fire_count": self.fire_count,
            "adaptive_enabled": self.adaptive_enabled,
            "compression_ratio": round(self.baseline_interval / max(self.current_interval, 0.001), 2),
        }


@dataclass
class PulseTransition:
    """Record of a pulse mode transition."""
    from_mode: PulseMode
    to_mode: PulseMode
    reason: str
    timestamp: float = field(default_factory=time.time)
    health_score: float = 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_mode": self.from_mode.value,
            "to_mode": self.to_mode.value,
            "reason": self.reason,
            "timestamp": self.timestamp,
            "health_score": round(self.health_score, 4),
        }


@dataclass
class PulseMetrics:
    """Aggregate metrics for the pulse controller."""
    current_mode: PulseMode = PulseMode.STEADY
    total_transitions: int = 0
    time_in_steady: float = 0.0
    time_in_accelerated: float = 0.0
    time_in_emergency: float = 0.0
    time_in_recovery: float = 0.0
    daemons_managed: int = 0
    avg_compression_ratio: float = 1.0
    last_mode_change: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "current_mode": self.current_mode.value,
            "total_transitions": self.total_transitions,
            "time_in_steady": round(self.time_in_steady, 1),
            "time_in_accelerated": round(self.time_in_accelerated, 1),
            "time_in_emergency": round(self.time_in_emergency, 1),
            "time_in_recovery": round(self.time_in_recovery, 1),
            "daemons_managed": self.daemons_managed,
            "avg_compression_ratio": round(self.avg_compression_ratio, 2),
            "last_mode_change": self.last_mode_change,
        }


# ---------------------------------------------------------------------------
# Adaptive Pulse Controller
# ---------------------------------------------------------------------------

class AdaptivePulseController:
    """
    Dynamic interval controller for Tranc3 daemons.

    Manages check intervals for all long-running subsystems based on
    real-time health conditions. When the system is healthy, intervals
    are stretched to minimize overhead. When issues are detected, intervals
    are compressed for faster detection and response.

    The controller uses a simple but effective algorithm:
        1. Monitor system health score (0.0 to 1.0)
        2. Map health score to a PulseMode
        3. Adjust intervals based on mode:
           - STEADY:      baseline_interval
           - ACCELERATED: baseline_interval / acceleration_factor
           - EMERGENCY:   baseline_interval / emergency_factor
           - RECOVERY:    gradually return to baseline from current
        4. Respect min/max interval bounds
        5. Gradual transitions (no sudden jumps)

    Usage:
        pulse = AdaptivePulseController()

        # Register daemons
        pulse.register("sentinel", baseline_interval=300.0)
        pulse.register("discovery", baseline_interval=60.0)
        pulse.register("orchestrator", baseline_interval=30.0)

        # Update based on system health
        pulse.update(health_score=0.65)  # → ACCELERATED

        # Get current intervals
        interval = pulse.get_interval("sentinel")  # 300.0 / 3.0 = 100.0
    """

    def __init__(
        self,
        *,
        acceleration_factor: float = _DEFAULT_ACCELERATION_FACTOR,
        emergency_factor: float = _DEFAULT_EMERGENCY_FACTOR,
        recovery_rate: float = _DEFAULT_RECOVERY_RATE,
        health_threshold_accel: float = _DEFAULT_HEALTH_THRESHOLD_ACCEL,
        health_threshold_emerg: float = _DEFAULT_HEALTH_THRESHOLD_EMERG,
        global_baseline: float = _DEFAULT_BASELINE_INTERVAL,
        global_min: float = _DEFAULT_MIN_INTERVAL,
        global_max: float = _DEFAULT_MAX_INTERVAL,
    ):
        self._acceleration_factor = acceleration_factor
        self._emergency_factor = emergency_factor
        self._recovery_rate = recovery_rate
        self._health_threshold_accel = health_threshold_accel
        self._health_threshold_emerg = health_threshold_emerg
        self._global_baseline = global_baseline
        self._global_min = global_min
        self._global_max = global_max

        # Daemon registrations
        self._daemons: Dict[str, PulseConfig] = {}

        # State tracking
        self._current_mode = PulseMode.STEADY
        self._last_health_score = 1.0
        self._mode_history: deque = deque(maxlen=1000)
        self._transition_times: Dict[PulseMode, float] = {
            PulseMode.STEADY: 0.0,
            PulseMode.ACCELERATED: 0.0,
            PulseMode.EMERGENCY: 0.0,
            PulseMode.RECOVERY: 0.0,
        }
        self._last_mode_change_time: float = time.time()
        self._health_history: deque = deque(maxlen=200)  # recent health scores

        # Register self as a daemon
        self.register(
            "pulse_controller",
            baseline_interval=10.0,
            min_interval=5.0,
            max_interval=60.0,
        )

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self,
        name: str,
        baseline_interval: Optional[float] = None,
        min_interval: Optional[float] = None,
        max_interval: Optional[float] = None,
        adaptive_enabled: bool = True,
    ) -> PulseConfig:
        """Register a daemon for adaptive pulse control."""
        config = PulseConfig(
            name=name,
            baseline_interval=baseline_interval or self._global_baseline,
            min_interval=min_interval or self._global_min,
            max_interval=max_interval or self._global_max,
            adaptive_enabled=adaptive_enabled,
        )
        self._daemons[name] = config
        logger.info(
            "Pulse registered: %s (baseline=%.1fs)",
            sanitize_for_log(name),
            config.baseline_interval,
        )
        return config

    def deregister(self, name: str) -> bool:
        """Remove a daemon from pulse control."""
        if name in self._daemons:
            del self._daemons[name]
            return True
        return False

    # ------------------------------------------------------------------
    # Health-Based Mode Selection
    # ------------------------------------------------------------------

    def update(self, health_score: float, reason: str = "") -> PulseMode:
        """
        Update the pulse mode based on the current system health score.

        Args:
            health_score: 0.0 (failing) to 1.0 (healthy)
            reason: Human-readable reason for the health score

        Returns:
            The new PulseMode after the update
        """
        health_score = max(0.0, min(1.0, health_score))
        self._last_health_score = health_score
        self._health_history.append((time.time(), health_score))

        # Determine target mode based on health score
        if health_score < self._health_threshold_emerg:
            target_mode = PulseMode.EMERGENCY
        elif health_score < self._health_threshold_accel:
            target_mode = PulseMode.ACCELERATED
        elif self._current_mode == PulseMode.EMERGENCY:
            # Coming out of emergency → recovery first
            target_mode = PulseMode.RECOVERY
        elif self._current_mode == PulseMode.ACCELERATED:
            # Coming out of accelerated → recovery first
            target_mode = PulseMode.RECOVERY
        elif self._current_mode == PulseMode.RECOVERY:
            # Stay in recovery until health is fully restored
            if health_score >= 0.9:
                target_mode = PulseMode.STEADY
            else:
                target_mode = PulseMode.RECOVERY
        else:
            target_mode = PulseMode.STEADY

        # Apply mode transition if changed
        if target_mode != self._current_mode:
            self._apply_transition(target_mode, health_score, reason)

        # Update all daemon intervals based on current mode
        self._update_intervals()

        return self._current_mode

    def force_mode(self, mode: PulseMode, reason: str = "manual_override") -> None:
        """Force the pulse to a specific mode (for testing or manual override)."""
        self._apply_transition(mode, self._last_health_score, reason)
        self._update_intervals()

    def _apply_transition(self, new_mode: PulseMode, health_score: float, reason: str) -> None:
        """Apply a pulse mode transition and record it."""
        # Track time spent in previous mode
        now = time.time()
        time_in_mode = now - self._last_mode_change_time
        if self._current_mode in self._transition_times:
            self._transition_times[self._current_mode] += time_in_mode

        # Record transition
        transition = PulseTransition(
            from_mode=self._current_mode,
            to_mode=new_mode,
            reason=reason,
            health_score=health_score,
        )
        self._mode_history.append(transition)

        old_mode = self._current_mode
        self._current_mode = new_mode
        self._last_mode_change_time = now

        logger.info(
            "Pulse mode transition: %s → %s (health=%.2f, reason=%s)",
            old_mode.value,
            new_mode.value,
            health_score,
            sanitize_for_log(reason),
        )

    # ------------------------------------------------------------------
    # Interval Calculation
    # ------------------------------------------------------------------

    def _update_intervals(self) -> None:
        """Update all daemon intervals based on the current pulse mode."""
        for _name, config in self._daemons.items():
            if not config.adaptive_enabled:
                continue

            target = self._calculate_target_interval(config)
            self._apply_gradual_change(config, target)

    def _calculate_target_interval(self, config: PulseConfig) -> float:
        """Calculate the target interval for a daemon based on current mode."""
        baseline = config.baseline_interval

        if self._current_mode == PulseMode.STEADY:
            return baseline

        elif self._current_mode == PulseMode.ACCELERATED:
            return max(config.min_interval, baseline / self._acceleration_factor)

        elif self._current_mode == PulseMode.EMERGENCY:
            return max(config.min_interval, baseline / self._emergency_factor)

        elif self._current_mode == PulseMode.RECOVERY:
            # Gradually return to baseline
            current = config.current_interval
            recovery_target = current + (baseline - current) * self._recovery_rate
            return min(config.max_interval, recovery_target)

        return baseline

    def _apply_gradual_change(self, config: PulseConfig, target: float) -> None:
        """Apply a gradual change to a daemon's interval (no sudden jumps)."""
        current = config.current_interval
        max_change_rate = 0.3  # Max 30% change per update

        if abs(target - current) / max(current, 0.001) < 0.05:
            # Within 5% — snap to target
            config.current_interval = target
        elif target < current:
            # Compressing (faster checks)
            config.current_interval = max(
                target,
                current * (1.0 - max_change_rate),
            )
        else:
            # Stretching (slower checks)
            config.current_interval = min(
                target,
                current * (1.0 + max_change_rate),
            )

        # Clamp to bounds
        config.current_interval = max(
            config.min_interval,
            min(config.max_interval, config.current_interval),
        )
        config.pulse_mode = self._current_mode

    # ------------------------------------------------------------------
    # Query Interface
    # ------------------------------------------------------------------

    def get_interval(self, name: str) -> float:
        """Get the current interval for a registered daemon."""
        config = self._daemons.get(name)
        if not config:
            return self._global_baseline
        return config.current_interval

    def should_fire(self, name: str) -> bool:
        """Check if a daemon should fire now based on its interval."""
        config = self._daemons.get(name)
        if not config:
            return True

        now = time.time()
        if config.last_fired == 0.0:
            return True  # Never fired

        elapsed = now - config.last_fired
        return elapsed >= config.current_interval

    def record_fire(self, name: str) -> None:
        """Record that a daemon has fired."""
        config = self._daemons.get(name)
        if config:
            config.last_fired = time.time()
            config.fire_count += 1

    def get_config(self, name: str) -> Optional[PulseConfig]:
        """Get the pulse config for a specific daemon."""
        return self._daemons.get(name)

    def get_all_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get pulse configs for all registered daemons."""
        return {name: config.to_dict() for name, config in self._daemons.items()}

    @property
    def current_mode(self) -> PulseMode:
        """Get the current pulse mode."""
        return self._current_mode

    @property
    def last_health_score(self) -> float:
        """Get the last reported health score."""
        return self._last_health_score

    # ------------------------------------------------------------------
    # Introspection & Statistics
    # ------------------------------------------------------------------

    def get_transition_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent pulse mode transitions."""
        transitions = list(self._mode_history)
        return [t.to_dict() for t in transitions[-limit:]]

    def get_health_trend(self) -> str:
        """Get the health score trend (improving, stable, degrading)."""
        if len(self._health_history) < 3:
            return "stable"

        recent = [h for _, h in list(self._health_history)[-10:]]
        if len(recent) < 3:
            return "stable"

        # Simple trend: compare first half to second half
        mid = len(recent) // 2
        first_half_avg = sum(recent[:mid]) / mid
        second_half_avg = sum(recent[mid:]) / (len(recent) - mid)

        diff = second_half_avg - first_half_avg
        if diff > 0.05:
            return "improving"
        elif diff < -0.05:
            return "degrading"
        return "stable"

    def get_metrics(self) -> PulseMetrics:
        """Get aggregate pulse metrics."""
        configs = list(self._daemons.values())
        avg_compression = 1.0
        if configs:
            compressions = [
                c.baseline_interval / max(c.current_interval, 0.001)
                for c in configs
            ]
            avg_compression = sum(compressions) / len(compressions)

        return PulseMetrics(
            current_mode=self._current_mode,
            total_transitions=len(self._mode_history),
            time_in_steady=self._transition_times[PulseMode.STEADY],
            time_in_accelerated=self._transition_times[PulseMode.ACCELERATED],
            time_in_emergency=self._transition_times[PulseMode.EMERGENCY],
            time_in_recovery=self._transition_times[PulseMode.RECOVERY],
            daemons_managed=len(self._daemons),
            avg_compression_ratio=avg_compression,
            last_mode_change=self._last_mode_change_time,
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive pulse controller statistics."""
        return {
            "current_mode": self._current_mode.value,
            "last_health_score": round(self._last_health_score, 4),
            "health_trend": self.get_health_trend(),
            "acceleration_factor": self._acceleration_factor,
            "emergency_factor": self._emergency_factor,
            "recovery_rate": self._recovery_rate,
            "daemons": self.get_all_configs(),
            "metrics": self.get_metrics().to_dict(),
            "recent_transitions": self.get_transition_history(10),
        }


# Singleton
adaptive_pulse = AdaptivePulseController()
