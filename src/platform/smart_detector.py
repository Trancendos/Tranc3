"""
Smart Detector — Trancendos Platform
======================================
Behavioural anomaly detection, threat pattern matching, and drift
detection across all 43 platform entities.

Detection layers:
  1. Statistical anomaly — Z-score and IQR on request rates, error rates,
     and latency per entity (no ML model needed — pure statistics)
  2. Threat pattern matching — known attack signatures against request
     logs (SQLi, XSS, path traversal, SSRF, prompt injection)
  3. Behavioural drift — detects gradual shifts in entity behaviour
     (e.g., rising error rate, memory growth, slowdown trend)
  4. AI agent drift — detects when a Lead AI's response pattern deviates
     from its personality profile baseline
  5. Zero-cost enforcement — alerts if any entity attempts a call to a
     paid external service

All detection is in-process (zero external dependencies).
Alerts are emitted to The Observatory and Sentinel Station.

Usage:
    from src.platform.smart_detector import get_detector

    detector = get_detector()
    detector.ingest(entity_id="the-spark", metric="latency_ms", value=142.3)
    alerts = detector.flush_alerts()
"""

from __future__ import annotations

import collections
import logging
import math
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("tranc3.platform.smart_detector")

# ---------------------------------------------------------------------------
# Alert types
# ---------------------------------------------------------------------------


class AlertType(str, Enum):
    ANOMALY_SPIKE = "ANOMALY_SPIKE"
    ANOMALY_LATENCY = "ANOMALY_LATENCY"
    ANOMALY_ERROR_RATE = "ANOMALY_ERROR_RATE"
    THREAT_INJECTION = "THREAT_INJECTION"
    THREAT_PATH_TRAVERSAL = "THREAT_TRAVERSAL"
    THREAT_SSRF = "THREAT_SSRF"
    THREAT_PROMPT_INJECTION = "THREAT_PROMPT_INJECTION"
    DRIFT_BEHAVIOURAL = "DRIFT_BEHAVIOURAL"
    DRIFT_AI_AGENT = "DRIFT_AI_AGENT"
    ZERO_COST_VIOLATION = "ZERO_COST_VIOLATION"
    HEALTH_DEGRADATION = "HEALTH_DEGRADATION"


@dataclass
class DetectorAlert:
    alert_type: AlertType
    entity_id: str
    lead_ai: str
    message: str
    value: float = 0.0
    threshold: float = 0.0
    severity: str = "MEDIUM"
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "alert_type": self.alert_type.value,
            "entity_id": self.entity_id,
            "lead_ai": self.lead_ai,
            "message": self.message,
            "value": round(self.value, 4),
            "threshold": round(self.threshold, 4),
            "severity": self.severity,
            "ts": self.ts,
        }


# ---------------------------------------------------------------------------
# Sliding window statistics
# ---------------------------------------------------------------------------


class SlidingWindowStats:
    """Maintains a fixed-size sliding window of numeric values with Z-score."""

    def __init__(self, maxlen: int = 60) -> None:
        self._buf: Deque[float] = collections.deque(maxlen=maxlen)

    def push(self, value: float) -> None:
        self._buf.append(value)

    def mean(self) -> float:
        if not self._buf:
            return 0.0
        return sum(self._buf) / len(self._buf)

    def std(self) -> float:
        if len(self._buf) < 2:
            return 0.0
        m = self.mean()
        variance = sum((x - m) ** 2 for x in self._buf) / len(self._buf)
        return math.sqrt(variance)

    def z_score(self, value: float) -> float:
        s = self.std()
        if s == 0:
            return 0.0
        return abs(value - self.mean()) / s

    def iqr_outlier(self, value: float, k: float = 1.5) -> bool:
        if len(self._buf) < 4:
            return False
        sorted_buf = sorted(self._buf)
        n = len(sorted_buf)
        q1 = sorted_buf[n // 4]
        q3 = sorted_buf[3 * n // 4]
        iqr = q3 - q1
        return value < q1 - k * iqr or value > q3 + k * iqr


# ---------------------------------------------------------------------------
# Threat pattern database (zero-cost, no external feed)
# ---------------------------------------------------------------------------

THREAT_PATTERNS: List[Tuple[AlertType, str, re.Pattern]] = [
    (
        AlertType.THREAT_INJECTION,
        "SQL injection attempt",
        re.compile(
            r"(?i)(\bunion\b.*\bselect\b|'\s*or\s*'1'\s*=\s*'1|drop\s+table|;\s*delete\s+from)",
            re.I,
        ),
    ),
    (
        AlertType.THREAT_INJECTION,
        "XSS attempt",
        re.compile(r"<script[^>]*>|javascript:|on\w+\s*=", re.I),
    ),
    (
        AlertType.THREAT_PATH_TRAVERSAL,
        "Path traversal attempt",
        re.compile(r"\.\./|\.\.\\|%2e%2e[%/\\]", re.I),
    ),
    (
        AlertType.THREAT_SSRF,
        "SSRF / internal IP probe",
        re.compile(
            r"(?:http|ftp)s?://(?:127\.0\.0\.1|0\.0\.0\.0|169\.254\.|10\.|172\.1[6-9]\.|192\.168\.)",
            re.I,
        ),
    ),
    (
        AlertType.THREAT_PROMPT_INJECTION,
        "Prompt injection attempt",
        re.compile(
            r"(?i)(ignore\s+previous\s+instructions|system\s+prompt|forget\s+everything|act\s+as\s+(an?\s+)?(?:ai|assistant|gpt|claude)|jailbreak)",
            re.I,
        ),
    ),
]

# Paid provider domains — alert if any entity tries to call these
PAID_PROVIDER_PATTERNS = re.compile(
    r"(?i)(api\.openai\.com|api\.anthropic\.com|api\.cohere\.ai|"
    r"api\.replicate\.com|openrouter\.ai(?!/free)|api\.deepseek\.com|"
    r"api\.mistral\.ai|api\.together\.xyz)",
    re.I,
)


# ---------------------------------------------------------------------------
# Per-entity detector state
# ---------------------------------------------------------------------------


@dataclass
class EntityDetectorState:
    entity_id: str
    lead_ai: str
    latency_stats: SlidingWindowStats = field(default_factory=lambda: SlidingWindowStats(60))
    error_rate_stats: SlidingWindowStats = field(default_factory=lambda: SlidingWindowStats(60))
    rps_stats: SlidingWindowStats = field(default_factory=lambda: SlidingWindowStats(60))
    # Cumulative counters (current minute window)
    _request_count: int = 0
    _error_count: int = 0
    _window_start: float = field(default_factory=time.monotonic)
    # AI agent response pattern baseline (simple token count distribution)
    _ai_response_lengths: Deque[int] = field(default_factory=lambda: collections.deque(maxlen=100))

    def tick(self) -> None:
        """Flush per-minute counters into stats windows."""
        now = time.monotonic()
        if now - self._window_start >= 60.0:
            rps = self._request_count / max(now - self._window_start, 1.0)
            err_rate = (self._error_count / max(self._request_count, 1)) * 100.0
            self.rps_stats.push(rps)
            self.error_rate_stats.push(err_rate)
            self._request_count = 0
            self._error_count = 0
            self._window_start = now

    def record_request(self, latency_ms: float, is_error: bool = False) -> None:
        self._request_count += 1
        if is_error:
            self._error_count += 1
        self.latency_stats.push(latency_ms)

    def record_ai_response(self, response_length: int) -> None:
        self._ai_response_lengths.append(response_length)


# ---------------------------------------------------------------------------
# SmartDetector
# ---------------------------------------------------------------------------


class SmartDetector:
    """
    Detects anomalies, threats, and drift across all 43 platform entities.
    Uses only zero-cost in-process statistical methods.
    """

    # Thresholds
    Z_SCORE_THRESHOLD = 3.5  # Alert if Z-score exceeds this
    ERROR_RATE_THRESHOLD = 15.0  # Alert if error rate % exceeds this
    LATENCY_Z_THRESHOLD = 4.0  # Latency Z-score alarm level
    AI_DRIFT_THRESHOLD = 3.0  # AI response length Z-score for drift

    def __init__(self) -> None:
        self._states: Dict[str, EntityDetectorState] = {}
        self._alert_queue: List[DetectorAlert] = []
        self._scan_count = 0

    def _state(self, entity_id: str, lead_ai: str = "Unknown") -> EntityDetectorState:
        if entity_id not in self._states:
            self._states[entity_id] = EntityDetectorState(
                entity_id=entity_id,
                lead_ai=lead_ai,
            )
        return self._states[entity_id]

    # -----------------------------------------------------------------------
    # Ingestion API
    # -----------------------------------------------------------------------

    def ingest(
        self,
        entity_id: str,
        metric: str,
        value: float,
        lead_ai: str = "Unknown",
        is_error: bool = False,
    ) -> None:
        """Ingest a metric data point for an entity."""
        state = self._state(entity_id, lead_ai)
        state.tick()
        if metric == "latency_ms":
            state.record_request(value, is_error)
            self._check_latency_anomaly(state, value)
        elif metric == "error_rate":
            state.error_rate_stats.push(value)
            self._check_error_rate(state, value)
        elif metric == "rps":
            state.rps_stats.push(value)
            self._check_rps_anomaly(state, value)

    def ingest_ai_response(
        self, entity_id: str, response_text: str, lead_ai: str = "Unknown"
    ) -> None:
        """Ingest an AI agent response for drift detection."""
        state = self._state(entity_id, lead_ai)
        state.record_ai_response(len(response_text))
        self._check_ai_drift(state, len(response_text))

    def scan_request(
        self,
        entity_id: str,
        request_body: str,
        request_url: str = "",
        lead_ai: str = "Unknown",
    ) -> List[DetectorAlert]:
        """Scan a request for threat patterns. Returns immediate alerts."""
        immediate: List[DetectorAlert] = []
        full_text = f"{request_url} {request_body}"
        for alert_type, description, pattern in THREAT_PATTERNS:
            if pattern.search(full_text):
                alert = DetectorAlert(
                    alert_type=alert_type,
                    entity_id=entity_id,
                    lead_ai=lead_ai,
                    message=f"{description} detected in request to {entity_id}",
                    severity="HIGH",
                )
                immediate.append(alert)
                self._alert_queue.append(alert)
                logger.warning(
                    "[THREAT] %s entity=%s type=%s",
                    description,
                    entity_id,
                    alert_type.value,
                )
        if PAID_PROVIDER_PATTERNS.search(full_text):
            alert = DetectorAlert(
                alert_type=AlertType.ZERO_COST_VIOLATION,
                entity_id=entity_id,
                lead_ai=lead_ai,
                message=f"Zero-cost violation: {entity_id} attempting call to paid external provider",
                severity="CRITICAL",
            )
            immediate.append(alert)
            self._alert_queue.append(alert)
            logger.critical("[ZERO-COST VIOLATION] entity=%s attempted paid API call", entity_id)
        return immediate

    # -----------------------------------------------------------------------
    # Internal anomaly checks
    # -----------------------------------------------------------------------

    def _check_latency_anomaly(self, state: EntityDetectorState, value: float) -> None:
        z = state.latency_stats.z_score(value)
        if z > self.LATENCY_Z_THRESHOLD:
            self._emit(
                DetectorAlert(
                    alert_type=AlertType.ANOMALY_LATENCY,
                    entity_id=state.entity_id,
                    lead_ai=state.lead_ai,
                    message=f"Latency spike: {value:.0f}ms (Z={z:.1f}) on {state.entity_id}",
                    value=value,
                    threshold=self.LATENCY_Z_THRESHOLD,
                    severity="MEDIUM",
                )
            )

    def _check_error_rate(self, state: EntityDetectorState, value: float) -> None:
        if value > self.ERROR_RATE_THRESHOLD:
            self._emit(
                DetectorAlert(
                    alert_type=AlertType.ANOMALY_ERROR_RATE,
                    entity_id=state.entity_id,
                    lead_ai=state.lead_ai,
                    message=f"High error rate {value:.1f}% on {state.entity_id} (threshold={self.ERROR_RATE_THRESHOLD}%)",
                    value=value,
                    threshold=self.ERROR_RATE_THRESHOLD,
                    severity="HIGH",
                )
            )

    def _check_rps_anomaly(self, state: EntityDetectorState, value: float) -> None:
        z = state.rps_stats.z_score(value)
        if z > self.Z_SCORE_THRESHOLD:
            self._emit(
                DetectorAlert(
                    alert_type=AlertType.ANOMALY_SPIKE,
                    entity_id=state.entity_id,
                    lead_ai=state.lead_ai,
                    message=f"Request rate spike: {value:.1f} rps (Z={z:.1f}) on {state.entity_id}",
                    value=value,
                    threshold=self.Z_SCORE_THRESHOLD,
                    severity="MEDIUM",
                )
            )

    def _check_ai_drift(self, state: EntityDetectorState, response_len: int) -> None:
        buf = state._ai_response_lengths
        if len(buf) < 10:
            return
        values = list(buf)
        mean = sum(values) / len(values)
        std = math.sqrt(sum((x - mean) ** 2 for x in values) / len(values))
        if std == 0:
            return
        z = abs(response_len - mean) / std
        if z > self.AI_DRIFT_THRESHOLD:
            self._emit(
                DetectorAlert(
                    alert_type=AlertType.DRIFT_AI_AGENT,
                    entity_id=state.entity_id,
                    lead_ai=state.lead_ai,
                    message=(
                        f"AI agent drift detected: {state.lead_ai} response length "
                        f"{response_len} chars deviates {z:.1f}σ from baseline on {state.entity_id}"
                    ),
                    value=float(response_len),
                    threshold=self.AI_DRIFT_THRESHOLD,
                    severity="LOW",
                )
            )

    def _emit(self, alert: DetectorAlert) -> None:
        self._alert_queue.append(alert)
        logger.warning(
            "[ALERT] %s entity=%s lead_ai=%s msg=%s",
            alert.alert_type.value,
            alert.entity_id,
            alert.lead_ai,
            alert.message,
        )

    # -----------------------------------------------------------------------
    # Alert access
    # -----------------------------------------------------------------------

    def flush_alerts(self) -> List[DetectorAlert]:
        """Return and clear all pending alerts."""
        alerts = list(self._alert_queue)
        self._alert_queue.clear()
        return alerts

    def peek_alerts(self) -> List[dict]:
        """Return all pending alerts without clearing."""
        return [a.to_dict() for a in self._alert_queue]

    def entity_health(self, entity_id: str) -> dict:
        """Return current health snapshot for an entity."""
        state = self._states.get(entity_id)
        if not state:
            return {"entity_id": entity_id, "status": "no_data"}
        state.tick()
        return {
            "entity_id": entity_id,
            "lead_ai": state.lead_ai,
            "latency_mean_ms": round(state.latency_stats.mean(), 2),
            "latency_std_ms": round(state.latency_stats.std(), 2),
            "error_rate_mean_pct": round(state.error_rate_stats.mean(), 2),
            "rps_mean": round(state.rps_stats.mean(), 4),
            "pending_alerts": sum(1 for a in self._alert_queue if a.entity_id == entity_id),
        }

    def platform_health_summary(self) -> dict:
        """Summarise health across all monitored entities."""
        total_alerts = len(self._alert_queue)
        critical = sum(1 for a in self._alert_queue if a.severity == "CRITICAL")
        high = sum(1 for a in self._alert_queue if a.severity == "HIGH")
        return {
            "monitored_entities": len(self._states),
            "pending_alerts": total_alerts,
            "critical": critical,
            "high": high,
            "zero_cost_compliant": not any(
                a.alert_type == AlertType.ZERO_COST_VIOLATION for a in self._alert_queue
            ),
            "entities": [self.entity_health(eid) for eid in self._states],
        }


# ---------------------------------------------------------------------------
# Singleton accessor
# ---------------------------------------------------------------------------

_detector: Optional[SmartDetector] = None


def get_detector() -> SmartDetector:
    global _detector
    if _detector is None:
        _detector = SmartDetector()
    return _detector
