"""
Trancendos audit-service — Self-Hosted Worker (The Observatory)
===============================================================
Append-only, SHA-256 hash-chained audit log for tamper detection.
Every entry is linked to the previous via a chain hash, enabling full
integrity verification at any time.

Port  : 8017  (env: PORT)
DB    : /data/audit.db  (env: DATA_DIR)
Zero-cost: FastAPI + SQLite, stdlib hashlib, no external paid services.

Routes
------
GET  /health              — {status, total_events, chain_valid}
POST /events              — append new audit event
GET  /events              — query (?service=, ?actor=, ?action=, ?from=, ?to=, ?severity=, ?limit=, ?offset=)
GET  /events/{event_id}   — single event by event_id (UUID string)
GET  /verify              — full chain integrity check → {valid, checked, first_break_at}
GET  /export              — NDJSON download for compliance (?from=, ?to=)
GET  /stats               — counts by service/action/severity for 24h / 7d / 30d
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("PORT", 8017))
WORKER_NAME = "audit-service"
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


_data_dir = Path(os.environ.get("DATA_DIR", "/data"))
_data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = _data_dir / "audit.db"

# Serialise chain-tip reads + inserts to prevent concurrent hash-chain forks
_chain_lock = threading.Lock()

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

GENESIS_HASH = "0" * 64

# Serialises concurrent /audit POSTs so the hash chain cannot fork.
_chain_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

GENESIS_HASH = "0" * 64  # seed for the first entry's prev_hash

VALID_SEVERITIES = {"info", "warning", "error", "critical"}
VALID_OUTCOMES = {"success", "failure", "error", "denied"}

# ---------------------------------------------------------------------------
# SQLite helpers
# ---------------------------------------------------------------------------

_CREATE_AUDIT_LOG = """
CREATE TABLE IF NOT EXISTS audit_log (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id     TEXT    NOT NULL UNIQUE,
    timestamp    TEXT    NOT NULL,
    service      TEXT    NOT NULL DEFAULT 'unknown',
    action       TEXT    NOT NULL,
    actor        TEXT    NOT NULL,
    resource     TEXT    NOT NULL DEFAULT '',
    outcome      TEXT    NOT NULL DEFAULT 'success',
    severity     TEXT    NOT NULL DEFAULT 'info',
    details_json TEXT    NOT NULL DEFAULT '{}',
    prev_hash    TEXT    NOT NULL,
    hash         TEXT    NOT NULL
)
"""

_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_al_event_id  ON audit_log(event_id)",
    "CREATE INDEX IF NOT EXISTS idx_al_timestamp ON audit_log(timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_al_service   ON audit_log(service)",
    "CREATE INDEX IF NOT EXISTS idx_al_actor     ON audit_log(actor)",
    "CREATE INDEX IF NOT EXISTS idx_al_action    ON audit_log(action)",
    "CREATE INDEX IF NOT EXISTS idx_al_severity  ON audit_log(severity)",
]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")  # append-only log: durability matters
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.execute(_CREATE_AUDIT_LOG)
        for idx in _INDEXES:
            conn.execute(idx)
        conn.commit()


init_db = _init_db  # public alias for tests


# ---------------------------------------------------------------------------
# Hash chaining
# ---------------------------------------------------------------------------


def _compute_hash(
    prev_hash: str,
    event_id: str,
    timestamp: str,
    service: str,
    action: str,
    actor: str,
    resource: str,
    outcome: str,
) -> str:
    """
    SHA-256( prev_hash | event_id | timestamp | service | action | actor | resource | outcome )
    All fields concatenated with '|' to avoid ambiguity.  'service' is included so
    an attacker cannot swap the originating service without breaking chain integrity.
    """
    payload = "|".join([prev_hash, event_id, timestamp, service, action, actor, resource, outcome])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tail_hash(conn: sqlite3.Connection) -> str:
    """Return the hash of the most recent entry, or GENESIS_HASH if empty.
    Must be called within an open connection (and under _chain_lock).
    """
    row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row["hash"] if row else GENESIS_HASH


def _last_hash() -> str:
    with _connect() as conn:
        return _tail_hash(conn)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class AuditEventIn(BaseModel):
    """Input model for POST /events."""

    event_id: Optional[str] = Field(
        None,
        description="Caller-supplied UUID; auto-generated if omitted.",
    )
    timestamp: Optional[str] = Field(
        None,
        description="ISO-8601 UTC timestamp; defaults to now.",
    )
    service: str = Field("unknown", description="Originating service / worker name.")
    action: str = Field(..., description="What happened (e.g. 'user.login', 'secret.read').")
    actor: str = Field(..., description="Who triggered the event (user ID, service account, etc.).")
    resource: str = Field("", description="The object/entity acted upon.")
    outcome: str = Field("success", description="success | failure | error | denied")
    severity: str = Field("info", description="info | warning | error | critical")
    details: Dict[str, Any] = Field(
        default_factory=dict, description="Arbitrary structured metadata."
    )


class AuditEventOut(BaseModel):
    id: int
    event_id: str
    timestamp: str
    service: str
    action: str
    actor: str
    resource: str
    outcome: str
    severity: str
    details: Dict[str, Any]
    prev_hash: str
    hash: str


class AuditEventCreated(BaseModel):
    id: int
    event_id: str
    timestamp: str
    hash: str
    prev_hash: str


class HealthResponse(BaseModel):
    status: str
    service: str
    port: int
    db_path: str
    total_events: int
    chain_valid: bool  # spot-check of last 100 entries
    uptime_s: float = 0.0


class VerifyResponse(BaseModel):
    valid: bool
    checked: int
    first_break_at: Optional[str] = None  # event_id of the first broken link


class StatsWindow(BaseModel):
    by_service: Dict[str, int]
    by_action: Dict[str, int]
    by_severity: Dict[str, int]
    by_outcome: Dict[str, int]
    total: int


class StatsResponse(BaseModel):
    last_24h: StatsWindow
    last_7d: StatsWindow
    last_30d: StatsWindow


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_START_TIME = time.monotonic()


def _row_to_out(row: sqlite3.Row) -> AuditEventOut:
    return AuditEventOut(
        id=row["id"],
        event_id=row["event_id"],
        timestamp=row["timestamp"],
        service=row["service"],
        action=row["action"],
        actor=row["actor"],
        resource=row["resource"],
        outcome=row["outcome"],
        severity=row["severity"],
        details=json.loads(row["details_json"] or "{}"),
        prev_hash=row["prev_hash"],
        hash=row["hash"],
    )


def _spot_check_chain(n: int = 100) -> bool:
    """
    Verify the last `n` entries form a valid chain.
    Returns True if valid (or if the log is empty).
    """
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (n,)).fetchall()

    if not rows:
        return True

    # rows are DESC; walk them in reverse (oldest first within the window)
    rows = list(reversed(rows))

    # For the oldest entry in our window we need its declared prev_hash to be
    # whatever was before it — we can't recompute that, so we start verification
    # from the second entry in the window.
    for i in range(1, len(rows)):
        prev_row = rows[i - 1]
        cur_row = rows[i]
        # Chain link: cur.prev_hash must equal prev.hash
        if cur_row["prev_hash"] != prev_row["hash"]:
            return False
        # Hash integrity: cur.hash must equal recomputed hash
        expected = _compute_hash(
            cur_row["prev_hash"],
            cur_row["event_id"],
            cur_row["timestamp"],
            cur_row["service"],
            cur_row["action"],
            cur_row["actor"],
            cur_row["resource"],
            cur_row["outcome"],
        )
        if cur_row["hash"] != expected:
            return False
    return True


_STATS_QUERIES: Dict[str, str] = {
    "service": "SELECT service, COUNT(*) AS c FROM audit_log WHERE timestamp >= ? GROUP BY service",
    "action": "SELECT action, COUNT(*) AS c FROM audit_log WHERE timestamp >= ? GROUP BY action",
    "severity": "SELECT severity, COUNT(*) AS c FROM audit_log WHERE timestamp >= ? GROUP BY severity",
    "outcome": "SELECT outcome, COUNT(*) AS c FROM audit_log WHERE timestamp >= ? GROUP BY outcome",
}


def _build_stats_window(since_iso: str) -> StatsWindow:
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE timestamp >= ?", (since_iso,)
        ).fetchone()[0]

        def _group(col: str) -> Dict[str, int]:
            sql = _STATS_QUERIES[col]  # col is always a key from this hardcoded dict
            rows = conn.execute(sql, (since_iso,)).fetchall()
            return {r[col]: r["c"] for r in rows}

        return StatsWindow(
            by_service=_group("service"),
            by_action=_group("action"),
            by_severity=_group("severity"),
            by_outcome=_group("outcome"),
            total=total,
        )


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.audit-service")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel is optional — never block startup
    _init_db()
    logger.info("%s started on port %d, DB=%s", WORKER_NAME, PORT, DB_PATH)
    yield
    logger.info("%s shut down", WORKER_NAME)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="The Observatory — Audit Service",
    description=(
        "Append-only, SHA-256 hash-chained audit log. "
        "Every entry is tamper-evident via chain verification."
    ),
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


@app.get("/health")
async def health() -> dict:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    chain_valid = _spot_check_chain(100)
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": PORT,
        "db_path": str(DB_PATH),
        "total_events": total,
        "chain_valid": chain_valid,
        "chain_tip": _last_hash(),
        "uptime_s": round(time.monotonic() - _START_TIME, 2),
    }


def _require_internal(x_internal_secret: Optional[str] = Header(None)) -> None:
    """Validate X-Internal-Secret header for write endpoints."""
    if INTERNAL_SECRET and x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/events", response_model=AuditEventCreated, status_code=201)
async def append_event(
    body: AuditEventIn,
    x_internal_secret: Optional[str] = Header(None),
) -> AuditEventCreated:
    """Append a new audit event and chain it to the previous entry."""
    _require_internal(x_internal_secret)

    event_id = body.event_id or str(uuid.uuid4())
    ts = body.timestamp or datetime.now(timezone.utc).isoformat()
    with _chain_lock, _connect() as conn:
        prev = _tail_hash(conn)
        cur = conn.execute(
            "INSERT INTO audit_log (event_id, timestamp, service, action, actor, resource,"
            " outcome, severity, details_json, prev_hash, hash)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                event_id,
                ts,
                body.service,
                body.action,
                body.actor,
                body.resource,
                body.outcome,
                body.severity,
                json.dumps(body.details),
                prev,
                "pending",
            ),
        )
        row_id = cur.lastrowid
        chain_hash = _compute_hash(
            prev,
            event_id,
            ts,
            body.service,
            body.action,
            body.actor,
            body.resource,
            body.outcome,
        )
        conn.execute("UPDATE audit_log SET hash=? WHERE id=?", (chain_hash, row_id))
    return AuditEventCreated(
        id=row_id, event_id=event_id, timestamp=ts, hash=chain_hash, prev_hash=prev
    )


@app.get("/events", response_model=List[AuditEventOut])
async def list_events(
    service: Optional[str] = Query(None, description="Filter by service name"),
    actor: Optional[str] = Query(None, description="Filter by actor"),
    action: Optional[str] = Query(None, description="Filter by action"),
    from_: Optional[str] = Query(
        None, alias="from", description="ISO-8601 start timestamp (inclusive)"
    ),
    to: Optional[str] = Query(None, description="ISO-8601 end timestamp (inclusive)"),
    severity: Optional[str] = Query(None, description="Filter by severity"),
    limit: int = Query(100, ge=1, le=1000, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
) -> List[AuditEventOut]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE"
            " (? IS NULL OR service = ?)"
            " AND (? IS NULL OR actor = ?)"
            " AND (? IS NULL OR action = ?)"
            " AND (? IS NULL OR timestamp >= ?)"
            " AND (? IS NULL OR timestamp <= ?)"
            " AND (? IS NULL OR severity = ?)"
            " ORDER BY id DESC LIMIT ? OFFSET ?",
            (
                service,
                service,
                actor,
                actor,
                action,
                action,
                from_,
                from_,
                to,
                to,
                severity,
                severity,
                limit,
                offset,
            ),
        ).fetchall()

    return [_row_to_out(r) for r in rows]


@app.get("/events/{event_id}", response_model=AuditEventOut)
async def get_event(event_id: str) -> AuditEventOut:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM audit_log WHERE event_id = ?", (event_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Event {event_id!r} not found")
    return _row_to_out(row)


@app.get("/verify", response_model=VerifyResponse)
async def verify_chain() -> VerifyResponse:
    """
    Walk the entire audit log in insertion order and verify:
    1. Each entry's hash matches the recomputed hash of its fields.
    2. Each entry's prev_hash matches the hash of the preceding entry.
    """
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()

    if not rows:
        return VerifyResponse(valid=True, checked=0, first_break_at=None)

    prev_hash = GENESIS_HASH
    checked = 0

    for row in rows:
        checked += 1
        # Chain link check
        if row["prev_hash"] != prev_hash:
            return VerifyResponse(valid=False, checked=checked, first_break_at=row["event_id"])
        # Hash integrity check
        expected = _compute_hash(
            row["prev_hash"],
            row["event_id"],
            row["timestamp"],
            row["service"],
            row["action"],
            row["actor"],
            row["resource"] or "",
            row["outcome"] or "",
        )
        if row["hash"] != expected:
            return VerifyResponse(valid=False, checked=checked, first_break_at=row["event_id"])
        prev_hash = row["hash"]

    return VerifyResponse(valid=True, checked=checked, first_break_at=None)


@app.get("/export")
async def export_ndjson(
    from_: Optional[str] = Query(None, alias="from", description="ISO-8601 start timestamp"),
    to: Optional[str] = Query(None, description="ISO-8601 end timestamp"),
) -> StreamingResponse:
    """
    Download audit log as Newline-Delimited JSON (NDJSON) for compliance archival.
    Each line is one JSON object; safe for streaming large exports.
    """

    def _stream():
        with _connect() as conn:
            cur = conn.execute(
                "SELECT * FROM audit_log WHERE"
                " (? IS NULL OR timestamp >= ?)"
                " AND (? IS NULL OR timestamp <= ?)"
                " ORDER BY id ASC",
                (from_, from_, to, to),
            )
            for row in cur:
                record = {
                    "id": row["id"],
                    "event_id": row["event_id"],
                    "timestamp": row["timestamp"],
                    "service": row["service"],
                    "action": row["action"],
                    "actor": row["actor"],
                    "resource": row["resource"],
                    "outcome": row["outcome"],
                    "severity": row["severity"],
                    "details": json.loads(row["details_json"] or "{}"),
                    "prev_hash": row["prev_hash"],
                    "hash": row["hash"],
                }
                yield json.dumps(record) + "\n"

    # Build a descriptive filename
    date_part = datetime.now(timezone.utc).strftime("%Y%m%d")
    filename = f"audit_export_{date_part}.ndjson"

    return StreamingResponse(
        _stream(),
        media_type="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Audit-Service": WORKER_NAME,
        },
    )


@app.get("/stats")
async def stats() -> dict:
    """Return event counts grouped by service, action, severity, and outcome for 24h/7d/30d."""
    now = datetime.now(timezone.utc)
    iso_24h = (now - timedelta(hours=24)).isoformat()
    iso_7d = (now - timedelta(days=7)).isoformat()
    iso_30d = (now - timedelta(days=30)).isoformat()

    w24 = _build_stats_window(iso_24h)
    w7d = _build_stats_window(iso_7d)
    w30d = _build_stats_window(iso_30d)
    return {
        "last_24h": w24.model_dump(),
        "last_7d": w7d.model_dump(),
        "last_30d": w30d.model_dump(),
        "total_entries": w30d.total,
    }


# ---------------------------------------------------------------------------
# /audit compat aliases (tests and older callers use /audit/* routes)
# ---------------------------------------------------------------------------


@app.post("/audit", status_code=201)
async def audit_compat_post(
    body: AuditEventIn,
    x_internal_secret: Optional[str] = Header(None),
) -> dict:
    _require_internal(x_internal_secret)
    result = await append_event(body, x_internal_secret)
    return {"id": result.id, "chain_hash": result.hash, "prev_hash": result.prev_hash}


@app.get("/audit")
async def audit_compat_list(
    actor: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=1000),
    offset: int = Query(0, ge=0),
) -> dict:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM audit_log WHERE"
            " (? IS NULL OR actor = ?)"
            " AND (? IS NULL OR action = ?)"
            " ORDER BY id DESC LIMIT ? OFFSET ?",
            (actor, actor, action, action, limit, offset),
        ).fetchall()
    return {"entries": [_row_to_out(r).model_dump() for r in rows], "total": len(rows)}


@app.get("/audit/verify/chain")
async def audit_compat_verify() -> dict:
    result = await verify_chain()
    return {"valid": result.valid, "checked": result.checked}


@app.get("/audit/{entry_id}")
async def audit_compat_get(entry_id: str) -> dict:
    with _connect() as conn:
        try:
            row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (int(entry_id),)).fetchone()
        except ValueError:
            row = conn.execute("SELECT * FROM audit_log WHERE event_id = ?", (entry_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail=f"Entry {entry_id!r} not found")
    return _row_to_out(row).model_dump()


@app.post("/audit/batch", status_code=201)
async def audit_compat_batch(
    body: dict,
    x_internal_secret: Optional[str] = Header(None),
) -> dict:
    _require_internal(x_internal_secret)
    entries = body.get("entries", [])
    count = 0
    for e in entries:
        ev = AuditEventIn(**{k: v for k, v in e.items() if k in AuditEventIn.model_fields})
        await append_event(ev, x_internal_secret)
        count += 1
    return {"inserted": count}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
