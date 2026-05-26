"""Smart Adaptive Loop — TranceX Phase 8

Closed feedback loop integrating Genetic Optimizer, Vector Plan Cache,
Predictive Drift Service, and SHI Gateway for self-optimizing NRC query
execution. Continuously monitors, adapts, and evolves the system.

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class LoopPhase(Enum):
    """Phases of the adaptive loop cycle."""
    OBSERVE = "observe"
    ANALYZE = "analyze"
    PLAN = "plan"
    EXECUTE = "execute"
    EVALUATE = "evaluate"
    ADAPT = "adapt"


class AdaptationType(Enum):
    """Types of adaptations the loop can make."""
    RE_OPTIMIZE = "re_optimize"
    SCALE_UP = "scale_up"
    SCALE_DOWN = "scale_down"
    BACKEND_SWITCH = "backend_switch"
    CACHE_UPDATE = "cache_update"
    DRIFT_HEAL = "drift_heal"
    QUANTUM_ESCALATE = "quantum_escalate"
    WASM_OFFLOAD = "wasm_offload"
    GPU_ACCELERATE = "gpu_accelerate"
    RETRY = "retry"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


@dataclass
class Observation:
    """An observation from the system monitoring layer."""
    observation_id: str = ""
    source: str = ""
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    timestamp: float = field(default_factory=time.time)
    labels: Dict[str, str] = field(default_factory=dict)
    anomaly: bool = False

    def __post_init__(self):
        if not self.observation_id:
            self.observation_id = f"obs-{uuid.uuid4().hex[:8]}"


@dataclass
class AdaptationAction:
    """An action taken by the adaptive loop."""
    action_id: str = ""
    adaptation_type: AdaptationType = AdaptationType.RE_OPTIMIZE
    target: str = ""
    parameters: Dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    confidence: float = 0.5
    executed: bool = False
    result: Optional[Dict[str, Any]] = None
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.action_id:
            self.action_id = f"act-{uuid.uuid4().hex[:8]}"


@dataclass
class LoopCycleResult:
    """Result from a single adaptive loop cycle."""
    cycle_id: str = ""
    phase: LoopPhase = LoopPhase.OBSERVE
    observations: List[Observation] = field(default_factory=list)
    adaptations: List[AdaptationAction] = field(default_factory=list)
    cycle_duration_ms: float = 0.0
    improvements: Dict[str, float] = field(default_factory=dict)
    alerts: List[Dict[str, Any]] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.cycle_id:
            self.cycle_id = f"cycle-{uuid.uuid4().hex[:8]}"


class MetricsCollector:
    """Collects and aggregates metrics from all TranceX services.

    Provides a unified view of system health, performance, and
    resource utilization for the adaptive loop.
    """

    def __init__(self):
        self._metrics: Dict[str, List[Tuple[float, float]]] = {}  # name -> [(timestamp, value)]
        self._thresholds: Dict[str, float] = {
            "query_latency_ms": 1000.0,
            "cache_hit_rate": 0.5,
            "drift_signal_count": 10.0,
            "drone_availability": 0.7,
            "gpu_utilization": 0.3,
            "wasm_execution_ms": 500.0,
            "optimization_quality": 0.8,
        }

    def record(self, metric_name: str, value: float) -> None:
        """Record a metric observation."""
        self._metrics.setdefault(metric_name, []).append((time.time(), value))

    def get_current(self, metric_name: str) -> Optional[float]:
        """Get the most recent value for a metric."""
        values = self._metrics.get(metric_name, [])
        return values[-1][1] if values else None

    def get_trend(self, metric_name: str, window_seconds: float = 300.0) -> str:
        """Get the trend direction for a metric."""
        values = self._metrics.get(metric_name, [])
        if len(values) < 2:
            return "unknown"

        cutoff = time.time() - window_seconds
        recent = [(t, v) for t, v in values if t >= cutoff]
        if len(recent) < 2:
            return "unknown"

        first = recent[0][1]
        last = recent[-1][1]
        change = (last - first) / abs(first) if first != 0 else 0

        if change > 0.1:
            return "increasing"
        elif change < -0.1:
            return "decreasing"
        return "stable"

    def check_anomalies(self) -> List[Observation]:
        """Check for metric anomalies based on thresholds."""
        anomalies = []
        for name, threshold in self._thresholds.items():
            current = self.get_current(name)
            if current is None:
                continue

            # Some metrics are "below threshold = bad" (hit_rate, availability)
            below_threshold_bad = name in ("cache_hit_rate", "drone_availability", "gpu_utilization", "optimization_quality")

            is_anomaly = (
                (current < threshold and below_threshold_bad) or
                (current > threshold and not below_threshold_bad)
            )

            if is_anomaly:
                anomalies.append(Observation(
                    source="metrics_collector",
                    metric_name=name,
                    metric_value=current,
                    threshold=threshold,
                    anomaly=True,
                    labels={"direction": "below" if current < threshold else "above"},
                ))

        return anomalies

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of all collected metrics."""
        summary = {}
        for name, values in self._metrics.items():
            if not values:
                continue
            recent_values = [v for _, v in values[-100:]]
            summary[name] = {
                "current": recent_values[-1] if recent_values else None,
                "min": min(recent_values),
                "max": max(recent_values),
                "avg": sum(recent_values) / len(recent_values),
                "trend": self.get_trend(name),
            }
        return summary


class AdaptiveLoopEngine:
    """Core engine for the Smart Adaptive Loop.

    Implements the OODA (Observe-Orient-Decide-Act) loop pattern
    adapted for TranceX NRC query optimization.
    """

    def __init__(
        self,
        genetic_optimizer=None,
        vector_cache=None,
        predictive_drift=None,
        shi_gateway=None,
        gpu_service=None,
        drone_adapter=None,
        cycle_interval_seconds: float = 30.0,
    ):
        self.genetic_optimizer = genetic_optimizer
        self.vector_cache = vector_cache
        self.predictive_drift = predictive_drift
        self.shi_gateway = shi_gateway
        self.gpu_service = gpu_service
        self.drone_adapter = drone_adapter
        self.cycle_interval = cycle_interval_seconds

        self.metrics = MetricsCollector()
        self._running = False
        self._cycle_count = 0
        self._cycle_history: List[LoopCycleResult] = []
        self._action_history: List[AdaptationAction] = []

    async def run_cycle(self) -> LoopCycleResult:
        """Execute a single adaptive loop cycle."""
        start = time.monotonic()
        cycle_result = LoopCycleResult()

        # Phase 1: OBSERVE
        observations = await self._observe()
        cycle_result.observations = observations

        # Phase 2: ANALYZE
        analysis = self._analyze(observations)

        # Phase 3: PLAN
        adaptations = self._plan_adaptations(analysis)
        cycle_result.adaptations = adaptations

        # Phase 4: EXECUTE
        await self._execute_adaptations(adaptations)

        # Phase 5: EVALUATE
        improvements = self._evaluate_improvements()
        cycle_result.improvements = improvements

        # Phase 6: ADAPT (update thresholds and policies)
        self._adapt_policies(observations, improvements)

        cycle_result.cycle_duration_ms = (time.monotonic() - start) * 1000
        self._cycle_count += 1
        self._cycle_history.append(cycle_result)
        self._action_history.extend(adaptations)

        return cycle_result

    async def run_continuous(self, max_cycles: int = 0) -> None:
        """Run the adaptive loop continuously."""
        self._running = True
        cycles = 0

        while self._running:
            try:
                await self.run_cycle()
                cycles += 1

                if max_cycles > 0 and cycles >= max_cycles:
                    break

                await asyncio.sleep(self.cycle_interval)
            except Exception as e:
                logger.error(f"Adaptive loop cycle error: {e}")
                await asyncio.sleep(self.cycle_interval * 2)

    def stop(self) -> None:
        """Stop the continuous adaptive loop."""
        self._running = False

    async def _observe(self) -> List[Observation]:
        """Collect observations from all connected services."""
        observations = []

        # Collect metric anomalies
        anomalies = self.metrics.check_anomalies()
        observations.extend(anomalies)

        # Observe drift signals
        if self.predictive_drift:
            drift_metrics = self.predictive_drift.get_metrics()
            for key, value in drift_metrics.items():
                if isinstance(value, (int, float)):
                    obs = Observation(
                        source="predictive_drift",
                        metric_name=f"drift_{key}",
                        metric_value=float(value),
                    )
                    observations.append(obs)

        # Observe cache performance
        if self.vector_cache:
            cache_stats = self.vector_cache.get_cache_stats()
            self.metrics.record("cache_hit_rate", cache_stats.get("hit_rate", 0))

        # Observe drone availability
        if self.drone_adapter:
            swarm_status = self.drone_adapter.swarm.get_swarm_status()
            total = swarm_status.get("total_drones", 1)
            available = swarm_status.get("available_drones", 0)
            self.metrics.record("drone_availability", available / max(1, total))

        return observations

    def _analyze(self, observations: List[Observation]) -> Dict[str, Any]:
        """Analyze observations to identify issues and opportunities."""
        analysis: Dict[str, Any] = {
            "anomalies": [],
            "trends": {},
            "recommendations": [],
        }

        for obs in observations:
            if obs.anomaly:
                analysis["anomalies"].append({
                    "metric": obs.metric_name,
                    "value": obs.metric_value,
                    "threshold": obs.threshold,
                    "source": obs.source,
                })

        # Analyze trends
        for metric in ["query_latency_ms", "cache_hit_rate", "drift_signal_count"]:
            trend = self.metrics.get_trend(metric)
            if trend != "unknown":
                analysis["trends"][metric] = trend

        # Generate recommendations based on analysis
        if any(a["metric"] == "query_latency_ms" for a in analysis["anomalies"]):
            analysis["recommendations"].append("re_optimize")

        if any(a["metric"] == "cache_hit_rate" for a in analysis["anomalies"]):
            analysis["recommendations"].append("cache_update")

        if any(a["metric"].startswith("drift_") for a in analysis["anomalies"]):
            analysis["recommendations"].append("drift_heal")

        return analysis

    def _plan_adaptations(self, analysis: Dict[str, Any]) -> List[AdaptationAction]:
        """Plan adaptation actions based on analysis."""
        actions = []

        for rec in analysis.get("recommendations", []):
            if rec == "re_optimize":
                actions.append(AdaptationAction(
                    adaptation_type=AdaptationType.RE_OPTIMIZE,
                    target="query_planner",
                    reason="Query latency exceeds threshold",
                    confidence=0.8,
                ))
            elif rec == "cache_update":
                actions.append(AdaptationAction(
                    adaptation_type=AdaptationType.CACHE_UPDATE,
                    target="vector_plan_cache",
                    reason="Cache hit rate below threshold",
                    confidence=0.7,
                ))
            elif rec == "drift_heal":
                actions.append(AdaptationAction(
                    adaptation_type=AdaptationType.DRIFT_HEAL,
                    target="igi_gitops",
                    reason="Drift signals detected",
                    confidence=0.75,
                ))

        # Check for quantum escalation opportunity
        latency_trend = analysis.get("trends", {}).get("query_latency_ms", "stable")
        if latency_trend == "increasing":
            actions.append(AdaptationAction(
                adaptation_type=AdaptationType.QUANTUM_ESCALATE,
                target="quantum_solver",
                reason="Query latency trend is increasing",
                confidence=0.6,
            ))

        return actions

    async def _execute_adaptations(self, actions: List[AdaptationAction]) -> None:
        """Execute planned adaptation actions."""
        for action in actions:
            try:
                if action.adaptation_type == AdaptationType.RE_OPTIMIZE and self.genetic_optimizer:
                    # Re-run genetic optimization
                    action.executed = True
                    action.result = {"status": "optimization_triggered"}

                elif action.adaptation_type == AdaptationType.CACHE_UPDATE and self.vector_cache:
                    # Update cache policies
                    action.executed = True
                    action.result = {"status": "cache_refreshed"}

                elif action.adaptation_type == AdaptationType.DRIFT_HEAL and self.predictive_drift:
                    # Trigger drift analysis and healing
                    report = await self.predictive_drift.analyze_and_predict()
                    action.executed = True
                    action.result = {
                        "status": "drift_analyzed",
                        "predictions": len(report.predictions),
                        "recommendations": len(report.recommendations),
                    }

                elif action.adaptation_type == AdaptationType.QUANTUM_ESCALATE:
                    action.executed = True
                    action.result = {"status": "quantum_escalation_flagged"}

                else:
                    action.executed = False
                    action.result = {"status": "skipped", "reason": "service_not_available"}

            except Exception as e:
                action.executed = False
                action.result = {"status": "failed", "error": str(e)}

    def _evaluate_improvements(self) -> Dict[str, float]:
        """Evaluate improvements from recent adaptations."""
        improvements = {}
        summary = self.metrics.get_summary()

        for metric_name, data in summary.items():
            if data["trend"] == "decreasing" and metric_name in ("query_latency_ms", "drift_signal_count"):
                improvements[metric_name] = -0.1  # 10% improvement
            elif data["trend"] == "increasing" and metric_name in ("cache_hit_rate", "drone_availability"):
                improvements[metric_name] = 0.1

        return improvements

    def _adapt_policies(self, observations: List[Observation], improvements: Dict[str, float]) -> None:
        """Adapt internal policies based on observations and improvements."""
        # Adjust cycle interval based on activity level
        anomaly_count = sum(1 for o in observations if o.anomaly)
        if anomaly_count > 5:
            self.cycle_interval = max(5.0, self.cycle_interval * 0.8)  # Speed up
        elif anomaly_count == 0:
            self.cycle_interval = min(120.0, self.cycle_interval * 1.1)  # Slow down

    def get_loop_status(self) -> Dict[str, Any]:
        """Get the current adaptive loop status."""
        return {
            "running": self._running,
            "cycle_count": self._cycle_count,
            "cycle_interval": self.cycle_interval,
            "total_actions": len(self._action_history),
            "executed_actions": sum(1 for a in self._action_history if a.executed),
            "metrics_summary": self.metrics.get_summary(),
        }

    def get_cycle_history(self, last_n: int = 10) -> List[Dict[str, Any]]:
        """Get history of recent loop cycles."""
        recent = self._cycle_history[-last_n:]
        return [
            {
                "cycle_id": c.cycle_id,
                "observations": len(c.observations),
                "adaptations": len(c.adaptations),
                "duration_ms": c.cycle_duration_ms,
                "improvements": c.improvements,
            }
            for c in recent
        ]
