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

import httpx
from fastapi import (
    FastAPI,
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
    id           TEXT PRIMARY KEY,
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

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        async with self._lock:
            self._clients.append(ws)
        logger.info("WS client connected; total=%d", len(self._clients))

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients = [c for c in self._clients if c is not ws]
        logger.info("WS client disconnected; total=%d", len(self._clients))

    async def broadcast(self, payload: dict) -> None:
        msg = json.dumps(payload)
        stale: List[WebSocket] = []
        async with self._lock:
            snapshot = list(self._clients)
        for ws in snapshot:
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
                pass
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


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        uptime_seconds=round(time.monotonic() - _START_TIME, 2),
        db_size_bytes=_db_size_bytes(),
        db_path=str(DB_PATH),
        service=WORKER_NAME,
        port=PORT,
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
    clauses: List[str] = []
    params: List[Any] = []

    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if state == "firing":
        clauses.append("resolved_at IS NULL")
    elif state == "resolved":
        clauses.append("resolved_at IS NOT NULL")

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM alerts {where} ORDER BY fired_at DESC LIMIT ?",
            params,
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
async def ingest_alerts(body: AlertmanagerWebhook) -> Dict[str, Any]:
    """Ingest alert(s) from Prometheus Alertmanager webhook."""
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

            # Upsert — if same fingerprint already exists and is still firing, skip
            existing = conn.execute(
                "SELECT id, resolved_at FROM alerts WHERE id = ?", (alert_id,)
            ).fetchone()
            if existing and existing["resolved_at"] is None and am_alert.status == "firing":
                continue  # already tracked

            if am_alert.status == "resolved":
                resolved_at = am_alert.endsAt or now_iso
                conn.execute(
                    "INSERT INTO alerts (id, name, severity, message, fired_at, resolved_at, labels_json) "
                    "VALUES (?,?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET resolved_at=excluded.resolved_at",
                    (alert_id, name, severity, message, fired_at, resolved_at, json.dumps(labels)),
                )
            else:
                conn.execute(
                    "INSERT OR IGNORE INTO alerts (id, name, severity, message, fired_at, labels_json) "
                    "VALUES (?,?,?,?,?,?)",
                    (alert_id, name, severity, message, fired_at, json.dumps(labels)),
                )
                inserted_ids.append(alert_id)
                if _PROM_AVAILABLE:
                    _alerts_total.labels(severity=severity).inc()

        conn.commit()

    # Update active alert gauge
    if _PROM_AVAILABLE:
        with _connect() as conn:
            active = conn.execute(
                "SELECT COUNT(*) FROM alerts WHERE resolved_at IS NULL"
            ).fetchone()[0]
        _active_alerts.set(active)

    # Broadcast new firing alerts to WebSocket clients
    for alert_id in inserted_ids:
        with _connect() as conn:
            row = conn.execute("SELECT * FROM alerts WHERE id = ?", (alert_id,)).fetchone()
        if row:
            await _bus.broadcast(
                {
                    "event": "alert_fired",
                    "alert": {
                        "id": row["id"],
                        "name": row["name"],
                        "severity": row["severity"],
                        "message": row["message"],
                        "fired_at": row["fired_at"],
                        "labels": json.loads(row["labels_json"] or "{}"),
                    },
                }
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
async def resolve_alert(alert_id: str) -> AlertResolveResponse:
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
    clauses: List[str] = []
    params: List[Any] = []

    if service:
        clauses.append("service = ?")
        params.append(service)
    if metric:
        clauses.append("metric_name = ?")
        params.append(metric)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM metrics_snapshots {where} ORDER BY captured_at DESC LIMIT ?",
            params,
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
