"""Auto-Healing Diagnostics Engine — Phase 12

Proactive health monitoring, anomaly detection, and automated self-repair
for all nanoservices. Zero-cost implementation using statistical process
control and rule-based diagnostics.
"""

from __future__ import annotations

import logging
import math
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    CRITICAL = "critical"
    UNKNOWN = "unknown"


class AnomalyType(Enum):
    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE_HIGH = "error_rate_high"
    MEMORY_PRESSURE = "memory_pressure"
    CPU_THROTTLE = "cpu_throttle"
    QUEUE_BACKUP = "queue_backup"
    CONNECTION_LEAK = "connection_leak"
    RESPONSE_ANOMALY = "response_anomaly"
    THROUGHPUT_DROP = "throughput_drop"


class RepairAction(Enum):
    RESTART_SERVICE = "restart_service"
    CLEAR_CACHE = "clear_cache"
    DRAIN_QUEUE = "drain_queue"
    SCALE_UP = "scale_up"
    CIRCUIT_BREAK = "circuit_break"
    FAILOVER = "failover"
    THROTTLE_REQUESTS = "throttle_requests"
    RELOAD_CONFIG = "reload_config"
    NOOP = "noop"


class DiagnosticSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class HealthCheck:
    service_name: str
    status: HealthStatus
    latency_ms: float
    error_rate: float
    throughput_rps: float
    memory_usage_mb: float
    cpu_percent: float
    queue_depth: int
    active_connections: int
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    anomaly_type: AnomalyType = AnomalyType.LATENCY_SPIKE
    service_name: str = ""
    severity: DiagnosticSeverity = DiagnosticSeverity.MEDIUM
    description: str = ""
    detected_at: float = field(default_factory=time.time)
    metric_value: float = 0.0
    baseline_value: float = 0.0
    deviation_sigma: float = 0.0
    resolved: bool = False


@dataclass
class RepairRecord:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    anomaly_id: str = ""
    action: RepairAction = RepairAction.NOOP
    target_service: str = ""
    executed_at: float = field(default_factory=time.time)
    success: bool = False
    duration_ms: float = 0.0
    details: str = ""


@dataclass
class DiagnosticRule:
    name: str
    anomaly_type: AnomalyType
    condition: str  # Expression to evaluate
    threshold: float
    severity: DiagnosticSeverity
    repair_action: RepairAction
    cooldown_seconds: float = 60.0
    enabled: bool = True


class StatisticalBaseline:
    """Exponentially weighted moving average for anomaly detection."""

    def __init__(self, alpha: float = 0.1):
        self._alpha = alpha
        self._mean: Optional[float] = None
        self._variance: float = 0.0
        self._count: int = 0

    def update(self, value: float) -> None:
        if self._mean is None:
            self._mean = value
            self._variance = 0.0
        else:
            diff = value - self._mean
            self._mean = self._alpha * value + (1 - self._alpha) * self._mean
            self._variance = (1 - self._alpha) * (self._variance + self._alpha * diff * diff)
        self._count += 1

    @property
    def mean(self) -> float:
        return self._mean if self._mean is not None else 0.0

    @property
    def std_dev(self) -> float:
        return math.sqrt(max(0.0, self._variance))

    @property
    def is_ready(self) -> bool:
        return self._count >= 5

    def sigma_distance(self, value: float) -> float:
        if self.std_dev < 1e-10:
            return 0.0
        return abs(value - self._mean) / self.std_dev


class AnomalyDetector:
    """Detects anomalies using statistical process control."""

    def __init__(self, sigma_threshold: float = 3.0):
        self._sigma_threshold = sigma_threshold
        self._baselines: Dict[str, StatisticalBaseline] = {}
        self._anomalies: List[Anomaly] = []

    def register_metric(self, metric_name: str) -> None:
        if metric_name not in self._baselines:
            self._baselines[metric_name] = StatisticalBaseline()

    def observe(self, metric_name: str, value: float, service_name: str = "") -> Optional[Anomaly]:
        if metric_name not in self._baselines:
            self.register_metric(metric_name)
        baseline = self._baselines[metric_name]
        baseline.update(value)

        if not baseline.is_ready:
            return None

        sigma = baseline.sigma_distance(value)
        if sigma > self._sigma_threshold:
            anomaly_type = self._infer_anomaly_type(metric_name)
            anomaly = Anomaly(
                anomaly_type=anomaly_type,
                service_name=service_name,
                severity=self._sigma_to_severity(sigma),
                description=f"{metric_name} = {value:.2f} (baseline: {baseline.mean:.2f}, σ: {sigma:.1f})",
                metric_value=value,
                baseline_value=baseline.mean,
                deviation_sigma=sigma,
            )
            self._anomalies.append(anomaly)
            return anomaly
        return None

    def _infer_anomaly_type(self, metric_name: str) -> AnomalyType:
        name_lower = metric_name.lower()
        if "latency" in name_lower or "duration" in name_lower:
            return AnomalyType.LATENCY_SPIKE
        if "error" in name_lower or "failure" in name_lower:
            return AnomalyType.ERROR_RATE_HIGH
        if "memory" in name_lower or "mem" in name_lower:
            return AnomalyType.MEMORY_PRESSURE
        if "cpu" in name_lower:
            return AnomalyType.CPU_THROTTLE
        if "queue" in name_lower or "depth" in name_lower:
            return AnomalyType.QUEUE_BACKUP
        if "connection" in name_lower or "conn" in name_lower:
            return AnomalyType.CONNECTION_LEAK
        if "throughput" in name_lower or "rps" in name_lower:
            return AnomalyType.THROUGHPUT_DROP
        return AnomalyType.RESPONSE_ANOMALY

    def _sigma_to_severity(self, sigma: float) -> DiagnosticSeverity:
        if sigma > 5.0:
            return DiagnosticSeverity.CRITICAL
        if sigma > 4.0:
            return DiagnosticSeverity.HIGH
        if sigma > 3.5:
            return DiagnosticSeverity.MEDIUM
        return DiagnosticSeverity.LOW

    def get_active_anomalies(self) -> List[Anomaly]:
        return [a for a in self._anomalies if not a.resolved]

    def resolve_anomaly(self, anomaly_id: str) -> None:
        for a in self._anomalies:
            if a.id == anomaly_id:
                a.resolved = True
                break


class SelfHealingEngine:
    """Executes repair actions based on diagnostic rules."""

    def __init__(self):
        self._rules: List[DiagnosticRule] = []
        self._repair_history: List[RepairRecord] = []
        self._last_repair_time: Dict[str, float] = {}
        self._action_handlers: Dict[RepairAction, Any] = {}
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        self._rules = [
            DiagnosticRule(
                name="high_latency",
                anomaly_type=AnomalyType.LATENCY_SPIKE,
                condition="sigma > 3.0 and latency_ms > 1000",
                threshold=3.0,
                severity=DiagnosticSeverity.HIGH,
                repair_action=RepairAction.CLEAR_CACHE,
                cooldown_seconds=30.0,
            ),
            DiagnosticRule(
                name="error_rate_spike",
                anomaly_type=AnomalyType.ERROR_RATE_HIGH,
                condition="error_rate > 0.1",
                threshold=0.1,
                severity=DiagnosticSeverity.CRITICAL,
                repair_action=RepairAction.CIRCUIT_BREAK,
                cooldown_seconds=10.0,
            ),
            DiagnosticRule(
                name="memory_pressure",
                anomaly_type=AnomalyType.MEMORY_PRESSURE,
                condition="memory_usage_mb > 1024",
                threshold=1024.0,
                severity=DiagnosticSeverity.HIGH,
                repair_action=RepairAction.DRAIN_QUEUE,
                cooldown_seconds=60.0,
            ),
            DiagnosticRule(
                name="queue_backup",
                anomaly_type=AnomalyType.QUEUE_BACKUP,
                condition="queue_depth > 1000",
                threshold=1000.0,
                severity=DiagnosticSeverity.MEDIUM,
                repair_action=RepairAction.SCALE_UP,
                cooldown_seconds=45.0,
            ),
            DiagnosticRule(
                name="throughput_drop",
                anomaly_type=AnomalyType.THROUGHPUT_DROP,
                condition="throughput_rps < baseline * 0.5",
                threshold=0.5,
                severity=DiagnosticSeverity.MEDIUM,
                repair_action=RepairAction.RESTART_SERVICE,
                cooldown_seconds=120.0,
            ),
            DiagnosticRule(
                name="connection_leak",
                anomaly_type=AnomalyType.CONNECTION_LEAK,
                condition="active_connections > 500",
                threshold=500.0,
                severity=DiagnosticSeverity.MEDIUM,
                repair_action=RepairAction.RELOAD_CONFIG,
                cooldown_seconds=60.0,
            ),
        ]

    def register_action_handler(self, action: RepairAction, handler: Any) -> None:
        self._action_handlers[action] = handler

    def diagnose(
        self,
        health: HealthCheck,
        anomaly: Optional[Anomaly] = None,
    ) -> Optional[RepairAction]:
        if anomaly is None:
            return None

        for rule in self._rules:
            if not rule.enabled:
                continue
            if rule.anomaly_type != anomaly.anomaly_type:
                continue

            cooldown_key = f"{rule.name}:{health.service_name}"
            last_time = self._last_repair_time.get(cooldown_key, 0.0)
            if time.time() - last_time < rule.cooldown_seconds:
                continue

            if anomaly.deviation_sigma >= rule.threshold or anomaly.metric_value >= rule.threshold:
                return rule.repair_action

        return None

    def execute_repair(
        self,
        action: RepairAction,
        target_service: str,
        anomaly_id: str = "",
    ) -> RepairRecord:
        start = time.time()
        handler = self._action_handlers.get(action)
        success = False
        details = ""

        if handler:
            try:
                result = handler(target_service)
                success = True
                details = str(result)[:200]
            except Exception as e:
                success = False
                details = f"Handler error: {e}"
        else:
            success = True
            details = f"Auto-repair: {action.value} applied to {target_service} (simulation)"

        record = RepairRecord(
            anomaly_id=anomaly_id,
            action=action,
            target_service=target_service,
            success=success,
            duration_ms=(time.time() - start) * 1000,
            details=details,
        )
        self._repair_history.append(record)

        cooldown_key = f"{action.value}:{target_service}"
        self._last_repair_time[cooldown_key] = time.time()

        logger.info(f"Repair executed: {action.value} on {target_service} — success={success}")
        return record

    def get_repair_history(self, limit: int = 100) -> List[RepairRecord]:
        return self._repair_history[-limit:]


class AutoHealingDiagnosticsService:
    """Main service: monitors health, detects anomalies, executes self-repair."""

    def __init__(self, sigma_threshold: float = 3.0):
        self._detector = AnomalyDetector(sigma_threshold=sigma_threshold)
        self._healer = SelfHealingEngine()
        self._service_health: Dict[str, HealthCheck] = {}
        self._running = False
        self._check_count = 0

    def initialize(self) -> None:
        metrics = [
            "latency_ms",
            "error_rate",
            "throughput_rps",
            "memory_usage_mb",
            "cpu_percent",
            "queue_depth",
            "active_connections",
        ]
        for m in metrics:
            self._detector.register_metric(m)
        logger.info(
            "AutoHealingDiagnosticsService initialized with %d metric baselines",
            len(metrics),
        )

    def report_health(self, check: HealthCheck) -> Optional[Anomaly]:
        self._service_health[check.service_name] = check
        self._check_count += 1

        anomaly = self._detector.observe("latency_ms", check.latency_ms, check.service_name)
        self._detector.observe("error_rate", check.error_rate, check.service_name)
        self._detector.observe("throughput_rps", check.throughput_rps, check.service_name)
        self._detector.observe("memory_usage_mb", check.memory_usage_mb, check.service_name)
        self._detector.observe("cpu_percent", check.cpu_percent, check.service_name)
        self._detector.observe("queue_depth", float(check.queue_depth), check.service_name)
        self._detector.observe(
            "active_connections",
            float(check.active_connections),
            check.service_name,
        )

        if anomaly:
            action = self._healer.diagnose(check, anomaly)
            if action and action != RepairAction.NOOP:
                self._healer.execute_repair(action, check.service_name, anomaly.id)
                logger.warning(
                    "Anomaly detected in %s: %s → repair: %s",
                    check.service_name,
                    anomaly.description,
                    action.value,
                )

        return anomaly

    def get_service_health(self, service_name: str) -> Optional[HealthCheck]:
        return self._service_health.get(service_name)

    def get_all_health(self) -> Dict[str, HealthCheck]:
        return dict(self._service_health)

    def get_active_anomalies(self) -> List[Anomaly]:
        return self._detector.get_active_anomalies()

    def get_repair_history(self, limit: int = 100) -> List[RepairRecord]:
        return self._healer.get_repair_history(limit)

    def register_repair_handler(self, action: RepairAction, handler: Any) -> None:
        self._healer.register_action_handler(action, handler)

    def run_proactive_check(self) -> List[Anomaly]:
        """Proactive sweep — check all registered services for degradation."""
        new_anomalies = []
        for name, health in self._service_health.items():
            if health.status in (HealthStatus.DEGRADED, HealthStatus.UNHEALTHY):
                anomaly = Anomaly(
                    anomaly_type=AnomalyType.RESPONSE_ANOMALY,
                    service_name=name,
                    severity=DiagnosticSeverity.HIGH
                    if health.status == HealthStatus.UNHEALTHY
                    else DiagnosticSeverity.MEDIUM,
                    description=f"Service {name} is {health.status.value}",
                )
                new_anomalies.append(anomaly)
        return new_anomalies
