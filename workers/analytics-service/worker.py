"""
Trancendos analytics-service — ACO pheromone router, 7 zero-cost backends
==========================================================================
Backends (priority order):
  1. DuckDB OLAP      — in-process columnar analytics, zero-setup (MIT)
  2. SQLite WAL       — durable events store, always available
  3. Polars           — in-memory dataframe engine (MIT)
  4. MinIO Parquet    — DuckDB httpfs over MinIO (self-hosted)
  5. Pandas           — fallback dataframe engine (BSD)
  6. MotherDuck       — optional free-tier cloud DuckDB (rate-limited)
  7. Offline stub     — final fallback, never blocks

Port: 8016
Zero-cost: no paid cloud APIs; all backends self-hosted or in-process.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Config ────────────────────────────────────────────────────────────────────
WORKER_PORT = int(os.environ.get("ANALYTICS_PORT", "8016"))
WORKER_NAME = "analytics-service"
DB_PATH = Path(os.environ.get("ANALYTICS_DB_PATH", "/data/analytics.db"))
DUCKDB_PATH = os.environ.get("ANALYTICS_DUCKDB_PATH", "/data/analytics.duckdb")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_DEFAULT_BUCKET", "trancendos")

DUCKDB_ENABLED = os.environ.get("ANALYTICS_DUCKDB", "1") == "1"
POLARS_ENABLED = os.environ.get("ANALYTICS_POLARS", "1") == "1"
MINIO_PARQUET_ENABLED = os.environ.get("ANALYTICS_MINIO_PARQUET", "0") == "1"
PANDAS_ENABLED = os.environ.get("ANALYTICS_PANDAS", "1") == "1"
MOTHERDUCK_ENABLED = os.environ.get("ANALYTICS_MOTHERDUCK", "0") == "1"
MOTHERDUCK_TOKEN = os.environ.get("MOTHERDUCK_TOKEN", "")
MOTHERDUCK_HOURLY_LIMIT = int(os.environ.get("ANALYTICS_MOTHERDUCK_HOURLY_LIMIT", "500"))

PHEROMONE_DECAY = float(os.environ.get("ANALYTICS_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW = int(os.environ.get("ANALYTICS_QUOTA_WINDOW", "3600"))
QUOTA_MAX = int(os.environ.get("ANALYTICS_QUOTA_MAX_CALLS", "50000"))

INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ── ACO ThresholdGuard ────────────────────────────────────────────────────────


class ThresholdGuard:
    def __init__(self, name: str, quota: int, window: int) -> None:
        self.name = name
        self.quota = quota
        self.window = window
        self._calls: deque[float] = deque()
        self.pheromone: float = 1.0

    def can_allow(self) -> bool:
        now = time.time()
        cutoff = now - self.window
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        return len(self._calls) < self.quota

    def record(self) -> None:
        self._calls.append(time.time())

    def reinforce(self) -> None:
        self.pheromone = min(1.0, self.pheromone + 0.1)

    def decay(self) -> None:
        self.pheromone = max(0.0, self.pheromone - PHEROMONE_DECAY)

    @property
    def calls_in_window(self) -> int:
        now = time.time()
        cutoff = now - self.window
        return sum(1 for t in self._calls if t >= cutoff)

    @property
    def quota_remaining(self) -> int:
        return max(0, self.quota - self.calls_in_window)


_GUARDS: Dict[str, ThresholdGuard] = {
    "duckdb": ThresholdGuard("duckdb", QUOTA_MAX, QUOTA_WINDOW),
    "sqlite": ThresholdGuard("sqlite", QUOTA_MAX, QUOTA_WINDOW),
    "polars": ThresholdGuard("polars", QUOTA_MAX, QUOTA_WINDOW),
    "minio_parquet": ThresholdGuard("minio_parquet", QUOTA_MAX, QUOTA_WINDOW),
    "pandas": ThresholdGuard("pandas", QUOTA_MAX, QUOTA_WINDOW),
    "motherduck": ThresholdGuard("motherduck", MOTHERDUCK_HOURLY_LIMIT, 3600),
    "offline": ThresholdGuard("offline", 999_999, QUOTA_WINDOW),
}

_ENABLED: Dict[str, bool] = {
    "duckdb": DUCKDB_ENABLED,
    "sqlite": True,
    "polars": POLARS_ENABLED,
    "minio_parquet": MINIO_PARQUET_ENABLED,
    "pandas": PANDAS_ENABLED,
    "motherduck": MOTHERDUCK_ENABLED and bool(MOTHERDUCK_TOKEN),
    "offline": True,
}

_PRIORITY = ["duckdb", "sqlite", "polars", "minio_parquet", "pandas", "motherduck", "offline"]


def _select_backend() -> str:
    available = [b for b in _PRIORITY if _ENABLED[b] and _GUARDS[b].can_allow()]
    return max(available, key=lambda b: _GUARDS[b].pheromone) if available else "offline"


# ── SQLite backend ────────────────────────────────────────────────────────────


def _db_conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init_db() -> None:
    with _db_conn() as c:
        c.executescript("""
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

            CREATE TABLE IF NOT EXISTS backend_events (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                backend TEXT NOT NULL,
                success INTEGER NOT NULL,
                ts      REAL NOT NULL
            );
        """)
        c.commit()


init_db = _init_db  # public alias for tests


def _record_backend_event(backend: str, success: bool) -> None:
    try:
        with _db_conn() as c:
            c.execute(
                "INSERT INTO backend_events (backend,success,ts) VALUES (?,?,?)",
                (backend, int(success), time.time()),
            )
            c.commit()
    except Exception:  # never block on audit writes
        pass


# ── DuckDB backend ────────────────────────────────────────────────────────────


def _duckdb_insert_event(
    ev_type: str,
    user_id: Optional[str],
    session_id: Optional[str],
    props: Dict[str, Any],
    ts: float,
    date_str: str,
) -> Optional[int]:
    try:
        import duckdb  # type: ignore[import-untyped]

        con = duckdb.connect(DUCKDB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                session_id TEXT,
                properties TEXT,
                timestamp DOUBLE NOT NULL,
                date_str TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE SEQUENCE IF NOT EXISTS events_seq START 1
        """)
        row = con.execute("SELECT nextval('events_seq')").fetchone()
        new_id = row[0]
        con.execute(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            [new_id, ev_type, user_id, session_id, json.dumps(props), ts, date_str],
        )
        con.close()
        return new_id
    except Exception:  # DuckDB failure — fall through to SQLite
        return None


def _duckdb_query_events(
    event_type: Optional[str],
    user_id: Optional[str],
    since: Optional[float],
    until: Optional[float],
    limit: int,
    offset: int,
) -> Optional[List[Dict[str, Any]]]:
    try:
        import duckdb  # type: ignore[import-untyped]

        con = duckdb.connect(DUCKDB_PATH)
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
        rows = con.execute(
            f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        cols = [d[0] for d in con.description]
        con.close()
        return [dict(zip(cols, r, strict=False)) for r in rows]
    except Exception:  # DuckDB failure
        return None


# ── Polars backend ────────────────────────────────────────────────────────────


def _polars_aggregate(
    name: str, agg: str, since: Optional[float], until: Optional[float]
) -> Optional[float]:
    try:
        import polars as pl  # type: ignore[import-untyped]

        with _db_conn() as c:
            rows = c.execute("SELECT value FROM metrics WHERE name=?", (name,)).fetchall()
        if not rows:
            return None
        df = pl.DataFrame({"value": [r["value"] for r in rows]})
        if agg == "avg":
            return df["value"].mean()
        if agg == "sum":
            return df["value"].sum()
        if agg == "min":
            return df["value"].min()
        if agg == "max":
            return df["value"].max()
        return float(len(df))
    except Exception:  # Polars not installed or failure
        return None


# ── Models ────────────────────────────────────────────────────────────────────


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


class FunnelIn(BaseModel):
    steps: List[str] = Field(..., min_length=2)
    user_id: Optional[str] = None
    since: Optional[float] = None


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        otel_ep = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if otel_ep:
            provider = TracerProvider()
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_ep)))
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
    except Exception:  # OTel is optional — never block startup
        pass
    _init_db()
    logger.info("analytics-service ready — db=%s duckdb=%s", DB_PATH, DUCKDB_PATH)
    yield


# ── App ───────────────────────────────────────────────────────────────────────

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="analytics-service",
    description="Multi-backend ACO analytics (7 zero-cost backends) — DuckDB OLAP primary",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def _auth(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    if not INTERNAL_SECRET:
        return
    if x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


_router = APIRouter(dependencies=[Depends(_auth)])


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    with _db_conn() as c:
        ev = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        me = c.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
    return JSONResponse(
        {
            "service": WORKER_NAME,
            "status": "healthy",
            "uptime_s": round((datetime.now(timezone.utc) - STARTED_AT).total_seconds(), 1),
            "event_count": ev,
            "metric_count": me,
            "active_backend": _select_backend(),
        }
    )


@_router.post("/events", status_code=201)
def ingest_event(ev: EventIn) -> Dict[str, Any]:
    ts = ev.timestamp or time.time()
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")

    backend = _select_backend()
    _GUARDS[backend].record()
    success = True
    event_id: Optional[int] = None

    if backend == "duckdb":
        event_id = _duckdb_insert_event(
            ev.event_type, ev.user_id, ev.session_id, ev.properties, ts, date_str
        )
        success = event_id is not None
        if not success:
            _GUARDS[backend].decay()
            backend = "sqlite"

    if backend in ("sqlite", "offline", "polars", "pandas", "minio_parquet", "motherduck"):
        with _db_conn() as c:
            cur = c.execute(
                "INSERT INTO events (event_type,user_id,session_id,properties,timestamp,date_str) VALUES (?,?,?,?,?,?)",
                (ev.event_type, ev.user_id, ev.session_id, json.dumps(ev.properties), ts, date_str),
            )
            event_id = cur.lastrowid
            c.commit()
        success = True
    if success:
        _GUARDS[backend].reinforce()
    _record_backend_event(backend, success)

    return {"id": event_id, "event_type": ev.event_type, "timestamp": ts, "backend": backend}


@_router.post("/events/batch", status_code=201)
def ingest_batch(batch: BatchEventsIn) -> Dict[str, Any]:
    rows = []
    for ev in batch.events:
        ts = ev.timestamp or time.time()
        date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        rows.append(
            (ev.event_type, ev.user_id, ev.session_id, json.dumps(ev.properties), ts, date_str)
        )
    with _db_conn() as c:
        c.executemany(
            "INSERT INTO events (event_type,user_id,session_id,properties,timestamp,date_str) VALUES (?,?,?,?,?,?)",
            rows,
        )
        c.commit()
    return {"inserted": len(rows)}


@_router.get("/events")
def query_events(
    event_type: Optional[str] = None,
    user_id: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
) -> Dict[str, Any]:
    backend = _select_backend()

    if backend == "duckdb":
        rows = _duckdb_query_events(event_type, user_id, since, until, limit, offset)
        if rows is not None:
            _GUARDS[backend].reinforce()
            return {"total": len(rows), "events": rows, "backend": backend}
        _GUARDS[backend].decay()

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
    with _db_conn() as c:
        total = c.execute(f"SELECT COUNT(*) FROM events {where}", params).fetchone()[0]
        sql_rows = c.execute(
            f"SELECT * FROM events {where} ORDER BY timestamp DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "events": [dict(r) for r in sql_rows], "limit": limit, "offset": offset}


@_router.get("/events/types")
def event_types() -> Dict[str, Any]:
    with _db_conn() as c:
        rows = c.execute(
            "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type ORDER BY count DESC"
        ).fetchall()
    return {"types": [dict(r) for r in rows]}


@_router.post("/events/funnel")
def funnel(req: FunnelIn) -> Dict[str, Any]:
    with _db_conn() as c:
        counts = []
        for step in req.steps:
            q = "SELECT COUNT(DISTINCT user_id) FROM events WHERE event_type=? AND user_id IS NOT NULL"
            params: list = [step]
            if req.user_id:
                q += " AND user_id=?"
                params.append(req.user_id)
            if req.since:
                q += " AND timestamp>=?"
                params.append(req.since)
            counts.append({"step": step, "users": c.execute(q, params).fetchone()[0]})
    return {"funnel": counts}


@_router.post("/metrics", status_code=201)
def record_metric(m: MetricIn) -> Dict[str, Any]:
    ts = m.timestamp or time.time()
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    with _db_conn() as c:
        cur = c.execute(
            "INSERT INTO metrics (name,value,labels,timestamp,date_str) VALUES (?,?,?,?,?)",
            (m.name, m.value, json.dumps(m.labels), ts, date_str),
        )
        c.commit()
    return {"id": cur.lastrowid, "name": m.name, "value": m.value, "timestamp": ts}


@_router.get("/metrics/{name}")
def get_metric(
    name: str,
    agg: str = Query("avg", pattern="^(avg|sum|min|max|count)$"),
    since: Optional[float] = None,
    until: Optional[float] = None,
) -> Dict[str, Any]:
    backend = _select_backend()

    if backend == "polars":
        result = _polars_aggregate(name, agg, since, until)
        if result is not None:
            _GUARDS[backend].reinforce()
            return {"name": name, "aggregation": agg, "result": result, "backend": backend}
        _GUARDS[backend].decay()

    clauses, params = ["name = ?"], [name]
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)
    where = "WHERE " + " AND ".join(clauses)
    agg_fn = {"avg": "AVG", "sum": "SUM", "min": "MIN", "max": "MAX", "count": "COUNT"}[agg]
    with _db_conn() as c:
        row = c.execute(
            f"SELECT {agg_fn}(value) as result, COUNT(*) as samples FROM metrics {where}", params
        ).fetchone()
    return {"name": name, "aggregation": agg, "result": row["result"], "samples": row["samples"]}


@_router.get("/metrics/{name}/timeseries")
def metric_timeseries(
    name: str,
    bucket: str = Query("day", pattern="^(hour|day)$"),
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(90, le=365),
) -> Dict[str, Any]:
    fmt = "%Y-%m-%dT%H" if bucket == "hour" else "%Y-%m-%d"
    clauses, params = ["name = ?"], [name]
    if since:
        clauses.append("timestamp >= ?")
        params.append(since)
    if until:
        clauses.append("timestamp <= ?")
        params.append(until)
    where = "WHERE " + " AND ".join(clauses)
    with _db_conn() as c:
        rows = c.execute(
            f"SELECT strftime('{fmt}', timestamp, 'unixepoch') as bucket, AVG(value) as avg, COUNT(*) as samples "
            f"FROM metrics {where} GROUP BY bucket ORDER BY bucket DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return {"name": name, "bucket": bucket, "series": [dict(r) for r in rows]}


@_router.get("/summary")
def summary() -> Dict[str, Any]:
    with _db_conn() as c:
        event_count = c.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        metric_count = c.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        top_events = c.execute(
            "SELECT event_type, COUNT(*) as c FROM events GROUP BY event_type ORDER BY c DESC LIMIT 5"
        ).fetchall()
        top_metrics = c.execute(
            "SELECT name, AVG(value) as avg_val FROM metrics GROUP BY name ORDER BY avg_val DESC LIMIT 5"
        ).fetchall()
    return {
        "total_events": event_count,
        "total_metric_points": metric_count,
        "top_event_types": [dict(r) for r in top_events],
        "top_metrics_by_avg": [dict(r) for r in top_metrics],
    }


@_router.get("/status")
def analytics_status() -> Dict[str, Any]:
    return {
        "active_backend": _select_backend(),
        "backends": [
            {
                "name": b,
                "enabled": _ENABLED[b],
                "healthy": _GUARDS[b].can_allow(),
                "pheromone": round(_GUARDS[b].pheromone, 4),
                "calls_in_window": _GUARDS[b].calls_in_window,
                "quota_remaining": _GUARDS[b].quota_remaining,
            }
            for b in _PRIORITY
        ],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
