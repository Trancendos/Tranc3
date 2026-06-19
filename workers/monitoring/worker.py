"""
Trancendos Monitoring Dashboard — Self-Hosted Worker (The Observatory)
======================================================================
Replaces CF infinity-monitoring-dashboard.
Port: 8007  |  Maps to: The Observatory / monitoring
Zero-cost: SQLite + prometheus_client, no external paid services.

Routes
------
GET  /health                   — {status, uptime, db_size}
GET  /metrics                  — Prometheus text format
GET  /alerts                   — list alerts (?severity=, ?limit=, ?state=)
POST /alerts                   — ingest from Alertmanager webhook
GET  /alerts/{id}              — single alert detail
PATCH /alerts/{id}/resolve     — mark resolved
GET  /snapshots                — metric snapshots (?service=, ?metric=, ?limit=)
GET  /summary                  — platform health summary
WS  /ws/live                   — push new alerts as JSON lines
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from shared_core.error_handlers import safe_error_detail
from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("PORT", 8007))
WORKER_NAME = "the-observatory-monitoring"
PROMETHEUS_URL = os.environ.get("PROMETHEUS_URL", "http://prometheus:9091")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

_data_dir = Path(os.environ.get("DATA_DIR", "/data"))
_data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = _data_dir / "monitoring.db"

# ---------------------------------------------------------------------------
# Logging (structured JSON)
# ---------------------------------------------------------------------------

_LOG_HANDLER = logging.StreamHandler()
_LOG_HANDLER.setFormatter(
    logging.Formatter(
        '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}'
    )
)
logging.basicConfig(level=logging.INFO, handlers=[_LOG_HANDLER])
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Prometheus metrics (self-instrumentation)
# ---------------------------------------------------------------------------

try:
    from prometheus_client import (
        REGISTRY,
        Counter,
        Gauge,
        generate_latest,
    )

    _PROM_AVAILABLE = True
except ImportError:
    _PROM_AVAILABLE = False
    logger.warning("prometheus_client not installed; /metrics returns empty text")

if _PROM_AVAILABLE:
    _alerts_total = Counter(
        "monitoring_alerts_total",
        "Total alerts ingested",
        ["severity"],
        registry=REGISTRY,
    )
    _active_alerts = Gauge(
        "monitoring_active_alerts",
        "Currently firing alerts",
        registry=REGISTRY,
    )
    _snapshots_total = Counter(
        "monitoring_snapshots_total",
        "Total metric snapshots stored",
        registry=REGISTRY,
    )

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_CREATE_ALERTS = """
CREATE TABLE IF NOT EXISTS alerts (
    row_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    id           TEXT NOT NULL,
    name         TEXT NOT NULL,
    severity     TEXT NOT NULL DEFAULT 'warning',
    message      TEXT NOT NULL DEFAULT '',
    fired_at     TEXT NOT NULL,
    resolved_at  TEXT,
    labels_json  TEXT NOT NULL DEFAULT '{}'
)
"""

_CREATE_SNAPSHOTS = """
CREATE TABLE IF NOT EXISTS metrics_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    service      TEXT NOT NULL,
    metric_name  TEXT NOT NULL,
    value        REAL NOT NULL,
    labels_json  TEXT NOT NULL DEFAULT '{}',
    captured_at  TEXT NOT NULL
)
"""

_IDX_ALERTS_ID = "CREATE INDEX IF NOT EXISTS idx_alerts_id     ON alerts(id)"
_IDX_ALERTS_SEV = "CREATE INDEX IF NOT EXISTS idx_alerts_sev    ON alerts(severity)"
_IDX_ALERTS_FIRED = "CREATE INDEX IF NOT EXISTS idx_alerts_fired  ON alerts(fired_at)"
_IDX_SNAP_SVC = "CREATE INDEX IF NOT EXISTS idx_snap_svc      ON metrics_snapshots(service)"
_IDX_SNAP_METRIC = "CREATE INDEX IF NOT EXISTS idx_snap_metric   ON metrics_snapshots(metric_name)"
_IDX_SNAP_CAP = "CREATE INDEX IF NOT EXISTS idx_snap_cap      ON metrics_snapshots(captured_at)"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(_CREATE_ALERTS)
        conn.execute(_CREATE_SNAPSHOTS)
        conn.execute(_IDX_ALERTS_ID)
        conn.execute(_IDX_ALERTS_SEV)
        conn.execute(_IDX_ALERTS_FIRED)
        conn.execute(_IDX_SNAP_SVC)
        conn.execute(_IDX_SNAP_METRIC)
        conn.execute(_IDX_SNAP_CAP)
        conn.commit()
    logger.info("SQLite DB initialised at %s", DB_PATH)


def _db_size_bytes() -> int:
    try:
        return DB_PATH.stat().st_size
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AlertOut(BaseModel):
    id: str
    name: str
    severity: str
    message: str
    fired_at: str
    resolved_at: Optional[str] = None
    labels: Dict[str, Any] = Field(default_factory=dict)


class AlertResolveResponse(BaseModel):
    id: str
    resolved_at: str
    ok: bool = True


class AlertmanagerAlert(BaseModel):
    """One alert entry from Alertmanager's POST body."""

    status: str = "firing"
    labels: Dict[str, Any] = Field(default_factory=dict)
    annotations: Dict[str, Any] = Field(default_factory=dict)
    startsAt: Optional[str] = None
    endsAt: Optional[str] = None
    fingerprint: Optional[str] = None


class AlertmanagerWebhook(BaseModel):
    """Alertmanager webhook payload."""

    version: Optional[str] = None
    groupKey: Optional[str] = None
    status: Optional[str] = None
    receiver: Optional[str] = None
    alerts: List[AlertmanagerAlert] = Field(default_factory=list)


class SnapshotOut(BaseModel):
    id: int
    service: str
    metric_name: str
    value: float
    labels: Dict[str, Any] = Field(default_factory=dict)
    captured_at: str


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    db_size_bytes: int
    db_path: str
    service: str
    port: int


class SummaryResponse(BaseModel):
    firing_total: int
    resolved_total: int
    by_severity: Dict[str, int]
    top_degraded_services: List[str]
    snapshot_count: int


# ---------------------------------------------------------------------------
# WebSocket live-push manager
# ---------------------------------------------------------------------------


class LiveAlertBus:
    """Broadcast new alerts to all connected WebSocket clients."""

    def __init__(self) -> None:
        self._clients: List[WebSocket] = []
        self._lock = asyncio.Lock()

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
        return [dict(r) for r in rows]

    def get_health_history(self, service_name: str, hours: int = 24) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        rows = conn.execute(
            "SELECT * FROM health_reports WHERE service_name=? AND timestamp>=? ORDER BY timestamp ASC",
            (service_name, cutoff),
        ).fetchall()
        return [dict(r) for r in rows]

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
        return [dict(r) for r in rows]

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
        return [dict(r) for r in rows]

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
        async with self._lock:
            self._clients.append(ws)
        logger.info("WS client connected; total=%d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients = [c for c in self._clients if c is not ws]
        logger.info("WS client disconnected; total=%d", len(self._clients))

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
            await self.disconnect(ws)


_bus = LiveAlertBus()

# ---------------------------------------------------------------------------
# Prometheus scrape background task
# ---------------------------------------------------------------------------

# Key Prometheus queries to snapshot every cycle
_PROM_QUERIES: List[Dict[str, str]] = [
    {"metric": "up", "service": "__all__"},
    {"metric": "process_cpu_seconds_total", "service": "__all__"},
    {"metric": "process_resident_memory_bytes", "service": "__all__"},
    {"metric": "http_requests_total", "service": "__all__"},
    {"metric": "http_request_duration_seconds_sum", "service": "__all__"},
]

_SCRAPE_INTERVAL = int(os.environ.get("SCRAPE_INTERVAL_SECONDS", 60))


async def _scrape_prometheus() -> None:
    """Query Prometheus every SCRAPE_INTERVAL seconds and store snapshots."""
    logger.info(
        "Prometheus scraper started; target=%s interval=%ds", PROMETHEUS_URL, _SCRAPE_INTERVAL
    )
    async with httpx.AsyncClient(timeout=10.0) as client:
        while True:
            await asyncio.sleep(_SCRAPE_INTERVAL)
            for q in _PROM_QUERIES:
                metric = q["metric"]
                try:
                    resp = await client.get(
                        f"{PROMETHEUS_URL}/api/v1/query",
                        params={"query": metric},
                    )
                    if resp.status_code != 200:
                        continue
                    data = resp.json()
                    results = data.get("data", {}).get("result", [])
                    now_iso = datetime.now(timezone.utc).isoformat()
                    rows = []
                    for r in results:
                        labels = r.get("metric", {})
                        service = labels.get("job") or labels.get("instance", "unknown")
                        try:
                            value = float(r["value"][1])
                        except (KeyError, IndexError, ValueError):
                            continue
                        rows.append((service, metric, value, json.dumps(labels), now_iso))
                    if rows:
                        with _connect() as conn:
                            conn.executemany(
                                "INSERT INTO metrics_snapshots (service, metric_name, value, labels_json, captured_at) VALUES (?,?,?,?,?)",
                                rows,
                            )
                            conn.commit()
                        if _PROM_AVAILABLE:
                            _snapshots_total.inc(len(rows))
                except Exception as exc:
                    logger.debug("Prometheus scrape failed for %s: %s", metric, exc)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

_START_TIME = time.monotonic()
_background_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.monitoring")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel is optional — never block startup
    global _background_task
    _init_db()
    _background_task = asyncio.create_task(_scrape_prometheus())
    logger.info("%s started on port %d", WORKER_NAME, PORT)
    try:
        yield
    finally:
        if _background_task:
            _background_task.cancel()
            try:
                await _background_task
            except asyncio.CancelledError:
                pass  # expected on graceful shutdown; task was intentionally cancelled
        logger.info("%s shut down", WORKER_NAME)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="The Observatory — Monitoring Dashboard",
    description="Self-hosted alert ingestion, metric snapshots, and live dashboard API.",
    version="2.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


def _require_internal(x_internal_secret: Optional[str]) -> None:
    """Enforce X-Internal-Secret on write/sensitive endpoints when INTERNAL_SECRET is set."""
    if INTERNAL_SECRET and x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


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


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint() -> str:
    """Prometheus text exposition format."""
    if not _PROM_AVAILABLE:
        return "# prometheus_client not installed\n"
    return generate_latest(REGISTRY).decode("utf-8")


@app.get("/alerts", response_model=List[AlertOut])
async def list_alerts(
    severity: Optional[str] = Query(None, description="Filter by severity: info|warning|critical"),
    state: Optional[str] = Query(None, description="Filter by state: firing|resolved"),
    limit: int = Query(100, ge=1, le=1000),
) -> List[AlertOut]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM alerts WHERE"
            " (? IS NULL OR severity = ?)"
            " AND (? IS NULL OR (? = 'firing' AND resolved_at IS NULL)"
            "     OR (? = 'resolved' AND resolved_at IS NOT NULL))"
            " ORDER BY fired_at DESC LIMIT ?",
            (severity, severity, state, state, state, limit),
        ).fetchall()

    return [
        AlertOut(
            id=r["id"],
            name=r["name"],
            severity=r["severity"],
            message=r["message"],
            fired_at=r["fired_at"],
            resolved_at=r["resolved_at"],
            labels=json.loads(r["labels_json"] or "{}"),
        )
        for r in rows
    ]


@app.post("/alerts", status_code=201)
async def ingest_alerts(
    body: AlertmanagerWebhook,
    x_internal_secret: Optional[str] = Header(None),
) -> Dict[str, Any]:
    """Ingest alert(s) from Prometheus Alertmanager webhook."""
    _require_internal(x_internal_secret)
    inserted_ids: List[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    with _connect() as conn:
        for am_alert in body.alerts:
            labels = am_alert.labels
            name = labels.get("alertname", "unknown")
            severity = labels.get("severity", "warning")
            fingerprint = am_alert.fingerprint or str(uuid.uuid4())
            alert_id = fingerprint
            message = am_alert.annotations.get("description") or am_alert.annotations.get(
                "summary", ""
            )
            fired_at = am_alert.startsAt or now_iso

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
                body = resp.json()
            report = HealthReport(
                service_name=svc["name"],
                status=HealthStatus.healthy,
                metadata=body,
            )
            db.store_health(report)
            results.append({"service": svc["name"], "status": "healthy"})
        except Exception as e:
            report = HealthReport(
                service_name=svc["name"],
                status=HealthStatus.unhealthy,
                metadata={"error": str(e)},
            )
            db.store_health(report)
            results.append(
                {"service": svc["name"], "status": "unhealthy", "error": str(e)},
            )

    return {"ok": True, "ingested": len(body.alerts), "new_firing": len(inserted_ids)}


@app.get("/alerts/{alert_id}", response_model=AlertOut)
async def get_alert(alert_id: str) -> AlertOut:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Alert {alert_id!r} not found")
    return AlertOut(
        id=row["id"],
        name=row["name"],
        severity=row["severity"],
        message=row["message"],
        fired_at=row["fired_at"],
        resolved_at=row["resolved_at"],
        labels=json.loads(row["labels_json"] or "{}"),
    )


@app.patch("/alerts/{alert_id}/resolve", response_model=AlertResolveResponse)
async def resolve_alert(
    alert_id: str,
    x_internal_secret: Optional[str] = Header(None),
) -> AlertResolveResponse:
    _require_internal(x_internal_secret)
    resolved_at = datetime.now(timezone.utc).isoformat()
    with _connect() as conn:
        result = conn.execute(
            "UPDATE alerts SET resolved_at = ? WHERE id = ? AND resolved_at IS NULL",
            (resolved_at, alert_id),
        )
        conn.commit()
        if result.rowcount == 0:
            # Check if it exists at all
            exists = conn.execute("SELECT id FROM alerts WHERE id = ?", (alert_id,)).fetchone()
            if not exists:
                raise HTTPException(status_code=404, detail=f"Alert {alert_id!r} not found")
            # Already resolved — return current state
            row = conn.execute(
                "SELECT resolved_at FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            resolved_at = row["resolved_at"]

    if _PROM_AVAILABLE:
        with _connect() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL"
            ).fetchone()[0]
        _active_alerts.set(active)

    await _bus.broadcast(
        {"event": "alert_resolved", "alert_id": alert_id, "resolved_at": resolved_at}
    )
    return AlertResolveResponse(id=alert_id, resolved_at=resolved_at)


@app.get("/snapshots", response_model=List[SnapshotOut])
async def list_snapshots(
    service: Optional[str] = Query(None),
    metric: Optional[str] = Query(None, alias="metric"),
    limit: int = Query(200, ge=1, le=5000),
) -> List[SnapshotOut]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM metrics_snapshots WHERE"
            " (? IS NULL OR service = ?)"
            " AND (? IS NULL OR metric_name = ?)"
            " ORDER BY captured_at DESC LIMIT ?",
            (service, service, metric, metric, limit),
        ).fetchall()

    return [
        SnapshotOut(
            id=r["id"],
            service=r["service"],
            metric_name=r["metric_name"],
            value=r["value"],
            labels=json.loads(r["labels_json"] or "{}"),
            captured_at=r["captured_at"],
        )
        for r in rows
    ]


@app.get("/summary", response_model=SummaryResponse)
async def summary() -> SummaryResponse:
    with _connect() as conn:
        firing_total = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL"
        ).fetchone()[0]
        resolved_total = conn.execute(
            "SELECT COUNT(*) FROM alerts WHERE resolved_at IS NOT NULL"
        ).fetchone()[0]
        sev_rows = conn.execute(
            "SELECT severity, COUNT(*) as c FROM alerts WHERE resolved_at IS NULL GROUP BY severity"
        ).fetchall()
        snap_count = conn.execute("SELECT COUNT(*) FROM metrics_snapshots").fetchone()[0]

        # Services with the most firing alerts = "most degraded"
        degraded_rows = conn.execute(
            "SELECT labels_json FROM alerts WHERE resolved_at IS NULL ORDER BY fired_at DESC LIMIT 100"
        ).fetchall()

    by_severity: Dict[str, int] = {r["severity"]: r["c"] for r in sev_rows}

    # Extract service/job label from firing alert labels
    service_counts: Dict[str, int] = {}
    for row in degraded_rows:
        labels = json.loads(row["labels_json"] or "{}")
        svc = labels.get("job") or labels.get("service") or labels.get("instance", "unknown")
        service_counts[svc] = service_counts.get(svc, 0) + 1

    top_degraded = sorted(service_counts, key=lambda k: -service_counts[k])[:5]

    return SummaryResponse(
        firing_total=firing_total,
        resolved_total=resolved_total,
        by_severity=by_severity,
        top_degraded_services=top_degraded,
        snapshot_count=snap_count,
    )


@app.websocket("/ws/live")
async def ws_live(ws: WebSocket) -> None:
    """Push new alerts as JSON lines to connected clients."""
    await _bus.connect(ws)
    try:
        # Keep connection alive; client can send pings
        while True:
            try:
                text = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                if text.strip() == "ping":
                    await ws.send_text(json.dumps({"event": "pong"}))
            except asyncio.TimeoutError:
                # Send heartbeat
                try:
                    await ws.send_text(
                        json.dumps(
                            {"event": "heartbeat", "ts": datetime.now(timezone.utc).isoformat()}
                        )
                    )
                except Exception:
                    break
    except WebSocketDisconnect:
        pass
    finally:
        await _bus.disconnect(ws)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
