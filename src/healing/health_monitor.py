"""
Health Monitor — real-time predictive service degradation detection.

Architecture:
  LogicCoreHealthMonitor sweeps all registered services every check_interval
  seconds, computes a composite compliance/licensing/cost score, fits a linear
  trend, projects a 30-minute score delta, and classifies each service into a
  HealthStatus tier.  Subscribers receive async callbacks on status transitions.
"""

import asyncio
import logging
import math
import os
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

import httpx
import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class HealthStatus(Enum):
    HEALTHY = "healthy"
    REVIEW = "review"
    ROLLBACK = "rollback"
    QUARANTINE = "quarantine"
    EMERGENCY = "emergency"


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class ServiceMetrics:
    service_id: str
    timestamp: float
    response_time_ms: float
    error_rate: float
    cpu_percent: float
    memory_percent: float
    free_tier_usage: float
    compliance_score: float
    licensing_score: float
    cost_score: float

    @property
    def composite_score(self) -> float:
        """
        Composite health score in [0, 1].

        Uses a weighted quadratic formula so each dimension contributes
        independently — a single zero-score axis cannot be rescued by
        perfect performance on the others:

            composite = sqrt(0.5 * compliance² + 0.3 * licensing² + 0.2 * cost²)

        The outer sqrt keeps the result in the same [0, 1] range as the
        individual scores while amplifying divergence near the extremes.
        """
        c = max(0.0, min(1.0, self.compliance_score))
        l_ = max(0.0, min(1.0, self.licensing_score))
        k = max(0.0, min(1.0, self.cost_score))
        return math.sqrt(0.5 * c * c + 0.3 * l_ * l_ + 0.2 * k * k)


@dataclass
class HealthRecord:
    service_id: str
    history: deque = field(default_factory=lambda: deque(maxlen=100))
    last_status: HealthStatus = HealthStatus.HEALTHY
    last_checked: float = 0.0

    def trend(self, window: int = 5) -> float:
        """
        Linear regression slope of the last *window* composite scores.

        Returns a value in roughly (-1, 1) — positive means improving,
        negative means degrading.  Returns 0.0 when there is insufficient
        history.
        """
        metrics: List[ServiceMetrics] = list(self.history)[-window:]
        if len(metrics) < 2:
            return 0.0

        scores = np.array([m.composite_score for m in metrics], dtype=float)
        xs = np.arange(len(scores), dtype=float)

        # Ordinary Least Squares slope: cov(x, y) / var(x)
        x_mean = xs.mean()
        y_mean = scores.mean()
        numerator = float(np.sum((xs - x_mean) * (scores - y_mean)))
        denominator = float(np.sum((xs - x_mean) ** 2))
        if abs(denominator) < 1e-12:
            return 0.0
        return numerator / denominator

    def predict_score_delta(self, minutes: int = 30) -> float:
        """
        Project the expected score change over the next *minutes* minutes.

        Uses the per-sample slope from trend() and scales by the number
        of future samples we would expect (minutes == future samples when
        the sweep interval is 1 minute; otherwise it is a directional proxy).
        """
        slope = self.trend()
        return slope * minutes


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------

class LogicCoreHealthMonitor:
    """
    Autonomous health monitor for the Tranc3 service mesh.

    Usage::

        health_monitor.register_service(
            "svc-001", "Embedding API",
            endpoint="http://embed:8080",
            health_endpoint="http://embed:8080/health",
        )
        asyncio.create_task(health_monitor.run_continuous())
    """

    # Status thresholds: minimum score to qualify for the given status.
    # Iterated in descending order so the first match wins.
    _THRESHOLD_TABLE: List[Tuple[float, HealthStatus]] = [
        (0.80, HealthStatus.HEALTHY),
        (0.60, HealthStatus.REVIEW),
        (0.40, HealthStatus.ROLLBACK),
        (0.20, HealthStatus.QUARANTINE),
        (0.00, HealthStatus.EMERGENCY),
    ]

    def __init__(self) -> None:
        # service_id → HealthRecord
        self._records: Dict[str, HealthRecord] = {}
        # service_id → service metadata
        self._services: Dict[str, Dict] = {}
        # Sweep period — default 6 hours, overridable via env.
        self.check_interval: float = float(
            os.getenv("HEALTH_CHECK_INTERVAL_SEC", str(6 * 3600))
        )
        # Alert subscribers
        self._alert_callbacks: List[Callable] = []
        # Shared async HTTP client (created lazily to avoid event-loop issues)
        self._http_client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_service(
        self,
        service_id: str,
        name: str,
        endpoint: str,
        health_endpoint: str,
        config: dict = {},
    ) -> None:
        """Register a service for continuous health monitoring."""
        self._services[service_id] = {
            "name": name,
            "endpoint": endpoint,
            "health_endpoint": health_endpoint,
            "config": config,
        }
        if service_id not in self._records:
            self._records[service_id] = HealthRecord(service_id=service_id)
        logger.info("Registered service %s (%s) for health monitoring.", service_id, name)

    # ------------------------------------------------------------------
    # HTTP helper
    # ------------------------------------------------------------------

    async def _client(self) -> httpx.AsyncClient:
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    async def check_service(self, service_id: str) -> ServiceMetrics:
        """
        Perform a single health check against the service's health endpoint.

        The endpoint is expected to return JSON with any subset of the
        following fields (missing fields default to neutral values):

            {
              "response_time_ms": 42.5,
              "error_rate": 0.01,
              "cpu_percent": 35.0,
              "memory_percent": 60.0,
              "free_tier_usage": 0.45,
              "compliance_score": 0.95,
              "licensing_score": 0.88,
              "cost_score": 0.72
            }
        """
        svc = self._services[service_id]
        health_url = svc["health_endpoint"]
        t0 = time.perf_counter()
        payload: Dict = {}

        try:
            client = await self._client()
            response = await client.get(health_url)
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.warning("Health check HTTP error for %s: %s", service_id, exc)
            # Penalise for HTTP errors but keep the service in the loop.
            payload = {
                "error_rate": 1.0,
                "compliance_score": 0.0,
                "licensing_score": 0.5,
                "cost_score": 0.5,
            }
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000.0
            logger.error("Health check failed for %s: %s", service_id, exc)
            payload = {
                "error_rate": 1.0,
                "compliance_score": 0.0,
                "licensing_score": 0.0,
                "cost_score": 0.0,
            }

        return ServiceMetrics(
            service_id=service_id,
            timestamp=time.time(),
            response_time_ms=payload.get("response_time_ms", elapsed_ms),
            error_rate=float(payload.get("error_rate", 0.0)),
            cpu_percent=float(payload.get("cpu_percent", 0.0)),
            memory_percent=float(payload.get("memory_percent", 0.0)),
            free_tier_usage=float(payload.get("free_tier_usage", 0.0)),
            compliance_score=float(payload.get("compliance_score", 1.0)),
            licensing_score=float(payload.get("licensing_score", 1.0)),
            cost_score=float(payload.get("cost_score", 1.0)),
        )

    # ------------------------------------------------------------------
    # Sweep
    # ------------------------------------------------------------------

    async def sweep(self) -> None:
        """Check all registered services and update records + status."""
        if not self._services:
            logger.debug("No services registered — skipping sweep.")
            return

        tasks = {
            sid: asyncio.create_task(self.check_service(sid))
            for sid in self._services
        }

        for service_id, task in tasks.items():
            try:
                metrics: ServiceMetrics = await task
            except Exception as exc:
                logger.error("Sweep task failed for %s: %s", service_id, exc)
                continue

            record = self._records.setdefault(
                service_id, HealthRecord(service_id=service_id)
            )
            record.history.append(metrics)
            record.last_checked = metrics.timestamp

            new_status = self._classify_status(metrics.composite_score)
            if new_status != record.last_status:
                self._emit_alert(
                    service_id, record.last_status, new_status, metrics
                )
            record.last_status = new_status

            logger.info(
                "Service %s: composite=%.3f status=%s",
                service_id,
                metrics.composite_score,
                new_status.value,
            )

    # ------------------------------------------------------------------
    # Classification
    # ------------------------------------------------------------------

    def _classify_status(self, score: float) -> HealthStatus:
        """Map a composite score to a HealthStatus tier."""
        for threshold, status in self._THRESHOLD_TABLE:
            if score >= threshold:
                return status
        return HealthStatus.EMERGENCY

    # ------------------------------------------------------------------
    # Continuous loop
    # ------------------------------------------------------------------

    async def run_continuous(self) -> None:
        """
        Run sweeps indefinitely, sleeping check_interval seconds between runs.
        Designed to be executed as an asyncio background task.
        """
        logger.info(
            "LogicCoreHealthMonitor starting — interval=%.0f s", self.check_interval
        )
        while True:
            try:
                await self.sweep()
            except Exception as exc:
                logger.exception("Unexpected error in sweep: %s", exc)
            await asyncio.sleep(self.check_interval)

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def get_dashboard(self) -> Dict:
        """Return a full health dashboard suitable for API serialisation."""
        services_out = {}
        for service_id, record in self._records.items():
            svc_meta = self._services.get(service_id, {})
            latest: Optional[ServiceMetrics] = (
                record.history[-1] if record.history else None
            )
            services_out[service_id] = {
                "name": svc_meta.get("name", service_id),
                "endpoint": svc_meta.get("endpoint", ""),
                "status": record.last_status.value,
                "last_checked": record.last_checked,
                "composite_score": latest.composite_score if latest else None,
                "metrics": {
                    "response_time_ms": latest.response_time_ms if latest else None,
                    "error_rate": latest.error_rate if latest else None,
                    "cpu_percent": latest.cpu_percent if latest else None,
                    "memory_percent": latest.memory_percent if latest else None,
                    "free_tier_usage": latest.free_tier_usage if latest else None,
                    "compliance_score": latest.compliance_score if latest else None,
                    "licensing_score": latest.licensing_score if latest else None,
                    "cost_score": latest.cost_score if latest else None,
                }
                if latest
                else {},
                "trend": record.trend(),
                "predicted_delta_30m": record.predict_score_delta(30),
                "history_length": len(record.history),
            }

        healthy = sum(
            1
            for r in self._records.values()
            if r.last_status == HealthStatus.HEALTHY
        )
        return {
            "timestamp": time.time(),
            "total_services": len(self._records),
            "healthy": healthy,
            "degraded": len(self._records) - healthy,
            "services": services_out,
        }

    # ------------------------------------------------------------------
    # Alerts / pub-sub
    # ------------------------------------------------------------------

    def subscribe_alerts(self, callback: Callable) -> None:
        """Register a callable to receive status-change events."""
        self._alert_callbacks.append(callback)

    def _emit_alert(
        self,
        service_id: str,
        old_status: HealthStatus,
        new_status: HealthStatus,
        metrics: ServiceMetrics,
    ) -> None:
        """Fire alert callbacks.  Async callbacks are scheduled on the loop."""
        event = {
            "service_id": service_id,
            "old_status": old_status.value,
            "new_status": new_status.value,
            "composite_score": metrics.composite_score,
            "timestamp": metrics.timestamp,
        }
        for cb in self._alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    asyncio.ensure_future(cb(event))
                else:
                    cb(event)
            except Exception as exc:
                logger.error("Alert callback error: %s", exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

health_monitor = LogicCoreHealthMonitor()
