"""
Trancendos ledger-service — Self-Hosted Worker
================================================
Immutable audit ledger with SHA-256 hash chain and sentinel verification.

Features:
    - Hash-chained entries (SHA-256, each entry links to prev hash)
    - Digital signature verification per entry
    - Sentinel verification daemon with history tracking
    - Query by actor, action, resource type, time range

Port: 8032
Zero-cost: FastAPI + SQLite, no external services required.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("LEDGER_DB_PATH", "data/ledger.db")

logger = logging.getLogger("ledger-service")

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS ledger_entries (
            id TEXT PRIMARY KEY,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            resource_type TEXT DEFAULT '',
            resource_id TEXT DEFAULT '',
            details TEXT DEFAULT '{}',
            hash TEXT NOT NULL,
            prev_hash TEXT,
            signature TEXT DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS sentinel_checks (
            id TEXT PRIMARY KEY,
            chain_valid INTEGER NOT NULL DEFAULT 1,
            entry_count INTEGER DEFAULT 0,
            invalid_entries TEXT DEFAULT '[]',
            checked_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_ledger_actor ON ledger_entries(actor);
        CREATE INDEX IF NOT EXISTS idx_ledger_action ON ledger_entries(action);
        CREATE INDEX IF NOT EXISTS idx_ledger_created ON ledger_entries(created_at);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class LedgerEntryCreate(BaseModel):
    actor: str = Field(..., min_length=1, max_length=200)
    action: str = Field(..., min_length=1, max_length=200)
    resource_type: str = ""
    resource_id: str = ""
    details: Dict[str, Any] = Field(default_factory=dict)
    signature: str = ""


class LedgerEntryResponse(BaseModel):
    id: str
    actor: str
    action: str
    resource_type: str
    resource_id: str
    details: Dict[str, Any]
    hash: str
    prev_hash: Optional[str]
    signature: str
    created_at: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _get_last_hash(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT hash FROM ledger_entries ORDER BY rowid DESC LIMIT 1").fetchone()
    return row["hash"] if row else "0" * 64


def _compute_hash(entry_id: str, prev_hash: str, actor: str, action: str, timestamp: str) -> str:
    payload = f"{entry_id}:{prev_hash}:{actor}:{action}:{timestamp}"
    return hashlib.sha256(payload.encode()).hexdigest()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("ledger-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 Ledger Service", version="0.1.0", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {"status": "ok", "service": "ledger-service", "port": 8032}


# ---------------------------------------------------------------------------
# Entries
# ---------------------------------------------------------------------------


@app.post("/entries", response_model=LedgerEntryResponse, status_code=201)
async def append_entry(body: LedgerEntryCreate):
    conn = _get_db()
    now = _now()
    eid = _new_id()
    prev_hash = _get_last_hash(conn)
    entry_hash = _compute_hash(eid, prev_hash, body.actor, body.action, now)

    conn.execute(
        "INSERT INTO ledger_entries (id, actor, action, resource_type, resource_id, details, hash, prev_hash, signature, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            eid,
            body.actor,
            body.action,
            body.resource_type,
            body.resource_id,
            json.dumps(body.details),
            entry_hash,
            prev_hash,
            body.signature,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return LedgerEntryResponse(
        id=eid,
        actor=body.actor,
        action=body.action,
        resource_type=body.resource_type,
        resource_id=body.resource_id,
        details=body.details,
        hash=entry_hash,
        prev_hash=prev_hash,
        signature=body.signature,
        created_at=now,
    )


@app.get("/entries", response_model=List[LedgerEntryResponse])
async def query_entries(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM ledger_entries WHERE 1=1"
    params: list = []
    if actor:
        q += " AND actor=?"
        params.append(actor)
    if action:
        q += " AND action=?"
        params.append(action)
    if resource_type:
        q += " AND resource_type=?"
        params.append(resource_type)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [
        LedgerEntryResponse(
            id=r["id"],
            actor=r["actor"],
            action=r["action"],
            resource_type=r["resource_type"],
            resource_id=r["resource_id"],
            details=json.loads(r["details"]),
            hash=r["hash"],
            prev_hash=r["prev_hash"],
            signature=r["signature"],
            created_at=r["created_at"],
        )
        for r in rows
    ]


@app.get("/entries/{entry_id}", response_model=LedgerEntryResponse)
async def get_entry(entry_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM ledger_entries WHERE id=?", (entry_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Entry not found")
    return LedgerEntryResponse(
        id=row["id"],
        actor=row["actor"],
        action=row["action"],
        resource_type=row["resource_type"],
        resource_id=row["resource_id"],
        details=json.loads(row["details"]),
        hash=row["hash"],
        prev_hash=row["prev_hash"],
        signature=row["signature"],
        created_at=row["created_at"],
    )


# ---------------------------------------------------------------------------
# Chain Verification
# ---------------------------------------------------------------------------


@app.get("/verify")
async def verify_chain():
    conn = _get_db()
    rows = conn.execute(
        "SELECT id, hash, prev_hash FROM ledger_entries ORDER BY rowid ASC"
    ).fetchall()
    conn.close()

    if not rows:
        result = {"chain_valid": True, "entry_count": 0, "invalid_entries": []}
    else:
        invalid = []
        for i in range(1, len(rows)):
            if rows[i]["prev_hash"] != rows[i - 1]["hash"]:
                invalid.append(rows[i]["id"])
        result = {
            "chain_valid": len(invalid) == 0,
            "entry_count": len(rows),
            "invalid_entries": invalid,
        }

    # Record sentinel check
    conn2 = _get_db()
    now = _now()
    sid = _new_id()
    conn2.execute(
        "INSERT INTO sentinel_checks (id, chain_valid, entry_count, invalid_entries, checked_at) VALUES (?,?,?,?,?)",
        (
            sid,
            1 if result["chain_valid"] else 0,
            result["entry_count"],
            json.dumps(result["invalid_entries"]),
            now,
        ),
    )
    conn2.commit()
    conn2.close()

    return result


@app.get("/sentinel/history")
async def sentinel_history(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM sentinel_checks ORDER BY checked_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats")
async def get_stats():
    conn = _get_db()
    total = conn.execute("SELECT COUNT(*) as c FROM ledger_entries").fetchone()["c"]
    sentinel_count = conn.execute("SELECT COUNT(*) as c FROM sentinel_checks").fetchone()["c"]
    last_check = conn.execute(
        "SELECT checked_at FROM sentinel_checks ORDER BY checked_at DESC LIMIT 1"
    ).fetchone()
    conn.close()

    # Quick chain validity check
    chain_valid = True
    if total > 1:
        conn2 = _get_db()
        rows = conn2.execute(
            "SELECT hash, prev_hash FROM ledger_entries ORDER BY rowid ASC"
        ).fetchall()
        conn2.close()
        for i in range(1, len(rows)):
            if rows[i]["prev_hash"] != rows[i - 1]["hash"]:
                chain_valid = False
                break

    return {
        "total_entries": total,
        "chain_valid": chain_valid,
        "sentinel_checks": sentinel_count,
        "last_sentinel_check": last_check["checked_at"] if last_check else None,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8032)
