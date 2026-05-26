"""Prometheus Custom Metrics — Observability for TranceX Nanoservices

Provides Prometheus-compatible metrics collection, exposition, and
alerting for all nanoservice components. Generates standard Prometheus
text exposition format for scraping.

Key features:
- Counter, Gauge, Histogram, Summary metric types
- Label-based dimensional data
- Per-service and cross-service metrics
- Alert rule evaluation and notification
- Standard Prometheus text exposition format
- Custom TranceX-specific metrics (NRC query latency, flow throughput, etc.)
- Zero-cost: no external dependencies required (generates Prometheus format directly)

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class MetricType(Enum):
    """Prometheus metric types."""
    COUNTER = "counter"
    GAUGE = "gauge"
    HISTOGRAM = "histogram"
    SUMMARY = "summary"
    UNTYPED = "untyped"


class AlertSeverity(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    FATAL = "fatal"


@dataclass
class MetricLabel:
    """Label for dimensional metrics."""
    name: str
    value: str


@dataclass
class MetricSample:
    """A single metric sample with timestamp."""
    value: float
    timestamp: float = 0.0
    labels: List[MetricLabel] = field(default_factory=list)

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


@dataclass
class NanoServiceMetric:
    """A Prometheus-compatible metric for nanoservices."""
    name: str = ""
    help_text: str = ""
    metric_type: MetricType = MetricType.GAUGE
    labels: List[MetricLabel] = field(default_factory=list)
    samples: List[MetricSample] = field(default_factory=list)
    unit: str = ""

    # Histogram-specific fields
    bucket_boundaries: List[float] = field(default_factory=lambda: [
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
    ])
    bucket_counts: List[int] = field(default_factory=list)
    sum_value: float = 0.0
    count_value: int = 0

    def __post_init__(self):
        if self.metric_type == MetricType.HISTOGRAM and not self.bucket_counts:
            self.bucket_counts = [0] * len(self.bucket_boundaries)

    def observe(self, value: float, labels: Optional[List[MetricLabel]] = None) -> None:
        """Record an observation (for histogram/summary)."""
        sample = MetricSample(value=value, labels=labels or self.labels)
        self.samples.append(sample)

        if self.metric_type == MetricType.HISTOGRAM:
            self.sum_value += value
            self.count_value += 1
            for i, boundary in enumerate(self.bucket_boundaries):
                if value <= boundary:
                    self.bucket_counts[i] += 1

        elif self.metric_type == MetricType.COUNTER:
            if self.samples:
                self.samples[-1].value = self.samples[-1].value + value
            else:
                self.samples.append(sample)

        elif self.metric_type == MetricType.GAUGE:
            # Replace last sample for gauge
            if self.samples:
                self.samples[-1] = sample
            else:
                self.samples.append(sample)

    def set(self, value: float, labels: Optional[List[MetricLabel]] = None) -> None:
        """Set gauge value directly."""
        if self.metric_type not in (MetricType.GAUGE, MetricType.UNTYPED):
            logger.warning("set() called on non-gauge metric: %s", self.name)
        sample = MetricSample(value=value, labels=labels or self.labels)
        self.samples = [sample]

    def inc(self, value: float = 1.0, labels: Optional[List[MetricLabel]] = None) -> None:
        """Increment counter."""
        if self.metric_type != MetricType.COUNTER:
            logger.warning("inc() called on non-counter metric: %s", self.name)
        current = self.samples[-1].value if self.samples else 0.0
        sample = MetricSample(value=current + value, labels=labels or self.labels)
        self.samples = [sample]

    def to_prometheus_format(self) -> str:
        """Export metric in Prometheus text exposition format."""
        lines = []

        # HELP line
        if self.help_text:
            lines.append(f"# HELP {self.name} {self.help_text}")

        # TYPE line
        lines.append(f"# TYPE {self.name} {self.metric_type.value}")

        label_str = ""
        if self.labels:
            label_pairs = ", ".join(f'{l.name}="{l.value}"' for l in self.labels)
            label_str = "{" + label_pairs + "}"

        if self.metric_type == MetricType.HISTOGRAM:
            # Histogram format: _bucket, _sum, _count
            for i, boundary in enumerate(self.bucket_boundaries):
                le_labels = self.labels + [MetricLabel("le", str(boundary))]
                le_label_str = ", ".join(f'{l.name}="{l.value}"' for l in le_labels)
                count = sum(self.bucket_counts[:i + 1])  # Cumulative
                lines.append(f'{self.name}_bucket{{{le_label_str}}} {count}')

            # +Inf bucket
            inf_labels = self.labels + [MetricLabel("le", "+Inf")]
            inf_label_str = ", ".join(f'{l.name}="{l.value}"' for l in inf_labels)
            lines.append(f'{self.name}_bucket{{{inf_label_str}}} {self.count_value}')

            lines.append(f'{self.name}_sum{label_str} {self.sum_value}')
            lines.append(f'{self.name}_count{label_str} {self.count_value}')

        elif self.metric_type == MetricType.SUMMARY:
            # Summary format: _sum, _count, quantiles
            lines.append(f'{self.name}_sum{label_str} {self.sum_value}')
            lines.append(f'{self.name}_count{label_str} {self.count_value}')
            if self.samples:
                sorted_samples = sorted(s.value for s in self.samples)
                for q in [0.5, 0.9, 0.95, 0.99]:
                    idx = int(len(sorted_samples) * q)
                    idx = min(idx, len(sorted_samples) - 1)
                    q_labels = self.labels + [MetricLabel("quantile", str(q))]
                    q_label_str = ", ".join(f'{l.name}="{l.value}"' for l in q_labels)
                    lines.append(f'{self.name}{q_label_str} {sorted_samples[idx]}')
        else:
            # Counter/Gauge/Untyped
            for sample in self.samples[-1:]:  # Latest sample only
                lines.append(f'{self.name}{label_str} {sample.value}')

        return "\n".join(lines)


class PrometheusRegistry:
    """Central Prometheus metrics registry.

    Collects and manages all metrics for the nanoservice mesh,
    providing a unified exposition endpoint for Prometheus scraping.
    """

    def __init__(self, namespace: str = "trancex", subsystem: str = "nanoservices"):
        self.namespace = namespace
        self.subsystem = subsystem
        self._metrics: Dict[str, NanoServiceMetric] = {}
        self._registration_time: float = time.time()
        logger.info("PrometheusRegistry initialized: %s/%s", namespace, subsystem)

    def _full_name(self, name: str) -> str:
        """Generate full metric name with namespace."""
        return f"{self.namespace}_{self.subsystem}_{name}"

    def register(
        self,
        name: str,
        help_text: str,
        metric_type: MetricType = MetricType.GAUGE,
        labels: Optional[List[MetricLabel]] = None,
        unit: str = "",
        bucket_boundaries: Optional[List[float]] = None,
    ) -> NanoServiceMetric:
        """Register a new metric."""
        full_name = self._full_name(name)
        if full_name in self._metrics:
            logger.warning("Metric %s already registered, returning existing", full_name)
            return self._metrics[full_name]

        metric = NanoServiceMetric(
            name=full_name,
            help_text=help_text,
            metric_type=metric_type,
            labels=labels or [],
            unit=unit,
        )

        if bucket_boundaries and metric_type == MetricType.HISTOGRAM:
            metric.bucket_boundaries = bucket_boundaries
            metric.bucket_counts = [0] * len(bucket_boundaries)

        self._metrics[full_name] = metric
        return metric

    def get(self, name: str) -> Optional[NanoServiceMetric]:
        """Get a registered metric by name."""
        return self._metrics.get(self._full_name(name))

    def unregister(self, name: str) -> bool:
        """Unregister a metric."""
        full_name = self._full_name(name)
        if full_name in self._metrics:
            del self._metrics[full_name]
            return True
        return False

    def collect(self) -> str:
        """Generate Prometheus text exposition format for all metrics."""
        lines = []
        for metric in self._metrics.values():
            lines.append(metric.to_prometheus_format())
            lines.append("")  # Blank line between metrics

        # Add process metrics
        lines.append(f"# HELP {self.namespace}_process_uptime_seconds Process uptime")
        lines.append(f"# TYPE {self.namespace}_process_uptime_seconds gauge")
        uptime = time.time() - self._registration_time
        lines.append(f"{self.namespace}_process_uptime_seconds {uptime:.2f}")

        return "\n".join(lines)

    def get_metric_count(self) -> int:
        """Get number of registered metrics."""
        return len(self._metrics)


class NanoserviceMetricsCollector:
    """Pre-configured metrics collector for all nanoservice components.

    Automatically registers standard TranceX metrics and provides
    convenience methods for recording observations.
    """

    def __init__(self, registry: Optional[PrometheusRegistry] = None):
        self.registry = registry or PrometheusRegistry()
        self._setup_default_metrics()

    def _setup_default_metrics(self) -> None:
        """Set up default TranceX nanoservice metrics."""
        # NSA Broker metrics
        self.nsa_messages_total = self.registry.register(
            "nsa_messages_total",
            "Total number of NSA IPC messages processed",
            MetricType.COUNTER,
        )
        self.nsa_message_latency = self.registry.register(
            "nsa_message_latency_seconds",
            "NSA IPC message latency",
            MetricType.HISTOGRAM,
            unit="seconds",
        )
        self.nsa_ring_buffer_utilization = self.registry.register(
            "nsa_ring_buffer_utilization",
            "NSA ring buffer utilization ratio",
            MetricType.GAUGE,
        )

        # NRC Query metrics
        self.nrc_queries_total = self.registry.register(
            "nrc_queries_total",
            "Total NRC queries executed",
            MetricType.COUNTER,
        )
        self.nrc_query_duration = self.registry.register(
            "nrc_query_duration_seconds",
            "NRC query execution duration",
            MetricType.HISTOGRAM,
            unit="seconds",
        )
        self.nrc_query_errors = self.registry.register(
            "nrc_query_errors_total",
            "Total NRC query errors",
            MetricType.COUNTER,
        )

        # DNF Flow metrics
        self.dnf_flows_active = self.registry.register(
            "dnf_flows_active",
            "Currently active DNF flows",
            MetricType.GAUGE,
        )
        self.dnf_flow_duration = self.registry.register(
            "dnf_flow_duration_seconds",
            "DNF flow execution duration",
            MetricType.HISTOGRAM,
            unit="seconds",
        )

        # SHI Inference metrics
        self.shi_inferences_total = self.registry.register(
            "shi_inferences_total",
            "Total SHI inference requests",
            MetricType.COUNTER,
        )
        self.shi_inference_latency = self.registry.register(
            "shi_inference_latency_seconds",
            "SHI inference latency",
            MetricType.HISTOGRAM,
            unit="seconds",
        )

        # WASM Edge metrics
        self.wasm_executions_total = self.registry.register(
            "wasm_executions_total",
            "Total WASM edge executions",
            MetricType.COUNTER,
        )
        self.wasm_gas_consumed = self.registry.register(
            "wasm_gas_consumed_total",
            "Total WASM gas consumed",
            MetricType.COUNTER,
        )

        # Genetic Optimizer metrics
        self.genetic_generations = self.registry.register(
            "genetic_generations_total",
            "Total genetic optimizer generations",
            MetricType.COUNTER,
        )
        self.genetic_pareto_size = self.registry.register(
            "genetic_pareto_front_size",
            "Current Pareto front size",
            MetricType.GAUGE,
        )

        # Adaptive Loop metrics
        self.adaptive_cycles_total = self.registry.register(
            "adaptive_cycles_total",
            "Total adaptive loop cycles",
            MetricType.COUNTER,
        )
        self.adaptive_adaptations = self.registry.register(
            "adaptive_adaptations_total",
            "Total adaptations made",
            MetricType.COUNTER,
        )

        # Liquidic Flow metrics
        self.liquidic_containers = self.registry.register(
            "liquidic_containers_active",
            "Active liquidic flow containers",
            MetricType.GAUGE,
        )
        self.liquidic_flow_rate = self.registry.register(
            "liquidic_flow_rate",
            "Current liquidic flow rate",
            MetricType.GAUGE,
        )

        # Drone metrics
        self.drone_active = self.registry.register(
            "drones_active",
            "Active aerial drones",
            MetricType.GAUGE,
        )
        self.drone_missions_total = self.registry.register(
            "drone_missions_total",
            "Total drone missions completed",
            MetricType.COUNTER,
        )

        # GPU Kernel metrics
        self.gpu_kernels_compiled = self.registry.register(
            "gpu_kernels_compiled_total",
            "Total GPU kernels compiled",
            MetricType.COUNTER,
        )
        self.gpu_kernel_duration = self.registry.register(
            "gpu_kernel_duration_seconds",
            "GPU kernel execution duration",
            MetricType.HISTOGRAM,
            unit="seconds",
        )

    def record_nsa_message(self, latency_seconds: float, buffer_util: float) -> None:
        """Record NSA broker message metrics."""
        self.nsa_messages_total.inc()
        self.nsa_message_latency.observe(latency_seconds)
        self.nsa_ring_buffer_utilization.set(buffer_util)

    def record_nrc_query(self, duration_seconds: float, success: bool = True) -> None:
        """Record NRC query execution metrics."""
        self.nrc_queries_total.inc()
        self.nrc_query_duration.observe(duration_seconds)
        if not success:
            self.nrc_query_errors.inc()

    def record_dnf_flow(self, active_count: int, duration_seconds: float = 0.0) -> None:
        """Record DNF flow metrics."""
        self.dnf_flows_active.set(active_count)
        if duration_seconds > 0:
            self.dnf_flow_duration.observe(duration_seconds)

    def record_shi_inference(self, latency_seconds: float) -> None:
        """Record SHI inference metrics."""
        self.shi_inferences_total.inc()
        self.shi_inference_latency.observe(latency_seconds)

    def record_wasm_execution(self, gas_consumed: float) -> None:
        """Record WASM edge execution metrics."""
        self.wasm_executions_total.inc()
        self.wasm_gas_consumed.inc(gas_consumed)

    def record_genetic_generation(self, pareto_size: int) -> None:
        """Record genetic optimizer metrics."""
        self.genetic_generations.inc()
        self.genetic_pareto_size.set(pareto_size)

    def record_adaptive_cycle(self, adaptations: int = 0) -> None:
        """Record adaptive loop metrics."""
        self.adaptive_cycles_total.inc()
        if adaptations > 0:
            self.adaptive_adaptations.inc(adaptations)

    def get_prometheus_output(self) -> str:
        """Get Prometheus text exposition format output."""
        return self.registry.collect()


@dataclass
class AlertRule:
    """Prometheus alerting rule."""
    rule_id: str = ""
    name: str = ""
    expression: str = ""      # PromQL-like expression
    severity: AlertSeverity = AlertSeverity.WARNING
    message: str = ""
    for_duration: str = "5m"  # How long condition must persist
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    last_evaluated: float = 0.0
    last_fired: float = 0.0
    fire_count: int = 0

    def __post_init__(self):
        if not self.rule_id:
            self.rule_id = f"alert-{uuid.uuid4().hex[:8]}"


class AlertManager:
    """Simple alert manager for Prometheus-like alerting.

    Evaluates alert rules against current metric values and
    fires alerts when conditions are met.
    """

    def __init__(self, registry: Optional[PrometheusRegistry] = None):
        self.registry = registry or PrometheusRegistry()
        self._rules: Dict[str, AlertRule] = {}
        self._active_alerts: Dict[str, Dict[str, Any]] = {}
        self._alert_history: List[Dict[str, Any]] = []
        self._callbacks: List[Callable] = []

    def add_rule(self, rule: AlertRule) -> str:
        """Add an alert rule."""
        self._rules[rule.rule_id] = rule
        return rule.rule_id

    def add_callback(self, callback: Callable) -> None:
        """Add a callback to be called when an alert fires."""
        self._callbacks.append(callback)

    def evaluate(self) -> List[Dict[str, Any]]:
        """Evaluate all alert rules against current metrics."""
        fired = []
        for rule_id, rule in self._rules.items():
            if not rule.enabled:
                continue

            rule.last_evaluated = time.time()

            # Simple threshold evaluation
            # Parse expression like "metric_name > 0.8"
            try:
                fired_alert = self._evaluate_rule(rule)
                if fired_alert:
                    rule.last_fired = time.time()
                    rule.fire_count += 1
                    self._active_alerts[rule_id] = fired_alert
                    self._alert_history.append(fired_alert)
                    fired.append(fired_alert)

                    # Fire callbacks
                    for callback in self._callbacks:
                        try:
                            callback(fired_alert)
                        except Exception as e:
                            logger.error("Alert callback error: %s", e)
                else:
                    # Alert resolved
                    if rule_id in self._active_alerts:
                        resolved = self._active_alerts.pop(rule_id)
                        resolved["status"] = "resolved"
                        resolved["resolved_at"] = time.time()
            except Exception as e:
                logger.error("Error evaluating rule %s: %s", rule.name, e)

        return fired

    def _evaluate_rule(self, rule: AlertRule) -> Optional[Dict[str, Any]]:
        """Evaluate a single alert rule (simple threshold-based)."""
        # Parse simple expressions: "metric_name operator value"
        parts = rule.expression.split()
        if len(parts) != 3:
            return None

        metric_name, operator, threshold_str = parts
        try:
            threshold = float(threshold_str)
        except ValueError:
            return None

        # Find metric value
        metric = self.registry.get(metric_name)
        if not metric:
            # Try with full namespace
            metric = self.registry._metrics.get(metric_name)
        if not metric or not metric.samples:
            return None

        current_value = metric.samples[-1].value

        # Evaluate condition
        condition_met = False
        if operator == ">":
            condition_met = current_value > threshold
        elif operator == ">=":
            condition_met = current_value >= threshold
        elif operator == "<":
            condition_met = current_value < threshold
        elif operator == "<=":
            condition_met = current_value <= threshold
        elif operator == "==":
            condition_met = current_value == threshold
        elif operator == "!=":
            condition_met = current_value != threshold

        if condition_met:
            return {
                "rule_id": rule.rule_id,
                "name": rule.name,
                "severity": rule.severity.value,
                "message": rule.message,
                "expression": rule.expression,
                "current_value": current_value,
                "threshold": threshold,
                "fired_at": time.time(),
                "status": "firing",
            }

        return None

    def get_active_alerts(self) -> List[Dict[str, Any]]:
        """Get currently active (firing) alerts."""
        return list(self._active_alerts.values())

    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alert history."""
        return self._alert_history[-limit:]

    def create_default_rules(self) -> None:
        """Create default alerting rules for nanoservices."""
        defaults = [
            AlertRule(
                name="HighNSABufferUtilization",
                expression="trancex_nanoservices_nsa_ring_buffer_utilization > 0.9",
                severity=AlertSeverity.WARNING,
                message="NSA ring buffer utilization above 90%",
            ),
            AlertRule(
                name="NRCQueryLatencyHigh",
                expression="trancex_nanoservices_nrc_query_duration_seconds > 5.0",
                severity=AlertSeverity.WARNING,
                message="NRC query latency above 5 seconds",
            ),
            AlertRule(
                name="LiquidicContainerOverflow",
                expression="trancex_nanoservices_liquidic_containers_active > 100",
                severity=AlertSeverity.CRITICAL,
                message="Too many liquidic containers active",
            ),
            AlertRule(
                name="SHIInferenceSlow",
                expression="trancex_nanoservices_shi_inference_latency_seconds > 10.0",
                severity=AlertSeverity.WARNING,
                message="SHI inference latency above 10 seconds",
            ),
            AlertRule(
                name="WASMGasExhaustion",
                expression="trancex_nanoservices_wasm_gas_consumed_total > 1000000",
                severity=AlertSeverity.CRITICAL,
                message="WASM gas consumption exceeding limit",
            ),
            AlertRule(
                name="DroneOffline",
                expression="trancex_nanoservices_drones_active < 1",
                severity=AlertSeverity.INFO,
                message="No drones currently active",
            ),
        ]

        for rule in defaults:
            self.add_rule(rule)
