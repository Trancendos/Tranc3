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
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("PORT", 8017))
WORKER_NAME = "audit-service"

_data_dir = Path(os.environ.get("DATA_DIR", "/data"))
_data_dir.mkdir(parents=True, exist_ok=True)
DB_PATH = _data_dir / "audit.db"

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
    logger.info("SQLite DB initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Hash chaining
# ---------------------------------------------------------------------------


def _compute_hash(
    prev_hash: str,
    event_id: str,
    timestamp: str,
    action: str,
    actor: str,
    resource: str,
    outcome: str,
) -> str:
    """
    SHA-256( prev_hash + event_id + timestamp + action + actor + resource + outcome )
    All fields concatenated with '|' as separator to avoid ambiguity.
    """
    payload = "|".join([prev_hash, event_id, timestamp, action, actor, resource, outcome])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _tail_hash() -> str:
    """Return the hash of the most recent entry, or GENESIS_HASH if empty."""
    with _connect() as conn:
        row = conn.execute("SELECT hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row["hash"] if row else GENESIS_HASH


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
            cur_row["action"],
            cur_row["actor"],
            cur_row["resource"],
            cur_row["outcome"],
        )
        if cur_row["hash"] != expected:
            return False
    return True


def _build_stats_window(since_iso: str) -> StatsWindow:
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE timestamp >= ?", (since_iso,)
        ).fetchone()[0]

        def _group(col: str) -> Dict[str, int]:
            rows = conn.execute(
                f"SELECT {col}, COUNT(*) AS c FROM audit_log WHERE timestamp >= ? GROUP BY {col}",
                (since_iso,),
            ).fetchall()
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


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    with _connect() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
    chain_valid = _spot_check_chain(100)
    return HealthResponse(
        status="healthy",
        service=WORKER_NAME,
        port=PORT,
        db_path=str(DB_PATH),
        total_events=total,
        chain_valid=chain_valid,
    )


@app.post("/events", response_model=AuditEventCreated, status_code=201)
async def append_event(body: AuditEventIn) -> AuditEventCreated:
    """Append a new audit event and chain it to the previous entry."""
    event_id = body.event_id or str(uuid.uuid4())
    timestamp = body.timestamp or datetime.now(timezone.utc).isoformat()

    # Validate enumerated fields
    outcome = body.outcome if body.outcome in VALID_OUTCOMES else "success"
    severity = body.severity if body.severity in VALID_SEVERITIES else "info"

    prev_hash = _tail_hash()
    entry_hash = _compute_hash(
        prev_hash,
        event_id,
        timestamp,
        body.action,
        body.actor,
        body.resource,
        outcome,
    )

    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO audit_log
                    (event_id, timestamp, service, action, actor, resource,
                     outcome, severity, details_json, prev_hash, hash)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    timestamp,
                    body.service,
                    body.action,
                    body.actor,
                    body.resource,
                    outcome,
                    severity,
                    json.dumps(body.details),
                    prev_hash,
                    entry_hash,
                ),
            )
            conn.commit()
            row_id = cur.lastrowid
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Event with event_id={event_id!r} already exists.",
        ) from exc

    logger.info(
        "audit event appended id=%d event_id=%s action=%s actor=%s",
        row_id,
        event_id,
        body.action,
        body.actor,
    )
    return AuditEventCreated(
        id=row_id,
        event_id=event_id,
        timestamp=timestamp,
        hash=entry_hash,
        prev_hash=prev_hash,
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
    clauses: List[str] = []
    params: List[Any] = []

    if service:
        clauses.append("service = ?")
        params.append(service)
    if actor:
        clauses.append("actor = ?")
        params.append(actor)
    if action:
        clauses.append("action = ?")
        params.append(action)
    if from_:
        clauses.append("timestamp >= ?")
        params.append(from_)
    if to:
        clauses.append("timestamp <= ?")
        params.append(to)
    if severity:
        clauses.append("severity = ?")
        params.append(severity)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    params += [limit, offset]

    with _connect() as conn:
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params,
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
            row["action"],
            row["actor"],
            row["resource"],
            row["outcome"],
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
    clauses: List[str] = []
    params: List[Any] = []

    if from_:
        clauses.append("timestamp >= ?")
        params.append(from_)
    if to:
        clauses.append("timestamp <= ?")
        params.append(to)

    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    def _stream():
        with _connect() as conn:
            cur = conn.execute(
                f"SELECT * FROM audit_log {where} ORDER BY id ASC",
                params,
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


@app.get("/stats", response_model=StatsResponse)
async def stats() -> StatsResponse:
    """Return event counts grouped by service, action, severity, and outcome for 24h/7d/30d."""
    now = datetime.now(timezone.utc)
    iso_24h = (now - timedelta(hours=24)).isoformat()
    iso_7d = (now - timedelta(days=7)).isoformat()
    iso_30d = (now - timedelta(days=30)).isoformat()

    return StatsResponse(
        last_24h=_build_stats_window(iso_24h),
        last_7d=_build_stats_window(iso_7d),
        last_30d=_build_stats_window(iso_30d),
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
