"""
Trancendos analytics-service — DuckDB OLAP Layer
=================================================
Event ingestion (SQLite hot path) + analytical queries (DuckDB OLAP engine).

Architecture
------------
  Hot path   : events/metrics written to encrypted SQLite — O(1) inserts, WAL mode
  OLAP path  : DuckDB attaches SQLite directly (sqlite_scanner) for vectorised
               columnar queries — no ETL pipeline, no data duplication
  Archive    : nightly background task exports events older than ARCHIVE_AFTER_DAYS
               to per-month Parquet files; DuckDB union-queries live + archived data
               transparently via the `all_events` view
  Cross-svc  : DuckDB can attach other worker SQLite databases (audit, monitoring)
               via the /analytics/query endpoint — the natural integration point for
               The Dutchy (Intelligence & Market Analysis, port 8016 → The Dutchy)

Endpoints
---------
  POST /events                   ingest single event
  POST /events/batch             ingest up to 1 000 events
  GET  /events                   paginated event query
  GET  /events/types             event type counts
  POST /events/funnel            ordered funnel conversion
  POST /metrics                  record metric point
  GET  /metrics/{name}           aggregate metric value
  GET  /metrics/{name}/timeseries  bucketed timeseries
  GET  /analytics/dau            daily / weekly / monthly active users
  GET  /analytics/retention      cohort retention (day-1, day-7, day-30)
  GET  /analytics/sessions       session depth, duration, bounce rate
  GET  /analytics/journeys       top N event sequences per session
  GET  /analytics/platform       cross-service platform-wide summary
  POST /analytics/query          arbitrary DuckDB SELECT (OLAP power query)
  POST /analytics/archive        trigger Parquet archival manually
  GET  /summary                  quick dashboard summary
  GET  /health                   health + row counts

Port: 8016  |  Zero-cost: FastAPI + SQLite + DuckDB (in-process, no server)
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator

from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.entities.health_metadata import health_entity_block

# ── optional DuckDB ───────────────────────────────────────────────────────────

try:
    import duckdb  # type: ignore[import-untyped]

    _DUCKDB_AVAILABLE = True
except ImportError:
    duckdb = None  # type: ignore[assignment]
    _DUCKDB_AVAILABLE = False

try:
    import polars as pl  # type: ignore[import-untyped]

    _POLARS_AVAILABLE = True
except ImportError:
    pl = None  # type: ignore[assignment]
    _POLARS_AVAILABLE = False

import sqlite3

# ── Configuration ─────────────────────────────────────────────────────────────

WORKER_PORT = 8016
WORKER_NAME = "analytics-service"

_data_dir = Path(os.environ.get("ANALYTICS_DATA_DIR", str(Path(__file__).parent / "data")))
_data_dir.mkdir(parents=True, exist_ok=True)

DB_PATH = _data_dir / "analytics.db"
PARQUET_DIR = _data_dir / "parquet"
PARQUET_DIR.mkdir(parents=True, exist_ok=True)

ARCHIVE_AFTER_DAYS = int(os.environ.get("ANALYTICS_ARCHIVE_AFTER_DAYS", "7"))
QUERY_ROW_LIMIT = int(os.environ.get("ANALYTICS_QUERY_ROW_LIMIT", "10000"))
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

# Paths to other worker SQLite databases (for cross-service queries)
_CROSS_SERVICE_DBS: Dict[str, str] = {
    "audit":      os.environ.get("AUDIT_DB_PATH",      "/data/audit.db"),
    "monitoring": os.environ.get("MONITORING_DB_PATH", "/data/monitoring.db"),
    "auth":       os.environ.get("AUTH_DB_PATH",       "/data/auth.db"),
    "users":      os.environ.get("USERS_DB_PATH",      "/data/users.db"),
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

STARTED_AT = datetime.now(timezone.utc)


# ── SQLite helpers ────────────────────────────────────────────────────────────


def get_conn() -> sqlite3.Connection:
    conn = sqlite3_connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
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
            CREATE INDEX IF NOT EXISTS idx_ev_sess ON events(session_id);

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

            CREATE TABLE IF NOT EXISTS archive_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                filename    TEXT NOT NULL,
                rows        INTEGER NOT NULL,
                date_from   TEXT NOT NULL,
                date_to     TEXT NOT NULL,
                archived_at TEXT NOT NULL
            );
        """)
        conn.commit()


# ── DuckDB OLAP engine ────────────────────────────────────────────────────────


def _duckdb_conn() -> "duckdb.DuckDBPyConnection":
    """Open a fresh DuckDB connection with SQLite attached and Parquet union view."""
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not installed — OLAP queries unavailable")

    con = duckdb.connect(database=":memory:")

    # Load sqlite_scanner — comes bundled with DuckDB
    try:
        con.execute("INSTALL sqlite; LOAD sqlite;")
    except Exception:
        try:
            con.execute("LOAD sqlite;")
        except Exception:
            pass  # older DuckDB builds have it auto-loaded

    # Paths used in ATTACH/read_parquet are server-controlled config values (not
    # user input). Validate them defensively to satisfy static analysis tools.
    def _safe_path(p: str) -> str:
        """Reject paths that contain characters unsafe in SQL string literals."""
        if any(c in p for c in ("'", '"', ";", "\\")):
            raise ValueError(f"Unsafe character in DB path: {p!r}")
        return p

    # Attach live SQLite as 'live'
    con.execute(f"ATTACH '{_safe_path(str(DB_PATH))}' AS live (TYPE sqlite, READ_ONLY)")

    # Discover archived Parquet files
    parquet_files = sorted(PARQUET_DIR.glob("events_*.parquet"))

    if parquet_files:
        parquet_glob = _safe_path(str(PARQUET_DIR / "events_*.parquet"))
        con.execute(f"""
            CREATE VIEW all_events AS
            SELECT id, event_type, user_id, session_id, properties, timestamp, date_str
            FROM live.events
            UNION ALL
            SELECT id, event_type, user_id, session_id, properties, timestamp, date_str
            FROM read_parquet('{parquet_glob}')
        """)
    else:
        con.execute("""
            CREATE VIEW all_events AS
            SELECT id, event_type, user_id, session_id, properties, timestamp, date_str
            FROM live.events
        """)

    # Attach available cross-service databases
    _safe_alias_re = re.compile(r"^[a-z_][a-z0-9_]*$")
    for alias, path in _CROSS_SERVICE_DBS.items():
        if not _safe_alias_re.match(alias):
            continue  # skip misconfigured alias
        if Path(path).exists():
            try:
                con.execute(f"ATTACH '{_safe_path(path)}' AS {alias}_db (TYPE sqlite, READ_ONLY)")
            except Exception as exc:
                logger.debug("DuckDB: could not attach %s db: %s", alias, exc)

    return con


def _safe_select(sql: str) -> None:
    """Raise ValueError if SQL is not a pure SELECT statement (used inside Pydantic validators → 422)."""
    normalised = sql.strip().upper()
    if not normalised.startswith("SELECT") and not normalised.startswith("WITH"):
        raise ValueError("Only SELECT queries are permitted")
    # Block any mutation keywords
    forbidden = re.compile(
        r"\b(INSERT|UPDATE|DELETE|DROP|CREATE|ALTER|TRUNCATE|REPLACE|ATTACH|DETACH|COPY|EXPORT|IMPORT)\b"
    )
    if forbidden.search(normalised):
        raise ValueError("Mutation statements are not permitted")


# ── Archival task ─────────────────────────────────────────────────────────────


async def _archive_old_events() -> Dict[str, Any]:
    """Export events older than ARCHIVE_AFTER_DAYS to per-month Parquet files."""
    if not _DUCKDB_AVAILABLE:
        return {"status": "skipped", "reason": "duckdb_not_available"}

    cutoff = datetime.now(timezone.utc) - timedelta(days=ARCHIVE_AFTER_DAYS)
    cutoff_ts = cutoff.timestamp()
    cutoff_str = cutoff.strftime("%Y-%m-%d")

    with get_conn() as conn:
        months = conn.execute(
            "SELECT DISTINCT strftime('%Y_%m', timestamp, 'unixepoch') as m FROM events WHERE timestamp < ?",
            (cutoff_ts,),
        ).fetchall()

    if not months:
        return {"status": "nothing_to_archive"}

    total_archived = 0
    files_written: List[str] = []

    # month values come from SQLite's strftime — validate format before use in SQL
    _month_re = re.compile(r"^\d{4}_\d{2}$")

    for (month,) in months:
        if not _month_re.match(month):
            logger.warning("archive: skipping unexpected month value %r", month)
            continue

        parquet_path = PARQUET_DIR / f"events_{month}.parquet"
        if parquet_path.exists():
            continue  # already archived this month

        con = _duckdb_conn()
        try:
            # Use ? params for user-derived values; month is regex-validated above
            row_count = con.execute(
                "SELECT COUNT(*) FROM live.events"
                f" WHERE strftime('%Y_%m', timestamp, 'unixepoch') = '{month}'"
                " AND timestamp < ?",
                [cutoff_ts],
            ).fetchone()[0]

            if row_count == 0:
                continue

            # COPY destination path is server-controlled; parquet_path validated by PARQUET_DIR prefix
            safe_parquet = str(parquet_path)
            if any(c in safe_parquet for c in ("'", '"', ";")):
                logger.error("archive: unsafe parquet path %r — skipping", safe_parquet)
                continue

            con.execute(
                f"""
                COPY (
                    SELECT * FROM live.events
                    WHERE strftime('%Y_%m', timestamp, 'unixepoch') = '{month}'
                      AND timestamp < ?
                    ORDER BY timestamp
                ) TO '{safe_parquet}' (FORMAT PARQUET, COMPRESSION ZSTD)
                """,
                [cutoff_ts],
            )

            # Log archive in SQLite
            with get_conn() as conn:
                date_range = conn.execute(
                    "SELECT MIN(date_str), MAX(date_str) FROM events WHERE strftime('%Y_%m', timestamp, 'unixepoch') = ?",
                    (month,),
                ).fetchone()
                conn.execute(
                    "INSERT INTO archive_log (filename, rows, date_from, date_to, archived_at) VALUES (?,?,?,?,?)",
                    (
                        f"events_{month}.parquet",
                        row_count,
                        date_range[0] or "",
                        date_range[1] or "",
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                # Delete archived rows from SQLite to keep it lean
                conn.execute(
                    "DELETE FROM events WHERE strftime('%Y_%m', timestamp, 'unixepoch') = ? AND timestamp < ?",
                    (month, cutoff_ts),
                )
                conn.commit()

            total_archived += row_count
            files_written.append(f"events_{month}.parquet")
            logger.info("archive: wrote %s (%d rows)", parquet_path.name, row_count)
        finally:
            con.close()

    return {
        "status": "ok",
        "archived_rows": total_archived,
        "files_written": files_written,
        "cutoff_date": cutoff_str,
    }


# ── Models ────────────────────────────────────────────────────────────────────


class EventIn(BaseModel):
    event_type: str = Field(min_length=1, max_length=100)
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    properties: Dict[str, Any] = {}
    timestamp: Optional[float] = None


class BatchEventsIn(BaseModel):
    events: List[EventIn] = Field(..., max_length=1000)


class MetricIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    value: float
    labels: Dict[str, Any] = {}
    timestamp: Optional[float] = None


class FunnelIn(BaseModel):
    steps: List[str] = Field(..., min_length=2, max_length=10)
    user_id: Optional[str] = None
    since: Optional[float] = None


class OlapQueryIn(BaseModel):
    sql: str = Field(min_length=1, max_length=4000)
    limit: int = Field(default=1000, ge=1, le=QUERY_ROW_LIMIT)

    @field_validator("sql")
    @classmethod
    def must_be_select(cls, v: str) -> str:
        _safe_select(v)
        return v


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    backend = "DuckDB OLAP + SQLite" if _DUCKDB_AVAILABLE else "SQLite only (DuckDB not installed)"
    logger.info("analytics-service ready — backend: %s", backend)
    yield


# ── App ───────────────────────────────────────────────────────────────────────


app = FastAPI(
    title="analytics-service",
    description="Event analytics + DuckDB OLAP engine (self-hosted, zero-cost)",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if _INTERNAL_SECRET and x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    with get_conn() as conn:
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        metric_count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        archive_count = conn.execute("SELECT COUNT(*) FROM archive_log").fetchone()[0]
    parquet_files = list(PARQUET_DIR.glob("events_*.parquet"))
    parquet_total_bytes = sum(p.stat().st_size for p in parquet_files)
    return {
        "entity": health_entity_block(8016, "analytics-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "backend": "duckdb+sqlite" if _DUCKDB_AVAILABLE else "sqlite",
        "duckdb_available": _DUCKDB_AVAILABLE,
        "live_events": event_count,
        "live_metrics": metric_count,
        "archive_batches": archive_count,
        "parquet_files": len(parquet_files),
        "parquet_bytes": parquet_total_bytes,
        "polars_available": _POLARS_AVAILABLE,
    }


# ── Event Ingestion ───────────────────────────────────────────────────────────


@_router.post("/events", status_code=201)
async def ingest_event(ev: EventIn):
    ts = ev.timestamp or time.time()
    date_str = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO events (event_type, user_id, session_id, properties, timestamp, date_str)"
            " VALUES (?,?,?,?,?,?)",
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
            (ev.event_type, ev.user_id, ev.session_id, json.dumps(ev.properties), ts, date_str),
        )
    with get_conn() as conn:
        conn.executemany(
            "INSERT INTO events (event_type, user_id, session_id, properties, timestamp, date_str)"
            " VALUES (?,?,?,?,?,?)",
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
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
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
            "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type ORDER BY count DESC",
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


# ── Metrics ───────────────────────────────────────────────────────────────────


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
            f"SELECT {agg_fn}(value) as result, COUNT(*) as samples FROM metrics {where}",
            params,
        ).fetchone()
    return {"name": name, "aggregation": agg, "result": row["result"], "samples": row["samples"]}


@_router.get("/metrics/{name}/timeseries")
async def metric_timeseries(
    name: str,
    bucket: str = Query("day", pattern="^(hour|day)$"),
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(90, ge=1, le=365),
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
            f"SELECT strftime('{fmt}', timestamp, 'unixepoch') as bucket,"
            f" AVG(value) as avg, MIN(value) as min, MAX(value) as max, COUNT(*) as samples"
            f" FROM metrics {where} GROUP BY bucket ORDER BY bucket DESC LIMIT ?",
            params + [limit],
        ).fetchall()
    return {"name": name, "bucket": bucket, "series": [dict(r) for r in rows]}


# ── DuckDB OLAP Endpoints ─────────────────────────────────────────────────────


@_router.get("/analytics/dau")
async def active_users(
    days: int = Query(30, ge=1, le=365),
):
    """Daily / weekly / monthly active users over the last N days."""
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    con = _duckdb_conn()
    try:
        since_ts = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        wau_ts = (datetime.now(timezone.utc) - timedelta(days=7)).timestamp()
        mau_ts = (datetime.now(timezone.utc) - timedelta(days=30)).timestamp()

        dau_rows = con.execute(
            "SELECT date_str,"
            " COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL) AS dau"
            " FROM all_events"
            " WHERE timestamp >= ?"
            " GROUP BY date_str"
            " ORDER BY date_str DESC",
            [since_ts],
        ).fetchall()

        wau = con.execute(
            "SELECT COUNT(DISTINCT user_id) AS wau FROM all_events"
            " WHERE user_id IS NOT NULL AND timestamp >= ?",
            [wau_ts],
        ).fetchone()[0]

        mau = con.execute(
            "SELECT COUNT(DISTINCT user_id) AS mau FROM all_events"
            " WHERE user_id IS NOT NULL AND timestamp >= ?",
            [mau_ts],
        ).fetchone()[0]

        return {
            "window_days": days,
            "wau": wau,
            "mau": mau,
            "daily": [{"date": r[0], "dau": r[1]} for r in dau_rows],
        }
    finally:
        con.close()


@_router.get("/analytics/retention")
async def retention_cohorts(
    cohort_days: int = Query(30, ge=7, le=180),
):
    """Day-1, day-7, and day-30 retention cohorts."""
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    since_ts = (datetime.now(timezone.utc) - timedelta(days=cohort_days)).timestamp()
    con = _duckdb_conn()
    try:
        # First appearance of each user = cohort entry date
        rows = con.execute(
            "WITH first_seen AS ("
            "  SELECT user_id, MIN(timestamp) AS first_ts, MIN(date_str) AS cohort_date"
            "  FROM all_events"
            "  WHERE user_id IS NOT NULL AND timestamp >= ?"
            "  GROUP BY user_id"
            "),"
            "activity AS ("
            "  SELECT e.user_id, f.first_ts, f.cohort_date, e.timestamp AS event_ts,"
            "         CAST((e.timestamp - f.first_ts) / 86400 AS INTEGER) AS day_offset"
            "  FROM all_events e"
            "  JOIN first_seen f ON e.user_id = f.user_id"
            "  WHERE e.user_id IS NOT NULL"
            ")"
            "SELECT cohort_date,"
            "  COUNT(DISTINCT user_id) AS cohort_size,"
            "  COUNT(DISTINCT CASE WHEN day_offset >= 1  THEN user_id END) AS retained_d1,"
            "  COUNT(DISTINCT CASE WHEN day_offset >= 7  THEN user_id END) AS retained_d7,"
            "  COUNT(DISTINCT CASE WHEN day_offset >= 30 THEN user_id END) AS retained_d30"
            " FROM activity"
            " GROUP BY cohort_date"
            " ORDER BY cohort_date DESC"
            " LIMIT 60",
            [since_ts],
        ).fetchall()

        cohorts = []
        for r in rows:
            # SELECT returns: cohort_date(0), cohort_size(1), retained_d1(2), retained_d7(3), retained_d30(4)
            size = r[1] or 1  # avoid div-by-zero
            cohorts.append({
                "cohort_date": r[0],
                "cohort_size": r[1],
                "day_1_retained": r[2],
                "day_7_retained": r[3],
                "day_30_retained": r[4],
                "day_1_rate": round(r[2] / size, 4),
                "day_7_rate": round(r[3] / size, 4),
                "day_30_rate": round(r[4] / size, 4),
            })

        return {"cohort_window_days": cohort_days, "cohorts": cohorts}
    finally:
        con.close()


@_router.get("/analytics/sessions")
async def session_analysis(
    since: Optional[float] = None,
    limit: int = Query(1000, ge=1, le=10000),
):
    """Session depth, duration, and bounce rate analysis."""
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    con = _duckdb_conn()
    try:
        # Build base query; since is Optional[float] — pass as param, never interpolate
        base_sql = (
            "SELECT session_id,"
            " COUNT(*) AS depth,"
            " MIN(timestamp) AS session_start,"
            " MAX(timestamp) AS session_end,"
            " MAX(timestamp) - MIN(timestamp) AS duration_seconds,"
            " MIN(event_type) AS first_event,"
            " MAX(event_type) AS last_event"
            " FROM all_events"
            " WHERE session_id IS NOT NULL"
        )
        params: list = []
        if since is not None:
            base_sql += " AND timestamp >= ?"
            params.append(since)
        # LIMIT: Pydantic-validated int (ge=1, le=10000) — safe to interpolate as int literal
        base_sql += f" GROUP BY session_id ORDER BY session_start DESC LIMIT {int(limit)}"
        rows = con.execute(base_sql, params).fetchall()

        sessions = [
            {
                "session_id": r[0],
                "depth": r[1],
                "start": r[2],
                "end": r[3],
                "duration_seconds": round(r[4], 1),
                "first_event": r[5],
                "last_event": r[6],
            }
            for r in rows
        ]

        total = len(sessions)
        bounces = sum(1 for s in sessions if s["depth"] == 1)
        avg_depth = sum(s["depth"] for s in sessions) / total if total else 0
        avg_duration = sum(s["duration_seconds"] for s in sessions) / total if total else 0

        return {
            "total_sessions": total,
            "bounce_rate": round(bounces / total, 4) if total else 0,
            "avg_depth": round(avg_depth, 2),
            "avg_duration_seconds": round(avg_duration, 1),
            "sessions": sessions,
        }
    finally:
        con.close()


@_router.get("/analytics/journeys")
async def top_journeys(
    top_n: int = Query(20, ge=1, le=100),
    since: Optional[float] = None,
):
    """Top N event-type sequences across sessions (user journey analysis)."""
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    con = _duckdb_conn()
    try:
        # since is Optional[float] — pass as param; top_n is Pydantic int (ge=1, le=100)
        base_cte = (
            "WITH ordered AS ("
            "  SELECT session_id, event_type,"
            "    ROW_NUMBER() OVER (PARTITION BY session_id ORDER BY timestamp) AS step"
            "  FROM all_events"
            "  WHERE session_id IS NOT NULL"
        )
        params: list = []
        if since is not None:
            base_cte += " AND timestamp >= ?"
            params.append(since)
        journey_sql = (
            base_cte
            + "),"
            "journeys AS ("
            "  SELECT session_id,"
            "    STRING_AGG(event_type, ' → ' ORDER BY step) AS journey"
            "  FROM ordered GROUP BY session_id"
            ")"
            # top_n is a Pydantic-validated int literal — safe to interpolate
            f" SELECT journey, COUNT(*) AS count FROM journeys"
            f" GROUP BY journey ORDER BY count DESC LIMIT {int(top_n)}"
        )
        rows = con.execute(journey_sql, params).fetchall()

        return {
            "top_n": top_n,
            "journeys": [{"journey": r[0], "sessions": r[1]} for r in rows],
        }
    finally:
        con.close()


@_router.get("/analytics/platform")
async def platform_summary():
    """Cross-service platform-wide summary using DuckDB cross-attach queries."""
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    con = _duckdb_conn()
    result: Dict[str, Any] = {}
    try:
        # Live analytics events
        result["analytics"] = {
            "live_events": con.execute("SELECT COUNT(*) FROM live.events").fetchone()[0],
            "live_metrics": con.execute("SELECT COUNT(*) FROM live.metrics").fetchone()[0],
        }

        # Auth events — logins, registrations
        if Path(_CROSS_SERVICE_DBS["auth"]).exists():
            try:
                auth_stats = con.execute("""
                    SELECT
                        COUNT(*) FILTER (WHERE event_type = 'login')       AS logins,
                        COUNT(*) FILTER (WHERE event_type = 'register')    AS registrations,
                        COUNT(*) FILTER (WHERE event_type = 'mfa_passed')  AS mfa_passes,
                        COUNT(*) FILTER (WHERE event_type = 'login_failed') AS failed_logins
                    FROM auth_db.auth_events
                    WHERE created_at >= datetime('now', '-7 days')
                """).fetchone()
                result["auth_7d"] = {
                    "logins": auth_stats[0],
                    "registrations": auth_stats[1],
                    "mfa_passes": auth_stats[2],
                    "failed_logins": auth_stats[3],
                }
            except Exception as exc:
                result["auth_7d"] = {"error": str(exc)}

        # Audit chain length
        if Path(_CROSS_SERVICE_DBS["audit"]).exists():
            try:
                audit_count = con.execute("SELECT COUNT(*) FROM audit_db.audit_log").fetchone()[0]
                result["audit"] = {"total_entries": audit_count}
            except Exception as exc:
                result["audit"] = {"error": str(exc)}

        # User count from users-service
        if Path(_CROSS_SERVICE_DBS["users"]).exists():
            try:
                user_stats = con.execute("""
                    SELECT
                        COUNT(*) AS total_users,
                        COUNT(*) FILTER (WHERE is_active = 1) AS active_users
                    FROM users_db.users
                """).fetchone()
                result["users"] = {
                    "total": user_stats[0],
                    "active": user_stats[1],
                }
            except Exception as exc:
                result["users"] = {"error": str(exc)}

        return {"platform": result, "generated_at": datetime.now(timezone.utc).isoformat()}
    finally:
        con.close()


@_router.post("/analytics/query")
async def olap_query(req: OlapQueryIn):
    """
    Execute an arbitrary DuckDB SELECT against the analytics data.

    Available tables / views:
      all_events        — live SQLite events + all Parquet archives (union)
      live.events       — live SQLite events only
      live.metrics      — live SQLite metrics only
      audit_db.*        — audit-service tables (if DB present)
      auth_db.*         — infinity-auth tables (if DB present)
      users_db.*        — users-service tables (if DB present)
      monitoring_db.*   — monitoring tables (if DB present)

    Only SELECT (and WITH ... SELECT) statements are permitted.
    """
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")

    # Wrap in LIMIT — req.limit is a Pydantic-validated int (ge=1, le=QUERY_ROW_LIMIT)
    safe_sql = f"SELECT * FROM ({req.sql}) AS _q LIMIT {int(req.limit)}"

    con = _duckdb_conn()
    try:
        relation = con.execute(safe_sql)
        columns = [d[0] for d in relation.description]
        rows = relation.fetchall()
        return {
            "columns": columns,
            "rows": [dict(zip(columns, r)) for r in rows],
            "row_count": len(rows),
            "limit": req.limit,
        }
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Query error: {exc}") from exc
    finally:
        con.close()


@_router.post("/analytics/archive")
async def trigger_archive(background_tasks: BackgroundTasks):
    """Manually trigger Parquet archival of events older than ARCHIVE_AFTER_DAYS days."""
    background_tasks.add_task(_archive_old_events)
    return {
        "message": "Archival task queued",
        "archive_after_days": ARCHIVE_AFTER_DAYS,
        "parquet_dir": str(PARQUET_DIR),
    }


# ── Polars DataFrame endpoint ─────────────────────────────────────────────────


class DataFrameIn(BaseModel):
    sql: str = Field(min_length=1, max_length=4000, description="DuckDB SELECT to materialise as a Polars DataFrame")
    operations: List[str] = Field(
        default=[],
        description=(
            "Polars operations to apply after materialising. "
            "Supported: 'describe', 'null_count', 'dtypes', "
            "'value_counts:<col>', 'corr:<col_a>:<col_b>'"
        ),
    )
    limit: int = Field(default=1000, ge=1, le=QUERY_ROW_LIMIT)

    @field_validator("sql")
    @classmethod
    def must_be_select(cls, v: str) -> str:
        _safe_select(v)
        return v


@_router.post("/analytics/dataframe")
async def analytics_dataframe(body: DataFrameIn):
    """
    Execute a DuckDB SELECT, materialise the result as a Polars DataFrame,
    and apply optional DataFrame operations (describe, corr, value_counts …).

    This endpoint is the natural integration point between The Dutchy
    (intelligence & market analysis) and the platform's event/metric data.
    """
    if not _DUCKDB_AVAILABLE:
        raise HTTPException(status_code=503, detail="DuckDB not available")
    if not _POLARS_AVAILABLE:
        raise HTTPException(status_code=503, detail="Polars not available")

    con = _duckdb_conn()
    try:
        # Push LIMIT into the SQL layer — avoids materialising the full result
        # set in memory before truncating (same pattern as /analytics/query).
        limited_sql = f"SELECT * FROM ({body.sql}) _q LIMIT {int(body.limit)}"
        arrow_table = con.execute(limited_sql).arrow()
        df = pl.from_arrow(arrow_table)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Query error: {exc}") from exc
    finally:
        con.close()

    result: Dict[str, Any] = {
        "rows": len(df),
        "columns": df.columns,
        "schema": {col: str(dtype) for col, dtype in zip(df.columns, df.dtypes)},
        "data": df.to_dicts(),
    }

    # Apply optional operations
    for op in body.operations:
        try:
            if op == "describe":
                result["describe"] = df.describe().to_dicts()
            elif op == "null_count":
                result["null_count"] = df.null_count().to_dicts()[0]
            elif op == "dtypes":
                result["dtypes"] = {c: str(t) for c, t in zip(df.columns, df.dtypes)}
            elif op.startswith("value_counts:"):
                col = op.split(":", 1)[1]
                if col in df.columns:
                    result[f"value_counts_{col}"] = (
                        df[col].value_counts(sort=True).to_dicts()
                    )
            elif op.startswith("corr:"):
                parts = op.split(":")
                if len(parts) == 3:
                    col_a, col_b = parts[1], parts[2]
                    if col_a in df.columns and col_b in df.columns:
                        result[f"corr_{col_a}_{col_b}"] = df[col_a].corr(df[col_b])
        except Exception as exc:
            result[f"op_error_{op}"] = str(exc)

    return result


# ── Summary dashboard ─────────────────────────────────────────────────────────


@_router.get("/summary")
async def summary():
    with get_conn() as conn:
        event_count = conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        metric_count = conn.execute("SELECT COUNT(*) FROM metrics").fetchone()[0]
        top_events = conn.execute(
            "SELECT event_type, COUNT(*) as c FROM events GROUP BY event_type ORDER BY c DESC LIMIT 10",
        ).fetchall()
        top_metrics = conn.execute(
            "SELECT name, AVG(value) as avg_val, COUNT(*) as samples FROM metrics GROUP BY name ORDER BY samples DESC LIMIT 10",
        ).fetchall()
        archive_rows = conn.execute(
            "SELECT filename, rows, date_from, date_to, archived_at FROM archive_log ORDER BY archived_at DESC LIMIT 10",
        ).fetchall()

    parquet_files = sorted(PARQUET_DIR.glob("events_*.parquet"))

    return {
        "live_events": event_count,
        "live_metrics": metric_count,
        "top_event_types": [dict(r) for r in top_events],
        "top_metrics": [dict(r) for r in top_metrics],
        "archive_log": [dict(r) for r in archive_rows],
        "parquet_files": [p.name for p in parquet_files],
        "duckdb_olap": _DUCKDB_AVAILABLE,
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
