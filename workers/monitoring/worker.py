"""
Trancendos Monitoring Dashboard — Self-Hosted Worker (The Observatory)
======================================================================
Replaces CF infinity-monitoring-dashboard.
Provides health aggregation, metrics collection, alerting, and dashboard API.

Port: 8007
Maps to: The Observatory / monitoring
Zero-cost: All data stored in SQLite, no external metrics services required.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import sys
import threading
import uuid

sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8007
WORKER_NAME = "the-observatory"
DB_PATH = Path(__file__).parent / "data" / "monitoring.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class HealthStatus(str, Enum):
    healthy = "healthy"
    degraded = "degraded"
    unhealthy = "unhealthy"
    unknown = "unknown"


class MetricType(str, Enum):
    counter = "counter"
    gauge = "gauge"
    histogram = "histogram"


class AlertSeverity(str, Enum):
    info = "info"
    warning = "warning"
    critical = "critical"


class AlertState(str, Enum):
    firing = "firing"
    resolved = "resolved"
    silenced = "silenced"


class HealthReport(BaseModel):
    service_name: str
    status: HealthStatus
    response_time_ms: Optional[float] = None
    error_rate: Optional[float] = None
    uptime_seconds: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetricPayload(BaseModel):
    name: str
    type: MetricType
    value: float
    labels: Dict[str, str] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AlertRule(BaseModel):
    rule_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    metric_name: str
    condition: str  # e.g. "> 90", "< 1", "== 0"
    threshold: float
    severity: AlertSeverity = AlertSeverity.warning
    for_duration_seconds: int = 60
    labels: Dict[str, str] = Field(default_factory=dict)
    enabled: bool = True


class Alert(BaseModel):
    alert_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    rule_id: str
    name: str
    severity: AlertSeverity
    state: AlertState = AlertState.firing
    message: str = ""
    labels: Dict[str, str] = Field(default_factory=dict)
    fired_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None


class DashboardPanel(BaseModel):
    panel_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    type: str  # "line_chart", "stat", "table", "gauge"
    metric_names: List[str]
    refresh_interval_seconds: int = 30
    labels_filter: Dict[str, str] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class MonitoringDatabase:
    """SQLite-backed storage for metrics, health reports, alerts, and rules."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS health_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    response_time_ms REAL,
                    error_rate REAL,
                    uptime_seconds REAL,
                    metadata TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    type TEXT NOT NULL,
                    value REAL NOT NULL,
                    labels TEXT DEFAULT '{}',
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alert_rules (
                    rule_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    metric_name TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    threshold REAL NOT NULL,
                    severity TEXT NOT NULL DEFAULT 'warning',
                    for_duration_seconds INTEGER DEFAULT 60,
                    labels TEXT DEFAULT '{}',
                    enabled INTEGER DEFAULT 1
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    alert_id TEXT PRIMARY KEY,
                    rule_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'firing',
                    message TEXT DEFAULT '',
                    labels TEXT DEFAULT '{}',
                    fired_at TEXT NOT NULL,
                    resolved_at TEXT
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_health_service ON health_reports(service_name)"
            )
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_health_timestamp ON health_reports(timestamp)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(name)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_metrics_timestamp ON metrics(timestamp)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_state ON alerts(state)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_alerts_fired ON alerts(fired_at)")

    # -- Health Reports --

    def store_health(self, report: HealthReport):
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO health_reports (service_name, status, response_time_ms, error_rate, uptime_seconds, metadata, timestamp) VALUES (?,?,?,?,?,?,?)",
                (
                    report.service_name,
                    report.status.value,
                    report.response_time_ms,
                    report.error_rate,
                    report.uptime_seconds,
                    json.dumps(report.metadata),
                    report.timestamp.isoformat(),
                ),
            )

    @staticmethod
    def _parse_health_row(r: sqlite3.Row) -> Dict[str, Any]:
        d = dict(r)
        d["metadata"] = json.loads(d.get("metadata") or "{}")
        return d

    def get_latest_health(self, service_name: Optional[str] = None) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if service_name:
            rows = conn.execute(
                "SELECT * FROM health_reports WHERE service_name=? ORDER BY timestamp DESC LIMIT 1",
                (service_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT hr.* FROM health_reports hr INNER JOIN (SELECT service_name, MAX(timestamp) as max_ts FROM health_reports GROUP BY service_name) latest ON hr.service_name = latest.service_name AND hr.timestamp = latest.max_ts",
            ).fetchall()
        return [self._parse_health_row(r) for r in rows]

    def get_health_history(self, service_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT * FROM health_reports WHERE service_name=? AND timestamp>=? ORDER BY timestamp ASC",
            (service_name, cutoff),
        ).fetchall()
        return [self._parse_health_row(r) for r in rows]

    # -- Metrics --

    def store_metric(self, metric: MetricPayload):
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO metrics (name, type, value, labels, timestamp) VALUES (?,?,?,?,?)",
                (
                    metric.name,
                    metric.type.value,
                    metric.value,
                    json.dumps(metric.labels),
                    metric.timestamp.isoformat(),
                ),
            )

    def store_metrics_batch(self, metrics: List[MetricPayload]):
        with self._cursor() as cur:
            cur.executemany(
                "INSERT INTO metrics (name, type, value, labels, timestamp) VALUES (?,?,?,?,?)",
                [
                    (m.name, m.type.value, m.value, json.dumps(m.labels), m.timestamp.isoformat())
                    for m in metrics
                ],
            )

    def query_metrics(
        self, name: str, hours: int = 1, labels: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        if labels:
            rows = conn.execute(
                "SELECT * FROM metrics WHERE name=? AND timestamp>=? ORDER BY timestamp ASC",
                (name, cutoff),
            ).fetchall()
            # Filter by labels in Python (simple approach)
            result = []
            for r in rows:
                d = dict(r)
                m_labels = json.loads(d.get("labels", "{}"))
                if all(m_labels.get(k) == v for k, v in labels.items()):
                    result.append(d)
            return result
        rows = conn.execute(
            "SELECT * FROM metrics WHERE name=? AND timestamp>=? ORDER BY timestamp ASC",
            (name, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

    def get_metric_names(self) -> List[str]:
        conn = self._get_conn()
        rows = conn.execute("SELECT DISTINCT name FROM metrics ORDER BY name").fetchall()
        return [r["name"] for r in rows]

    # -- Alert Rules --

    def create_alert_rule(self, rule: AlertRule) -> AlertRule:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO alert_rules (rule_id, name, metric_name, condition, threshold, severity, for_duration_seconds, labels, enabled) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    rule.rule_id,
                    rule.name,
                    rule.metric_name,
                    rule.condition,
                    rule.threshold,
                    rule.severity.value,
                    rule.for_duration_seconds,
                    json.dumps(rule.labels),
                    int(rule.enabled),
                ),
            )
        return rule

    def get_alert_rules(self, enabled_only: bool = False) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if enabled_only:
            rows = conn.execute(
                "SELECT * FROM alert_rules WHERE enabled=1 ORDER BY name"
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM alert_rules ORDER BY name").fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["labels"] = json.loads(d.get("labels") or "{}")
            result.append(d)
        return result

    def delete_alert_rule(self, rule_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM alert_rules WHERE rule_id=?", (rule_id,))
            return cur.rowcount > 0

    # -- Alerts --

    def create_alert(self, alert: Alert) -> Alert:
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO alerts (alert_id, rule_id, name, severity, state, message, labels, fired_at, resolved_at) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    alert.alert_id,
                    alert.rule_id,
                    alert.name,
                    alert.severity.value,
                    alert.state.value,
                    alert.message,
                    json.dumps(alert.labels),
                    alert.fired_at.isoformat(),
                    alert.resolved_at.isoformat() if alert.resolved_at else None,
                ),
            )
        return alert

    def get_alerts(
        self, state: Optional[AlertState] = None, hours: Optional[int] = 168
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        if hours is not None:
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            if state:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE state=? AND fired_at>=? ORDER BY fired_at DESC",
                    (state.value, cutoff),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE fired_at>=? ORDER BY fired_at DESC",
                    (cutoff,),
                ).fetchall()
        else:
            if state:
                rows = conn.execute(
                    "SELECT * FROM alerts WHERE state=? ORDER BY fired_at DESC",
                    (state.value,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM alerts ORDER BY fired_at DESC",
                ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["labels"] = json.loads(d.get("labels") or "{}")
            result.append(d)
        return result

    def resolve_alert(self, alert_id: str) -> bool:
        with self._cursor() as cur:
            now = datetime.now(timezone.utc).isoformat()
            cur.execute(
                "UPDATE alerts SET state='resolved', resolved_at=? WHERE alert_id=?",
                (now, alert_id),
            )
            return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Alert Engine
# ---------------------------------------------------------------------------


class AlertEngine:
    """Evaluates alert rules against incoming metrics and fires/resolves alerts."""

    def __init__(self, db: MonitoringDatabase):
        self.db = db
        self._metric_buffer: Dict[str, List[tuple]] = defaultdict(
            list
        )  # rule_id -> [(value, timestamp)]

    def evaluate(self, metric: MetricPayload):
        """Evaluate all enabled rules against a new metric."""
        rules = self.db.get_alert_rules(enabled_only=True)
        for rule in rules:
            if rule["metric_name"] != metric.name:
                continue
            self._check_rule(rule, metric)

    def _check_rule(self, rule: Dict[str, Any], metric: MetricPayload):
        threshold = rule["threshold"]
        value = metric.value
        condition = rule["condition"]
        triggered = self._evaluate_condition(value, condition, threshold)

        if triggered:
            # Check if there's already a firing alert for this rule (no time limit for dedup)
            firing = self.db.get_alerts(state=AlertState.firing, hours=None)
            existing = [a for a in firing if a["rule_id"] == rule["rule_id"]]
            if not existing:
                alert = Alert(
                    rule_id=rule["rule_id"],
                    name=rule["name"],
                    severity=AlertSeverity(rule["severity"]),
                    message=f"{metric.name} {condition} {threshold} (current: {value})",
                    labels=json.loads(rule.get("labels", "{}")),
                )
                self.db.create_alert(alert)
                logger.warning("🔔 Alert fired: %s — %s", alert.name, alert.message)
        else:
            # Auto-resolve firing alerts for this rule if condition no longer met (no time limit)
            firing = self.db.get_alerts(state=AlertState.firing, hours=None)
            for a in firing:
                if a["rule_id"] == rule["rule_id"]:
                    self.db.resolve_alert(a["alert_id"])
                    logger.info("✅ Alert resolved: %s", a["name"])

    @staticmethod
    def _evaluate_condition(value: float, condition: str, threshold: float) -> bool:
        try:
            if condition.startswith(">="):
                return value >= threshold
            elif condition.startswith("<="):
                return value <= threshold
            elif condition.startswith(">"):
                return value > threshold
            elif condition.startswith("<"):
                return value < threshold
            elif condition.startswith("=="):
                return value == threshold
            elif condition.startswith("!="):
                return value != threshold
        except Exception:
            logger.debug("Graceful degradation in Exception")  # nosec B110
        return False


# ---------------------------------------------------------------------------
# WebSocket Manager for Live Dashboard
# ---------------------------------------------------------------------------


class DashboardWSManager:
    """Manages WebSocket connections for live dashboard updates."""

    def __init__(self):
        self.connections: List[WebSocket] = []
        self._lock = threading.Lock()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        with self._lock:
            self.connections.append(ws)
        logger.info("Dashboard WebSocket connected. Total: %d", len(self.connections))

    def disconnect(self, ws: WebSocket):
        with self._lock:
            if ws in self.connections:
                self.connections.remove(ws)
        logger.info("Dashboard WebSocket disconnected. Total: %d", len(self.connections))

    async def broadcast(self, event_type: str, data: Any):
        msg = json.dumps(
            {"type": event_type, "data": data, "timestamp": datetime.now(timezone.utc).isoformat()}
        )
        # Snapshot the connection list under the lock, then send outside to avoid
        # awaiting while holding a threading.Lock (which would block the event loop).
        with self._lock:
            conns = list(self.connections)
        stale = []
        for ws in conns:
            try:
                await ws.send_text(msg)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ws)


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

db = MonitoringDatabase(DB_PATH)
alert_engine = AlertEngine(db)
ws_manager = DashboardWSManager()

app = FastAPI(
    title="The Observatory — Monitoring Dashboard",
    description="Self-hosted monitoring, metrics, alerting, and dashboard API. Replaces CF infinity-monitoring-dashboard.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

try:
    from src.observability.worker_setup import instrument_worker

    instrument_worker(app, service_name="tranc3.monitoring")
except Exception as _otel_exc:  # noqa: BLE001
    logger.warning("OTel instrumentation unavailable: %s", _otel_exc)


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
STARTED_AT = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Health & Info
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": uptime,
        "version": "1.0.0",
        "entity": {
            "location": "The Observatory",
            "pillar": "Knowledge",
            "lead_ai": "Norman Hawkins",
            "primes": ["Cornelius MacIntyre"],
            "primary_function": "Audit Log & Monitoring Platform",
        },
    }


@_router.get("/stats")
async def stats():
    """Overview statistics for the monitoring system."""
    return _get_stats_data()


# ---------------------------------------------------------------------------
# Health Reports
# ---------------------------------------------------------------------------


@_router.post("/health/report")
async def submit_health_report(report: HealthReport):
    """Submit a health report for a service."""
    db.store_health(report)
    await ws_manager.broadcast(
        "health_update", {"service": report.service_name, "status": report.status.value}
    )
    return {"ok": True, "service": report.service_name, "status": report.status.value}


@_router.get("/health/services")
async def list_service_health():
    """Get latest health status for all services."""
    return {"services": db.get_latest_health()}


@_router.get("/health/services/{service_name}")
async def get_service_health(service_name: str, hours: int = Query(24, ge=1, le=168)):
    """Get health history for a specific service."""
    history = db.get_health_history(service_name, hours=hours)
    if not history:
        raise HTTPException(404, f"No health data for service: {service_name}")
    return {"service": service_name, "history": history}


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------


@_router.post("/metrics")
async def submit_metric(metric: MetricPayload):
    """Submit a single metric data point."""
    db.store_metric(metric)
    alert_engine.evaluate(metric)
    await ws_manager.broadcast("metric_update", {"name": metric.name, "value": metric.value})
    return {"ok": True, "name": metric.name, "value": metric.value}


@_router.post("/metrics/batch")
async def submit_metrics_batch(metrics: List[MetricPayload]):
    """Submit multiple metric data points at once."""
    db.store_metrics_batch(metrics)
    for m in metrics:
        alert_engine.evaluate(m)
    await ws_manager.broadcast("metrics_batch", {"count": len(metrics)})
    return {"ok": True, "count": len(metrics)}


@_router.get("/metrics/names")
async def list_metric_names():
    """List all distinct metric names."""
    return {"names": db.get_metric_names()}


@_router.get("/metrics/query")
async def query_metrics(
    name: str = Query(..., description="Metric name"),
    hours: int = Query(1, ge=1, le=168),
    labels: Optional[str] = Query(None, description="JSON labels filter"),
):
    """Query metric data points by name and optional labels."""
    labels_dict = json.loads(labels) if labels else None
    data = db.query_metrics(name, hours=hours, labels=labels_dict)
    return {"name": name, "data_points": len(data), "metrics": data}


# ---------------------------------------------------------------------------
# Alert Rules
# ---------------------------------------------------------------------------


@_router.post("/alerts/rules")
async def create_alert_rule(rule: AlertRule):
    """Create a new alert rule."""
    created = db.create_alert_rule(rule)
    await ws_manager.broadcast("alert_rule_created", {"rule_id": rule.rule_id, "name": rule.name})
    return {"ok": True, "rule": created}


@_router.get("/alerts/rules")
async def list_alert_rules(enabled_only: bool = False):
    """List all alert rules."""
    return {"rules": db.get_alert_rules(enabled_only=enabled_only)}


@_router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(rule_id: str):
    """Delete an alert rule."""
    if not db.delete_alert_rule(rule_id):
        raise HTTPException(404, f"Alert rule not found: {rule_id}")
    return {"ok": True, "deleted": rule_id}


# ---------------------------------------------------------------------------
# Alerts
# ---------------------------------------------------------------------------


@_router.get("/alerts")
async def list_alerts(
    state: Optional[AlertState] = None,
    hours: int = Query(168, ge=1, le=720),
):
    """List alerts, optionally filtered by state."""
    return {"alerts": db.get_alerts(state=state, hours=hours)}


@_router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    """Manually resolve an alert."""
    if not db.resolve_alert(alert_id):
        raise HTTPException(404, f"Alert not found: {alert_id}")
    await ws_manager.broadcast("alert_resolved", {"alert_id": alert_id})
    return {"ok": True, "resolved": alert_id}


# ---------------------------------------------------------------------------
# Dashboard WebSocket
# ---------------------------------------------------------------------------


def _get_stats_data() -> dict:
    """Internal helper returning stats payload — shared by HTTP and WebSocket handlers."""
    services = db.get_latest_health()
    firing_alerts = db.get_alerts(state=AlertState.firing)
    metric_names = db.get_metric_names()
    return {
        "services_monitored": len(services),
        "healthy_services": sum(1 for s in services if s.get("status") == "healthy"),
        "degraded_services": sum(1 for s in services if s.get("status") == "degraded"),
        "unhealthy_services": sum(1 for s in services if s.get("status") == "unhealthy"),
        "firing_alerts": len(firing_alerts),
        "total_metric_names": len(metric_names),
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


@app.websocket("/ws/dashboard")
async def dashboard_websocket(
    ws: WebSocket,
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
):
    """WebSocket endpoint for live dashboard updates."""
    if _INTERNAL_SECRET and x_internal_secret != _INTERNAL_SECRET:
        await ws.close(code=1008)
        return
    await ws_manager.connect(ws)
    try:
        while True:
            data = await ws.receive_text()
            # Client can request specific data
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_text(json.dumps({"type": "pong"}))
                elif msg.get("type") == "get_stats":
                    stats_data = _get_stats_data()
                    await ws.send_text(json.dumps({"type": "stats", "data": stats_data}))
            except json.JSONDecodeError:
                logger.debug("Graceful degradation in json")  # nosec B110
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Self-Monitoring: Periodic health collection from known services
# ---------------------------------------------------------------------------

KNOWN_SERVICES = [
    {"name": "tranc3-ai", "url": "http://localhost:8001/health"},
    {"name": "infinity-void", "url": "http://localhost:8002/health"},
    {"name": "api-gateway", "url": "http://localhost:8003/health"},
    {"name": "infinity-ws", "url": "http://localhost:8004/health"},
    {"name": "infinity-auth", "url": "http://localhost:8005/health"},
    {"name": "users-service", "url": "http://localhost:8006/health"},
    {"name": "notifications-service", "url": "http://localhost:8008/health"},
    {"name": "infinity-ai", "url": "http://localhost:8009/health"},
]


@_router.post("/monitoring/collect")
async def collect_health():
    """Trigger health collection from all known services. Called by scheduler or manually."""
    import httpx

    results = []
    for svc in KNOWN_SERVICES:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(svc["url"], headers={"Accept": "application/json"})
            body = resp.json() if "application/json" in resp.headers.get("content-type", "") else {}
            status = HealthStatus.healthy if resp.is_success else HealthStatus.unhealthy
            report = HealthReport(
                service_name=svc["name"],
                status=status,
                response_time_ms=resp.elapsed.total_seconds() * 1000 if resp.elapsed else None,
                metadata=body,
            )
            db.store_health(report)
            results.append({"service": svc["name"], "status": "healthy"})
        except Exception as e:
            report = HealthReport(
                service_name=svc["name"],
                status=HealthStatus.unhealthy,
                metadata={"error": str(e)[:200]},
            )
            db.store_health(report)
            results.append(
                {"service": svc["name"], "status": "unhealthy", "error": str(e)[:200]},
            )

    await ws_manager.broadcast("health_collection", {"results": results})
    return {"collected": len(results), "results": results}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
