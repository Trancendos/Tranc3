"""
shared_core.infinity.adaptive_intelligence — Unified Smart Adaptive Intelligence Layer
========================================================================================
Trancendos Universe — Phase 22 Enhancement

Integrates the following GitHub-sourced subsystems into a single, intelligence-driven
layer that all Infinity workers automatically benefit from:

  AdaptivePulseController  → Dynamic interval compression on degradation
  AnomalyDetector          → Z-score statistical anomaly detection on all metrics
  SelfRepairEngine         → Priority-based autonomous self-healing strategies
  AdaptiveConfigTuner      → Regression-based config optimisation (auto-applies at ≥80% confidence)
  EnhancedServiceRegistry  → Weighted capability routing + auto-discovery
  ReactiveState            → Observable state for live topology updates
  HotConfig                → Zero-downtime config hot-reload
  TelemetryCollector       → Prometheus-compatible per-service metrics
  DefenseEngine            → Firewall + security incident management
  ForesightEngine          → Predictive health trajectory analysis

Architecture:
    ┌─────────────────────────────────────────────────────────────────────────┐
    │                   InfinityHealthOrchestrator                            │
    │                                                                         │
    │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐    │
    │  │ AdaptivePulse  │  │ AnomalyDetect  │  │ SelfRepairEngine       │    │
    │  │ Controller     │  │ (z-score)      │  │ (5 builtin strategies) │    │
    │  └───────┬────────┘  └───────┬────────┘  └──────────┬─────────────┘    │
    │          │                   │                       │                  │
    │  ┌───────┴───────────────────┴───────────────────────┴─────────────┐    │
    │  │                    Health Score Pipeline                         │    │
    │  │  (aggregate → normalise → feed pulse → trigger anomaly →        │    │
    │  │   evaluate repair → publish to Sentinel Station)                │    │
    │  └─────────────────────────────────────────────────────────────────┘    │
    │                                                                         │
    │  ┌────────────────┐  ┌────────────────┐  ┌────────────────────────┐    │
    │  │ HotConfig      │  │ TelemetryMW    │  │ AdaptiveConfigTuner    │    │
    │  │ (hot-reload)   │  │ (Prometheus)   │  │ (ML regression)        │    │
    │  └────────────────┘  └────────────────┘  └────────────────────────┘    │
    │                                                                         │
    │  ┌────────────────────────────────────────────────────────────────┐     │
    │  │ ForesightEngine — Predictive Trajectory Analysis               │     │
    │  │ STEADY/DEGRADING/CRITICAL trajectory → pre-emptive actions     │     │
    │  └────────────────────────────────────────────────────────────────┘     │
    └─────────────────────────────────────────────────────────────────────────┘

Usage in any Infinity worker:
    from shared_core.infinity.adaptive_intelligence import InfinityHealthOrchestrator

    # At startup:
    orchestrator = InfinityHealthOrchestrator(service_name="infinity-portal")
    await orchestrator.start(app)           # Mounts telemetry middleware + starts loops
    orchestrator.register_daemon("session_cleaner", baseline_interval=300.0)

    # In background loops:
    if orchestrator.pulse.should_fire("session_cleaner"):
        await clean_sessions()
        orchestrator.pulse.record_fire("session_cleaner")
        orchestrator.record_metric("session_count", session_count)

    # Health endpoint integration:
    health = orchestrator.get_health_summary()
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# ── Optional imports (graceful degradation) ──────────────────────────────────

try:
    from shared_core.architecture.adaptive_pulse import (  # codeql[py/cyclic-import]
        AdaptivePulseController,
    )

    _PULSE_AVAILABLE = True
except ImportError:
    _PULSE_AVAILABLE = False
    AdaptivePulseController = None  # type: ignore[assignment,misc]

try:
    from src.healing.anomaly_detector import AnomalyDetector  # codeql[py/cyclic-import]

    _ANOMALY_AVAILABLE = True
except ImportError:
    _ANOMALY_AVAILABLE = False
    AnomalyDetector = None  # type: ignore[assignment,misc]

try:
    from src.healing.self_repair import (  # codeql[py/cyclic-import]
        AdaptiveConfigTuner,
        SelfRepairEngine,
    )

    _REPAIR_AVAILABLE = True
except ImportError:
    _REPAIR_AVAILABLE = False
    SelfRepairEngine = None  # type: ignore[assignment,misc]
    AdaptiveConfigTuner = None  # type: ignore[assignment,misc]

try:
    from src.fluidic.reactive_state import StateStore  # codeql[py/cyclic-import]

    _REACTIVE_AVAILABLE = True
except ImportError:
    _REACTIVE_AVAILABLE = False
    StateStore = None  # type: ignore[assignment,misc]

try:
    from src.fluidic.hot_config import HotConfig  # codeql[py/cyclic-import]

    _HOTCONFIG_AVAILABLE = True
except ImportError:
    _HOTCONFIG_AVAILABLE = False
    HotConfig = None  # type: ignore[assignment,misc]

try:
    from shared_core.middleware.telemetry import (  # codeql[py/cyclic-import]
        TelemetryCollector,
        TelemetryMiddleware,
    )

    _TELEMETRY_AVAILABLE = True
except ImportError:
    _TELEMETRY_AVAILABLE = False
    TelemetryCollector = None  # type: ignore[assignment,misc]
    TelemetryMiddleware = None  # type: ignore[assignment,misc]

try:
    from src.adaptive.foresight import (  # codeql[py/cyclic-import]
        ConversationTrajectoryPredictor,
    )

    _FORESIGHT_AVAILABLE = True
except ImportError:
    _FORESIGHT_AVAILABLE = False
    ConversationTrajectoryPredictor = None  # type: ignore[assignment,misc]

try:
    from shared_core.security_automation.defense_engine import (  # codeql[py/cyclic-import]
        DefenseEngine,
    )

    _DEFENSE_AVAILABLE = True
except ImportError:
    _DEFENSE_AVAILABLE = False
    DefenseEngine = None  # type: ignore[assignment,misc]


# ── Health Tier ───────────────────────────────────────────────────────────────


class HealthTier:
    """Health score → operational tier mapping."""

    OPTIMAL = (0.9, 1.0, "optimal", "🟢")
    HEALTHY = (0.7, 0.9, "healthy", "🟡")
    DEGRADED = (0.4, 0.7, "degraded", "🟠")
    CRITICAL = (0.0, 0.4, "critical", "🔴")

    @classmethod
    def classify(cls, score: float) -> tuple[str, str]:
        for lo, hi, label, icon in [cls.OPTIMAL, cls.HEALTHY, cls.DEGRADED, cls.CRITICAL]:
            if lo <= score <= hi:
                return label, icon
        return "unknown", "⚪"


# ── Adaptive Intelligence Config ──────────────────────────────────────────────


@dataclass
class AIConfig:
    """Configuration for InfinityHealthOrchestrator."""

    service_name: str = "infinity-service"
    baseline_pulse_interval: float = 30.0
    anomaly_window_size: int = 100
    anomaly_z_threshold: float = 3.0
    anomaly_min_samples: int = 10
    health_history_size: int = 500
    repair_eval_interval: float = 60.0
    foresight_enabled: bool = True
    defense_enabled: bool = True
    telemetry_enabled: bool = True
    hotconfig_watch_paths: List[str] = field(default_factory=lambda: [".env"])
    sentinel_publish_fn: Optional[Callable] = None  # set post-init if Sentinel available


# ── Health Summary ────────────────────────────────────────────────────────────


@dataclass
class HealthSummary:
    service_name: str
    score: float
    tier: str
    tier_icon: str
    pulse_mode: str
    anomalies_detected: int
    repairs_applied: int
    metrics: Dict[str, float]
    foresight: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service_name,
            "health_score": round(self.score, 4),
            "health_tier": self.tier,
            "health_icon": self.tier_icon,
            "pulse_mode": self.pulse_mode,
            "anomalies_detected": self.anomalies_detected,
            "repairs_applied": self.repairs_applied,
            "metrics": {k: round(v, 4) for k, v in self.metrics.items()},
            "foresight": self.foresight,
            "timestamp": self.timestamp,
            "uptime_seconds": round(self.uptime_seconds, 1),
        }


# ── InfinityHealthOrchestrator ────────────────────────────────────────────────


class InfinityHealthOrchestrator:
    """
    Unified smart adaptive intelligence layer for all Infinity workers.

    Automatically wires together:
    - AdaptivePulseController  (dynamic daemon intervals)
    - AnomalyDetector          (statistical anomaly detection on all metrics)
    - SelfRepairEngine         (autonomous healing strategy evaluation)
    - AdaptiveConfigTuner      (ML regression config optimisation)
    - TelemetryCollector       (Prometheus metrics)
    - HotConfig                (zero-downtime config reload)
    - ForesightEngine          (trajectory prediction)
    - DefenseEngine            (firewall + incidents)
    - ReactiveState            (observable topology state)

    All subsystems are optional — the orchestrator degrades gracefully when
    any subsystem is unavailable (e.g., in test environments).
    """

    def __init__(self, config: Optional[AIConfig] = None):
        self.config = config or AIConfig()
        self._start_time = time.time()
        self._health_score = 1.0
        self._anomaly_count = 0
        self._repair_count = 0
        self._metric_cache: Dict[str, float] = {}
        self._health_history: list = []
        self._loops: List[asyncio.Task] = []
        self._running = False

        # ── Subsystem initialisation ──────────────────────────────────────

        # AdaptivePulseController
        if _PULSE_AVAILABLE:
            self.pulse = AdaptivePulseController(
                global_baseline=self.config.baseline_pulse_interval,
            )
            self.pulse.register(
                f"{self.config.service_name}.health_loop",
                baseline_interval=self.config.repair_eval_interval,
                min_interval=5.0,
            )
            logger.info(
                "AdaptivePulseController ready for %s",
                sanitize_for_log(self.config.service_name),
            )
        else:
            self.pulse = None
            logger.warning("AdaptivePulseController not available — pulse control disabled")

        # AnomalyDetector
        if _ANOMALY_AVAILABLE:
            self.anomaly_detector = AnomalyDetector(
                window_size=self.config.anomaly_window_size,
                z_threshold=self.config.anomaly_z_threshold,
                min_samples=self.config.anomaly_min_samples,
            )
            self.anomaly_detector.add_handler(self._on_anomaly)
        else:
            self.anomaly_detector = None

        # SelfRepairEngine + AdaptiveConfigTuner
        if _REPAIR_AVAILABLE:
            self.repair_engine = SelfRepairEngine()
            self.config_tuner = AdaptiveConfigTuner()
        else:
            self.repair_engine = None
            self.config_tuner = None

        # TelemetryCollector
        if _TELEMETRY_AVAILABLE:
            self.telemetry = TelemetryCollector.get_instance()
        else:
            self.telemetry = None

        # HotConfig
        if _HOTCONFIG_AVAILABLE and self.config.hotconfig_watch_paths:
            self.hot_config = HotConfig(watch_paths=self.config.hotconfig_watch_paths)
        else:
            self.hot_config = None

        # ForesightEngine
        if _FORESIGHT_AVAILABLE and self.config.foresight_enabled:
            self.foresight = ConversationTrajectoryPredictor()
        else:
            self.foresight = None

        # DefenseEngine
        if _DEFENSE_AVAILABLE and self.config.defense_enabled:
            self.defense = DefenseEngine()
        else:
            self.defense = None

        # ReactiveState for service topology
        if _REACTIVE_AVAILABLE:
            self.state_store = StateStore()
            self.health_state = self.state_store.create(
                f"{self.config.service_name}.health",
                {"score": 1.0, "tier": "optimal", "pulse_mode": "steady"},
            )
        else:
            self.state_store = None
            self.health_state = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def start(self, app=None) -> None:
        """Start all intelligence loops. Optionally mount telemetry middleware on a FastAPI app."""
        self._running = True

        # Mount telemetry middleware if FastAPI app provided
        if app is not None and _TELEMETRY_AVAILABLE and self.config.telemetry_enabled:
            try:
                app.add_middleware(TelemetryMiddleware)
                logger.info(
                    "TelemetryMiddleware mounted on %s",
                    sanitize_for_log(self.config.service_name),
                )
            except Exception as e:
                logger.warning("Could not mount TelemetryMiddleware: %s", sanitize_for_log(str(e)))

        # Start HotConfig watcher
        if self.hot_config:
            try:
                await self.hot_config.start()
            except Exception as e:
                logger.warning("HotConfig start failed: %s", sanitize_for_log(str(e)))

        # Start background intelligence loops
        self._loops = [
            asyncio.create_task(self._health_loop()),
            asyncio.create_task(self._repair_loop()),
        ]
        logger.info(
            "InfinityHealthOrchestrator started for %s (pulse=%s, anomaly=%s, repair=%s)",
            sanitize_for_log(self.config.service_name),
            _PULSE_AVAILABLE,
            _ANOMALY_AVAILABLE,
            _REPAIR_AVAILABLE,
        )

    async def stop(self) -> None:
        """Stop all intelligence loops gracefully."""
        self._running = False
        if self.hot_config:
            await self.hot_config.stop()
        for task in self._loops:
            task.cancel()
        self._loops.clear()
        logger.info(
            "InfinityHealthOrchestrator stopped for %s",
            sanitize_for_log(self.config.service_name),
        )

    # ── Daemon Registration ───────────────────────────────────────────────────

    def register_daemon(
        self,
        name: str,
        baseline_interval: float = 30.0,
        min_interval: float = 1.0,
        max_interval: float = 300.0,
    ) -> None:
        """Register a daemon task for adaptive pulse control."""
        if self.pulse:
            self.pulse.register(
                name,
                baseline_interval=baseline_interval,
                min_interval=min_interval,
                max_interval=max_interval,
            )

    def should_fire(self, daemon_name: str) -> bool:
        """Check if a daemon should fire now (based on pulse interval)."""
        if self.pulse:
            return self.pulse.should_fire(daemon_name)
        return True  # Always fire if pulse unavailable

    def record_fire(self, daemon_name: str) -> None:
        """Record that a daemon fired."""
        if self.pulse:
            self.pulse.record_fire(daemon_name)

    # ── Metric Recording ─────────────────────────────────────────────────────

    def record_metric(self, name: str, value: float, *, feed_anomaly: bool = True) -> None:
        """
        Record a metric value.
        - Updates internal metric cache
        - Feeds to AnomalyDetector for z-score analysis
        - Feeds to AdaptiveConfigTuner for regression optimisation
        - Feeds to TelemetryCollector for Prometheus export
        """
        self._metric_cache[name] = value

        if feed_anomaly and self.anomaly_detector:
            try:
                self.anomaly_detector.record(name, value)
            except Exception as e:
                logger.debug("Anomaly record error: %s", sanitize_for_log(str(e)))

        if self.config_tuner:
            try:
                self.config_tuner.record_metric(name, value)
            except Exception as e:
                logger.debug("Config tuner record error: %s", sanitize_for_log(str(e)))

        if self.telemetry:
            try:
                self.telemetry.observe(name, value)
            except Exception as e:
                logger.debug("Telemetry observe error: %s", sanitize_for_log(str(e)))

    def record_request(
        self,
        latency_ms: float,
        status_code: int,
        method: str = "",
        path: str = "",
    ) -> None:
        """Record an HTTP request metric."""
        is_error = status_code >= 400
        if self.telemetry:
            self.telemetry.record_request(
                latency_ms=latency_ms,
                status_code=status_code,
                method=method,
                path=path,
                is_error=is_error,
            )
        self.record_metric("request_latency_ms", latency_ms, feed_anomaly=True)
        if is_error:
            self.record_metric(
                "error_count",
                self._metric_cache.get("error_count", 0) + 1,
                feed_anomaly=False,
            )

    # ── Health Score ──────────────────────────────────────────────────────────

    def update_health(self, score: float, reason: str = "") -> None:
        """
        Update system health score (0.0–1.0).
        Feeds AdaptivePulseController → adjusts all daemon intervals.
        Publishes to Sentinel Station if configured.
        Updates ReactiveState for live topology subscribers.
        """
        score = max(0.0, min(1.0, score))
        self._health_score = score
        self._health_history.append((time.time(), score))
        if len(self._health_history) > self.config.health_history_size:
            self._health_history = self._health_history[-self.config.health_history_size :]

        # Feed pulse controller
        if self.pulse:
            self.pulse.update(score, reason=reason or f"{self.config.service_name}.health_update")

        # Update reactive state
        tier_label, tier_icon = HealthTier.classify(score)
        if self.health_state and _REACTIVE_AVAILABLE:
            asyncio.get_event_loop().call_soon_threadsafe(
                asyncio.ensure_future,
                self.health_state.set(
                    {
                        "score": round(score, 4),
                        "tier": tier_label,
                        "tier_icon": tier_icon,
                        "pulse_mode": self.pulse.current_mode.value if self.pulse else "unknown",
                        "reason": reason,
                    },
                ),
            )

        # Publish to Sentinel Station
        if self.config.sentinel_publish_fn and score < 0.7:
            try:
                asyncio.get_event_loop().call_soon_threadsafe(
                    asyncio.ensure_future,
                    self._publish_health_event(score, tier_label, reason),
                )
            except Exception as e:
                logger.debug("Sentinel health publish error: %s", sanitize_for_log(str(e)))

    async def _publish_health_event(self, score: float, tier: str, reason: str) -> None:
        """Publish a health degradation event to Sentinel Station."""
        if self.config.sentinel_publish_fn:
            try:
                await self.config.sentinel_publish_fn(
                    "system_health",
                    {
                        "service": self.config.service_name,
                        "health_score": score,
                        "health_tier": tier,
                        "reason": reason,
                        "timestamp": time.time(),
                    },
                )
            except Exception as e:
                logger.debug("Sentinel publish failed: %s", sanitize_for_log(str(e)))

    # ── Anomaly Handling ──────────────────────────────────────────────────────

    def _on_anomaly(self, anomaly) -> None:
        """Callback invoked when AnomalyDetector identifies an anomaly."""
        self._anomaly_count += 1
        logger.warning(
            "Anomaly detected on %s.%s: value=%.4f severity=%s",
            sanitize_for_log(self.config.service_name),
            sanitize_for_log(getattr(anomaly, "metric_name", "unknown")),
            getattr(anomaly, "value", 0.0),
            sanitize_for_log(getattr(anomaly, "severity", "unknown")),
        )

        # Degrade health score on anomaly
        severity = getattr(anomaly, "severity", "low")
        penalty = {"low": 0.05, "medium": 0.15, "high": 0.25, "critical": 0.4}.get(severity, 0.05)
        new_score = max(0.0, self._health_score - penalty)
        self.update_health(
            new_score,
            reason=f"anomaly:{getattr(anomaly, 'metric_name', 'unknown')}",
        )

        # Publish to Sentinel security channel for critical anomalies
        if severity in ("high", "critical") and self.config.sentinel_publish_fn:
            asyncio.get_event_loop().call_soon_threadsafe(
                asyncio.ensure_future,
                self.config.sentinel_publish_fn(
                    "anomaly_detected",
                    {
                        "service": self.config.service_name,
                        "metric": getattr(anomaly, "metric_name", "unknown"),
                        "severity": severity,
                        "value": getattr(anomaly, "value", 0.0),
                        "timestamp": time.time(),
                    },
                ),
            )

    # ── Background Loops ──────────────────────────────────────────────────────

    async def _health_loop(self) -> None:
        """Continuous health aggregation loop."""
        while self._running:
            try:
                await asyncio.sleep(10.0)  # Base interval; pulse adjusts internally

                # Aggregate health from available subsystems
                scores = []

                # Error rate contribution
                if self.telemetry:
                    error_rate = self.telemetry.get_error_rate()
                    scores.append(max(0.0, 1.0 - error_rate * 2))

                # Anomaly-based contribution
                if self._anomaly_count > 0:
                    # Recover gradually
                    anomaly_penalty = min(1.0, self._anomaly_count * 0.05)
                    scores.append(max(0.0, 1.0 - anomaly_penalty))
                    self._anomaly_count = max(0, self._anomaly_count - 1)  # decay

                # Default: use current score if no other signals
                if not scores:
                    scores.append(self._health_score)

                new_score = sum(scores) / len(scores)
                self.update_health(new_score, reason="health_loop_aggregate")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Health loop error: %s", sanitize_for_log(str(e)))

    async def _repair_loop(self) -> None:
        """Autonomous self-repair evaluation loop."""
        while self._running:
            try:
                interval = 60.0
                if self.pulse:
                    interval = self.pulse.get_interval(f"{self.config.service_name}.health_loop")
                await asyncio.sleep(interval)

                if self.repair_engine and self._health_score < 0.8:
                    context = {
                        "service_id": self.config.service_name,
                        "error_rate": self._metric_cache.get("error_rate", 0.0),
                        "memory_percent": self._metric_cache.get("memory_percent", 0.0),
                        "queue_depth": int(self._metric_cache.get("queue_depth", 0)),
                        "prediction_confidence": self._health_score,
                        **self._metric_cache,
                    }

                    results = await self.repair_engine.evaluate_and_repair(context)
                    if results:
                        self._repair_count += len(results)
                        successful = [r for r in results if r.get("success")]
                        if successful:
                            # Health improvement from successful repairs
                            improvement = min(0.2, len(successful) * 0.05)
                            self.update_health(
                                min(1.0, self._health_score + improvement),
                                reason=f"repair:{','.join(r['strategy'] for r in successful)}",
                            )

                # Adaptive config tuning
                if self.config_tuner and self._health_score > 0.6:
                    try:
                        await self.config_tuner.tune()
                    except Exception as e:
                        logger.debug("Config tuner error: %s", sanitize_for_log(str(e)))

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("Repair loop error: %s", sanitize_for_log(str(e)))

    # ── Query Interface ───────────────────────────────────────────────────────

    def get_health_summary(self) -> HealthSummary:
        """Get a comprehensive health summary for API responses."""
        tier_label, tier_icon = HealthTier.classify(self._health_score)
        pulse_mode = "unknown"
        if self.pulse:
            pulse_mode = self.pulse.current_mode.value

        foresight_data: Dict[str, Any] = {}
        if self.foresight:
            try:
                # Use service name as session proxy for system-level prediction
                traj = self.foresight.predict_trajectory(self.config.service_name)
                top = traj.top(3) if hasattr(traj, "top") else []
                foresight_data = {
                    "top_trajectories": [(t, round(p, 4)) for t, p in top],
                    "confidence": round(traj.confidence(), 4)
                    if hasattr(traj, "confidence")
                    else 0.0,
                    "entropy": round(traj.entropy(), 4) if hasattr(traj, "entropy") else 0.0,
                }
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        return HealthSummary(
            service_name=self.config.service_name,
            score=round(self._health_score, 4),
            tier=tier_label,
            tier_icon=tier_icon,
            pulse_mode=pulse_mode,
            anomalies_detected=self._anomaly_count,
            repairs_applied=self._repair_count,
            metrics=dict(self._metric_cache),
            foresight=foresight_data,
            uptime_seconds=time.time() - self._start_time,
        )

    def get_prometheus_metrics(self) -> str:
        """Export all metrics in Prometheus exposition format."""
        if self.telemetry and hasattr(self.telemetry, "to_prometheus"):
            return self.telemetry.to_prometheus()
        # Minimal fallback
        svc = self.config.service_name
        lines = [
            "# TYPE infinity_health_score gauge",
            f'infinity_health_score{{service="{svc}"}} {self._health_score:.4f}',
            "# TYPE infinity_anomaly_count counter",
            f'infinity_anomaly_count{{service="{svc}"}} {self._anomaly_count}',
            "# TYPE infinity_repair_count counter",
            f'infinity_repair_count{{service="{svc}"}} {self._repair_count}',
            "# TYPE infinity_uptime_seconds gauge",
            f'infinity_uptime_seconds{{service="{svc}"}} {time.time() - self._start_time:.1f}',
        ]
        return "\n".join(lines) + "\n"

    def get_pulse_stats(self) -> Dict[str, Any]:
        """Get AdaptivePulseController statistics."""
        if self.pulse:
            return self.pulse.get_stats()
        return {"available": False}

    def get_defense_incidents(self) -> List[Dict[str, Any]]:
        """Get active security incidents from DefenseEngine."""
        if self.defense and hasattr(self.defense, "list_incidents"):
            try:
                incidents = self.defense.list_incidents()
                return [i.to_dict() if hasattr(i, "to_dict") else i for i in incidents]
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)
        return []


# ── Factory helper ────────────────────────────────────────────────────────────


def create_orchestrator(
    service_name: str,
    *,
    sentinel_publish_fn: Optional[Callable] = None,
    baseline_pulse_interval: float = 30.0,
    **kwargs: Any,
) -> InfinityHealthOrchestrator:
    """
    Factory function to create an InfinityHealthOrchestrator with standard defaults.

    Usage:
        orchestrator = create_orchestrator("infinity-portal", sentinel_publish_fn=station.publish)
        await orchestrator.start(app)
    """
    cfg = AIConfig(
        service_name=service_name,
        baseline_pulse_interval=baseline_pulse_interval,
        sentinel_publish_fn=sentinel_publish_fn,
        **kwargs,
    )
    return InfinityHealthOrchestrator(cfg)


# ── Availability Report ───────────────────────────────────────────────────────

SUBSYSTEM_AVAILABILITY = {
    "adaptive_pulse": _PULSE_AVAILABLE,
    "anomaly_detector": _ANOMALY_AVAILABLE,
    "self_repair": _REPAIR_AVAILABLE,
    "reactive_state": _REACTIVE_AVAILABLE,
    "hot_config": _HOTCONFIG_AVAILABLE,
    "telemetry": _TELEMETRY_AVAILABLE,
    "foresight": _FORESIGHT_AVAILABLE,
    "defense_engine": _DEFENSE_AVAILABLE,
}
