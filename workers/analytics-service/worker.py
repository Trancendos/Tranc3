"""
Trancendos analytics-service — Self-Hosted Worker
==================================================
Event ingestion, metric recording, and reporting API backed by SQLite.
Compatible with a minimal OpenTelemetry-style events model.

Port: 8016
Zero-cost: FastAPI + SQLite (FTS5 for event search), no external deps.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_PORT = 8016
WORKER_NAME = "analytics-service"
DB_PATH = Path(__file__).parent / "data" / "analytics.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                user_id     TEXT,
                session_id  TEXT,
                properties  TEXT DEFAULT '{}',
                timestamp   REAL NOT NULL,
                date_str    TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_ev_type ON events(event_type);
            CREATE INDEX IF NOT EXISTS idx_ev_user ON events(user_id);
            CREATE INDEX IF NOT EXISTS idx_ev_ts   ON events(timestamp);
            CREATE INDEX IF NOT EXISTS idx_ev_date ON events(date_str);

            CREATE TABLE IF NOT EXISTS metrics (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT NOT NULL,
                value     REAL NOT NULL,
                labels    TEXT DEFAULT '{}',
                timestamp REAL NOT NULL,
                date_str  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_m_name ON metrics(name);
            CREATE INDEX IF NOT EXISTS idx_m_ts   ON metrics(timestamp);
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class EventIn(BaseModel):
    event_type: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    properties: Dict[str, Any] = {}
    timestamp: Optional[float] = None


class BatchEventsIn(BaseModel):
    events: List[EventIn]


class MetricIn(BaseModel):
    name: str
    value: float
    labels: Dict[str, Any] = {}
    timestamp: Optional[float] = None


class FunnelStep(BaseModel):
    event_type: str


class FunnelIn(BaseModel):
    steps: List[str] = Field(..., min_length=2)
    user_id: Optional[str] = None
    since: Optional[float] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("analytics-service DB ready")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="analytics-service",
    description="Event analytics and metrics (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    with get_conn() as conn:
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        metric_count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        archive_count = conn.execute("SELECT COUNT(*) FROM events WHERE archived=1").fetchone()[0] if conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='events'").fetchone() else 0
        parquet_total_bytes = 0
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "event_count": event_count,
        "metric_count": metric_count,
        "archive_count": archive_count,
        "parquet_total_bytes": parquet_total_bytes,
    }


@_router.post("/events", status_code=201)
async def ingest_event(ev: EventIn):
    ts = ev.timestamp or time.time()
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (event_type, user_id, session_id, properties, timestamp, date_str) VALUES (?,?,?,?,?,?)",
            (ev.event_type, ev.user_id, ev.session_id, json.dumps(ev.properties), ts, date_str),
        )
        conn.commit()
        return {"id": cur.lastrowid, "event_type": ev.event_type, "timestamp": ts}


@_router.post("/events/batch", status_code=201)
async def ingest_batch(batch: BatchEventsIn):
    rows = []
    for ev in batch.events:
        ts = ev.timestamp or time.time()
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(
            (ev.event_type, ev.user_id, ev.session_id, json.dumps(ev.properties), ts, date_str)
        )
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO events (event_type, user_id, session_id, properties, timestamp, date_str) VALUES (?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
    return {"inserted": len(rows)}


@_router.get("/events")
async def query_events(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    clauses, params = [], []
    if event_type:
        clauses.append("event_type = ?")
        params.append(event_type)
    if user_id:
        clauses.append("user_id = ?")
        params.append(user_id)
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM events {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {
        "total": total,
        "events": [dict(r) for r in rows],
        "limit": limit,
        "offset": offset,
    }


@_router.get("/events/types")
async def event_types():
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type ORDER BY count DESC"
        ).fetchall()
    return {"types": [dict(r) for r in rows]}


@_router.post("/events/funnel")
async def funnel(req: FunnelIn):
    with get_conn() as conn:
        counts = []
        for step in req.steps:
            q = "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type = ? AND user_id IS NOT NULL"
            params: list = [step]
            if req.user_id:
                q += " AND user_id = ?"
                params.append(req.user_id)
            if req.since:
                q += " AND timestamp >= ?"
                params.append(req.since)
            c = conn.execute(q, params).fetchone()[0]
            counts.append({"step": step, "users": c})
    return {"funnel": counts}


@_router.post("/metrics", status_code=201)
async def record_metric(m: MetricIn):
    ts = m.timestamp or time.time()
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO metrics (name, value, labels, timestamp, date_str) VALUES (?,?,?,?,?)",
            (m.name, m.value, json.dumps(m.labels), ts, date_str),
        )
        conn.commit()
    return {"id": cur.lastrowid, "name": m.name, "value": m.value, "timestamp": ts}


@_router.get("/metrics/{name}")
async def get_metric(
    name: str,
    agg: str = Query("avg", pattern="^(avg|sum|min|max|count)$"),
    since: Optional[float] = None,
    until: Optional[float] = None,
):
    clauses = ["name = ?"]
    params: list = [name]
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)
    where = "WHERE " + " AND ".join(clauses)
    agg_fn = {"avg": "AVG", "sum": "SUM", "min": "MIN", "max": "MAX", "count": "COUNT"}[agg]
    with get_conn() as conn:
        row = conn.execute(
            f"SELECT {agg_fn}(value) as result, COUNT(*) as samples FROM metrics {where}", params
        ).fetchone()
    return {"name": name, "aggregation": agg, "result": row["result"], "samples": row["samples"]}


@_router.get("/metrics/{name}/timeseries")
async def metric_timeseries(
    name: str,
    bucket: str = Query("day", pattern="^(hour|day)$"),
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(90, le=365),
):
    fmt = "%Y-%m-%dT%H" if bucket == "hour" else "%Y-%m-%d"
    clauses = ["name = ?"]
    params: list = [name]
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)
    where = "WHERE " + " AND ".join(clauses)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT strftime('{fmt}', timestamp, 'unixepoch') as bucket, AVG(value) as avg, COUNT(*) as samples "
            f"FROM metrics {where} GROUP BY bucket ORDER BY bucket DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return {"name": name, "bucket": bucket, "series": [dict(r) for r in rows]}


@_router.get("/summary")
async def summary():
    with get_conn() as conn:
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        metric_count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        top_events = conn.execute(
            "SELECT event_type, COUNT(*) as c FROM events GROUP BY event_type ORDER BY c DESC LIMIT 5",
        ).fetchall()
        top_metrics = conn.execute(
            "SELECT name, AVG(value) as avg_val FROM metrics GROUP BY name ORDER BY avg_val DESC LIMIT 5",
        ).fetchall()
    return {
        "total_events": event_count,
        "total_metric_points": metric_count,
        "top_event_types": [dict(r) for r in top_events],
        "top_metrics_by_avg": [dict(r) for r in top_metrics],
    }


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
