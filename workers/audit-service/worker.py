"""
Trancendos audit-service — Self-Hosted Worker
=============================================
Append-only audit log with SHA-256 hash chaining for tamper detection.
Every entry is linked to the previous via a chain hash, enabling full
integrity verification.

Port: 8025
Zero-cost: FastAPI + SQLite (PRAGMA synchronous=FULL), no external deps.
"""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8025
WORKER_NAME = "audit-service"
DB_PATH = Path(__file__).parent / "data" / "audit.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

GENESIS_HASH = "0" * 64


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=FULL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                actor       TEXT NOT NULL,
                action      TEXT NOT NULL,
                resource    TEXT,
                details     TEXT DEFAULT '{}',
                outcome     TEXT DEFAULT 'success',
                ip_address  TEXT,
                chain_hash  TEXT NOT NULL,
                prev_hash   TEXT NOT NULL,
                timestamp   REAL NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_actor  ON audit_log(actor)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_ts     ON audit_log(timestamp)")
        conn.commit()


def _compute_hash(entry_id: int, actor: str, action: str, timestamp: float, prev_hash: str) -> str:
    payload = f"{entry_id}:{actor}:{action}:{timestamp}:{prev_hash}"
    return hashlib.sha256(payload.encode()).hexdigest()


def _last_hash() -> str:
    with get_conn() as conn:
        row = conn.execute("SELECT chain_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return row["chain_hash"] if row else GENESIS_HASH


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class AuditIn(BaseModel):
    actor: str
    action: str
    resource: Optional[str] = None
    details: Dict[str, Any] = {}
    outcome: str = "success"
    ip_address: Optional[str] = None
    timestamp: Optional[float] = None


class AuditBatchIn(BaseModel):
    entries: List[AuditIn]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("audit-service DB ready")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(title="audit-service", description="Append-only hash-chained audit log (self-hosted)", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        last = conn.execute("SELECT chain_hash, timestamp FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "total_entries": count,
        "chain_tip": last["chain_hash"] if last else GENESIS_HASH,
        "entity": {
            "location": "The Observatory",
            "pillar": "Knowledge",
            "lead_ai": "Norman Hawkins",
            "primes": ["Cornelius MacIntyre"],
            "primary_function": "Audit Log & Monitoring Platform",
            "layer": "supporting",
        },
    }


@app.post("/audit", status_code=201)
async def append_entry(entry: AuditIn):
    ts = entry.timestamp or time.time()
    prev_hash = _last_hash()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO audit_log (actor, action, resource, details, outcome, ip_address, chain_hash, prev_hash, timestamp) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (entry.actor, entry.action, entry.resource, json.dumps(entry.details),
             entry.outcome, entry.ip_address, "pending", prev_hash, ts),
        )
        row_id = cur.lastrowid
        chain_hash = _compute_hash(row_id, entry.actor, entry.action, ts, prev_hash)
        conn.execute("UPDATE audit_log SET chain_hash = ? WHERE id = ?", (chain_hash, row_id))
        conn.commit()
    return {
        "id": row_id,
        "actor": entry.actor,
        "action": entry.action,
        "timestamp": ts,
        "chain_hash": chain_hash,
        "prev_hash": prev_hash,
    }


@app.post("/audit/batch", status_code=201)
async def append_batch(batch: AuditBatchIn):
    results = []
    with get_conn() as conn:
        for entry in batch.entries:
            ts = entry.timestamp or time.time()
            row = conn.execute("SELECT chain_hash FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
            prev_hash = row["chain_hash"] if row else GENESIS_HASH
            cur = conn.execute(
                "INSERT INTO audit_log (actor, action, resource, details, outcome, ip_address, chain_hash, prev_hash, timestamp) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (entry.actor, entry.action, entry.resource, json.dumps(entry.details),
                 entry.outcome, entry.ip_address, "pending", prev_hash, ts),
            )
            row_id = cur.lastrowid
            chain_hash = _compute_hash(row_id, entry.actor, entry.action, ts, prev_hash)
            conn.execute("UPDATE audit_log SET chain_hash = ? WHERE id = ?", (chain_hash, row_id))
            results.append({"id": row_id, "chain_hash": chain_hash})
        conn.commit()
    return {"inserted": len(results), "entries": results}


@app.get("/audit")
async def list_entries(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    outcome: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    clauses, params = [], []
    if actor:
        clauses.append("actor = ?"); params.append(actor)
    if action:
        clauses.append("action = ?"); params.append(action)
    if outcome:
        clauses.append("outcome = ?"); params.append(outcome)
    if since:
        clauses.append("timestamp >= ?"); params.append(since)
    if until:
        clauses.append("timestamp <= ?"); params.append(until)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM audit_log {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM audit_log {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "entries": [dict(r) for r in rows], "limit": limit, "offset": offset}


@app.get("/audit/{entry_id}")
async def get_entry(entry_id: int):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM audit_log WHERE id = ?", (entry_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    return dict(row)


@app.get("/audit/verify/chain")
async def verify_chain():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM audit_log ORDER BY id ASC").fetchall()
    if not rows:
        return {"valid": True, "entries_checked": 0, "message": "Empty log"}

    prev_hash = GENESIS_HASH
    broken_at = None
    for row in rows:
        expected = _compute_hash(row["id"], row["actor"], row["action"], row["timestamp"], row["prev_hash"])
        if row["chain_hash"] != expected or row["prev_hash"] != prev_hash:
            broken_at = row["id"]
            break
        prev_hash = row["chain_hash"]

    return {
        "valid": broken_at is None,
        "entries_checked": len(rows),
        "broken_at_id": broken_at,
        "chain_tip": rows[-1]["chain_hash"] if broken_at is None else None,
    }


@app.get("/stats")
async def stats():
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        by_actor = conn.execute(
            "SELECT actor, COUNT(*) as c FROM audit_log GROUP BY actor ORDER BY c DESC LIMIT 10"
        ).fetchall()
        by_action = conn.execute(
            "SELECT action, COUNT(*) as c FROM audit_log GROUP BY action ORDER BY c DESC LIMIT 10"
        ).fetchall()
        by_outcome = conn.execute(
            "SELECT outcome, COUNT(*) as c FROM audit_log GROUP BY outcome"
        ).fetchall()
    return {
        "total_entries": total,
        "by_actor": [dict(r) for r in by_actor],
        "by_action": [dict(r) for r in by_action],
        "by_outcome": [dict(r) for r in by_outcome],
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
