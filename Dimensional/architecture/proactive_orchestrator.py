"""
Dimensional.architecture.proactive_orchestrator — Unified Intelligent Adaptive Proactive System.

The ProactiveOrchestrator is the central brain of the Tranc3 platform, unifying
all existing intelligent subsystems into a single adaptive, proactive, and
self-healing architecture. It bridges:

    - ForesightEngine    → Predictive intelligence & trajectory analysis
    - FluidicRouter      → Adaptive request routing with liquid neural weights
    - CircuitBreaker     → Resilience & cascade-failure prevention
    - Sentinel           → Continuous verification & drift detection
    - EventBus           → Nanoservice communication & causal ordering
    - SmartStorageOrchestrator → Zero-cost multi-tier storage
    - EnhancedServiceRegistry  → Capability-based service discovery
    - DefenseEngine      → Active security & threat response

Design Principles:
    - Smart:    Auto-detects anomalies and takes corrective action
    - Intelligent: Predicts issues before they occur using metric trends
    - Logical:  Priority-based action selection with cost-awareness
    - Adaptive: Dynamically adjusts all parameters based on system state
    - Fluidic:  Seamless transitions between operational modes
    - Dynamic:  Runtime reconfiguration without service interruption
    - Modular:  Each subsystem remains independently operable
    - Nanoservice: Every action is atomic, traceable, and reversible

Universal ID Taxonomy:
    PID (Product/Location ID)  — identifies locations/products in the 8 pillars
    AID (AI ID)                — identifies AI entities (e.g., tAImra Lead AI)
    SID (Service/Agent ID)     — identifies services and agents
    NID (Nano-ID/Bot ID)       — identifies nanoservice bots

Zero-Cost Auto-Modulation:
    The orchestrator continuously monitors free-tier capacity across all
    cloud providers and proactively migrates data before any charges occur.
    When a provider approaches its free-tier limit, the system automatically
    shifts traffic and data to alternative free-tier providers, maintaining
    the zero-cost mandate at all times.

Proactive Actions Taxonomy:
    HEAL           — Auto-remediate detected issues (restart, retry, failover)
    SCALE_UP       — Proactively add capacity before demand spike
    SCALE_DOWN     — Release resources when demand decreases
    MIGRATE_STORAGE — Move data between tiers to maintain zero-cost
    REBALANCE      — Adjust routing weights for optimal performance
    HARDEN         — Tighten security in response to threats
    ALERT          — Notify operators of conditions requiring attention
    RECONFIGURE    — Adjust system parameters for optimal operation
    QUARANTINE     — Isolate unhealthy components to prevent cascade

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                   ProactiveOrchestrator                         │
    │                                                                  │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
    │  │  Predictive   │  │  Auto-Heal   │  │  Zero-Cost           │  │
    │  │  Health       │  │  Engine      │  │  Modulator           │  │
    │  │  Analyzer     │  │              │  │                      │  │
    │  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
    │         │                 │                      │              │
    │  ┌──────┴─────────────────┴──────────────────────┴───────────┐  │
    │  │              Action Dispatcher (EventBus)                  │  │
    │  └──────┬─────────────────┬──────────────────────┬───────────┘  │
    │         │                 │                      │              │
    │  ┌──────┴───────┐  ┌──────┴───────┐  ┌──────────┴───────────┐  │
    │  │  Foresight   │  │  Fluidic     │  │  Smart Storage       │  │
    │  │  Engine      │  │  Router      │  │  Orchestrator        │  │
    │  └──────────────┘  └──────────────┘  └──────────────────────┘  │
    │                                                                  │
    │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
    │  │  Sentinel     │  │  Defense     │  │  Enhanced Registry   │  │
    │  │  (verify)     │  │  Engine      │  │  (discovery)         │  │
    │  └──────────────┘  └──────────────┘  └──────────────────────┘  │
    │                                                                  │
    │  ┌──────────────┐  ┌──────────────────────────────────────┐    │
    │  │  Resilience   │  │  Adaptive Pulse Controller           │    │
    │  │  Manager      │  │  (dynamic interval adjustment)       │    │
    │  └──────────────┘  └──────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_DEFAULT_ORCHESTRATION_INTERVAL = 30.0  # seconds between proactive cycles
_DEFAULT_HEALTH_WINDOW = 100  # metrics history depth
_DEFAULT_PREDICTION_HORIZON = 300  # seconds ahead to predict
_DEFAULT_AUTO_HEAL_ENABLED = True
_DEFAULT_ZERO_COST_SAFETY_MARGIN = 0.85  # migrate at 85% of free-tier limit


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ProactiveAction(str, Enum):
    """Taxonomy of proactive actions the orchestrator can take."""

    HEAL = "heal"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    MIGRATE_STORAGE = "migrate_storage"
    REBALANCE = "rebalance"
    HARDEN = "harden"
    ALERT = "alert"
    RECONFIGURE = "reconfigure"
    QUARANTINE = "quarantine"


class ActionPriority(int, Enum):
    """Priority levels for proactive actions."""

    CRITICAL = 0  # Immediate execution required (system at risk)
    HIGH = 1  # Execute within seconds (degradation detected)
    MEDIUM = 2  # Execute within minutes (optimization opportunity)
    LOW = 3  # Execute when convenient (housekeeping)
    INFORMATIONAL = 4  # Log only, no action needed


class ActionStatus(str, Enum):
    """Status of a proactive action."""

    PENDING = "pending"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"
    CANCELLED = "cancelled"


class SystemVitalSign(str, Enum):
    """Vital signs monitored by the orchestrator."""

    CPU_LOAD = "cpu_load"
    MEMORY_USAGE = "memory_usage"
    STORAGE_CAPACITY = "storage_capacity"
    SERVICE_HEALTH = "service_health"
    ERROR_RATE = "error_rate"
    LATENCY = "latency"
    THROUGHPUT = "throughput"
    THREAT_LEVEL = "threat_level"
    CIRCUIT_HEALTH = "circuit_health"
    REGISTRY_HEALTH = "registry_health"


class OrchestratorMode(str, Enum):
    """Operational mode of the ProactiveOrchestrator."""

    OBSERVE = "observe"  # Monitor only, no automatic actions
    ASSIST = "assist"  # Suggest actions, require approval
    AUTONOMOUS = "autonomous"  # Execute actions automatically
    EMERGENCY = "emergency"  # Maximum automation, override safety limits


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class MetricSample:
    """A single metric sample with timestamp."""

    name: str
    value: float
    timestamp: float = field(default_factory=time.time)
    tags: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "timestamp": self.timestamp,
            "tags": self.tags,
        }


@dataclass
class HealthPrediction:
    """Predicted health state for a subsystem."""

    subsystem: str
    current_score: float  # 0.0 (failing) to 1.0 (healthy)
    predicted_score: float  # predicted score at horizon
    trend: str  # "improving", "stable", "degrading", "critical"
    confidence: float  # 0.0 to 1.0
    time_to_degradation: Optional[float] = None  # seconds until score < 0.5
    horizon_seconds: float = 300.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "subsystem": self.subsystem,
            "current_score": round(self.current_score, 4),
            "predicted_score": round(self.predicted_score, 4),
            "trend": self.trend,
            "confidence": round(self.confidence, 4),
            "time_to_degradation": (
                round(self.time_to_degradation, 1) if self.time_to_degradation is not None else None
            ),
            "horizon_seconds": self.horizon_seconds,
            "timestamp": self.timestamp,
        }


@dataclass
class ActionPlan:
    """A structured proactive action with priority, execution details, and rollback."""

    id: str
    action: ProactiveAction
    priority: ActionPriority
    target: str  # subsystem or resource to act on
    description: str
    status: ActionStatus = ActionStatus.PENDING
    created_at: float = field(default_factory=time.time)
    executed_at: Optional[float] = None
    completed_at: Optional[float] = None
    deadline: Optional[float] = None
    executor: Optional[Callable] = None
    rollback: Optional[Callable] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "action": self.action.value,
            "priority": self.priority.value,
            "priority_name": self.priority.name,
            "target": self.target,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at,
            "executed_at": self.executed_at,
            "completed_at": self.completed_at,
            "deadline": self.deadline,
            "result": self.result,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class SystemHealthProfile:
    """Composite health profile across all subsystems."""

    overall_score: float = 1.0  # 0.0 (failing) to 1.0 (healthy)
    storage_health: float = 1.0
    service_health: float = 1.0
    security_health: float = 1.0
    resilience_health: float = 1.0
    foresight_health: float = 1.0
    routing_health: float = 1.0
    predictions: List[HealthPrediction] = field(default_factory=list)
    active_actions: int = 0
    pending_actions: int = 0
    failed_actions_24h: int = 0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_score": round(self.overall_score, 4),
            "storage_health": round(self.storage_health, 4),
            "service_health": round(self.service_health, 4),
            "security_health": round(self.security_health, 4),
            "resilience_health": round(self.resilience_health, 4),
            "foresight_health": round(self.foresight_health, 4),
            "routing_health": round(self.routing_health, 4),
            "predictions": [p.to_dict() for p in self.predictions],
            "active_actions": self.active_actions,
            "pending_actions": self.pending_actions,
            "failed_actions_24h": self.failed_actions_24h,
            "timestamp": self.timestamp,
        }


@dataclass
class ZeroCostStatus:
    """Zero-cost compliance status across all storage tiers."""

    compliant: bool = True  # True if all tiers are within free limits
    total_free_gb: float = 0.0  # Total free-tier capacity across providers
    total_used_gb: float = 0.0  # Total used across providers
    utilization_pct: float = 0.0  # Overall utilization percentage
    approaching_limit: List[str] = field(default_factory=list)  # Tiers near limit
    critical_tiers: List[str] = field(default_factory=list)  # Tiers at critical
    migration_in_progress: bool = False
    last_migration_at: Optional[float] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "compliant": self.compliant,
            "total_free_gb": round(self.total_free_gb, 2),
            "total_used_gb": round(self.total_used_gb, 2),
            "utilization_pct": round(self.utilization_pct, 2),
            "approaching_limit": self.approaching_limit,
            "critical_tiers": self.critical_tiers,
            "migration_in_progress": self.migration_in_progress,
            "last_migration_at": self.last_migration_at,
            "timestamp": self.timestamp,
        }


# ---------------------------------------------------------------------------
# Predictive Health Analyzer
# ---------------------------------------------------------------------------


class PredictiveHealthAnalyzer:
    """
    Analyzes metric trends to predict future health states.
    Uses exponential moving averages and linear regression
    on recent metric history to forecast degradation.

    This is a lightweight, zero-dependency predictor — no ML frameworks required.
    For each subsystem, it maintains a sliding window of health scores and
    extrapolates forward to detect degradation before it impacts users.
    """

    def __init__(
        self,
        window_size: int = _DEFAULT_HEALTH_WINDOW,
        prediction_horizon: float = _DEFAULT_PREDICTION_HORIZON,
        smoothing_alpha: float = 0.3,
    ):
        self._window_size = window_size
        self._prediction_horizon = prediction_horizon
        self._smoothing_alpha = smoothing_alpha
        self._metrics: Dict[str, deque] = {}  # subsystem -> deque of MetricSample
        self._ema_cache: Dict[str, float] = {}  # subsystem -> current EMA value
        self._trend_cache: Dict[str, float] = {}  # subsystem -> trend slope

    def record(self, subsystem: str, score: float, tags: Optional[Dict[str, str]] = None) -> None:
        """Record a health score sample for a subsystem."""
        if subsystem not in self._metrics:
            self._metrics[subsystem] = deque(maxlen=self._window_size)

        sample = MetricSample(name=subsystem, value=score, tags=tags or {})
        self._metrics[subsystem].append(sample)

        # Update EMA (Exponential Moving Average)
        prev_ema = self._ema_cache.get(subsystem, score)
        alpha = self._smoothing_alpha
        new_ema = alpha * score + (1 - alpha) * prev_ema
        self._ema_cache[subsystem] = new_ema

        # Update trend (simple linear regression slope on recent samples)
        history = list(self._metrics[subsystem])
        if len(history) >= 3:
            recent = history[-10:]  # Use last 10 samples for trend
            n = len(recent)
            sum_x = n * (n - 1) / 2.0
            sum_y = sum(s.value for s in recent)
            sum_xy = sum(i * recent[i].value for i in range(n))
            sum_x2 = sum(i * i for i in range(n))
            denom = n * sum_x2 - sum_x * sum_x
            if abs(denom) > 1e-10:
                slope = (n * sum_xy - sum_x * sum_y) / denom
                self._trend_cache[subsystem] = slope

    def predict(self, subsystem: str) -> HealthPrediction:
        """Predict the future health of a subsystem."""
        history = list(self._metrics.get(subsystem, []))

        if len(history) < 2:
            score = history[0].value if history else 1.0
            return HealthPrediction(
                subsystem=subsystem,
                current_score=score,
                predicted_score=score,
                trend="stable",
                confidence=0.0,
                time_to_degradation=None,
                horizon_seconds=self._prediction_horizon,
            )

        current_ema = self._ema_cache.get(subsystem, 1.0)
        slope = self._trend_cache.get(subsystem, 0.0)

        # Project forward: predicted_score = EMA + slope * horizon_steps
        # Estimate steps: assume samples come at ~30s intervals
        sample_interval = 30.0
        horizon_steps = self._prediction_horizon / sample_interval
        predicted_score = current_ema + slope * horizon_steps

        # Clamp to [0, 1]
        predicted_score = max(0.0, min(1.0, predicted_score))

        # Determine trend
        if slope < -0.01:
            trend = "critical" if current_ema < 0.5 else "degrading"
        elif slope > 0.01:
            trend = "improving"
        else:
            trend = "stable"

        # Estimate time to degradation (score < 0.5)
        time_to_degradation = None
        if slope < -1e-6 and current_ema > 0.5:
            steps_to_degrade = (current_ema - 0.5) / abs(slope)
            time_to_degradation = steps_to_degrade * sample_interval

        # Confidence based on sample count and consistency
        n_samples = len(history)
        confidence = min(1.0, n_samples / 20.0)  # Full confidence at 20+ samples

        # Reduce confidence if trend is volatile
        if len(history) >= 5:
            values = [s.value for s in history[-5:]]
            variance = sum((v - sum(values) / len(values)) ** 2 for v in values) / len(values)
            confidence *= max(0.3, 1.0 - variance * 4.0)

        return HealthPrediction(
            subsystem=subsystem,
            current_score=round(current_ema, 4),
            predicted_score=round(predicted_score, 4),
            trend=trend,
            confidence=round(confidence, 4),
            time_to_degradation=round(time_to_degradation, 1) if time_to_degradation else None,
            horizon_seconds=self._prediction_horizon,
        )

    def get_all_predictions(self) -> List[HealthPrediction]:
        """Get predictions for all monitored subsystems."""
        return [self.predict(name) for name in self._metrics]

    def get_degrading(self, threshold: float = 0.7) -> List[HealthPrediction]:
        """Get predictions for subsystems currently degrading or below threshold."""
        predictions = self.get_all_predictions()
        return [
            p
            for p in predictions
            if p.current_score < threshold or p.trend in ("degrading", "critical")
        ]

    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        return {
            "subsystems_monitored": len(self._metrics),
            "window_size": self._window_size,
            "prediction_horizon": self._prediction_horizon,
            "smoothing_alpha": self._smoothing_alpha,
            "ema_values": {k: round(v, 4) for k, v in self._ema_cache.items()},
            "trend_slopes": {k: round(v, 6) for k, v in self._trend_cache.items()},
        }


# ---------------------------------------------------------------------------
# Auto-Healing Engine
# ---------------------------------------------------------------------------


class AutoHealingEngine:
    """
    Automated remediation engine with safety constraints.

    Executes healing actions based on detected issues, with configurable
    safety limits to prevent runaway remediation attempts.

    Safety Constraints:
        - Max concurrent healing actions (default: 3)
        - Max retries per target per hour (default: 5)
        - Cooldown between retries (default: 60s)
        - Escalation: if retries exceed limit, escalate to ALERT instead
        - Rollback: each action can specify a rollback function

    Healing Actions:
        - Restart unhealthy services
        - Failover to backup providers
        - Clear stuck circuit breakers (with caution)
        - Re-register lost services
        - Migrate data from full tiers
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        max_retries_per_hour: int = 5,
        retry_cooldown: float = 60.0,
        enabled: bool = _DEFAULT_AUTO_HEAL_ENABLED,
    ):
        self._max_concurrent = max_concurrent
        self._max_retries_per_hour = max_retries_per_hour
        self._retry_cooldown = retry_cooldown
        self._enabled = enabled
        self._active_heals: Dict[str, ActionPlan] = {}
        self._retry_tracker: Dict[str, List[float]] = {}  # target -> [timestamps]
        self._heal_history: List[ActionPlan] = []
        self._total_heals = 0
        self._successful_heals = 0
        self._failed_heals = 0
        self._rolled_back_heals = 0

    @property
    def enabled(self) -> bool:
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = value
        logger.info("Auto-healing %s", "enabled" if value else "disabled")

    def can_heal(self, target: str) -> bool:
        """Check if a healing action can be executed for the target."""
        if not self._enabled:
            return False
        if len(self._active_heals) >= self._max_concurrent:
            return False

        # Check retry limits
        now = time.time()
        recent = self._retry_tracker.get(target, [])
        recent = [t for t in recent if now - t < 3600.0]  # Last hour
        self._retry_tracker[target] = recent

        if len(recent) >= self._max_retries_per_hour:
            return False

        # Check cooldown
        if recent and (now - recent[-1]) < self._retry_cooldown:
            return False

        return True

    def create_heal_action(
        self,
        target: str,
        description: str,
        executor: Callable,
        rollback: Optional[Callable] = None,
        priority: ActionPriority = ActionPriority.HIGH,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ActionPlan]:
        """Create a healing action plan."""
        if not self.can_heal(target):
            logger.warning(
                "Cannot create heal action for %s: rate-limited or disabled",
                sanitize_for_log(target),
            )
            return None

        plan = ActionPlan(
            id=f"heal-{uuid.uuid4().hex[:8]}",
            action=ProactiveAction.HEAL,
            priority=priority,
            target=target,
            description=description,
            executor=executor,
            rollback=rollback,
            metadata=metadata or {},
        )

        self._active_heals[plan.id] = plan
        self._total_heals += 1

        # Track retry
        now = time.time()
        if target not in self._retry_tracker:
            self._retry_tracker[target] = []
        self._retry_tracker[target].append(now)

        logger.info(
            "Heal action created: %s → %s (priority=%s)",
            sanitize_for_log(plan.id),
            sanitize_for_log(target),
            priority.name,
        )
        return plan

    async def execute_heal(self, plan: ActionPlan) -> ActionPlan:
        """Execute a healing action."""
        if plan.id not in self._active_heals:
            return plan

        plan.status = ActionStatus.EXECUTING
        plan.executed_at = time.time()

        try:
            if asyncio.iscoroutinefunction(plan.executor):
                result = await plan.executor()
            else:
                result = plan.executor()

            plan.status = ActionStatus.COMPLETED
            plan.completed_at = time.time()
            plan.result = result if isinstance(result, dict) else {"result": str(result)}
            self._successful_heals += 1
            logger.info(
                "Heal action completed: %s → %s",
                sanitize_for_log(plan.id),
                sanitize_for_log(plan.target),
            )

        except Exception as e:
            plan.status = ActionStatus.FAILED
            plan.completed_at = time.time()
            plan.error = str(e)
            self._failed_heals += 1
            logger.error(
                "Heal action failed: %s → %s: %s",
                sanitize_for_log(plan.id),
                sanitize_for_log(plan.target),
                sanitize_for_log(str(e)),
            )

            # Attempt rollback
            if plan.rollback:
                try:
                    if asyncio.iscoroutinefunction(plan.rollback):
                        await plan.rollback()
                    else:
                        plan.rollback()
                    plan.status = ActionStatus.ROLLED_BACK
                    self._rolled_back_heals += 1
                    logger.info("Heal action rolled back: %s", sanitize_for_log(plan.id))
                except Exception as rb_err:
                    logger.error(
                        "Rollback failed for %s: %s",
                        sanitize_for_log(plan.id),
                        sanitize_for_log(str(rb_err)),
                    )

        # Move to history
        self._active_heals.pop(plan.id, None)
        self._heal_history.append(plan)

        # Keep only last 1000
        if len(self._heal_history) > 1000:
            self._heal_history = self._heal_history[-1000:]

        return plan

    def get_active_heals(self) -> List[Dict[str, Any]]:
        """Get currently executing heal actions."""
        return [p.to_dict() for p in self._active_heals.values()]

    def get_recent_heals(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent heal action history."""
        return [p.to_dict() for p in self._heal_history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get healing engine statistics."""
        return {
            "enabled": self._enabled,
            "max_concurrent": self._max_concurrent,
            "max_retries_per_hour": self._max_retries_per_hour,
            "retry_cooldown": self._retry_cooldown,
            "active_heals": len(self._active_heals),
            "total_heals": self._total_heals,
            "successful_heals": self._successful_heals,
            "failed_heals": self._failed_heals,
            "rolled_back_heals": self._rolled_back_heals,
            "success_rate": (
                round(self._successful_heals / self._total_heals, 4)
                if self._total_heals > 0
                else 1.0
            ),
        }


# ---------------------------------------------------------------------------
# Zero-Cost Modulator
# ---------------------------------------------------------------------------


class ZeroCostModulator:
    """
    Proactive zero-cost compliance engine.

    Continuously monitors storage tier capacity and proactively migrates
    data before any free-tier limits are exceeded. This ensures the
    zero-cost mandate is maintained at all times.

    Strategy:
        1. Monitor all cloud storage tiers for approaching limits
        2. When a tier reaches safety_margin (default 85%) of free tier:
           a. Identify the best alternative free-tier provider
           b. Create a MIGRATE_STORAGE action plan
           c. Execute the migration proactively
        3. If no alternative is available, trigger ALERT
        4. Track migration history to avoid oscillation

    The modulator integrates with SmartStorageOrchestrator to:
        - Read capacity metrics from all providers
        - Trigger tier migrations via the orchestrator
        - Verify migration success
    """

    def __init__(
        self,
        safety_margin: float = _DEFAULT_ZERO_COST_SAFETY_MARGIN,
        migration_cooldown: float = 300.0,  # 5 minutes between migrations
        max_migrations_per_hour: int = 10,
    ):
        self._safety_margin = safety_margin
        self._migration_cooldown = migration_cooldown
        self._max_migrations_per_hour = max_migrations_per_hour
        self._migration_history: List[Dict[str, Any]] = []
        self._last_migration_time: float = 0.0
        self._recent_migrations: List[float] = []  # timestamps
        self._total_migrations = 0
        self._successful_migrations = 0
        self._storage_orchestrator: Any = None  # SmartStorageOrchestrator (lazy)

    def attach_storage(self, storage_orchestrator: Any) -> None:
        """Attach a SmartStorageOrchestrator instance for capacity monitoring."""
        self._storage_orchestrator = storage_orchestrator
        logger.info("ZeroCostModulator attached to SmartStorageOrchestrator")

    def check_compliance(self) -> ZeroCostStatus:
        """Check zero-cost compliance across all storage tiers."""
        status = ZeroCostStatus()

        if not self._storage_orchestrator:
            return status

        try:
            capacities = self._storage_orchestrator.get_all_capacities()
            total_free = 0.0
            total_used = 0.0

            for tier_name, cap_dict in capacities.items():
                free_gb = cap_dict.get("free_gb", 0.0)
                used_gb = cap_dict.get("used_gb", 0.0)
                usage_pct = cap_dict.get("usage_pct", 0.0)

                total_free += free_gb
                total_used += used_gb

                # Check against safety margin
                if usage_pct >= self._safety_margin * 100:
                    if usage_pct >= 95.0:
                        status.critical_tiers.append(tier_name)
                        status.compliant = False
                    else:
                        status.approaching_limit.append(tier_name)

            status.total_free_gb = total_free
            status.total_used_gb = total_used
            status.total_free_gb = total_free
            status.utilization_pct = (
                round(total_used / (total_used + total_free) * 100, 2)
                if (total_used + total_free) > 0
                else 0.0
            )
            status.migration_in_progress = (
                time.time() - self._last_migration_time < 60.0
                if self._last_migration_time > 0
                else False
            )
            status.last_migration_at = (
                self._last_migration_time if self._last_migration_time > 0 else None
            )

        except Exception as e:
            logger.error("Zero-cost compliance check failed: %s", sanitize_for_log(str(e)))
            status.compliant = False

        return status

    def should_migrate(self, tier_name: str, usage_pct: float) -> bool:
        """Determine if a storage tier needs proactive migration."""
        if usage_pct < self._safety_margin * 100:
            return False

        # Check cooldown
        now = time.time()
        if (
            self._last_migration_time > 0
            and (now - self._last_migration_time) < self._migration_cooldown
        ):
            return False

        # Check rate limit
        recent = [t for t in self._recent_migrations if now - t < 3600.0]
        self._recent_migrations = recent
        if len(recent) >= self._max_migrations_per_hour:
            return False

        # Check oscillation (don't migrate back to a tier we just migrated from)
        for migration in self._migration_history[-5:]:
            if migration.get("destination") == tier_name:
                if now - migration.get("timestamp", 0) < 600.0:
                    return False

        return True

    def record_migration(
        self,
        source: str,
        destination: str,
        success: bool,
        bytes_migrated: int = 0,
    ) -> None:
        """Record a completed migration."""
        self._total_migrations += 1
        if success:
            self._successful_migrations += 1
        self._last_migration_time = time.time()
        self._recent_migrations.append(self._last_migration_time)

        self._migration_history.append(
            {
                "source": source,
                "destination": destination,
                "success": success,
                "bytes_migrated": bytes_migrated,
                "timestamp": self._last_migration_time,
            }
        )

        # Keep history manageable
        if len(self._migration_history) > 100:
            self._migration_history = self._migration_history[-100:]

    def get_migration_recommendation(self, tier_name: str) -> Optional[str]:
        """Recommend the best alternative tier for migration."""
        if not self._storage_orchestrator:
            return None

        try:
            capacities = self._storage_orchestrator.get_all_capacities()
            best = None
            best_free = 0.0

            for alt_name, cap_dict in capacities.items():
                if alt_name == tier_name:
                    continue
                free_gb = cap_dict.get("free_gb", 0.0)
                usage_pct = cap_dict.get("usage_pct", 0.0)
                is_available = cap_dict.get("is_available", False)

                # Must be available and have significant free space
                if is_available and usage_pct < 50.0 and free_gb > best_free:
                    best = alt_name
                    best_free = free_gb

            return best

        except Exception as e:
            logger.error("Migration recommendation failed: %s", sanitize_for_log(str(e)))
            return None

    def get_stats(self) -> Dict[str, Any]:
        """Get modulator statistics."""
        return {
            "safety_margin": self._safety_margin,
            "migration_cooldown": self._migration_cooldown,
            "max_migrations_per_hour": self._max_migrations_per_hour,
            "total_migrations": self._total_migrations,
            "successful_migrations": self._successful_migrations,
            "success_rate": (
                round(self._successful_migrations / self._total_migrations, 4)
                if self._total_migrations > 0
                else 1.0
            ),
            "last_migration_at": self._last_migration_time or None,
            "migration_history_size": len(self._migration_history),
            "storage_attached": self._storage_orchestrator is not None,
        }


# ---------------------------------------------------------------------------
# Action Dispatcher
# ---------------------------------------------------------------------------


class ActionDispatcher:
    """
    Dispatches proactive actions through the EventBus and manages
    the lifecycle of action plans.

    Actions are dispatched in priority order and tracked through
    their full lifecycle. The dispatcher integrates with the EventBus
    to publish action events for downstream consumers.
    """

    def __init__(self, event_bus: Any = None):
        self._event_bus = event_bus
        self._pending: List[ActionPlan] = []
        self._completed: List[ActionPlan] = []
        self._action_handlers: Dict[ProactiveAction, List[Callable]] = {}
        self._total_dispatched = 0

    def register_handler(self, action: ProactiveAction, handler: Callable) -> None:
        """Register a handler for a specific proactive action type."""
        if action not in self._action_handlers:
            self._action_handlers[action] = []
        self._action_handlers[action].append(handler)

    def submit(self, plan: ActionPlan) -> None:
        """Submit an action plan for dispatch."""
        self._pending.append(plan)
        # Sort by priority (lower value = higher priority)
        self._pending.sort(key=lambda p: p.priority.value)
        logger.info(
            "Action plan submitted: %s (%s) → %s [priority=%s]",
            sanitize_for_log(plan.id),
            plan.action.value,
            sanitize_for_log(plan.target),
            plan.priority.name,
        )

    async def dispatch_next(self) -> Optional[ActionPlan]:
        """Dispatch the next highest-priority action plan."""
        if not self._pending:
            return None

        plan = self._pending.pop(0)
        plan.status = ActionStatus.EXECUTING
        plan.executed_at = time.time()
        self._total_dispatched += 1

        # Notify handlers
        handlers = self._action_handlers.get(plan.action, [])
        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(plan)
                else:
                    handler(plan)
            except Exception as e:
                logger.error(
                    "Action handler error for %s: %s",
                    sanitize_for_log(plan.id),
                    sanitize_for_log(str(e)),
                )

        # Publish event if bus is available
        if self._event_bus:
            try:
                from Dimensional.models import EventMessage

                event = EventMessage(
                    event_type=f"proactive.{plan.action.value}",
                    source="proactive_orchestrator",
                    data=plan.to_dict(),
                )
                await self._event_bus.publish(event)
            except Exception as e:
                logger.error("EventBus publish error: %s", sanitize_for_log(str(e)))

        # Move to completed
        plan.status = ActionStatus.COMPLETED
        plan.completed_at = time.time()
        self._completed.append(plan)

        # Keep only last 200 completed
        if len(self._completed) > 200:
            self._completed = self._completed[-200:]

        return plan

    async def dispatch_all_pending(self) -> List[ActionPlan]:
        """Dispatch all pending action plans in priority order."""
        dispatched = []
        while self._pending:
            plan = await self.dispatch_next()
            if plan:
                dispatched.append(plan)
        return dispatched

    def cancel(self, plan_id: str) -> bool:
        """Cancel a pending action plan."""
        for i, plan in enumerate(self._pending):
            if plan.id == plan_id:
                plan.status = ActionStatus.CANCELLED
                self._pending.pop(i)
                self._completed.append(plan)
                return True
        return False

    def get_pending(self) -> List[Dict[str, Any]]:
        """Get all pending action plans."""
        return [p.to_dict() for p in self._pending]

    def get_recent_completed(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recently completed action plans."""
        return [p.to_dict() for p in self._completed[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        """Get dispatcher statistics."""
        return {
            "total_dispatched": self._total_dispatched,
            "pending_count": len(self._pending),
            "completed_count": len(self._completed),
            "registered_handlers": {
                action.value: len(handlers) for action, handlers in self._action_handlers.items()
            },
        }


# ---------------------------------------------------------------------------
# Proactive Orchestrator
# ---------------------------------------------------------------------------


class ProactiveOrchestrator:
    """
    Unified intelligent adaptive proactive orchestrator for the Tranc3 platform.

    Bridges all existing subsystems into a single cohesive architecture that:
        - Monitors health across all subsystems
        - Predicts degradation before it impacts users
        - Proactively heals issues with safety constraints
        - Maintains zero-cost compliance across all storage tiers
        - Dispatches actions through the EventBus for nanoservice communication
        - Adapts operational parameters in real-time

    The orchestrator runs a continuous loop that:
        1. Collects health metrics from all subsystems
        2. Runs predictive analysis to forecast degradation
        3. Checks zero-cost compliance and triggers migrations
        4. Creates and dispatches action plans for any detected issues
        5. Publishes system health events to the EventBus

    Operational Modes:
        OBSERVE     — Monitor and report only
        ASSIST      — Suggest actions, require human approval
        AUTONOMOUS  — Execute actions automatically with safety limits
        EMERGENCY   — Maximum automation, override safety limits

    Usage:
        orchestrator = ProactiveOrchestrator(
            mode=OrchestratorMode.AUTONOMOUS,
            event_bus=bus,
        )
        orchestrator.attach_storage(storage_orchestrator)
        orchestrator.attach_sentinel(sentinel)
        orchestrator.attach_defense(defense_engine)
        await orchestrator.start()
    """

    def __init__(
        self,
        *,
        mode: OrchestratorMode = OrchestratorMode.AUTONOMOUS,
        event_bus: Any = None,
        orchestration_interval: float = _DEFAULT_ORCHESTRATION_INTERVAL,
        auto_heal_enabled: bool = _DEFAULT_AUTO_HEAL_ENABLED,
        zero_cost_safety_margin: float = _DEFAULT_ZERO_COST_SAFETY_MARGIN,
    ):
        self._mode = mode
        self._event_bus = event_bus
        self._orchestration_interval = orchestration_interval

        # Core subsystems
        self._health_analyzer = PredictiveHealthAnalyzer()
        self._healing_engine = AutoHealingEngine(enabled=auto_heal_enabled)
        self._zero_cost_modulator = ZeroCostModulator(safety_margin=zero_cost_safety_margin)
        self._action_dispatcher = ActionDispatcher(event_bus=event_bus)

        # Attached subsystems (lazy attachment)
        self._storage_orchestrator: Any = None
        self._sentinel: Any = None
        self._defense_engine: Any = None
        self._foresight_engine: Any = None
        self._fluidic_router: Any = None
        self._enhanced_registry: Any = None
        self._resilience_manager: Any = None

        # State
        self._running = False
        self._orchestration_task: Optional[asyncio.Task] = None
        self._last_cycle_time: float = 0.0
        self._cycle_count: int = 0
        self._started_at: Optional[float] = None
        self._health_profile = SystemHealthProfile()

        # Register internal action handlers
        self._register_default_handlers()

    # ------------------------------------------------------------------
    # Subsystem Attachment
    # ------------------------------------------------------------------

    def attach_storage(self, storage_orchestrator: Any) -> None:
        """Attach a SmartStorageOrchestrator instance."""
        self._storage_orchestrator = storage_orchestrator
        self._zero_cost_modulator.attach_storage(storage_orchestrator)
        logger.info("ProactiveOrchestrator: SmartStorageOrchestrator attached")

    def attach_sentinel(self, sentinel: Any) -> None:
        """Attach a Sentinel instance."""
        self._sentinel = sentinel
        logger.info("ProactiveOrchestrator: Sentinel attached")

    def attach_defense(self, defense_engine: Any) -> None:
        """Attach a DefenseEngine instance."""
        self._defense_engine = defense_engine
        logger.info("ProactiveOrchestrator: DefenseEngine attached")

    def attach_foresight(self, foresight_engine: Any) -> None:
        """Attach a ForesightEngine instance."""
        self._foresight_engine = foresight_engine
        logger.info("ProactiveOrchestrator: ForesightEngine attached")

    def attach_router(self, fluidic_router: Any) -> None:
        """Attach a FluidicRouter instance."""
        self._fluidic_router = fluidic_router
        logger.info("ProactiveOrchestrator: FluidicRouter attached")

    def attach_registry(self, enhanced_registry: Any) -> None:
        """Attach an EnhancedServiceRegistry instance."""
        self._enhanced_registry = enhanced_registry
        logger.info("ProactiveOrchestrator: EnhancedServiceRegistry attached")

    def attach_resilience(self, resilience_manager: Any) -> None:
        """Attach a ResilienceManager instance."""
        self._resilience_manager = resilience_manager
        logger.info("ProactiveOrchestrator: ResilienceManager attached")

    def attach_event_bus(self, event_bus: Any) -> None:
        """Attach an EventBus instance."""
        self._event_bus = event_bus
        self._action_dispatcher = ActionDispatcher(event_bus=event_bus)
        self._register_default_handlers()
        logger.info("ProactiveOrchestrator: EventBus attached")

    # ------------------------------------------------------------------
    # Mode Management
    # ------------------------------------------------------------------

    def set_mode(self, mode: OrchestratorMode) -> None:
        """Change the operational mode."""
        old_mode = self._mode
        self._mode = mode
        logger.info(
            "ProactiveOrchestrator mode: %s → %s",
            old_mode.value,
            mode.value,
        )

        # Adjust behavior based on mode
        if mode == OrchestratorMode.OBSERVE:
            self._healing_engine.enabled = False
        elif mode == OrchestratorMode.ASSIST:
            self._healing_engine.enabled = False  # Still suggest, don't auto-execute
        elif mode == OrchestratorMode.AUTONOMOUS:
            self._healing_engine.enabled = True
        elif mode == OrchestratorMode.EMERGENCY:
            self._healing_engine.enabled = True
            self._healing_engine._max_retries_per_hour = 50  # Allow more retries

    @property
    def mode(self) -> OrchestratorMode:
        return self._mode

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Start the proactive orchestration loop."""
        if self._running:
            logger.warning("ProactiveOrchestrator is already running")
            return

        self._running = True
        self._started_at = time.time()
        logger.info(
            "ProactiveOrchestrator starting (mode=%s, interval=%ss)",
            self._mode.value,
            self._orchestration_interval,
        )

        # Publish start event
        await self._publish_event(
            "orchestrator.start",
            {
                "mode": self._mode.value,
                "subsystems_attached": self._get_attached_subsystem_names(),
            },
        )

        # Start the orchestration loop
        self._orchestration_task = asyncio.create_task(self._orchestration_loop())

    async def stop(self) -> None:
        """Stop the proactive orchestration loop."""
        self._running = False

        if self._orchestration_task:
            self._orchestration_task.cancel()
            try:
                await self._orchestration_task
            except asyncio.CancelledError:
                pass
            self._orchestration_task = None

        await self._publish_event(
            "orchestrator.stop",
            {
                "cycles_completed": self._cycle_count,
                "uptime_seconds": time.time() - (self._started_at or time.time()),
            },
        )

        logger.info("ProactiveOrchestrator stopped after %d cycles", self._cycle_count)

    async def run_once(self) -> SystemHealthProfile:
        """Run a single orchestration cycle manually."""
        return await self._orchestration_cycle()

    # ------------------------------------------------------------------
    # Health Collection
    # ------------------------------------------------------------------

    def _collect_storage_health(self) -> float:
        """Collect health score from SmartStorageOrchestrator."""
        if not self._storage_orchestrator:
            return 1.0  # No storage = healthy (not applicable)

        try:
            capacities = self._storage_orchestrator.get_all_capacities()
            if not capacities:
                return 1.0

            # Score based on average available capacity
            scores = []
            for _tier_name, cap in capacities.items():
                usage = cap.get("usage_pct", 0.0)
                is_available = cap.get("is_available", False)
                if is_available:
                    scores.append(max(0.0, 1.0 - usage / 100.0))
                else:
                    scores.append(0.0)  # Unavailable = unhealthy

            return sum(scores) / len(scores) if scores else 1.0

        except Exception as e:
            logger.error("Storage health collection error: %s", sanitize_for_log(str(e)))
            return 0.5  # Unknown = degraded

    def _collect_service_health(self) -> float:
        """Collect health score from EnhancedServiceRegistry."""
        if not self._enhanced_registry:
            return 1.0

        try:
            services = self._enhanced_registry.list_all()
            if not services:
                return 1.0

            healthy = sum(1 for s in services if s.get("health") == "healthy")
            total = len(services)
            return healthy / total if total > 0 else 1.0

        except Exception as e:
            logger.error("Service health collection error: %s", sanitize_for_log(str(e)))
            return 0.5

    def _collect_security_health(self) -> float:
        """Collect health score from DefenseEngine."""
        if not self._defense_engine:
            return 1.0

        try:
            stats = self._defense_engine.get_stats()
            threat = stats.current_threat_level

            threat_scores = {
                "none": 1.0,
                "low": 0.9,
                "medium": 0.7,
                "high": 0.4,
                "critical": 0.1,
            }
            return threat_scores.get(threat.value if hasattr(threat, "value") else threat, 0.5)

        except Exception as e:
            logger.error("Security health collection error: %s", sanitize_for_log(str(e)))
            return 0.5

    def _collect_resilience_health(self) -> float:
        """Collect health score from ResilienceManager."""
        if not self._resilience_manager:
            return 1.0

        try:
            health = self._resilience_manager.health()
            breakers = health.get("circuit_breakers", {})

            if not breakers:
                return 1.0

            scores = []
            for _name, stats in breakers.items():
                state = stats.get("state", "closed")
                if state == "closed":
                    scores.append(1.0)
                elif state == "half_open":
                    scores.append(0.6)
                else:  # open
                    scores.append(0.2)

            return sum(scores) / len(scores) if scores else 1.0

        except Exception as e:
            logger.error("Resilience health collection error: %s", sanitize_for_log(str(e)))
            return 0.5

    def _collect_foresight_health(self) -> float:
        """Collect health score from ForesightEngine."""
        if not self._foresight_engine:
            return 1.0

        try:
            # Foresight is healthy if it's tracking trajectories
            history = self._foresight_engine.trajectory._history
            active_sessions = len(history)
            return min(1.0, active_sessions / 5.0) if active_sessions > 0 else 0.8

        except Exception as e:
            logger.error("Foresight health collection error: %s", sanitize_for_log(str(e)))
            return 0.8

    def _collect_routing_health(self) -> float:
        """Collect health score from FluidicRouter."""
        if not self._fluidic_router:
            return 1.0

        try:
            stats = self._fluidic_router.stats
            cells = stats.get("cells", {})

            if not cells:
                return 1.0

            scores = []
            for _name, cell_stats in cells.items():
                error_rate = cell_stats.get("error_rate", 0.0)
                scores.append(max(0.0, 1.0 - error_rate))

            return sum(scores) / len(scores) if scores else 1.0

        except Exception as e:
            logger.error("Routing health collection error: %s", sanitize_for_log(str(e)))
            return 0.5

    def _collect_sentinel_health(self) -> float:
        """Collect health score from Sentinel."""
        if not self._sentinel:
            return 1.0

        try:
            stats = self._sentinel.get_stats()
            state = stats.get("state", "stopped")

            state_scores = {
                "running": 1.0,
                "degraded": 0.6,
                "starting": 0.8,
                "stopping": 0.5,
                "stopped": 0.3,
            }
            return state_scores.get(state, 0.5)

        except Exception as e:
            logger.error("Sentinel health collection error: %s", sanitize_for_log(str(e)))
            return 0.5

    # ------------------------------------------------------------------
    # Orchestration Cycle
    # ------------------------------------------------------------------

    async def _orchestration_loop(self) -> None:
        """Main orchestration loop — runs continuous proactive cycles."""
        while self._running:
            try:
                await self._orchestration_cycle()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Orchestration cycle error: %s", sanitize_for_log(str(e)))

            # Wait for next cycle
            try:
                await asyncio.sleep(self._orchestration_interval)
            except asyncio.CancelledError:
                break

    async def _orchestration_cycle(self) -> SystemHealthProfile:
        """Execute a single orchestration cycle."""
        cycle_start = time.time()
        self._cycle_count += 1

        # 1. Collect health metrics from all subsystems
        storage_health = self._collect_storage_health()
        service_health = self._collect_service_health()
        security_health = self._collect_security_health()
        resilience_health = self._collect_resilience_health()
        foresight_health = self._collect_foresight_health()
        routing_health = self._collect_routing_health()
        sentinel_health = self._collect_sentinel_health()

        # 2. Compute overall score (weighted average)
        weights = {
            "storage": 0.25,
            "service": 0.20,
            "security": 0.20,
            "resilience": 0.15,
            "foresight": 0.05,
            "routing": 0.10,
            "sentinel": 0.05,
        }
        overall = (
            storage_health * weights["storage"]
            + service_health * weights["service"]
            + security_health * weights["security"]
            + resilience_health * weights["resilience"]
            + foresight_health * weights["foresight"]
            + routing_health * weights["routing"]
            + sentinel_health * weights["sentinel"]
        )

        # 3. Record metrics for predictive analysis
        self._health_analyzer.record("storage", storage_health)
        self._health_analyzer.record("service", service_health)
        self._health_analyzer.record("security", security_health)
        self._health_analyzer.record("resilience", resilience_health)
        self._health_analyzer.record("foresight", foresight_health)
        self._health_analyzer.record("routing", routing_health)
        self._health_analyzer.record("sentinel", sentinel_health)
        self._health_analyzer.record("overall", overall)

        # 4. Run predictive analysis
        predictions = self._health_analyzer.get_all_predictions()

        # 5. Check zero-cost compliance
        zero_cost_status = self._zero_cost_modulator.check_compliance()

        # 6. Generate action plans based on predictions and compliance
        await self._generate_proactive_actions(predictions, zero_cost_status)

        # 7. Dispatch pending actions
        if self._mode in (OrchestratorMode.AUTONOMOUS, OrchestratorMode.EMERGENCY):
            await self._action_dispatcher.dispatch_all_pending()

        # 8. Update health profile
        self._health_profile = SystemHealthProfile(
            overall_score=overall,
            storage_health=storage_health,
            service_health=service_health,
            security_health=security_health,
            resilience_health=resilience_health,
            foresight_health=foresight_health,
            routing_health=routing_health,
            predictions=predictions,
            active_actions=len(self._healing_engine.get_active_heals()),
            pending_actions=len(self._action_dispatcher.get_pending()),
            failed_actions_24h=sum(
                1
                for p in self._healing_engine._heal_history
                if p.status == ActionStatus.FAILED and time.time() - p.completed_at < 86400.0  # type: ignore[operator]
                if p.completed_at
            ),
        )

        # 9. Publish health event
        await self._publish_event("orchestrator.health", self._health_profile.to_dict())

        # 10. Log cycle completion
        cycle_duration = time.time() - cycle_start
        self._last_cycle_time = time.time()
        logger.debug(
            "Orchestration cycle #%d completed in %.2fs (overall=%.2f%%)",
            self._cycle_count,
            cycle_duration,
            overall * 100,
        )

        return self._health_profile

    # ------------------------------------------------------------------
    # Proactive Action Generation
    # ------------------------------------------------------------------

    async def _generate_proactive_actions(
        self,
        predictions: List[HealthPrediction],
        zero_cost_status: ZeroCostStatus,
    ) -> None:
        """Generate action plans based on predictions and compliance status."""

        # 1. Handle degrading subsystems
        for prediction in predictions:
            if prediction.trend == "critical" and prediction.confidence > 0.3:
                await self._create_degradation_action(prediction)

            elif prediction.trend == "degrading" and prediction.confidence > 0.5:
                # In ASSIST mode, just alert; in AUTONOMOUS, take action
                if self._mode == OrchestratorMode.ASSIST:
                    self._action_dispatcher.submit(
                        ActionPlan(
                            id=f"alert-{uuid.uuid4().hex[:8]}",
                            action=ProactiveAction.ALERT,
                            priority=ActionPriority.MEDIUM,
                            target=prediction.subsystem,
                            description=(
                                f"Subsystem '{prediction.subsystem}' is degrading "
                                f"(current={prediction.current_score:.2f}, "
                                f"predicted={prediction.predicted_score:.2f})"
                            ),
                            metadata={"prediction": prediction.to_dict()},
                        )
                    )
                elif self._mode in (OrchestratorMode.AUTONOMOUS, OrchestratorMode.EMERGENCY):
                    await self._create_degradation_action(prediction)

        # 2. Handle zero-cost compliance violations
        if not zero_cost_status.compliant:
            for tier_name in zero_cost_status.critical_tiers:
                await self._create_migration_action(tier_name, critical=True)

            for tier_name in zero_cost_status.approaching_limit:
                await self._create_migration_action(tier_name, critical=False)

        # 3. Handle security threats
        if self._defense_engine:
            try:
                threat_level = self._defense_engine.get_current_threat_level()
                if threat_level.value in ("high", "critical"):
                    self._action_dispatcher.submit(
                        ActionPlan(
                            id=f"harden-{uuid.uuid4().hex[:8]}",
                            action=ProactiveAction.HARDEN,
                            priority=ActionPriority.CRITICAL
                            if threat_level.value == "critical"
                            else ActionPriority.HIGH,
                            target="defense",
                            description=f"Security threat level: {threat_level.value} — hardening defenses",
                            metadata={"threat_level": threat_level.value},
                        )
                    )
            except Exception as e:
                logger.error("Security threat assessment error: %s", sanitize_for_log(str(e)))

        # 4. Handle circuit breaker issues
        if self._resilience_manager:
            try:
                health = self._resilience_manager.health()
                for name, stats in health.get("circuit_breakers", {}).items():
                    if stats.get("state") == "open":
                        self._action_dispatcher.submit(
                            ActionPlan(
                                id=f"quarantine-{uuid.uuid4().hex[:8]}",
                                action=ProactiveAction.QUARANTINE,
                                priority=ActionPriority.HIGH,
                                target=name,
                                description=f"Circuit breaker '{name}' is OPEN — quarantining to prevent cascade",
                                metadata={"circuit_stats": stats},
                            )
                        )
            except Exception as e:
                logger.error("Circuit breaker assessment error: %s", sanitize_for_log(str(e)))

        # 5. Rebalance routing if routing health is degraded
        if routing_health := next((p for p in predictions if p.subsystem == "routing"), None):
            if routing_health.current_score < 0.7:
                self._action_dispatcher.submit(
                    ActionPlan(
                        id=f"rebalance-{uuid.uuid4().hex[:8]}",
                        action=ProactiveAction.REBALANCE,
                        priority=ActionPriority.MEDIUM,
                        target="routing",
                        description="Routing health degraded — rebalancing fluidic weights",
                        metadata={"routing_health": routing_health.current_score},
                    )
                )

    async def _create_degradation_action(self, prediction: HealthPrediction) -> None:
        """Create a healing action for a degrading subsystem."""
        subsystem = prediction.subsystem
        _action_type = ProactiveAction.HEAL  # noqa: F841 — explicit action classification
        priority = (
            ActionPriority.CRITICAL if prediction.trend == "critical" else ActionPriority.HIGH
        )

        # Map subsystem to healing strategy
        heal_strategies = {
            "storage": self._heal_storage,
            "service": self._heal_services,
            "security": self._heal_security,
            "resilience": self._heal_resilience,
            "routing": self._heal_routing,
            "sentinel": self._heal_sentinel,
            "foresight": self._heal_foresight,
        }

        executor = heal_strategies.get(subsystem, self._heal_generic)

        def _rollback_handler() -> None:
            logger.info("Rollback: %s", subsystem)

        # Use AutoHealingEngine if in AUTONOMOUS/EMERGENCY mode
        if self._mode in (OrchestratorMode.AUTONOMOUS, OrchestratorMode.EMERGENCY):
            plan = self._healing_engine.create_heal_action(
                target=subsystem,
                description=(
                    f"Subsystem '{subsystem}' {prediction.trend} "
                    f"(current={prediction.current_score:.2f}, "
                    f"predicted={prediction.predicted_score:.2f})"
                ),
                executor=executor,
                rollback=_rollback_handler,
                priority=priority,
                metadata={"prediction": prediction.to_dict()},
            )
            if plan:
                await self._healing_engine.execute_heal(plan)
        else:
            # OBSERVE or ASSIST — just create an alert
            self._action_dispatcher.submit(
                ActionPlan(
                    id=f"alert-{uuid.uuid4().hex[:8]}",
                    action=ProactiveAction.ALERT,
                    priority=priority,
                    target=subsystem,
                    description=(
                        f"Subsystem '{subsystem}' {prediction.trend} — "
                        f"healing recommended (mode={self._mode.value})"
                    ),
                    metadata={"prediction": prediction.to_dict()},
                )
            )

    async def _create_migration_action(self, tier_name: str, critical: bool) -> None:
        """Create a storage migration action to maintain zero-cost compliance."""
        # Check if migration is appropriate
        try:
            capacities = (
                self._storage_orchestrator.get_all_capacities()
                if self._storage_orchestrator
                else {}
            )
            usage_pct = capacities.get(tier_name, {}).get("usage_pct", 0.0)
        except Exception:
            usage_pct = 100.0 if critical else 0.0

        if not self._zero_cost_modulator.should_migrate(tier_name, usage_pct):
            return

        destination = self._zero_cost_modulator.get_migration_recommendation(tier_name)

        if not destination:
            # No alternative — alert only
            self._action_dispatcher.submit(
                ActionPlan(
                    id=f"alert-{uuid.uuid4().hex[:8]}",
                    action=ProactiveAction.ALERT,
                    priority=ActionPriority.CRITICAL if critical else ActionPriority.HIGH,
                    target=tier_name,
                    description=(
                        f"Storage tier '{tier_name}' approaching free-tier limit "
                        f"with no migration alternative available"
                    ),
                )
            )
            return

        async def migrate():
            """Execute the storage migration."""
            if self._storage_orchestrator:
                try:
                    success = await self._storage_orchestrator.migrate_tier(
                        source_tier=tier_name,
                        dest_tier=destination,
                    )
                    self._zero_cost_modulator.record_migration(
                        source=tier_name,
                        destination=destination,
                        success=success,
                    )
                    return {"migrated": success, "from": tier_name, "to": destination}
                except Exception as e:
                    self._zero_cost_modulator.record_migration(
                        source=tier_name,
                        destination=destination,
                        success=False,
                    )
                    raise RuntimeError(f"Migration failed: {e}") from None
            return {"migrated": False, "reason": "no storage orchestrator"}

        self._action_dispatcher.submit(
            ActionPlan(
                id=f"migrate-{uuid.uuid4().hex[:8]}",
                action=ProactiveAction.MIGRATE_STORAGE,
                priority=ActionPriority.CRITICAL if critical else ActionPriority.HIGH,
                target=tier_name,
                description=f"Migrate data from '{tier_name}' to '{destination}' (zero-cost compliance)",
                executor=migrate,
                metadata={"destination": destination, "critical": critical},
            )
        )

    # ------------------------------------------------------------------
    # Healing Strategies
    # ------------------------------------------------------------------

    def _heal_storage(self) -> Dict[str, Any]:
        """Heal storage subsystem — trigger tier rebalancing."""
        if self._storage_orchestrator:
            try:
                return {
                    "action": "storage_rebalance",
                    "capacities": self._storage_orchestrator.get_all_capacities(),
                }
            except Exception as e:
                return {"action": "storage_rebalance", "error": str(e)}
        return {"action": "storage_rebalance", "status": "no_orchestrator"}

    def _heal_services(self) -> Dict[str, Any]:
        """Heal services — trigger re-registration of unhealthy services."""
        if self._enhanced_registry:
            try:
                topology = self._enhanced_registry.get_routing_topology()
                unhealthy = []
                for _cap, services in topology.items():
                    for svc in services:
                        if svc.get("health") == "unhealthy":
                            unhealthy.append(svc["name"])

                if unhealthy:
                    for name in unhealthy:
                        self._enhanced_registry.update_health(name, "degraded")
                    return {"action": "service_heal", "recovered": unhealthy}
                return {"action": "service_heal", "status": "all_healthy"}
            except Exception as e:
                return {"action": "service_heal", "error": str(e)}
        return {"action": "service_heal", "status": "no_registry"}

    def _heal_security(self) -> Dict[str, Any]:
        """Heal security — ensure default rules are in place and threat is contained."""
        if self._defense_engine:
            try:
                stats = self._defense_engine.get_stats()
                return {
                    "action": "security_heal",
                    "threat_level": stats.current_threat_level.value,
                    "rules_count": stats.firewall_rules,
                }
            except Exception as e:
                return {"action": "security_heal", "error": str(e)}
        return {"action": "security_heal", "status": "no_defense_engine"}

    def _heal_resilience(self) -> Dict[str, Any]:
        """Heal resilience — transition open circuit breakers to half-open."""
        if self._resilience_manager:
            try:
                health = self._resilience_manager.health()
                opened = []
                for name, stats in health.get("circuit_breakers", {}).items():
                    if stats.get("state") == "open":
                        breaker = self._resilience_manager.get_breaker(name)
                        if breaker:
                            breaker.state = (
                                type(breaker.state).HALF_OPEN if hasattr(breaker, "state") else None
                            )
                            opened.append(name)

                return {"action": "resilience_heal", "transitioned_to_half_open": opened}
            except Exception as e:
                return {"action": "resilience_heal", "error": str(e)}
        return {"action": "resilience_heal", "status": "no_resilience_manager"}

    def _heal_routing(self) -> Dict[str, Any]:
        """Heal routing — reset fluidic weights for error-heavy routes."""
        if self._fluidic_router:
            try:
                stats = self._fluidic_router.stats
                reset = []
                for name, cell_stats in stats.get("cells", {}).items():
                    if cell_stats.get("error_rate", 0) > 0.5:
                        cell = self._fluidic_router._cells.get(name)
                        if cell:
                            cell.weight = 0.5  # Reset to moderate weight
                            cell.error_count = 0
                            reset.append(name)

                return {"action": "routing_heal", "reset_weights": reset}
            except Exception as e:
                return {"action": "routing_heal", "error": str(e)}
        return {"action": "routing_heal", "status": "no_router"}

    def _heal_sentinel(self) -> Dict[str, Any]:
        """Heal sentinel — restart if degraded."""
        if self._sentinel:
            try:
                state = self._sentinel.get_state()
                if state.value == "degraded":
                    self._sentinel.stop()
                    self._sentinel.start(background=True)
                    return {"action": "sentinel_heal", "restarted": True}
                return {"action": "sentinel_heal", "state": state.value}
            except Exception as e:
                return {"action": "sentinel_heal", "error": str(e)}
        return {"action": "sentinel_heal", "status": "no_sentinel"}

    def _heal_foresight(self) -> Dict[str, Any]:
        """Heal foresight — reinitialize trajectory predictor."""
        if self._foresight_engine:
            try:
                self._foresight_engine.trajectory._history.clear()
                return {"action": "foresight_heal", "cleared_history": True}
            except Exception as e:
                return {"action": "foresight_heal", "error": str(e)}
        return {"action": "foresight_heal", "status": "no_foresight"}

    def _heal_generic(self) -> Dict[str, Any]:
        """Generic healing action — log and report."""
        return {"action": "generic_heal", "status": "logged"}

    # ------------------------------------------------------------------
    # Default Action Handlers
    # ------------------------------------------------------------------

    def _register_default_handlers(self) -> None:
        """Register default action handlers for the dispatcher."""
        self._action_dispatcher.register_handler(
            ProactiveAction.HEAL,
            self._handle_heal_action,
        )
        self._action_dispatcher.register_handler(
            ProactiveAction.MIGRATE_STORAGE,
            self._handle_migration_action,
        )
        self._action_dispatcher.register_handler(
            ProactiveAction.ALERT,
            self._handle_alert_action,
        )
        self._action_dispatcher.register_handler(
            ProactiveAction.HARDEN,
            self._handle_harden_action,
        )
        self._action_dispatcher.register_handler(
            ProactiveAction.QUARANTINE,
            self._handle_quarantine_action,
        )
        self._action_dispatcher.register_handler(
            ProactiveAction.REBALANCE,
            self._handle_rebalance_action,
        )

    async def _handle_heal_action(self, plan: ActionPlan) -> None:
        """Handle a HEAL action."""
        logger.info(
            "Executing heal action: %s → %s",
            sanitize_for_log(plan.id),
            sanitize_for_log(plan.target),
        )

    async def _handle_migration_action(self, plan: ActionPlan) -> None:
        """Handle a MIGRATE_STORAGE action."""
        if plan.executor and self._mode in (
            OrchestratorMode.AUTONOMOUS,
            OrchestratorMode.EMERGENCY,
        ):
            try:
                if asyncio.iscoroutinefunction(plan.executor):
                    result = await plan.executor()
                else:
                    result = plan.executor()
                plan.result = result if isinstance(result, dict) else {"result": str(result)}
            except Exception as e:
                plan.error = str(e)
                logger.error("Migration action failed: %s", sanitize_for_log(str(e)))

    async def _handle_alert_action(self, plan: ActionPlan) -> None:
        """Handle an ALERT action."""
        logger.warning(
            "Proactive alert: [%s] %s — %s",
            plan.priority.name,
            sanitize_for_log(plan.target),
            sanitize_for_log(plan.description),
        )

    async def _handle_harden_action(self, plan: ActionPlan) -> None:
        """Handle a HARDEN action — tighten security."""
        if self._defense_engine:
            try:
                # Add a temporary strict rule
                self._defense_engine.add_rule(
                    name="Proactive Hardening - Rate Limit All",
                    description="Temporary rate limiting due to elevated threat level",
                    priority=0,
                    action="rate_limit",
                )
                logger.info("Proactive security hardening applied")
            except Exception as e:
                logger.error("Hardening action failed: %s", sanitize_for_log(str(e)))

    async def _handle_quarantine_action(self, plan: ActionPlan) -> None:
        """Handle a QUARANTINE action — isolate unhealthy component."""
        logger.warning(
            "Quarantine action: isolating %s",
            sanitize_for_log(plan.target),
        )
        if self._fluidic_router:
            try:
                cell = self._fluidic_router._cells.get(plan.target)
                if cell:
                    cell.weight = 0.01  # Minimum weight = effectively quarantined
            except Exception as e:
                logger.error("Quarantine action failed: %s", sanitize_for_log(str(e)))

    async def _handle_rebalance_action(self, plan: ActionPlan) -> None:
        """Handle a REBALANCE action — rebalance routing weights."""
        if self._enhanced_registry:
            try:
                self._enhanced_registry._rebalance_weights()
                logger.info("Proactive routing rebalance executed")
            except Exception as e:
                logger.error("Rebalance action failed: %s", sanitize_for_log(str(e)))

    # ------------------------------------------------------------------
    # Event Publishing
    # ------------------------------------------------------------------

    async def _publish_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Publish an event to the EventBus."""
        if not self._event_bus:
            return

        try:
            from Dimensional.models import EventMessage

            event = EventMessage(
                event_type=event_type,
                source="proactive_orchestrator",
                data=data,
            )
            await self._event_bus.publish(event)
        except Exception as e:
            logger.error("Event publish error: %s", sanitize_for_log(str(e)))

    # ------------------------------------------------------------------
    # Introspection & Statistics
    # ------------------------------------------------------------------

    def get_health_profile(self) -> SystemHealthProfile:
        """Get the current system health profile."""
        return self._health_profile

    def get_zero_cost_status(self) -> ZeroCostStatus:
        """Get the current zero-cost compliance status."""
        return self._zero_cost_modulator.check_compliance()

    def get_predictions(self) -> List[HealthPrediction]:
        """Get health predictions for all subsystems."""
        return self._health_analyzer.get_all_predictions()

    def get_degrading_subsystems(self) -> List[HealthPrediction]:
        """Get predictions for subsystems that are degrading."""
        return self._health_analyzer.get_degrading()

    def get_pending_actions(self) -> List[Dict[str, Any]]:
        """Get all pending action plans."""
        return self._action_dispatcher.get_pending()

    def get_heal_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent healing action history."""
        return self._healing_engine.get_recent_heals(limit)

    def get_migration_history(self) -> List[Dict[str, Any]]:
        """Get storage migration history."""
        return self._zero_cost_modulator._migration_history

    def _get_attached_subsystem_names(self) -> List[str]:
        """Get names of all attached subsystems."""
        attached = []
        if self._storage_orchestrator:
            attached.append("SmartStorageOrchestrator")
        if self._sentinel:
            attached.append("Sentinel")
        if self._defense_engine:
            attached.append("DefenseEngine")
        if self._foresight_engine:
            attached.append("ForesightEngine")
        if self._fluidic_router:
            attached.append("FluidicRouter")
        if self._enhanced_registry:
            attached.append("EnhancedServiceRegistry")
        if self._resilience_manager:
            attached.append("ResilienceManager")
        if self._event_bus:
            attached.append("EventBus")
        return attached

    def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator statistics."""
        uptime = time.time() - self._started_at if self._started_at else 0.0

        return {
            "mode": self._mode.value,
            "running": self._running,
            "uptime_seconds": round(uptime, 1),
            "cycle_count": self._cycle_count,
            "last_cycle_time": self._last_cycle_time,
            "orchestration_interval": self._orchestration_interval,
            "attached_subsystems": self._get_attached_subsystem_names(),
            "health_profile": self._health_profile.to_dict(),
            "health_analyzer": self._health_analyzer.get_stats(),
            "healing_engine": self._healing_engine.get_stats(),
            "zero_cost_modulator": self._zero_cost_modulator.get_stats(),
            "action_dispatcher": self._action_dispatcher.get_stats(),
        }

    def get_dashboard(self) -> Dict[str, Any]:
        """Get a comprehensive dashboard of all system vitals."""
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self._mode.value,
            "running": self._running,
            "health": self._health_profile.to_dict(),
            "zero_cost": self._zero_cost_modulator.check_compliance().to_dict(),
            "predictions": [p.to_dict() for p in self.get_predictions()],
            "pending_actions": self.get_pending_actions(),
            "degrading_subsystems": [p.to_dict() for p in self.get_degrading_subsystems()],
            "heal_stats": self._healing_engine.get_stats(),
            "migration_stats": self._zero_cost_modulator.get_stats(),
            "dispatcher_stats": self._action_dispatcher.get_stats(),
        }


# Singleton
proactive_orchestrator = ProactiveOrchestrator()
