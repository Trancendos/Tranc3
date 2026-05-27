"""
Proactive Health Monitor — The Observatory
==========================================
Zero-cost, pure-Python proactive monitoring that aggregates SWOT snapshots
from all registered Tier 1–5 entities, detects degradation patterns early,
and emits structured alerts before failures cascade.

Features:
  - Rolling EWMA health scoring per entity
  - SWOT threat escalation with configurable thresholds
  - Predictive degradation detection (3-sample trend)
  - SQLite-backed alert history (no external deps)
  - Asyncio-native; integrates with Tranc3 cycle loop
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_DB_PATH = Path("data/proactive_health.db")

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class HealthSample:
    entity_id: str
    health_score: float
    error_count: int
    cycle_count: int
    swot_threats: list[str]
    sampled_at: float = field(default_factory=time.monotonic)


@dataclass
class ProactiveAlert:
    alert_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    entity_id: str = ""
    severity: str = "info"  # info | warning | critical
    message: str = ""
    context: dict[str, Any] = field(default_factory=dict)
    raised_at: float = field(default_factory=time.time)
    acknowledged: bool = False


# ---------------------------------------------------------------------------
# Proactive health monitor
# ---------------------------------------------------------------------------


class ProactiveHealthMonitor:
    """
    Aggregate health from all registered entities and raise proactive alerts.

    Usage::

        monitor = ProactiveHealthMonitor()
        monitor.register(tranc3_lead_ai)
        asyncio.create_task(monitor.run())
    """

    _EWMA_ALPHA = 0.3
    _TREND_WINDOW = 3
    _DEGRADATION_THRESHOLD = 0.05  # score drop per sample to flag trend
    _CRITICAL_THRESHOLD = 0.35
    _WARNING_THRESHOLD = 0.55
    _CHECK_INTERVAL_S = 30.0

    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self._entities: dict[str, Any] = {}
        self._scores: dict[str, list[float]] = {}
        self._ewma: dict[str, float] = {}
        self._alerts: list[ProactiveAlert] = []
        self._running = False
        self._task: asyncio.Task | None = None
        self._db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _init_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    entity_id TEXT,
                    severity TEXT,
                    message TEXT,
                    raised_at REAL,
                    acknowledged INTEGER DEFAULT 0
                )"""
            )
            conn.commit()
        finally:
            conn.close()

    def _persist_alert(self, alert: ProactiveAlert) -> None:
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            conn.execute(
                "INSERT OR IGNORE INTO alerts VALUES (?,?,?,?,?,?)",
                (
                    alert.alert_id,
                    alert.entity_id,
                    alert.severity,
                    alert.message,
                    alert.raised_at,
                    int(alert.acknowledged),
                ),
            )
            conn.commit()
        except Exception as exc:
            logger.warning("ProactiveHealthMonitor: failed to persist alert: %s", exc)
        finally:
            if conn:
                conn.close()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entity: Any) -> None:
        """Register any entity that exposes .dna.aid and .status()."""
        try:
            eid = entity.dna.aid
            self._entities[eid] = entity
            self._scores[eid] = []
            self._ewma[eid] = 1.0
            logger.debug("ProactiveHealthMonitor: registered %s", eid)
        except AttributeError as exc:
            logger.warning("ProactiveHealthMonitor.register: entity missing .dna.aid — %s", exc)

    def deregister(self, aid: str) -> None:
        self._entities.pop(aid, None)
        self._scores.pop(aid, None)
        self._ewma.pop(aid, None)

    # ------------------------------------------------------------------
    # Core check
    # ------------------------------------------------------------------

    def _sample_entity(self, eid: str, entity: Any) -> HealthSample | None:
        try:
            status = entity.status()
            health = float(status.get("health_score", 1.0))
            errors = int(status.get("error_count", 0))
            cycles = int(status.get("cycle_count", 0))
            swot_threats: list[str] = []
            if hasattr(entity, "assess_swot"):
                snap = entity.assess_swot()
                swot_threats = snap.threats
            return HealthSample(
                entity_id=eid,
                health_score=health,
                error_count=errors,
                cycle_count=cycles,
                swot_threats=swot_threats,
            )
        except Exception as exc:
            logger.warning("ProactiveHealthMonitor: sample failed for %s: %s", eid, exc)
            return None

    def _update_ewma(self, eid: str, score: float) -> float:
        prev = self._ewma.get(eid, 1.0)
        ewma = self._EWMA_ALPHA * score + (1 - self._EWMA_ALPHA) * prev
        self._ewma[eid] = ewma
        return ewma

    def _detect_trend(self, eid: str, score: float) -> bool:
        history = self._scores[eid]
        history.append(score)
        if len(history) > 20:
            self._scores[eid] = history[-20:]
        window = self._scores[eid][-self._TREND_WINDOW :]
        if len(window) < self._TREND_WINDOW:
            return False
        # Declining trend if each step drops by threshold
        return all(
            window[i] - window[i + 1] >= self._DEGRADATION_THRESHOLD
            for i in range(len(window) - 1)
        )

    def _raise_alert(
        self,
        eid: str,
        severity: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> ProactiveAlert:
        alert = ProactiveAlert(
            entity_id=eid,
            severity=severity,
            message=message,
            context=context or {},
        )
        self._alerts.append(alert)
        if len(self._alerts) > 1000:
            self._alerts = self._alerts[-500:]
        self._persist_alert(alert)
        logger.log(
            logging.CRITICAL if severity == "critical" else logging.WARNING,
            "PROACTIVE ALERT [%s] %s — %s",
            severity.upper(),
            eid,
            message,
        )
        return alert

    def check_all(self) -> list[ProactiveAlert]:
        """Run one synchronous health check pass. Returns new alerts raised."""
        new_alerts: list[ProactiveAlert] = []
        for eid, entity in list(self._entities.items()):
            sample = self._sample_entity(eid, entity)
            if sample is None:
                continue
            ewma = self._update_ewma(eid, sample.health_score)
            trending_down = self._detect_trend(eid, sample.health_score)

            if ewma < self._CRITICAL_THRESHOLD:
                a = self._raise_alert(
                    eid,
                    "critical",
                    f"Health critical: EWMA={ewma:.2f}",
                    {"ewma": ewma, "raw": sample.health_score},
                )
                new_alerts.append(a)
            elif ewma < self._WARNING_THRESHOLD:
                a = self._raise_alert(
                    eid,
                    "warning",
                    f"Health degraded: EWMA={ewma:.2f}",
                    {"ewma": ewma, "raw": sample.health_score},
                )
                new_alerts.append(a)
            elif trending_down:
                a = self._raise_alert(
                    eid,
                    "warning",
                    f"Declining health trend ({self._TREND_WINDOW} samples)",
                    {"samples": self._scores[eid][-self._TREND_WINDOW :]},
                )
                new_alerts.append(a)

            for threat in sample.swot_threats:
                if "CRITICAL" in threat.upper():
                    a = self._raise_alert(eid, "critical", f"SWOT threat: {threat}")
                    new_alerts.append(a)

        return new_alerts

    # ------------------------------------------------------------------
    # Async run loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        self._running = True
        logger.info("ProactiveHealthMonitor started (%d entities)", len(self._entities))
        while self._running:
            try:
                alerts = self.check_all()
                if alerts:
                    logger.info(
                        "ProactiveHealthMonitor: %d new alerts this cycle", len(alerts)
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error("ProactiveHealthMonitor check error: %s", exc)
            await asyncio.sleep(self._CHECK_INTERVAL_S)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self.run(), name="proactive_health_monitor")

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected: task was cancelled

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        unacked = [a for a in self._alerts if not a.acknowledged]
        return {
            "registered_entities": len(self._entities),
            "total_alerts": len(self._alerts),
            "unacknowledged_alerts": len(unacked),
            "ewma_scores": {eid: round(s, 3) for eid, s in self._ewma.items()},
            "critical_entities": [
                eid for eid, s in self._ewma.items() if s < self._CRITICAL_THRESHOLD
            ],
        }

    def acknowledge_alert(self, alert_id: str) -> bool:
        for alert in self._alerts:
            if alert.alert_id == alert_id and not alert.acknowledged:
                alert.acknowledged = True
                conn = None
                try:
                    conn = sqlite3.connect(self._db_path)
                    conn.execute(
                        "UPDATE alerts SET acknowledged=1 WHERE alert_id=?",
                        (alert_id,),
                    )
                    conn.commit()
                except Exception as exc:
                    logger.warning("ProactiveHealthMonitor: failed to persist ack: %s", exc)
                finally:
                    if conn:
                        conn.close()
                return True
        # Alert may have been pruned from in-memory list; try persisted store directly.
        conn = None
        try:
            conn = sqlite3.connect(self._db_path)
            row = conn.execute(
                "SELECT acknowledged FROM alerts WHERE alert_id=?", (alert_id,)
            ).fetchone()
            if row is None or row[0]:
                return False
            conn.execute(
                "UPDATE alerts SET acknowledged=1 WHERE alert_id=?", (alert_id,)
            )
            conn.commit()
            return True
        except Exception as exc:
            logger.warning("ProactiveHealthMonitor: failed to persist ack: %s", exc)
            return False
        finally:
            if conn:
                conn.close()
