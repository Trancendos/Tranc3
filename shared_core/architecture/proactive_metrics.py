"""
shared_core.architecture.proactive_metrics — Unified Observability & Metrics for Tranc3.

The ProactiveMetricsCollector provides a single unified view of system health
across all intelligent subsystems. It collects, aggregates, and exports metrics
from the ProactiveOrchestrator, AdaptivePulseController, AutoConfigManager,
PredictiveAutoscaler, and all wired subsystems.

Key Features:
    - Unified metrics collection from all subsystems
    - Real-time composite system health dashboard (SystemVitals)
    - Prometheus-compatible metrics export
    - Health trend tracking and anomaly detection
    - Zero-cost compliance metrics
    - Action success/failure tracking
    - Pulse mode distribution tracking

Universal ID Taxonomy:
    PID (Product/Location ID)  — identifies locations/products in the 8 pillars
    AID (AI ID)                — identifies AI entities (e.g., tAImra Lead AI)
    SID (Service/Agent ID)     — identifies services and agents
    NID (Nano-ID/Bot ID)       — identifies nanoservice bots

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │               ProactiveMetricsCollector                       │
    │                                                              │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
    │  │ System   │  │Subsystem │  │ Action   │  │ Zero-Cost│    │
    │  │ Vitals   │  │ Metrics  │  │ Metrics  │  │ Metrics  │    │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘    │
    │       │              │             │              │          │
    │  ┌────┴──────────────┴─────────────┴──────────────┴────┐    │
    │  │              Aggregation & Trend Analysis            │    │
    │  └────┬──────────────┬─────────────┬──────────────┬────┘    │
    │       │              │             │              │          │
    │  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐  ┌────┴─────┐   │
    │  │Prometheus│  │ Dashboard│  │  Alert   │  │  Health  │   │
    │  │  Export  │  │   API    │  │  Rules   │  │ History  │   │
    │  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
    └──────────────────────────────────────────────────────────────┘
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_METRICS_HISTORY_SIZE = 1440  # 24h at 1-minute intervals
_VITALS_SNAPSHOT_INTERVAL = 60.0  # seconds between vitals snapshots
_PROMETHEUS_PREFIX = "tranc3_proactive_"


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class MetricType(str, Enum):
    """Type of metric being collected."""

    GAUGE = "gauge"
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"


class HealthTrend(str, Enum):
    """Trend direction for a health metric."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------


@dataclass
class SubsystemMetrics:
    """Metrics snapshot for a single subsystem."""

    name: str
    health_score: float = 0.0
    status: str = "unknown"
    events_processed: int = 0
    actions_dispatched: int = 0
    errors: int = 0
    uptime_seconds: float = 0.0
    last_activity: Optional[float] = None
    custom_metrics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "health_score": round(self.health_score, 4),
            "status": self.status,
            "events_processed": self.events_processed,
            "actions_dispatched": self.actions_dispatched,
            "errors": self.errors,
            "uptime_seconds": round(self.uptime_seconds, 2),
            "last_activity": self.last_activity,
            "custom_metrics": self.custom_metrics,
        }


@dataclass
class SystemVitals:
    """Real-time composite system health dashboard.

    Aggregates health across all subsystems into a single composite score
    with per-subsystem breakdowns, trend analysis, and zero-cost compliance.
    """

    timestamp: float = field(default_factory=time.time)
    composite_health: float = 0.0
    subsystem_health: Dict[str, float] = field(default_factory=dict)
    health_trend: HealthTrend = HealthTrend.UNKNOWN
    orchestrator_mode: str = "observe"
    pulse_mode: str = "steady"
    zero_cost_compliant: bool = True
    active_actions: int = 0
    pending_actions: int = 0
    healing_active: int = 0
    scaling_direction: str = "maintain"
    storage_tiers_healthy: int = 0
    storage_tiers_total: int = 0
    services_healthy: int = 0
    services_total: int = 0
    circuits_open: int = 0
    circuits_total: int = 0
    threat_level: str = "low"
    config_profile: str = "unknown"
    predictions_degrading: int = 0
    uptime_seconds: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "composite_health": round(self.composite_health, 4),
            "subsystem_health": {k: round(v, 4) for k, v in self.subsystem_health.items()},
            "health_trend": self.health_trend.value,
            "orchestrator_mode": self.orchestrator_mode,
            "pulse_mode": self.pulse_mode,
            "zero_cost_compliant": self.zero_cost_compliant,
            "active_actions": self.active_actions,
            "pending_actions": self.pending_actions,
            "healing_active": self.healing_active,
            "scaling_direction": self.scaling_direction,
            "storage_tiers_healthy": self.storage_tiers_healthy,
            "storage_tiers_total": self.storage_tiers_total,
            "services_healthy": self.services_healthy,
            "services_total": self.services_total,
            "circuits_open": self.circuits_open,
            "circuits_total": self.circuits_total,
            "threat_level": self.threat_level,
            "config_profile": self.config_profile,
            "predictions_degrading": self.predictions_degrading,
            "uptime_seconds": round(self.uptime_seconds, 2),
        }


@dataclass
class MetricsSnapshot:
    """A point-in-time snapshot of all proactive system metrics."""

    timestamp: float = field(default_factory=time.time)
    vitals: SystemVitals = field(default_factory=SystemVitals)
    subsystems: Dict[str, SubsystemMetrics] = field(default_factory=dict)
    action_stats: Dict[str, int] = field(default_factory=dict)
    zero_cost_details: Dict[str, Any] = field(default_factory=dict)
    pulse_details: Dict[str, Any] = field(default_factory=dict)
    scaler_details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "vitals": self.vitals.to_dict(),
            "subsystems": {k: v.to_dict() for k, v in self.subsystems.items()},
            "action_stats": self.action_stats,
            "zero_cost_details": self.zero_cost_details,
            "pulse_details": self.pulse_details,
            "scaler_details": self.scaler_details,
        }


# ---------------------------------------------------------------------------
# Proactive Metrics Collector
# ---------------------------------------------------------------------------


class ProactiveMetricsCollector:
    """Unified metrics collector for the Tranc3 proactive system.

    Collects, aggregates, and exports metrics from all intelligent subsystems.
    Provides real-time system vitals, historical trend analysis, and
    Prometheus-compatible metric export.

    Usage:
        collector = ProactiveMetricsCollector()
        collector.attach_orchestrator(proactive_orchestrator)
        collector.attach_pulse(adaptive_pulse)
        collector.attach_config(auto_config)
        collector.attach_scaler(predictive_scaler)
        collector.attach_bootstrap(proactive_bootstrap)

        # Collect a snapshot
        snapshot = collector.collect()

        # Get Prometheus-format metrics
        prom_metrics = collector.export_prometheus()

        # Get the real-time dashboard
        vitals = collector.get_vitals()
    """

    def __init__(
        self,
        history_size: int = _METRICS_HISTORY_SIZE,
        snapshot_interval: float = _VITALS_SNAPSHOT_INTERVAL,
        prometheus_prefix: str = _PROMETHEUS_PREFIX,
    ) -> None:
        self._history_size = history_size
        self._snapshot_interval = snapshot_interval
        self._prometheus_prefix = prometheus_prefix

        # Subsystem references
        self._orchestrator: Any = None
        self._pulse: Any = None
        self._config: Any = None
        self._scaler: Any = None
        self._bootstrap: Any = None

        # Metrics storage
        self._vitals_history: deque = deque(maxlen=history_size)
        self._snapshot_history: deque = deque(maxlen=history_size)
        self._last_snapshot_time: float = 0.0
        self._start_time: float = time.time()

        # Counters
        self._collections: int = 0
        self._export_errors: int = 0

        # Custom metric collectors
        self._custom_collectors: Dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Attachment
    # ------------------------------------------------------------------

    def attach_orchestrator(self, orchestrator: Any) -> None:
        """Attach the ProactiveOrchestrator for metric collection."""
        self._orchestrator = orchestrator
        logger.info("ProactiveMetricsCollector: Orchestrator attached")

    def attach_pulse(self, pulse: Any) -> None:
        """Attach the AdaptivePulseController for metric collection."""
        self._pulse = pulse
        logger.info("ProactiveMetricsCollector: Pulse controller attached")

    def attach_config(self, config: Any) -> None:
        """Attach the AutoConfigManager for metric collection."""
        self._config = config
        logger.info("ProactiveMetricsCollector: Config manager attached")

    def attach_scaler(self, scaler: Any) -> None:
        """Attach the PredictiveAutoscaler for metric collection."""
        self._scaler = scaler
        logger.info("ProactiveMetricsCollector: Scaler attached")

    def attach_bootstrap(self, bootstrap: Any) -> None:
        """Attach the ProactiveSystemBootstrap for metric collection."""
        self._bootstrap = bootstrap
        logger.info("ProactiveMetricsCollector: Bootstrap attached")

    def register_custom_collector(self, name: str, collector: Callable) -> None:
        """Register a custom metric collector function.

        The collector function should return a Dict[str, Any] of metrics.
        """
        self._custom_collectors[name] = collector
        logger.info(
            "ProactiveMetricsCollector: Custom collector registered: %s",
            sanitize_for_log(name),
        )

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def collect(self) -> MetricsSnapshot:
        """Collect a comprehensive metrics snapshot from all subsystems."""
        now = time.time()
        self._collections += 1

        # Collect vitals
        vitals = self._collect_vitals(now)

        # Collect subsystem metrics
        subsystems = self._collect_subsystem_metrics()

        # Collect action stats
        action_stats = self._collect_action_stats()

        # Collect zero-cost details
        zero_cost_details = self._collect_zero_cost_details()

        # Collect pulse details
        pulse_details = self._collect_pulse_details()

        # Collect scaler details
        scaler_details = self._collect_scaler_details()

        # Create snapshot
        snapshot = MetricsSnapshot(
            timestamp=now,
            vitals=vitals,
            subsystems=subsystems,
            action_stats=action_stats,
            zero_cost_details=zero_cost_details,
            pulse_details=pulse_details,
            scaler_details=scaler_details,
        )

        # Store in history
        self._vitals_history.append(vitals)
        self._snapshot_history.append(snapshot)
        self._last_snapshot_time = now

        return snapshot

    def get_vitals(self) -> SystemVitals:
        """Get the current system vitals (collects if stale)."""
        now = time.time()
        if not self._vitals_history or (now - self._last_snapshot_time) > self._snapshot_interval:
            snapshot = self.collect()
            return snapshot.vitals
        return self._vitals_history[-1]

    # ------------------------------------------------------------------
    # Internal Collection Methods
    # ------------------------------------------------------------------

    def _collect_vitals(self, now: float) -> SystemVitals:
        """Collect the composite system vitals."""
        vitals = SystemVitals(timestamp=now)
        vitals.uptime_seconds = now - self._start_time

        # Orchestrator-derived vitals
        if self._orchestrator:
            try:
                # Health profile
                if hasattr(self._orchestrator, "get_health_profile"):
                    hp = self._orchestrator.get_health_profile()
                    if hasattr(hp, "to_dict"):
                        hp_dict = hp.to_dict()
                        vitals.composite_health = hp_dict.get("composite_score", 0.0)
                        vitals.subsystem_health = hp_dict.get("subsystem_scores", {})

                # Orchestrator mode
                if hasattr(self._orchestrator, "mode"):
                    vitals.orchestrator_mode = self._orchestrator.mode.value

                # Action counts
                if hasattr(self._orchestrator, "get_stats"):
                    stats = self._orchestrator.get_stats()
                    vitals.active_actions = stats.get("active_actions", 0)
                    vitals.pending_actions = stats.get("pending_actions", 0)
                    vitals.healing_active = stats.get("active_heals", 0)

                # Predictions
                if hasattr(self._orchestrator, "get_predictions"):
                    predictions = self._orchestrator.get_predictions()
                    vitals.predictions_degrading = len(
                        [p for p in predictions if getattr(p, "trend", "") == "degrading"]
                    )

                # Zero-cost
                if hasattr(self._orchestrator, "get_zero_cost_status"):
                    zc = self._orchestrator.get_zero_cost_status()
                    if hasattr(zc, "to_dict"):
                        zc_dict = zc.to_dict()
                        vitals.zero_cost_compliant = zc_dict.get("compliant", True)

            except Exception as e:
                logger.debug(
                    "ProactiveMetricsCollector: Error collecting orchestrator vitals: %s",
                    sanitize_for_log(str(e)),
                )

        # Pulse-derived vitals
        if self._pulse:
            try:
                if hasattr(self._pulse, "get_metrics"):
                    pulse_metrics = self._pulse.get_metrics()
                    if isinstance(pulse_metrics, dict):
                        vitals.pulse_mode = pulse_metrics.get("current_mode", "steady")
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # Config-derived vitals
        if self._config:
            try:
                if hasattr(self._config, "get_active_profile"):
                    profile = self._config.get_active_profile()
                    vitals.config_profile = str(profile) if profile else "unknown"
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # Scaler-derived vitals
        if self._scaler:
            try:
                if hasattr(self._scaler, "get_all_decisions"):
                    decisions = self._scaler.get_all_decisions()
                    if decisions:
                        latest = decisions[-1] if isinstance(decisions, list) else decisions
                        if hasattr(latest, "direction"):
                            vitals.scaling_direction = latest.direction.value
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # Bootstrap-derived vitals
        if self._bootstrap:
            try:
                if hasattr(self._bootstrap, "get_status"):
                    status = self._bootstrap.get_status()
                    bridges = status.get("bridges", {})
                    # Count storage tiers
                    storage_bridge = bridges.get("storage", {})
                    if storage_bridge.get("status") in ("connected", "active"):
                        vitals.storage_tiers_healthy = status.get(
                            "subsystems_connected",
                            0,
                        )
                        vitals.storage_tiers_total = status.get(
                            "subsystems_total",
                            0,
                        )
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # Determine health trend from history
        vitals.health_trend = self._compute_health_trend()

        return vitals

    def _collect_subsystem_metrics(self) -> Dict[str, SubsystemMetrics]:
        """Collect metrics from each wired subsystem."""
        metrics: Dict[str, SubsystemMetrics] = {}

        # From bootstrap bridge status
        if self._bootstrap and hasattr(self._bootstrap, "get_status"):
            try:
                status = self._bootstrap.get_status()
                for bridge_type, bridge_data in status.get("bridges", {}).items():
                    name = bridge_data.get("subsystem_name", bridge_type)
                    metrics[bridge_type] = SubsystemMetrics(
                        name=name,
                        status=bridge_data.get("status", "unknown"),
                        events_processed=bridge_data.get("events_processed", 0),
                        actions_dispatched=bridge_data.get("actions_dispatched", 0),
                        errors=bridge_data.get("errors", 0),
                        last_activity=bridge_data.get("last_activity"),
                    )
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        # From individual subsystem stats
        subsystem_map = {
            "storage": self._orchestrator and getattr(self._orchestrator, "_storage", None),
            "sentinel": self._orchestrator and getattr(self._orchestrator, "_sentinel", None),
            "defense": self._orchestrator and getattr(self._orchestrator, "_defense", None),
            "foresight": self._orchestrator and getattr(self._orchestrator, "_foresight", None),
            "router": self._orchestrator and getattr(self._orchestrator, "_router", None),
            "registry": self._orchestrator and getattr(self._orchestrator, "_registry", None),
            "resilience": self._orchestrator and getattr(self._orchestrator, "_resilience", None),
        }

        for name, subsystem in subsystem_map.items():
            if subsystem is None:
                continue
            try:
                if hasattr(subsystem, "stats"):
                    stats = subsystem.stats()
                    if name in metrics:
                        metrics[name].custom_metrics = stats
                    else:
                        metrics[name] = SubsystemMetrics(
                            name=name,
                            status="active",
                            custom_metrics=stats,
                        )
                elif hasattr(subsystem, "get_stats"):
                    stats = subsystem.get_stats()
                    if name in metrics:
                        metrics[name].custom_metrics = stats
                    else:
                        metrics[name] = SubsystemMetrics(
                            name=name,
                            status="active",
                            custom_metrics=stats,
                        )
            except Exception as _exc:
                logger.debug("suppressed %s", _exc, exc_info=False)

        return metrics

    def _collect_action_stats(self) -> Dict[str, int]:
        """Collect action dispatcher statistics."""
        if not self._orchestrator:
            return {}

        try:
            if hasattr(self._orchestrator, "get_stats"):
                stats = self._orchestrator.get_stats()
                return {
                    "total_actions": stats.get("total_actions", 0),
                    "completed_actions": stats.get("completed_actions", 0),
                    "failed_actions": stats.get("failed_actions", 0),
                    "pending_actions": stats.get("pending_actions", 0),
                    "active_actions": stats.get("active_actions", 0),
                    "active_heals": stats.get("active_heals", 0),
                    "migrations_triggered": stats.get("migrations_triggered", 0),
                }
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)

        return {}

    def _collect_zero_cost_details(self) -> Dict[str, Any]:
        """Collect zero-cost compliance details."""
        if not self._orchestrator:
            return {}

        try:
            if hasattr(self._orchestrator, "get_zero_cost_status"):
                zc = self._orchestrator.get_zero_cost_status()
                if hasattr(zc, "to_dict"):
                    return zc.to_dict()
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)

        return {"compliant": True, "details": "no_data"}

    def _collect_pulse_details(self) -> Dict[str, Any]:
        """Collect adaptive pulse controller details."""
        if not self._pulse:
            return {}

        try:
            details: Dict[str, Any] = {}
            if hasattr(self._pulse, "get_metrics"):
                details["metrics"] = self._pulse.get_metrics()
            if hasattr(self._pulse, "get_all_intervals"):
                details["intervals"] = self._pulse.get_all_intervals()
            return details
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)

        return {}

    def _collect_scaler_details(self) -> Dict[str, Any]:
        """Collect predictive autoscaler details."""
        if not self._scaler:
            return {}

        try:
            details: Dict[str, Any] = {}
            if hasattr(self._scaler, "get_all_decisions"):
                details["decisions"] = self._scaler.get_all_decisions()
            if hasattr(self._scaler, "get_stats"):
                details["stats"] = self._scaler.get_stats()
            return details
        except Exception as _exc:
            logger.debug("suppressed %s", _exc, exc_info=False)

        return {}

    # ------------------------------------------------------------------
    # Health Trend Computation
    # ------------------------------------------------------------------

    def _compute_health_trend(self) -> HealthTrend:
        """Compute the overall health trend from recent vitals history."""
        if len(self._vitals_history) < 3:
            return HealthTrend.UNKNOWN

        # Get the last 3 composite health scores
        recent_scores = [v.composite_health for v in list(self._vitals_history)[-3:]]

        # Check for consistent degradation
        if all(s < 0.4 for s in recent_scores):
            return HealthTrend.CRITICAL

        # Check for downward trend
        if recent_scores[-1] < recent_scores[0] - 0.05:
            if recent_scores[-1] < 0.6:
                return HealthTrend.DEGRADING
            return HealthTrend.STABLE  # Slight decline but still healthy

        # Check for upward trend
        if recent_scores[-1] > recent_scores[0] + 0.05:
            return HealthTrend.IMPROVING

        return HealthTrend.STABLE

    # ------------------------------------------------------------------
    # Prometheus Export
    # ------------------------------------------------------------------

    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus exposition format.

        Returns a string in Prometheus text format that can be served
        at a /metrics HTTP endpoint for Prometheus scraping.

        Format:
            # TYPE metric_name metric_type
            metric_name{label="value"} number
        """
        try:
            snapshot = self.collect()
            lines: List[str] = []

            # System vitals
            vitals = snapshot.vitals
            prefix = self._prometheus_prefix

            # Composite health
            lines.append(f"# TYPE {prefix}composite_health gauge")
            lines.append(f"{prefix}composite_health {vitals.composite_health:.4f}")

            # Health trend (as numeric: improving=1.0, stable=0.7, degrading=0.3, critical=0.1, unknown=0.5)
            trend_scores = {
                HealthTrend.IMPROVING: 1.0,
                HealthTrend.STABLE: 0.7,
                HealthTrend.UNKNOWN: 0.5,
                HealthTrend.DEGRADING: 0.3,
                HealthTrend.CRITICAL: 0.1,
            }
            lines.append(f"# TYPE {prefix}health_trend gauge")
            lines.append(
                f'{prefix}health_trend{{trend="{vitals.health_trend.value}"}} '
                f"{trend_scores.get(vitals.health_trend, 0.5):.2f}"
            )

            # Subsystem health scores
            lines.append(f"# TYPE {prefix}subsystem_health gauge")
            for name, score in vitals.subsystem_health.items():
                lines.append(f'{prefix}subsystem_health{{subsystem="{name}"}} {score:.4f}')

            # Orchestrator mode
            lines.append(f"# TYPE {prefix}orchestrator_mode gauge")
            mode_scores = {"observe": 0, "assist": 1, "autonomous": 2, "emergency": 3}
            lines.append(
                f'{prefix}orchestrator_mode{{mode="{vitals.orchestrator_mode}"}} '
                f"{mode_scores.get(vitals.orchestrator_mode, 0)}"
            )

            # Pulse mode
            lines.append(f"# TYPE {prefix}pulse_mode gauge")
            pulse_scores = {"steady": 0, "accelerated": 1, "emergency": 2, "recovery": 3}
            lines.append(
                f'{prefix}pulse_mode{{mode="{vitals.pulse_mode}"}} '
                f"{pulse_scores.get(vitals.pulse_mode, 0)}"
            )

            # Zero-cost compliance
            lines.append(f"# TYPE {prefix}zero_cost_compliant gauge")
            lines.append(
                f"{prefix}zero_cost_compliant {1.0 if vitals.zero_cost_compliant else 0.0}"
            )

            # Action counts
            lines.append(f"# TYPE {prefix}active_actions gauge")
            lines.append(f"{prefix}active_actions {vitals.active_actions}")

            lines.append(f"# TYPE {prefix}pending_actions gauge")
            lines.append(f"{prefix}pending_actions {vitals.pending_actions}")

            lines.append(f"# TYPE {prefix}healing_active gauge")
            lines.append(f"{prefix}healing_active {vitals.healing_active}")

            # Storage tier health
            lines.append(f"# TYPE {prefix}storage_tiers_healthy gauge")
            lines.append(f"{prefix}storage_tiers_healthy {vitals.storage_tiers_healthy}")

            lines.append(f"# TYPE {prefix}storage_tiers_total gauge")
            lines.append(f"{prefix}storage_tiers_total {vitals.storage_tiers_total}")

            # Service health
            lines.append(f"# TYPE {prefix}services_healthy gauge")
            lines.append(f"{prefix}services_healthy {vitals.services_healthy}")

            lines.append(f"# TYPE {prefix}services_total gauge")
            lines.append(f"{prefix}services_total {vitals.services_total}")

            # Circuit breaker
            lines.append(f"# TYPE {prefix}circuits_open gauge")
            lines.append(f"{prefix}circuits_open {vitals.circuits_open}")

            lines.append(f"# TYPE {prefix}circuits_total gauge")
            lines.append(f"{prefix}circuits_total {vitals.circuits_total}")

            # Threat level
            lines.append(f"# TYPE {prefix}threat_level gauge")
            threat_scores = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            lines.append(
                f'{prefix}threat_level{{level="{vitals.threat_level}"}} '
                f"{threat_scores.get(vitals.threat_level, 0)}"
            )

            # Predictions degrading
            lines.append(f"# TYPE {prefix}predictions_degrading gauge")
            lines.append(f"{prefix}predictions_degrading {vitals.predictions_degrading}")

            # Uptime
            lines.append(f"# TYPE {prefix}uptime_seconds counter")
            lines.append(f"{prefix}uptime_seconds {vitals.uptime_seconds:.2f}")

            # Scaling direction
            lines.append(f"# TYPE {prefix}scaling_direction gauge")
            scaling_scores = {"up": 1, "maintain": 0, "down": -1}
            lines.append(
                f'{prefix}scaling_direction{{direction="{vitals.scaling_direction}"}} '
                f"{scaling_scores.get(vitals.scaling_direction, 0)}"
            )

            # Subsystem-specific metrics
            for name, sub_metrics in snapshot.subsystems.items():
                lines.append(f"# TYPE {prefix}subsystem_events_total counter")
                lines.append(
                    f'{prefix}subsystem_events_total{{subsystem="{name}"}} '
                    f"{sub_metrics.events_processed}"
                )
                lines.append(f"# TYPE {prefix}subsystem_errors_total counter")
                lines.append(
                    f'{prefix}subsystem_errors_total{{subsystem="{name}"}} {sub_metrics.errors}'
                )

            # Action stats
            for action_name, count in snapshot.action_stats.items():
                lines.append(f"# TYPE {prefix}action_{action_name} counter")
                lines.append(f"{prefix}action_{action_name} {count}")

            # Zero-cost details
            zc = snapshot.zero_cost_details
            if isinstance(zc, dict):
                approaching = zc.get("approaching_limit", [])
                if isinstance(approaching, list):
                    lines.append(f"# TYPE {prefix}zero_cost_approaching_limit gauge")
                    lines.append(f"{prefix}zero_cost_approaching_limit {len(approaching)}")

                critical = zc.get("critical_tiers", [])
                if isinstance(critical, list):
                    lines.append(f"# TYPE {prefix}zero_cost_critical_tiers gauge")
                    lines.append(f"{prefix}zero_cost_critical_tiers {len(critical)}")

            # Collections counter
            lines.append(f"# TYPE {prefix}collections_total counter")
            lines.append(f"{prefix}collections_total {self._collections}")

            return "\n".join(lines) + "\n"

        except Exception as e:
            self._export_errors += 1
            logger.error(
                "ProactiveMetricsCollector: Prometheus export failed: %s",
                sanitize_for_log(str(e)),
            )
            return (
                f"# Export error: {sanitize_for_log(str(e))}\n"
                f"{self._prometheus_prefix}export_errors_total {self._export_errors}\n"
            )

    # ------------------------------------------------------------------
    # History & Trends
    # ------------------------------------------------------------------

    def get_vitals_history(
        self,
        duration_seconds: Optional[float] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Get historical vitals snapshots.

        Args:
            duration_seconds: Only return vitals from the last N seconds
            limit: Maximum number of snapshots to return
        """
        history = list(self._vitals_history)

        if duration_seconds is not None:
            cutoff = time.time() - duration_seconds
            history = [v for v in history if v.timestamp >= cutoff]

        if limit is not None:
            history = history[-limit:]

        return [v.to_dict() for v in history]

    def get_health_timeline(
        self,
        duration_seconds: float = 3600.0,
    ) -> List[Tuple[float, float]]:
        """Get a timeline of composite health scores.

        Returns:
            List of (timestamp, composite_health) tuples.
        """
        cutoff = time.time() - duration_seconds
        return [
            (v.timestamp, v.composite_health) for v in self._vitals_history if v.timestamp >= cutoff
        ]

    def get_subsystem_health_timeline(
        self,
        subsystem: str,
        duration_seconds: float = 3600.0,
    ) -> List[Tuple[float, float]]:
        """Get a timeline of health scores for a specific subsystem.

        Args:
            subsystem: Subsystem name (e.g., "storage", "service", "security")
            duration_seconds: Time range to cover
        """
        cutoff = time.time() - duration_seconds
        return [
            (v.timestamp, v.subsystem_health.get(subsystem, 0.0))
            for v in self._vitals_history
            if v.timestamp >= cutoff
        ]

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def get_stats(self) -> Dict[str, Any]:
        """Get metrics collector statistics."""
        return {
            "collections": self._collections,
            "export_errors": self._export_errors,
            "history_size": len(self._vitals_history),
            "history_capacity": self._history_size,
            "custom_collectors": list(self._custom_collectors.keys()),
            "last_snapshot_time": self._last_snapshot_time,
            "uptime_seconds": time.time() - self._start_time,
            "subsystems_attached": {
                "orchestrator": self._orchestrator is not None,
                "pulse": self._pulse is not None,
                "config": self._config is not None,
                "scaler": self._scaler is not None,
                "bootstrap": self._bootstrap is not None,
            },
        }

    def get_dashboard(self) -> Dict[str, Any]:
        """Get a comprehensive dashboard of all proactive system metrics."""
        vitals = self.get_vitals()
        stats = self.get_stats()
        history = self.get_vitals_history(duration_seconds=300.0, limit=5)

        # Compute health summary
        health_summary = {
            "current": round(vitals.composite_health, 4),
            "trend": vitals.health_trend.value,
            "zero_cost_compliant": vitals.zero_cost_compliant,
            "mode": vitals.orchestrator_mode,
            "pulse": vitals.pulse_mode,
        }

        # Compute subsystem summary
        subsystem_summary = {}
        for name, score in vitals.subsystem_health.items():
            trend = HealthTrend.STABLE
            if len(self._vitals_history) >= 2:
                recent = list(self._vitals_history)[-2:]
                old_score = recent[0].subsystem_health.get(name, 0.5)
                new_score = recent[1].subsystem_health.get(name, 0.5)
                if new_score < old_score - 0.05:
                    trend = HealthTrend.DEGRADING
                elif new_score > old_score + 0.05:
                    trend = HealthTrend.IMPROVING
            subsystem_summary[name] = {
                "health": round(score, 4),
                "trend": trend.value,
                "status": "healthy" if score >= 0.7 else "degraded" if score >= 0.4 else "critical",
            }

        return {
            "health_summary": health_summary,
            "subsystem_summary": subsystem_summary,
            "vitals": vitals.to_dict(),
            "recent_history": history,
            "collector_stats": stats,
            "scaling_direction": vitals.scaling_direction,
            "threat_level": vitals.threat_level,
            "active_actions": vitals.active_actions,
            "healing_active": vitals.healing_active,
            "predictions_degrading": vitals.predictions_degrading,
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

proactive_metrics = ProactiveMetricsCollector()
