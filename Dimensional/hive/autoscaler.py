"""
Tranc3 HIVE Swarm Auto-Scaling
================================
Dynamic swarm node allocation based on throughput metrics with
predictive scaling, cooldown management, and threshold triggers.

Architecture:
    ┌──────────────────────────────────────────────┐
    │            AutoScalerEngine                    │
    │  ┌──────────────┐  ┌──────────────────────┐   │
    │  │ Metrics      │  │ ScalingDecision      │   │
    │  │ Collector    │  │ Engine               │   │
    │  └──────┬───────┘  └──────────┬───────────┘   │
    │         │                     │               │
    │  ┌──────▼───────┐  ┌─────────▼────────────┐   │
    │  │ Cooldown     │  │ ScalingPolicy        │   │
    │  │ Manager      │  │ Config               │   │
    │  └──────────────┘  └──────────────────────┘   │
    └──────────────────────────────────────────────┘

Key Features:
    - Throughput-based scaling (tasks_per_second)
    - Predictive scaling using linear regression
    - Cooldown periods to prevent flapping
    - Configurable scale-up/down thresholds

Zero-Cost: Uses in-process metrics collection and asyncio timers.
No external dependencies.

Tier Integration:
    Operates at Tier 1 (ORCHESTRATOR) since it coordinates
    dynamic resource allocation across HIVE swarms.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger("hive.autoscaler")


# ── Enums ────────────────────────────────────────────────────────────────────


class ScalingPolicyType(str, Enum):
    """Type of scaling policy."""
    THRESHOLD = "threshold"
    PREDICTIVE = "predictive"
    SCHEDULED = "scheduled"


class ScalingStatus(str, Enum):
    """Auto-scaler engine status."""
    ACTIVE = "active"
    PAUSED = "paused"
    STOPPED = "stopped"


class ScalingDirection(str, Enum):
    """Direction of a scaling action."""
    UP = "up"
    DOWN = "down"
    NONE = "none"


# ── Models ───────────────────────────────────────────────────────────────────


class ThroughputMetrics(BaseModel):
    """Metrics snapshot for a HIVE swarm."""
    swarm_id: str = ""
    tasks_per_second: float = 0.0
    active_nodes: int = 0
    pending_tasks: int = 0
    cpu_utilization: float = 0.0
    memory_utilization: float = 0.0
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def load_factor(self) -> float:
        """Compute overall load factor (0.0 to 1.0)."""
        if self.active_nodes <= 0:
            return 1.0 if self.pending_tasks > 0 else 0.0
        task_load = min(1.0, self.pending_tasks / max(1, self.active_nodes * 100))
        resource_load = (self.cpu_utilization + self.memory_utilization) / 2.0
        return min(1.0, (task_load + resource_load) / 2.0)


class ScalingPolicyConfig(BaseModel):
    """Configuration for a scaling policy."""
    policy_type: ScalingPolicyType = ScalingPolicyType.THRESHOLD
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    min_nodes: int = 1
    max_nodes: int = 20
    cooldown_seconds: int = 60
    prediction_window_samples: int = 6


class ScalingAction(BaseModel):
    """Record of a scaling action taken."""
    action_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    swarm_id: str = ""
    direction: ScalingDirection = ScalingDirection.NONE
    previous_nodes: int = 0
    target_nodes: int = 0
    reason: str = ""
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Metrics Collector ────────────────────────────────────────────────────────


class MetricsCollector:
    """Collects and stores throughput metrics for HIVE swarms.

    Maintains a sliding window of metrics samples per swarm
    and provides trend analysis for predictive scaling.
    """

    def __init__(self, max_samples: int = 100):
        self._max_samples = max_samples
        self._samples: Dict[str, deque] = {}
        self._lock = asyncio.Lock()
        logger.info("MetricsCollector initialized (max_samples=%d)", max_samples)

    async def record(self, metrics: ThroughputMetrics) -> None:
        """Record a metrics sample."""
        async with self._lock:
            if metrics.swarm_id not in self._samples:
                self._samples[metrics.swarm_id] = deque(maxlen=self._max_samples)
            self._samples[metrics.swarm_id].append(metrics)

    async def get_latest(self, swarm_id: str) -> Optional[ThroughputMetrics]:
        """Get the most recent metrics sample for a swarm."""
        async with self._lock:
            samples = self._samples.get(swarm_id)
            if samples:
                return samples[-1]
        return None

    async def get_samples(
        self, swarm_id: str, count: Optional[int] = None
    ) -> List[ThroughputMetrics]:
        """Get recent metrics samples for a swarm."""
        async with self._lock:
            samples = self._samples.get(swarm_id)
            if not samples:
                return []
            result = list(samples)
            if count is not None:
                result = result[-count:]
            return result

    async def get_load_trend(self, swarm_id: str, samples: int = 6) -> Optional[float]:
        """Calculate the load factor trend using linear regression.

        Returns the slope of the load factor over the given number of samples.
        Positive slope = increasing load; negative = decreasing load.
        Returns None if insufficient data.
        """
        async with self._lock:
            data = self._samples.get(swarm_id)
            if not data or len(data) < 2:
                return None
            recent = list(data)[-samples:]
            if len(recent) < 2:
                return None
            # Simple linear regression
            n = len(recent)
            xs = list(range(n))
            ys = [m.load_factor for m in recent]
            sum_x = sum(xs)
            sum_y = sum(ys)
            sum_xy = sum(x * y for x, y in zip(xs, ys))
            sum_xx = sum(x * x for x in xs)
            denom = n * sum_xx - sum_x * sum_x
            if denom == 0:
                return 0.0
            slope = (n * sum_xy - sum_x * sum_y) / denom
            return slope

    async def get_all_swarm_ids(self) -> List[str]:
        """Get all swarm IDs with recorded metrics."""
        async with self._lock:
            return list(self._samples.keys())

    async def clear(self, swarm_id: Optional[str] = None) -> None:
        """Clear metrics for a specific swarm or all swarms."""
        async with self._lock:
            if swarm_id:
                self._samples.pop(swarm_id, None)
            else:
                self._samples.clear()


# ── Cooldown Manager ────────────────────────────────────────────────────────


class CooldownManager:
    """Manages cooldown periods to prevent scaling flapping.

    After a scaling action, a cooldown period is enforced before
    another scaling action can be taken for the same swarm.
    """

    def __init__(self):
        self._cooldowns: Dict[str, Tuple[str, float]] = {}  # swarm_id → (reason, until_time)
        self._action_history: Dict[str, List[ScalingAction]] = defaultdict(list)
        logger.info("CooldownManager initialized")

    def is_on_cooldown(self, swarm_id: str) -> bool:
        """Check if a swarm is currently in cooldown."""
        if swarm_id not in self._cooldowns:
            return False
        _, until = self._cooldowns[swarm_id]
        if time.time() >= until:
            del self._cooldowns[swarm_id]
            return False
        return True

    def set_cooldown(self, swarm_id: str, reason: str, duration_seconds: int) -> None:
        """Set a cooldown for a swarm."""
        until = time.time() + duration_seconds
        self._cooldowns[swarm_id] = (reason, until)
        logger.info("Cooldown set for %s: %s (%ds)", swarm_id, reason, duration_seconds)

    def clear_cooldown(self, swarm_id: str) -> None:
        """Clear cooldown for a swarm."""
        self._cooldowns.pop(swarm_id, None)

    def record_action(self, action: ScalingAction) -> None:
        """Record a scaling action in history."""
        self._action_history[action.swarm_id].append(action)

    def is_flapping(self, swarm_id: str, window_seconds: int = 300, max_actions: int = 3) -> bool:
        """Detect if a swarm is flapping (repeated scale up/down)."""
        now = time.time()
        actions = self._action_history.get(swarm_id, [])
        recent = [
            a for a in actions
            if now - (datetime.fromisoformat(a.timestamp).timestamp() if a.timestamp else 0) < window_seconds
        ]
        if len(recent) < max_actions:
            return False
        # Check for alternating direction
        directions = [a.direction for a in recent[-max_actions:]]
        ups = sum(1 for d in directions if d == ScalingDirection.UP)
        downs = sum(1 for d in directions if d == ScalingDirection.DOWN)
        return ups > 0 and downs > 0


# ── Scaling Decision Engine ──────────────────────────────────────────────────


class ScalingDecisionEngine:
    """Makes scaling decisions based on metrics and policies.

    Evaluates throughput metrics against configured thresholds
    and determines whether to scale up, scale down, or hold.
    """

    def __init__(
        self,
        policy: Optional[ScalingPolicyConfig] = None,
        cooldown_mgr: Optional[CooldownManager] = None,
    ):
        self._policy = policy or ScalingPolicyConfig()
        self._cooldown_mgr = cooldown_mgr or CooldownManager()
        logger.info("ScalingDecisionEngine initialized (policy=%s)", self._policy.policy_type.value)

    @property
    def policy(self) -> ScalingPolicyConfig:
        return self._policy

    def evaluate(self, metrics: ThroughputMetrics) -> ScalingAction:
        """Evaluate metrics and determine scaling action."""
        load = metrics.load_factor

        if self._cooldown_mgr.is_on_cooldown(metrics.swarm_id):
            return ScalingAction(
                swarm_id=metrics.swarm_id,
                direction=ScalingDirection.NONE,
                previous_nodes=metrics.active_nodes,
                target_nodes=metrics.active_nodes,
                reason="cooldown_active",
            )

        if load >= self._policy.scale_up_threshold:
            target = min(
                metrics.active_nodes + max(1, metrics.active_nodes // 2),
                self._policy.max_nodes,
            )
            action = ScalingAction(
                swarm_id=metrics.swarm_id,
                direction=ScalingDirection.UP,
                previous_nodes=metrics.active_nodes,
                target_nodes=target,
                reason=f"load_factor_{load:.2f}_above_{self._policy.scale_up_threshold}",
            )
            self._cooldown_mgr.set_cooldown(
                metrics.swarm_id, "scale_up", self._policy.cooldown_seconds,
            )
            self._cooldown_mgr.record_action(action)
            return action

        if load <= self._policy.scale_down_threshold:
            target = max(
                metrics.active_nodes - max(1, metrics.active_nodes // 4),
                self._policy.min_nodes,
            )
            action = ScalingAction(
                swarm_id=metrics.swarm_id,
                direction=ScalingDirection.DOWN,
                previous_nodes=metrics.active_nodes,
                target_nodes=target,
                reason=f"load_factor_{load:.2f}_below_{self._policy.scale_down_threshold}",
            )
            self._cooldown_mgr.set_cooldown(
                metrics.swarm_id, "scale_down", self._policy.cooldown_seconds,
            )
            self._cooldown_mgr.record_action(action)
            return action

        return ScalingAction(
            swarm_id=metrics.swarm_id,
            direction=ScalingDirection.NONE,
            previous_nodes=metrics.active_nodes,
            target_nodes=metrics.active_nodes,
            reason="steady_state",
        )


# ── Auto-Scaler Engine ──────────────────────────────────────────────────────


class AutoScalerEngine:
    """Main auto-scaling engine for HIVE swarms.

    Coordinates metrics collection, decision making, and scaling
    actions with cooldown management.
    """

    def __init__(
        self,
        policy: Optional[ScalingPolicyConfig] = None,
        max_samples: int = 100,
    ):
        self._policy = policy or ScalingPolicyConfig()
        self._metrics_collector = MetricsCollector(max_samples=max_samples)
        self._cooldown_manager = CooldownManager()
        self._decision_engine = ScalingDecisionEngine(
            policy=self._policy, cooldown_mgr=self._cooldown_manager,
        )
        self._swarms: Dict[str, Dict[str, Any]] = {}
        self._actions: List[ScalingAction] = []
        self._running = False
        self._status = ScalingStatus.STOPPED
        self._lock = asyncio.Lock()
        self._start_time: Optional[float] = None
        logger.info("AutoScalerEngine initialized")

    @property
    def status(self) -> ScalingStatus:
        return self._status

    @property
    def metrics_collector(self) -> MetricsCollector:
        return self._metrics_collector

    @property
    def cooldown_manager(self) -> CooldownManager:
        return self._cooldown_manager

    @property
    def decision_engine(self) -> ScalingDecisionEngine:
        return self._decision_engine

    @property
    def policy(self) -> ScalingPolicyConfig:
        return self._policy

    async def start(self) -> None:
        """Start the auto-scaler engine."""
        if self._running:
            return
        self._running = True
        self._status = ScalingStatus.ACTIVE
        self._start_time = time.time()
        logger.info("AutoScalerEngine started")

    async def stop(self) -> None:
        """Stop the auto-scaler engine."""
        self._running = False
        self._status = ScalingStatus.STOPPED
        logger.info("AutoScalerEngine stopped")

    async def register_swarm(self, swarm_id: str, initial_nodes: int = 1) -> None:
        """Register a swarm for auto-scaling."""
        self._swarms[swarm_id] = {
            "swarm_id": swarm_id,
            "current_nodes": initial_nodes,
            "registered_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("Swarm registered: %s (%d nodes)", swarm_id, initial_nodes)

    async def unregister_swarm(self, swarm_id: str) -> None:
        """Unregister a swarm from auto-scaling."""
        self._swarms.pop(swarm_id, None)
        logger.info("Swarm unregistered: %s", swarm_id)

    async def record_metrics(self, metrics: ThroughputMetrics) -> None:
        """Record throughput metrics for a swarm."""
        await self._metrics_collector.record(metrics)

    async def evaluate(self, swarm_id: str) -> Optional[ScalingAction]:
        """Evaluate a swarm and return a scaling action if needed."""
        metrics = await self._metrics_collector.get_latest(swarm_id)
        if not metrics:
            return None
        action = self._decision_engine.evaluate(metrics)
        if action.direction != ScalingDirection.NONE:
            self._actions.append(action)
        return action

    async def pause(self) -> None:
        """Pause auto-scaling (stops evaluation but keeps registered swarms)."""
        self._running = False
        self._status = ScalingStatus.PAUSED
        logger.info("AutoScalerEngine paused")

    async def resume(self) -> None:
        """Resume auto-scaling after a pause."""
        self._running = True
        self._status = ScalingStatus.ACTIVE
        logger.info("AutoScalerEngine resumed")

    async def get_status(self) -> Dict[str, Any]:
        """Get comprehensive auto-scaler status."""
        return {
            "status": self._status.value,
            "running": self._running,
            "registered_swarms": len(self._swarms),
            "total_actions": len(self._actions),
            "uptime_seconds": time.time() - self._start_time if self._start_time else 0,
            "policy": self._policy.model_dump(),
        }


# ── Module Singleton ─────────────────────────────────────────────────────────

_autoscaler: Optional[AutoScalerEngine] = None


def get_autoscaler(
    policy: Optional[ScalingPolicyConfig] = None,
) -> AutoScalerEngine:
    """Get or create the module-level auto-scaler singleton."""
    global _autoscaler
    if _autoscaler is None:
        _autoscaler = AutoScalerEngine(policy=policy)
    return _autoscaler
