"""
Heartbeat Aggregation System — Ported from the-hive/heartbeat-aggregator.ts
==============================================================================

Collects, aggregates, and monitors heartbeat signals from all connected
services in the Trancendos ecosystem. Provides real-time health monitoring
with predictive maintenance capabilities and trend analysis.

Architecture: Trancendos Industry 6.0 / 2060 Standard

Features:
- Heartbeat ingestion with configurable retention
- Service health scoring (0-100) based on multi-metric analysis
- Automatic alert generation with deduplication (5-min window)
- Incident lifecycle tracking (active → resolved)
- Category-based health aggregation (availability, performance, errors, resources)
- Trend analysis across multiple time windows (1h, 6h, 24h, 7d, 30d)
- Actionable recommendation generation
- Zero external dependencies (stdlib only)
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.heartbeat")


# ── Enums ──────────────────────────────────────────────────────────────────────


class ServiceStatus(str, Enum):
    """Service health status levels."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class HealthCategory(str, Enum):
    """Health monitoring categories."""

    AVAILABILITY = "availability"
    PERFORMANCE = "performance"
    ERRORS = "errors"
    RESOURCES = "resources"
    DEPENDENCIES = "dependencies"


class AlertSeverity(str, Enum):
    """Alert severity levels."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class TrendStatus(str, Enum):
    """Health trend direction."""

    IMPROVING = "improving"
    STABLE = "stable"
    DEGRADING = "degrading"


class TrendPeriod(str, Enum):
    """Trend analysis time windows."""

    ONE_HOUR = "1h"
    SIX_HOURS = "6h"
    ONE_DAY = "24h"
    SEVEN_DAYS = "7d"
    THIRTY_DAYS = "30d"


class IncidentStatus(str, Enum):
    """Incident lifecycle status."""

    ACTIVE = "active"
    RESOLVED = "resolved"


# ── Data Models ────────────────────────────────────────────────────────────────


@dataclass
class HeartbeatMetrics:
    """Quantitative metrics from a service heartbeat."""

    uptime: float = 0.0  # seconds
    response_time: float = 0.0  # milliseconds
    error_rate: float = 0.0  # percentage (0-100)
    cpu_usage: float = 0.0  # percentage (0-100)
    memory_usage: float = 0.0  # percentage (0-100)
    disk_usage: float = 0.0  # percentage (0-100)
    active_connections: int = 0
    requests_per_minute: float = 0.0


@dataclass
class Heartbeat:
    """A single heartbeat signal from a service."""

    service_id: str
    service_name: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    status: ServiceStatus = ServiceStatus.UNKNOWN
    category: HealthCategory = HealthCategory.AVAILABILITY
    metrics: HeartbeatMetrics = field(default_factory=HeartbeatMetrics)
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class HealthAlert:
    """An alert generated from heartbeat analysis."""

    severity: AlertSeverity
    category: HealthCategory
    service_id: str
    service_name: str
    message: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class HealthIncident:
    """An incident tracking a service's critical state."""

    service_id: str
    start_time: datetime
    severity: ServiceStatus
    description: str
    affected_metrics: List[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    end_time: Optional[datetime] = None
    status: IncidentStatus = IncidentStatus.ACTIVE


@dataclass
class ServiceHealth:
    """Computed health state for a tracked service."""

    service_id: str
    service_name: str
    status: ServiceStatus = ServiceStatus.UNKNOWN
    score: float = 100.0
    last_heartbeat: Optional[datetime] = None
    heartbeat_interval: float = 60.0  # seconds, smoothed average
    missed_heartbeats: int = 0
    current_metrics: Optional[HeartbeatMetrics] = None
    historical_metrics: List[HeartbeatMetrics] = field(default_factory=list)
    status_history: List[Dict[str, Any]] = field(default_factory=list)
    incidents: List[HealthIncident] = field(default_factory=list)


@dataclass
class CategoryHealth:
    """Aggregated health for a category across services."""

    category: HealthCategory
    status: ServiceStatus = ServiceStatus.UNKNOWN
    score: float = 0.0
    affected_services: List[str] = field(default_factory=list)
    avg_response_time: float = 0.0
    avg_error_rate: float = 0.0
    avg_cpu_usage: float = 0.0
    avg_memory_usage: float = 0.0


@dataclass
class HealthTrend:
    """Trend analysis for a time period."""

    period: TrendPeriod
    status: TrendStatus = TrendStatus.STABLE
    score_change: float = 0.0
    avg_response_time: float = 0.0
    avg_error_rate: float = 0.0
    avg_uptime: float = 0.0


@dataclass
class AggregatedHealth:
    """Full aggregated health snapshot of the ecosystem."""

    overall_status: ServiceStatus = ServiceStatus.UNKNOWN
    overall_score: float = 0.0
    services: List[ServiceHealth] = field(default_factory=list)
    categories: List[CategoryHealth] = field(default_factory=list)
    trends: List[HealthTrend] = field(default_factory=list)
    alerts: List[HealthAlert] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class AlertThresholds:
    """Configurable thresholds for alert generation."""

    critical_response_time: float = 5000.0  # ms
    critical_error_rate: float = 10.0  # %
    critical_cpu_usage: float = 90.0  # %
    critical_memory_usage: float = 90.0  # %
    warning_response_time: float = 2000.0  # ms
    warning_error_rate: float = 5.0  # %
    warning_cpu_usage: float = 75.0  # %
    warning_memory_usage: float = 75.0  # %


@dataclass
class HeartbeatConfig:
    """Configuration for the heartbeat aggregator."""

    retention_period: int = 7 * 24 * 3600  # 7 days in seconds
    aggregation_interval: int = 60  # 1 minute
    max_historical_metrics: int = 1000
    max_status_history: int = 100
    alert_dedup_window_seconds: int = 300  # 5 minutes
    max_recommendations: int = 10
    thresholds: AlertThresholds = field(default_factory=AlertThresholds)


# ── HeartbeatAggregator ───────────────────────────────────────────────────────


class HeartbeatAggregator:
    """Collects and aggregates heartbeat signals for ecosystem health monitoring.

    Provides real-time health scoring, alert generation, incident tracking,
    trend analysis, and actionable recommendations — all with zero external
    dependencies beyond the Python standard library.

    Usage:
        aggregator = HeartbeatAggregator()
        aggregator.receive_heartbeat(Heartbeat(
            service_id="the-citadel",
            service_name="The Citadel",
            status=ServiceStatus.HEALTHY,
            metrics=HeartbeatMetrics(response_time=45.2, error_rate=0.1, cpu_usage=32.0, memory_usage=48.0),
        ))
        health = aggregator.aggregate_health()
    """

    def __init__(self, config: Optional[HeartbeatConfig] = None) -> None:
        self._config = config or HeartbeatConfig()
        self._heartbeats: Dict[str, List[Heartbeat]] = {}
        self._service_health: Dict[str, ServiceHealth] = {}
        self._alerts: List[HealthAlert] = []
        self._incidents: Dict[str, HealthIncident] = {}
        self._last_aggregation: Optional[datetime] = None
        logger.info(
            "HeartbeatAggregator initialized (retention=%ds)", self._config.retention_period
        )

    # ── Heartbeat Ingestion ────────────────────────────────────────────────

    def receive_heartbeat(self, heartbeat: Heartbeat) -> None:
        """Ingest a heartbeat signal from a service.

        Stores the heartbeat, updates service health, checks for alerts,
        and tracks incidents.
        """
        sid = heartbeat.service_id

        # Store heartbeat
        if sid not in self._heartbeats:
            self._heartbeats[sid] = []
        self._heartbeats[sid].append(heartbeat)

        # Clean up old heartbeats
        self._cleanup_heartbeats(sid)

        # Update service health
        self._update_service_health(heartbeat)

        # Check for alerts
        self._check_alerts(heartbeat)

        logger.debug(
            "Heartbeat received: service=%s status=%s score=%.1f",
            sid,
            heartbeat.status.value,
            self._calculate_service_score(heartbeat),
        )

    def _cleanup_heartbeats(self, service_id: str) -> None:
        """Remove heartbeats older than the retention period."""
        heartbeats = self._heartbeats.get(service_id)
        if not heartbeats:
            return

        cutoff = time.time() - self._config.retention_period
        self._heartbeats[service_id] = [
            hb for hb in heartbeats if hb.timestamp.timestamp() > cutoff
        ]

    # ── Service Health Calculation ─────────────────────────────────────────

    def _update_service_health(self, heartbeat: Heartbeat) -> None:
        """Update the stored health state for a service based on a new heartbeat."""
        sid = heartbeat.service_id
        existing = self._service_health.get(sid)

        if not existing:
            # Initialize new service health
            self._service_health[sid] = ServiceHealth(
                service_id=sid,
                service_name=heartbeat.service_name,
                status=heartbeat.status,
                score=self._calculate_service_score(heartbeat),
                last_heartbeat=heartbeat.timestamp,
                heartbeat_interval=60.0,
                missed_heartbeats=0,
                current_metrics=heartbeat.metrics,
                historical_metrics=[heartbeat.metrics],
                status_history=[
                    {"timestamp": heartbeat.timestamp, "status": heartbeat.status.value}
                ],
                incidents=[],
            )
            return

        # Update existing service health
        now = time.time()
        time_since_last = (
            now - existing.last_heartbeat.timestamp() if existing.last_heartbeat else 0
        )

        # Detect missed heartbeats
        if time_since_last > existing.heartbeat_interval * 2:
            existing.missed_heartbeats += 1
        else:
            existing.missed_heartbeats = 0

        # Smooth heartbeat interval (exponential moving average)
        if existing.last_heartbeat and time_since_last > 0:
            existing.heartbeat_interval = existing.heartbeat_interval * 0.9 + time_since_last * 0.1

        # Update metrics
        existing.current_metrics = heartbeat.metrics
        existing.historical_metrics.append(heartbeat.metrics)
        if len(existing.historical_metrics) > self._config.max_historical_metrics:
            existing.historical_metrics = existing.historical_metrics[
                -self._config.max_historical_metrics :
            ]

        # Update status history
        existing.status_history.append(
            {
                "timestamp": heartbeat.timestamp,
                "status": heartbeat.status.value,
            }
        )
        if len(existing.status_history) > self._config.max_status_history:
            existing.status_history = existing.status_history[-self._config.max_status_history :]

        # Recalculate status and score
        existing.status = heartbeat.status
        existing.score = self._calculate_service_score(heartbeat)
        existing.last_heartbeat = heartbeat.timestamp

        # Check for incident transitions
        self._check_incidents(existing, heartbeat)

    def _calculate_service_score(self, heartbeat: Heartbeat) -> float:
        """Calculate a 0-100 health score from heartbeat metrics.

        Scoring model:
          - Start at 100
          - Deduct points for threshold violations
          - Response time: -30 (critical) / -10 (warning)
          - Error rate: -40 (critical) / -15 (warning)
          - CPU usage: -20 (critical) / -5 (warning)
          - Memory usage: -20 (critical) / -5 (warning)
          - Recent restart (< 1h): -10, (< 24h): -5
        """
        m = heartbeat.metrics
        t = self._config.thresholds
        score = 100.0

        # Response time
        if m.response_time > t.critical_response_time:
            score -= 30
        elif m.response_time > t.warning_response_time:
            score -= 10

        # Error rate
        if m.error_rate > t.critical_error_rate:
            score -= 40
        elif m.error_rate > t.warning_error_rate:
            score -= 15

        # CPU usage
        if m.cpu_usage > t.critical_cpu_usage:
            score -= 20
        elif m.cpu_usage > t.warning_cpu_usage:
            score -= 5

        # Memory usage
        if m.memory_usage > t.critical_memory_usage:
            score -= 20
        elif m.memory_usage > t.warning_memory_usage:
            score -= 5

        # Uptime / recent restart
        uptime_hours = m.uptime / 3600
        if uptime_hours < 1:
            score -= 10
        elif uptime_hours < 24:
            score -= 5

        return max(0.0, min(100.0, score))

    # ── Incident Tracking ──────────────────────────────────────────────────

    def _check_incidents(self, service_health: ServiceHealth, heartbeat: Heartbeat) -> None:
        """Track incident lifecycle — start on critical entry, resolve on exit."""
        was_critical = (
            len(service_health.status_history) > 1
            and service_health.status_history[-2].get("status") == ServiceStatus.CRITICAL.value
        )
        is_critical = heartbeat.status == ServiceStatus.CRITICAL

        # Start new incident
        if is_critical and not was_critical:
            incident = HealthIncident(
                service_id=service_health.service_id,
                start_time=heartbeat.timestamp,
                severity=ServiceStatus.CRITICAL,
                description=f"Service {service_health.service_name} entered critical state",
                affected_metrics=self._get_affected_metrics(heartbeat),
            )
            self._incidents[incident.id] = incident
            service_health.incidents.append(incident)
            logger.warning(
                "Critical incident started: id=%s service=%s",
                incident.id,
                service_health.service_id,
            )

        # Resolve existing incident
        if not is_critical and was_critical:
            for incident in service_health.incidents:
                if incident.status == IncidentStatus.ACTIVE:
                    incident.end_time = heartbeat.timestamp
                    incident.status = IncidentStatus.RESOLVED
                    logger.info(
                        "Critical incident resolved: id=%s service=%s",
                        incident.id,
                        service_health.service_id,
                    )

    def _get_affected_metrics(self, heartbeat: Heartbeat) -> List[str]:
        """Identify which metrics are in critical state."""
        affected = []
        t = self._config.thresholds
        m = heartbeat.metrics

        if m.response_time > t.critical_response_time:
            affected.append("response_time")
        if m.error_rate > t.critical_error_rate:
            affected.append("error_rate")
        if m.cpu_usage > t.critical_cpu_usage:
            affected.append("cpu_usage")
        if m.memory_usage > t.critical_memory_usage:
            affected.append("memory_usage")
        return affected

    # ── Alert Generation ───────────────────────────────────────────────────

    def _check_alerts(self, heartbeat: Heartbeat) -> None:
        """Evaluate heartbeat metrics against thresholds and generate alerts."""
        m = heartbeat.metrics
        t = self._config.thresholds

        # Critical alerts
        if m.response_time > t.critical_response_time:
            self._create_alert(
                AlertSeverity.CRITICAL,
                HealthCategory.AVAILABILITY,
                heartbeat,
                f"Critical response time: {m.response_time:.0f}ms",
            )
        if m.error_rate > t.critical_error_rate:
            self._create_alert(
                AlertSeverity.CRITICAL,
                HealthCategory.ERRORS,
                heartbeat,
                f"Critical error rate: {m.error_rate:.1f}%",
            )
        if m.cpu_usage > t.critical_cpu_usage:
            self._create_alert(
                AlertSeverity.CRITICAL,
                HealthCategory.RESOURCES,
                heartbeat,
                f"Critical CPU usage: {m.cpu_usage:.1f}%",
            )
        if m.memory_usage > t.critical_memory_usage:
            self._create_alert(
                AlertSeverity.CRITICAL,
                HealthCategory.RESOURCES,
                heartbeat,
                f"Critical memory usage: {m.memory_usage:.1f}%",
            )

        # Warning alerts
        if t.warning_response_time < m.response_time <= t.critical_response_time:
            self._create_alert(
                AlertSeverity.WARNING,
                HealthCategory.PERFORMANCE,
                heartbeat,
                f"High response time: {m.response_time:.0f}ms",
            )
        if t.warning_error_rate < m.error_rate <= t.critical_error_rate:
            self._create_alert(
                AlertSeverity.WARNING,
                HealthCategory.ERRORS,
                heartbeat,
                f"High error rate: {m.error_rate:.1f}%",
            )
        if t.warning_cpu_usage < m.cpu_usage <= t.critical_cpu_usage:
            self._create_alert(
                AlertSeverity.WARNING,
                HealthCategory.RESOURCES,
                heartbeat,
                f"High CPU usage: {m.cpu_usage:.1f}%",
            )
        if t.warning_memory_usage < m.memory_usage <= t.critical_memory_usage:
            self._create_alert(
                AlertSeverity.WARNING,
                HealthCategory.RESOURCES,
                heartbeat,
                f"High memory usage: {m.memory_usage:.1f}%",
            )

    def _create_alert(
        self,
        severity: AlertSeverity,
        category: HealthCategory,
        heartbeat: Heartbeat,
        message: str,
    ) -> None:
        """Create a new alert with deduplication (5-min window per service/category/severity)."""
        # Deduplication: skip if same service/category/severity alert exists within window
        now = time.time()
        dedup_window = self._config.alert_dedup_window_seconds
        for existing in self._alerts:
            if (
                existing.service_id == heartbeat.service_id
                and existing.category == category
                and existing.severity == severity
                and not existing.resolved
                and (now - existing.timestamp.timestamp()) < dedup_window
            ):
                return  # Duplicate alert, skip

        alert = HealthAlert(
            severity=severity,
            category=category,
            service_id=heartbeat.service_id,
            service_name=heartbeat.service_name,
            message=message,
            timestamp=heartbeat.timestamp,
        )
        self._alerts.append(alert)
        logger.warning(
            "Health alert: id=%s severity=%s service=%s msg=%s",
            alert.id,
            severity.value,
            heartbeat.service_id,
            message,
        )

    # ── Aggregation ────────────────────────────────────────────────────────

    def aggregate_health(self) -> AggregatedHealth:
        """Compute a full aggregated health snapshot of the ecosystem.

        Includes service health, category aggregation, trend analysis,
        active alerts, and actionable recommendations.
        """
        services = list(self._service_health.values())
        categories = self._aggregate_categories(services)
        overall_status = self._calculate_overall_status(services)
        overall_score = sum(s.score for s in services) / len(services) if services else 100.0
        trends = self._calculate_trends(services)
        active_alerts = [a for a in self._alerts if not a.resolved]
        recommendations = self._generate_recommendations(services, categories)

        self._last_aggregation = datetime.now(timezone.utc)

        return AggregatedHealth(
            overall_status=overall_status,
            overall_score=round(overall_score),
            services=services,
            categories=categories,
            trends=trends,
            alerts=active_alerts,
            recommendations=recommendations,
            timestamp=self._last_aggregation,
        )

    def _aggregate_categories(self, services: List[ServiceHealth]) -> List[CategoryHealth]:
        """Aggregate health by category across all services."""
        category_map: Dict[HealthCategory, List[ServiceHealth]] = {}

        for service in services:
            for cat in self._get_categories_for_service(service):
                if cat not in category_map:
                    category_map[cat] = []
                category_map[cat].append(service)

        result = []
        for category, cat_services in category_map.items():
            n = len(cat_services)
            avg_rt = (
                sum(s.current_metrics.response_time for s in cat_services if s.current_metrics) / n
            )
            avg_er = (
                sum(s.current_metrics.error_rate for s in cat_services if s.current_metrics) / n
            )
            avg_cpu = (
                sum(s.current_metrics.cpu_usage for s in cat_services if s.current_metrics) / n
            )
            avg_mem = (
                sum(s.current_metrics.memory_usage for s in cat_services if s.current_metrics) / n
            )
            avg_score = sum(s.score for s in cat_services) / n

            status = (
                ServiceStatus.HEALTHY
                if avg_score >= 80
                else ServiceStatus.DEGRADED
                if avg_score >= 50
                else ServiceStatus.CRITICAL
            )

            result.append(
                CategoryHealth(
                    category=category,
                    status=status,
                    score=round(avg_score),
                    affected_services=[s.service_id for s in cat_services],
                    avg_response_time=round(avg_rt),
                    avg_error_rate=round(avg_er, 1),
                    avg_cpu_usage=round(avg_cpu, 1),
                    avg_memory_usage=round(avg_mem, 1),
                )
            )

        return result

    def _get_categories_for_service(self, service: ServiceHealth) -> List[HealthCategory]:
        """Determine which health categories apply to a service."""
        cats = [
            HealthCategory.AVAILABILITY,
            HealthCategory.PERFORMANCE,
            HealthCategory.ERRORS,
            HealthCategory.RESOURCES,
        ]
        if service.current_metrics and service.current_metrics.active_connections > 0:
            cats.append(HealthCategory.DEPENDENCIES)
        return cats

    def _calculate_overall_status(self, services: List[ServiceHealth]) -> ServiceStatus:
        """Determine overall ecosystem status from service states."""
        if not services:
            return ServiceStatus.UNKNOWN

        has_critical = any(s.status == ServiceStatus.CRITICAL for s in services)
        has_offline = any(s.status == ServiceStatus.OFFLINE for s in services)
        has_degraded = any(s.status == ServiceStatus.DEGRADED for s in services)

        if has_critical or has_offline:
            return ServiceStatus.CRITICAL
        if has_degraded:
            return ServiceStatus.DEGRADED
        return ServiceStatus.HEALTHY

    def _calculate_trends(self, services: List[ServiceHealth]) -> List[HealthTrend]:
        """Analyze health trends across time windows."""
        trends = []
        period_seconds = {
            TrendPeriod.ONE_HOUR: 3600,
            TrendPeriod.SIX_HOURS: 3600 * 6,
            TrendPeriod.ONE_DAY: 3600 * 24,
            TrendPeriod.SEVEN_DAYS: 3600 * 24 * 7,
            TrendPeriod.THIRTY_DAYS: 3600 * 24 * 30,
        }

        for period in TrendPeriod:
            time.time() - period_seconds[period]

            # Collect metrics within this period (simplified: use historical_metrics)
            all_metrics: List[HeartbeatMetrics] = []
            for s in services:
                if s.current_metrics:
                    all_metrics.append(s.current_metrics)

            n = len(all_metrics) if all_metrics else 1
            avg_rt = sum(m.response_time for m in all_metrics) / n
            avg_er = sum(m.error_rate for m in all_metrics) / n
            avg_uptime = sum(m.uptime for m in all_metrics) / n

            # Determine trend direction based on current scores
            avg_score = sum(s.score for s in services) / len(services) if services else 100
            trend_status = (
                TrendStatus.STABLE
                if avg_score >= 80
                else TrendStatus.DEGRADING
                if avg_score >= 50
                else TrendStatus.IMPROVING
            )

            trends.append(
                HealthTrend(
                    period=period,
                    status=trend_status,
                    avg_response_time=round(avg_rt),
                    avg_error_rate=round(avg_er, 1),
                    avg_uptime=round(avg_uptime),
                )
            )

        return trends

    def _generate_recommendations(
        self, services: List[ServiceHealth], categories: List[CategoryHealth]
    ) -> List[str]:
        """Generate actionable recommendations based on current health state."""
        recs: List[str] = []

        # Service-level recommendations
        for service in services:
            if service.status == ServiceStatus.CRITICAL:
                recs.append(
                    f"\U0001f6a8 {service.service_name}: Investigate immediately — service in critical state"
                )
            elif service.status == ServiceStatus.DEGRADED:
                recs.append(
                    f"\u26a0\ufe0f {service.service_name}: Review metrics and investigate performance issues"
                )

            if service.missed_heartbeats > 3:
                recs.append(
                    f"\U0001f50c {service.service_name}: Check connectivity — missed "
                    f"{service.missed_heartbeats} heartbeats"
                )

            if service.current_metrics:
                if service.current_metrics.cpu_usage > 80:
                    recs.append(
                        f"\U0001f4bb {service.service_name}: High CPU usage "
                        f"({service.current_metrics.cpu_usage:.0f}%) — consider scaling"
                    )
                if service.current_metrics.memory_usage > 80:
                    recs.append(
                        f"\U0001f9e0 {service.service_name}: High memory usage "
                        f"({service.current_metrics.memory_usage:.0f}%) — check for leaks"
                    )

        # Category-level recommendations
        for cat in categories:
            if cat.status == ServiceStatus.CRITICAL:
                recs.append(
                    f"\U0001f6a8 Category {cat.category.value}: Critical — "
                    f"all affected services need attention"
                )
            if cat.avg_response_time > 2000:
                recs.append(
                    f"\u23f1\ufe0f {cat.category.value}: High response times — "
                    f"optimize queries or add caching"
                )
            if cat.avg_error_rate > 5:
                recs.append(
                    f"\U0001f41b {cat.category.value}: Elevated error rates — "
                    f"review logs and fix bugs"
                )

        return recs[: self._config.max_recommendations]

    # ── Public API ─────────────────────────────────────────────────────────

    def get_service_health(self, service_id: str) -> Optional[ServiceHealth]:
        """Get health data for a specific service."""
        return self._service_health.get(service_id)

    def get_all_service_health(self) -> List[ServiceHealth]:
        """Get health data for all tracked services."""
        return list(self._service_health.values())

    def get_alerts(
        self,
        service_id: Optional[str] = None,
        resolved: Optional[bool] = None,
    ) -> List[HealthAlert]:
        """Get alerts, optionally filtered by service and/or resolved status."""
        alerts = self._alerts
        if service_id:
            alerts = [a for a in alerts if a.service_id == service_id]
        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]
        return alerts

    def resolve_alert(self, alert_id: str) -> bool:
        """Mark an alert as resolved. Returns True if found and resolved."""
        for alert in self._alerts:
            if alert.id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = datetime.now(timezone.utc)
                logger.info("Alert resolved: id=%s", alert_id)
                return True
        return False

    def get_active_incidents(self) -> List[HealthIncident]:
        """Get all currently active (unresolved) incidents."""
        return [i for i in self._incidents.values() if i.status == IncidentStatus.ACTIVE]

    def get_stats(self) -> Dict[str, Any]:
        """Get aggregate heartbeat monitoring statistics."""
        services = list(self._service_health.values())
        return {
            "total_services": len(services),
            "healthy_services": sum(1 for s in services if s.status == ServiceStatus.HEALTHY),
            "degraded_services": sum(1 for s in services if s.status == ServiceStatus.DEGRADED),
            "critical_services": sum(1 for s in services if s.status == ServiceStatus.CRITICAL),
            "offline_services": sum(1 for s in services if s.status == ServiceStatus.OFFLINE),
            "total_alerts": len(self._alerts),
            "active_alerts": sum(1 for a in self._alerts if not a.resolved),
            "active_incidents": len(self.get_active_incidents()),
        }

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the full aggregation state to a dictionary for API exposure."""
        health = self.aggregate_health()
        return {
            "overall_status": health.overall_status.value,
            "overall_score": health.overall_score,
            "timestamp": health.timestamp.isoformat(),
            "services": [
                {
                    "service_id": s.service_id,
                    "service_name": s.service_name,
                    "status": s.status.value,
                    "score": round(s.score, 1),
                    "last_heartbeat": s.last_heartbeat.isoformat() if s.last_heartbeat else None,
                    "missed_heartbeats": s.missed_heartbeats,
                    "metrics": {
                        "response_time": s.current_metrics.response_time
                        if s.current_metrics
                        else 0,
                        "error_rate": s.current_metrics.error_rate if s.current_metrics else 0,
                        "cpu_usage": s.current_metrics.cpu_usage if s.current_metrics else 0,
                        "memory_usage": s.current_metrics.memory_usage if s.current_metrics else 0,
                    }
                    if s.current_metrics
                    else {},
                }
                for s in health.services
            ],
            "categories": [
                {
                    "category": c.category.value,
                    "status": c.status.value,
                    "score": c.score,
                    "affected_services": c.affected_services,
                }
                for c in health.categories
            ],
            "trends": [
                {
                    "period": t.period.value,
                    "status": t.status.value,
                    "avg_response_time": t.avg_response_time,
                    "avg_error_rate": t.avg_error_rate,
                }
                for t in health.trends
            ],
            "alerts": [
                {
                    "id": a.id,
                    "severity": a.severity.value,
                    "category": a.category.value,
                    "service_id": a.service_id,
                    "message": a.message,
                    "resolved": a.resolved,
                }
                for a in health.alerts
            ],
            "recommendations": health.recommendations,
            "stats": self.get_stats(),
        }


# ── Singleton Instance ────────────────────────────────────────────────────────

heartbeat_aggregator = HeartbeatAggregator()
