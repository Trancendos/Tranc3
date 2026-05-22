# src/healing/anomaly_detector.py
# Statistical anomaly detection for self-healing systems

import logging
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class MetricSample:
    value: float
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Anomaly:
    metric_name: str
    severity: str  # "low", "medium", "high", "critical"
    value: float
    expected_range: Tuple[float, float]
    timestamp: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class AnomalyDetector:
    """
    Statistical anomaly detection using z-scores.
    Detects outliers in time-series metrics and triggers alerts.
    """

    def __init__(
        self,
        window_size: int = 100,
        z_threshold: float = 3.0,
        min_samples: int = 10,
    ):
        self.window_size = window_size
        self.z_threshold = z_threshold
        self.min_samples = min_samples
        self._metrics: Dict[str, List[MetricSample]] = {}
        self._handlers: List[Callable[[Anomaly], None]] = []

    def add_handler(self, handler: Callable[[Anomaly], None]) -> None:
        self._handlers.append(handler)

    def record(self, metric_name: str, value: float, metadata: Optional[Dict] = None) -> Optional[Anomaly]:
        import time

        sample = MetricSample(value=value, timestamp=time.time(), metadata=metadata or {})

        if metric_name not in self._metrics:
            self._metrics[metric_name] = []

        self._metrics[metric_name].append(sample)

        if len(self._metrics[metric_name]) > self.window_size:
            self._metrics[metric_name] = self._metrics[metric_name][-self.window_size:]

        return self._check(metric_name, sample)

    def _check(self, metric_name: str, sample: MetricSample) -> Optional[Anomaly]:
        samples = self._metrics[metric_name]

        if len(samples) < self.min_samples:
            return None

        historical = samples[:-1]
        values = [s.value for s in historical]

        mean = statistics.mean(values)
        stdev = statistics.stdev(values) if len(values) > 1 else 0.0

        if stdev == 0:
            return None

        z_score = abs((sample.value - mean) / stdev)

        if z_score >= self.z_threshold:
            if z_score >= 5.0:
                severity = "critical"
            elif z_score >= 4.0:
                severity = "high"
            elif z_score >= 3.0:
                severity = "medium"
            else:
                severity = "low"

            anomaly = Anomaly(
                metric_name=metric_name,
                severity=severity,
                value=sample.value,
                expected_range=(mean - 2 * stdev, mean + 2 * stdev),
                timestamp=sample.timestamp,
                metadata=sample.metadata,
            )

            logger.warning(
                f"Anomaly detected: {metric_name}={sample.value:.2f} "
                f"(z={z_score:.2f}, severity={severity})"
            )

            for handler in self._handlers:
                try:
                    handler(anomaly)
                except Exception as e:
                    logger.error("Anomaly handler error: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]

            return anomaly

        return None

    def get_stats(self, metric_name: str) -> Optional[Dict[str, Any]]:
        if metric_name not in self._metrics:
            return None

        samples = self._metrics[metric_name]
        if not samples:
            return None

        values = [s.value for s in samples]

        return {
            "count": len(values),
            "mean": statistics.mean(values),
            "median": statistics.median(values),
            "stdev": statistics.stdev(values) if len(values) > 1 else 0.0,
            "min": min(values),
            "max": max(values),
            "latest": values[-1],
        }

    def reset(self, metric_name: Optional[str] = None) -> None:
        if metric_name:
            self._metrics.pop(metric_name, None)
        else:
            self._metrics.clear()


anomaly_detector = AnomalyDetector()
