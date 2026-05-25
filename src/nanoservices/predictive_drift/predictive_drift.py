"""Predictive Drift Service — TranceX Phase 8

SHI-powered LLM analysis for predicting GitOps infrastructure drift
before it occurs. Combines log analysis, configuration diffing,
and LLM inference to forecast drift events and trigger auto-healing.

Integrates with IGI (Immutable GitOps Infrastructure) and SHI Gateway.
All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DriftSeverity(Enum):
    """Severity levels for drift predictions."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DriftCategory(Enum):
    """Categories of infrastructure drift."""
    CONFIG = "config"               # Configuration mismatch
    RESOURCE = "resource"           # Resource limit changes
    VERSION = "version"             # Image/tag version drift
    POLICY = "policy"               # Policy violation
    SCALING = "scaling"             # Replica/HPA drift
    NETWORK = "network"             # Service/network changes
    SECRET = "secret"               # Secret rotation needed
    DEPENDENCY = "dependency"       # Dependency version drift
    COMPLIANCE = "compliance"       # Compliance drift


class PredictionConfidence(Enum):
    """Confidence levels for drift predictions."""
    SPECULATIVE = auto()   # < 40% confidence
    POSSIBLE = auto()      # 40-60% confidence
    LIKELY = auto()        # 60-80% confidence
    PROBABLE = auto()      # 80-95% confidence
    CERTAIN = auto()       # > 95% confidence


@dataclass
class DriftSignal:
    """A single drift signal from monitoring data."""
    signal_id: str = ""
    source: str = ""
    category: DriftCategory = DriftCategory.CONFIG
    severity: DriftSeverity = DriftSeverity.INFO
    timestamp: float = field(default_factory=time.time)
    resource_name: str = ""
    namespace: str = "tranc3"
    expected_state: Dict[str, Any] = field(default_factory=dict)
    actual_state: Dict[str, Any] = field(default_factory=dict)
    diff: Dict[str, Any] = field(default_factory=dict)
    labels: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if not self.signal_id:
            self.signal_id = f"sig-{uuid.uuid4().hex[:8]}"


@dataclass
class DriftPrediction:
    """A predicted drift event with confidence scoring."""
    prediction_id: str = ""
    signals: List[DriftSignal] = field(default_factory=list)
    category: DriftCategory = DriftCategory.CONFIG
    severity: DriftSeverity = DriftSeverity.MEDIUM
    confidence: float = 0.5
    confidence_level: PredictionConfidence = PredictionConfidence.POSSIBLE
    predicted_time: float = 0.0
    time_horizon_hours: float = 24.0
    affected_resources: List[str] = field(default_factory=list)
    remediation: str = ""
    auto_heal: bool = False
    llm_reasoning: str = ""
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        if not self.prediction_id:
            self.prediction_id = f"pred-{uuid.uuid4().hex[:8]}"
        if self.confidence >= 0.95:
            self.confidence_level = PredictionConfidence.CERTAIN
        elif self.confidence >= 0.8:
            self.confidence_level = PredictionConfidence.PROBABLE
        elif self.confidence >= 0.6:
            self.confidence_level = PredictionConfidence.LIKELY
        elif self.confidence >= 0.4:
            self.confidence_level = PredictionConfidence.POSSIBLE
        else:
            self.confidence_level = PredictionConfidence.SPECULATIVE


@dataclass
class DriftAnalysisReport:
    """Complete drift analysis report for a time window."""
    report_id: str = ""
    time_window_start: float = 0.0
    time_window_end: float = 0.0
    total_signals: int = 0
    signals_by_category: Dict[str, int] = field(default_factory=dict)
    signals_by_severity: Dict[str, int] = field(default_factory=dict)
    predictions: List[DriftPrediction] = field(default_factory=list)
    top_drift_resources: List[Dict[str, Any]] = field(default_factory=list)
    trend_analysis: Dict[str, Any] = field(default_factory=dict)
    recommendations: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.report_id:
            self.report_id = f"rpt-{uuid.uuid4().hex[:8]}"


class LogAnalyzer:
    """Analyzes infrastructure logs for drift signals.

    Processes Kubernetes events, FluxCD logs, and application metrics
    to detect drift patterns and generate signals.
    """

    # Patterns that indicate drift
    DRIFT_PATTERNS = {
        DriftCategory.CONFIG: [
            "configmap updated", "configuration changed", "settings modified",
            "env var changed", "resource limit adjusted",
        ],
        DriftCategory.VERSION: [
            "image pull", "tag updated", "version mismatch",
            "rollback triggered", "image digest changed",
        ],
        DriftCategory.SCALING: [
            "replicas changed", "hpa triggered", "scale up",
            "scale down", "autoscaler",
        ],
        DriftCategory.NETWORK: [
            "service updated", "endpoint changed", "ingress modified",
            "network policy", "dns changed",
        ],
        DriftCategory.SECRET: [
            "secret rotated", "certificate expiring", "token refreshed",
            "credential updated",
        ],
        DriftCategory.POLICY: [
            "policy violation", "admission denied", "opa evaluation",
            "gatekeeper", "constraint violation",
        ],
    }

    def analyze_logs(self, log_entries: List[Dict[str, Any]]) -> List[DriftSignal]:
        """Parse log entries and extract drift signals."""
        signals = []
        for entry in log_entries:
            message = entry.get("message", "").lower()
            timestamp = entry.get("timestamp", time.time())
            source = entry.get("source", "unknown")
            resource = entry.get("resource", "")

            for category, patterns in self.DRIFT_PATTERNS.items():
                for pattern in patterns:
                    if pattern in message:
                        severity = self._determine_severity(message, category)
                        signal = DriftSignal(
                            source=source,
                            category=category,
                            severity=severity,
                            timestamp=timestamp,
                            resource_name=resource,
                            namespace=entry.get("namespace", "tranc3"),
                            expected_state=entry.get("expected", {}),
                            actual_state=entry.get("actual", {}),
                            diff=entry.get("diff", {}),
                            labels=entry.get("labels", {}),
                        )
                        signals.append(signal)
                        break

        return signals

    def _determine_severity(self, message: str, category: DriftCategory) -> DriftSeverity:
        """Determine drift severity from message content and category."""
        if any(w in message for w in ["critical", "emergency", "down", "failed"]):
            return DriftSeverity.CRITICAL
        if any(w in message for w in ["high", "urgent", "violation"]):
            return DriftSeverity.HIGH
        if category in (DriftCategory.SECRET, DriftCategory.POLICY):
            return DriftSeverity.HIGH
        if category in (DriftCategory.CONFIG, DriftCategory.VERSION):
            return DriftSeverity.MEDIUM
        return DriftSeverity.LOW


class LLMDriftPredictor:
    """Uses SHI LLM inference for drift prediction.

    Generates natural language prompts for the LLM to analyze
    drift signals and predict future drift events.
    """

    def __init__(self, shi_gateway=None):
        self.shi_gateway = shi_gateway
        self._prediction_cache: Dict[str, DriftPrediction] = {}

    async def predict_drift(
        self, signals: List[DriftSignal], time_horizon_hours: float = 24.0
    ) -> List[DriftPrediction]:
        """Use LLM to predict future drift events from current signals."""
        if not signals:
            return []

        # Build prompt for LLM
        prompt = self._build_prediction_prompt(signals, time_horizon_hours)

        # Try SHI gateway first, then fallback to heuristic prediction
        if self.shi_gateway:
            try:
                llm_response = await self._query_shi(prompt)
                return self._parse_llm_predictions(llm_response, signals, time_horizon_hours)
            except Exception as e:
                logger.warning(f"SHI LLM prediction failed, using heuristic: {e}")

        # Heuristic fallback
        return self._heuristic_prediction(signals, time_horizon_hours)

    def _build_prediction_prompt(
        self, signals: List[DriftSignal], time_horizon_hours: float
    ) -> str:
        """Build a prediction prompt for the LLM."""
        signal_summary = []
        for s in signals[:20]:  # Limit context window
            signal_summary.append(
                f"- [{s.category.value}/{s.severity.value}] {s.resource_name}: "
                f"expected={json.dumps(s.expected_state)[:100]} "
                f"actual={json.dumps(s.actual_state)[:100]}"
            )

        return f"""Analyze these infrastructure drift signals and predict likely future drift events in the next {time_horizon_hours} hours.

Current drift signals:
{chr(10).join(signal_summary)}

For each predicted drift event, provide:
1. Category (config, resource, version, policy, scaling, network, secret, dependency, compliance)
2. Severity (info, low, medium, high, critical)
3. Confidence (0.0-1.0)
4. Affected resources
5. Recommended remediation
6. Whether auto-healing should be triggered

Respond in JSON format as a list of predictions."""

    async def _query_shi(self, prompt: str) -> str:
        """Query the SHI gateway for LLM inference."""
        if self.shi_gateway and hasattr(self.shi_gateway, "infer"):
            result = await self.shi_gateway.infer(prompt)
            return result if isinstance(result, str) else json.dumps(result)
        return ""

    def _parse_llm_predictions(
        self, llm_response: str, signals: List[DriftSignal], time_horizon_hours: float
    ) -> List[DriftPrediction]:
        """Parse LLM response into structured predictions."""
        predictions = []
        try:
            parsed = json.loads(llm_response)
            if isinstance(parsed, list):
                for item in parsed[:10]:
                    pred = DriftPrediction(
                        signals=signals[:5],
                        category=DriftCategory(item.get("category", "config")),
                        severity=DriftSeverity(item.get("severity", "medium")),
                        confidence=float(item.get("confidence", 0.5)),
                        time_horizon_hours=time_horizon_hours,
                        predicted_time=time.time() + time_horizon_hours * 3600 * 0.5,
                        affected_resources=item.get("affected_resources", []),
                        remediation=item.get("remediation", ""),
                        auto_heal=item.get("auto_heal", False),
                        llm_reasoning=llm_response[:500],
                    )
                    predictions.append(pred)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning(f"Failed to parse LLM predictions: {e}")

        return predictions

    def _heuristic_prediction(
        self, signals: List[DriftSignal], time_horizon_hours: float
    ) -> List[DriftPrediction]:
        """Heuristic drift prediction when LLM is unavailable.

        Uses statistical analysis of signal patterns to predict drift.
        """
        predictions = []

        # Group signals by category
        by_category: Dict[DriftCategory, List[DriftSignal]] = {}
        for s in signals:
            by_category.setdefault(s.category, []).append(s)

        for category, cat_signals in by_category.items():
            # Count signals and calculate trend
            high_severity = sum(1 for s in cat_signals if s.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL))
            total = len(cat_signals)

            # Confidence based on signal count and severity
            confidence = min(0.95, 0.3 + (total * 0.05) + (high_severity * 0.1))

            # Predict drift escalation if high-severity signals are increasing
            if high_severity > total * 0.3:
                severity = DriftSeverity.HIGH
                auto_heal = True
            elif total > 5:
                severity = DriftSeverity.MEDIUM
                auto_heal = False
            else:
                severity = DriftSeverity.LOW
                auto_heal = False

            # Affected resources
            resources = list(set(s.resource_name for s in cat_signals if s.resource_name))

            # Remediation suggestion
            remediation_map = {
                DriftCategory.CONFIG: "Apply configuration from Git repository via FluxCD reconciliation",
                DriftCategory.VERSION: "Pin image tags and trigger FluxCD reconciliation",
                DriftCategory.SCALING: "Review HPA configuration and adjust thresholds",
                DriftCategory.NETWORK: "Reconcile network policies from GitOps manifests",
                DriftCategory.SECRET: "Rotate secrets via Forgejo CI pipeline",
                DriftCategory.POLICY: "Update OPA/Constraint policies and re-evaluate",
                DriftCategory.RESOURCE: "Adjust resource limits in Kustomize overlays",
                DriftCategory.DEPENDENCY: "Update dependency versions in base manifests",
                DriftCategory.COMPLIANCE: "Run compliance audit and apply remediation",
            }

            pred = DriftPrediction(
                signals=cat_signals[:5],
                category=category,
                severity=severity,
                confidence=confidence,
                time_horizon_hours=time_horizon_hours,
                predicted_time=time.time() + time_horizon_hours * 3600 * 0.3,
                affected_resources=resources,
                remediation=remediation_map.get(category, "Review and reconcile"),
                auto_heal=auto_heal,
                llm_reasoning=f"Heuristic prediction based on {total} signals ({high_severity} high severity) in {category.value} category",
            )
            predictions.append(pred)

        return predictions


class PredictiveDriftService:
    """Central service for predictive drift analysis in TranceX.

    Integrates log analysis, LLM-based prediction, and auto-healing
    to maintain infrastructure immutability (IGI compliance).
    """

    def __init__(
        self,
        shi_gateway=None,
        prediction_window_hours: float = 24.0,
        auto_heal_enabled: bool = True,
        signal_retention_hours: float = 168.0,  # 1 week
    ):
        self.log_analyzer = LogAnalyzer()
        self.llm_predictor = LLMDriftPredictor(shi_gateway=shi_gateway)
        self.prediction_window_hours = prediction_window_hours
        self.auto_heal_enabled = auto_heal_enabled
        self.signal_retention_hours = signal_retention_hours
        self._signals: List[DriftSignal] = []
        self._predictions: List[DriftPrediction] = []
        self._healing_actions: List[Dict[str, Any]] = []

    async def ingest_logs(self, log_entries: List[Dict[str, Any]]) -> int:
        """Ingest infrastructure logs and extract drift signals."""
        new_signals = self.log_analyzer.analyze_logs(log_entries)
        self._signals.extend(new_signals)
        self._prune_old_signals()
        logger.info(f"Ingested {len(new_signals)} drift signals from {len(log_entries)} log entries")
        return len(new_signals)

    async def ingest_signals(self, signals: List[DriftSignal]) -> None:
        """Directly ingest pre-processed drift signals."""
        self._signals.extend(signals)
        self._prune_old_signals()

    async def analyze_and_predict(self) -> DriftAnalysisReport:
        """Run full drift analysis and generate predictions."""
        now = time.time()
        window_start = now - self.prediction_window_hours * 3600

        # Filter signals in time window
        recent_signals = [s for s in self._signals if s.timestamp >= window_start]

        # Generate predictions
        predictions = await self.llm_predictor.predict_drift(
            recent_signals, self.prediction_window_hours
        )
        self._predictions.extend(predictions)

        # Auto-heal if enabled
        if self.auto_heal_enabled:
            await self._auto_heal(predictions)

        # Build report
        signals_by_category: Dict[str, int] = {}
        signals_by_severity: Dict[str, int] = {}
        for s in recent_signals:
            signals_by_category[s.category.value] = signals_by_category.get(s.category.value, 0) + 1
            signals_by_severity[s.severity.value] = signals_by_severity.get(s.severity.value, 0) + 1

        # Top drift resources
        resource_counts: Dict[str, int] = {}
        for s in recent_signals:
            if s.resource_name:
                resource_counts[s.resource_name] = resource_counts.get(s.resource_name, 0) + 1
        top_resources = sorted(
            [{"resource": k, "count": v} for k, v in resource_counts.items()],
            key=lambda x: -x["count"],
        )[:10]

        # Trend analysis
        trend = self._calculate_trend(recent_signals)

        # Recommendations
        recommendations = self._generate_recommendations(predictions)

        return DriftAnalysisReport(
            time_window_start=window_start,
            time_window_end=now,
            total_signals=len(recent_signals),
            signals_by_category=signals_by_category,
            signals_by_severity=signals_by_severity,
            predictions=predictions,
            top_drift_resources=top_resources,
            trend_analysis=trend,
            recommendations=recommendations,
        )

    async def _auto_heal(self, predictions: List[DriftPrediction]) -> None:
        """Execute auto-healing for high-confidence drift predictions."""
        for pred in predictions:
            if pred.auto_heal and pred.confidence >= 0.8:
                healing_action = {
                    "prediction_id": pred.prediction_id,
                    "category": pred.category.value,
                    "action": pred.remediation,
                    "affected_resources": pred.affected_resources,
                    "timestamp": time.time(),
                    "status": "initiated",
                }
                self._healing_actions.append(healing_action)
                logger.info(
                    f"Auto-heal initiated for {pred.category.value} drift "
                    f"(confidence={pred.confidence:.2f}): {pred.remediation}"
                )

    def _prune_old_signals(self) -> None:
        """Remove signals older than retention period."""
        cutoff = time.time() - self.signal_retention_hours * 3600
        self._signals = [s for s in self._signals if s.timestamp >= cutoff]

    def _calculate_trend(self, signals: List[DriftSignal]) -> Dict[str, Any]:
        """Calculate drift trend over time."""
        if len(signals) < 2:
            return {"trend": "insufficient_data", "direction": "unknown"}

        # Split signals into halves and compare
        mid = len(signals) // 2
        first_half = signals[:mid]
        second_half = signals[mid:]

        high_first = sum(1 for s in first_half if s.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL))
        high_second = sum(1 for s in second_half if s.severity in (DriftSeverity.HIGH, DriftSeverity.CRITICAL))

        if high_second > high_first * 1.2:
            direction = "increasing"
        elif high_second < high_first * 0.8:
            direction = "decreasing"
        else:
            direction = "stable"

        return {
            "trend": "drift_severity",
            "direction": direction,
            "first_half_high_severity": high_first,
            "second_half_high_severity": high_second,
            "total_signals": len(signals),
        }

    def _generate_recommendations(self, predictions: List[DriftPrediction]) -> List[str]:
        """Generate actionable recommendations from predictions."""
        recommendations = []
        for pred in sorted(predictions, key=lambda p: -p.confidence):
            if pred.confidence >= 0.6:
                recommendations.append(
                    f"[{pred.severity.value.upper()}] {pred.category.value}: "
                    f"{pred.remediation} (confidence: {pred.confidence:.0%})"
                )
        return recommendations[:10]

    def get_active_predictions(self) -> List[DriftPrediction]:
        """Get current active drift predictions."""
        return [p for p in self._predictions if p.predicted_time > time.time()]

    def get_healing_history(self) -> List[Dict[str, Any]]:
        """Get history of auto-healing actions."""
        return self._healing_actions.copy()

    def get_metrics(self) -> Dict[str, Any]:
        """Get predictive drift service metrics."""
        return {
            "total_signals": len(self._signals),
            "total_predictions": len(self._predictions),
            "active_predictions": len(self.get_active_predictions()),
            "healing_actions": len(self._healing_actions),
            "auto_heal_enabled": self.auto_heal_enabled,
            "prediction_window_hours": self.prediction_window_hours,
        }
