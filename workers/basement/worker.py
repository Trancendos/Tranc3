"""
Trancendos basement — Archived Information Store
================================================
Long-term archive from The Observatory audit trail. Append-only,
FTS5 full-text search, configurable retention pull from audit-service.

Port: 8039  Entity: The Basement  Lead AI: Gary Glowman (Glow-Worm)
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8039
WORKER_NAME = "basement"
DB_PATH = Path(__file__).parent / "data" / "basement.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

AUDIT_SERVICE_URL = os.getenv("AUDIT_SERVICE_URL", "http://localhost:8025")
INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS archive (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                source      TEXT NOT NULL DEFAULT 'audit-service',
                ref_id      TEXT,
                actor       TEXT,
                action      TEXT,
                resource    TEXT,
                details     TEXT DEFAULT '{}',
                outcome     TEXT DEFAULT 'success',
                archived_at REAL NOT NULL,
                original_ts REAL
            )
        """)
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS archive_fts USING fts5(
                actor, action, resource, details, outcome,
                content=archive, content_rowid=id
            )
        """)
        conn.execute("""
            CREATE TRIGGER IF NOT EXISTS archive_ai AFTER INSERT ON archive BEGIN
                INSERT INTO archive_fts(rowid, actor, action, resource, details, outcome)
                VALUES (new.id, new.actor, new.action, new.resource, new.details, new.outcome);
            END
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_archive_actor ON archive(actor)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_archive_ts ON archive(archived_at)
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield
    logger.info("%s shutdown", WORKER_NAME)


app = FastAPI(title="The Basement — Archive Store", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ArchiveIn(BaseModel):
    source: str = "manual"
    ref_id: Optional[str] = None
    actor: str
    action: str
    resource: Optional[str] = None
    details: dict = {}
    outcome: str = "success"
    original_ts: Optional[float] = None


class BulkArchiveIn(BaseModel):
    entries: list[ArchiveIn]


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@_router.get("/health")
async def health():
    with get_conn() as conn:
        count = conn.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Basement", "lead_ai": "Gary Glowman (Glow-Worm)"},
        "archive_count": count,
    }


@_router.get("/metrics")
async def metrics():
    uptime = time.time() - _start_time
    return (
        f"# HELP requests_total Total requests\n"
        f"# TYPE requests_total counter\n"
        f"requests_total {_req_count}\n"
        f"# HELP errors_total Total errors\n"
        f"# TYPE errors_total counter\n"
        f"errors_total {_err_count}\n"
        f"# HELP uptime_seconds Uptime\n"
        f"# TYPE uptime_seconds gauge\n"
        f"uptime_seconds {uptime:.2f}\n"
    )


@_router.post("/archive", status_code=201)
async def archive_entry(body: ArchiveIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO archive (source, ref_id, actor, action, resource, details, outcome, archived_at, original_ts) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (body.source, body.ref_id, body.actor, body.action, body.resource,
             json.dumps(body.details), body.outcome, now, body.original_ts or now),
        )
        conn.commit()
        return {"id": cur.lastrowid, "archived_at": now}


@_router.post("/archive/bulk", status_code=201)
async def archive_bulk(body: BulkArchiveIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    inserted = 0
    with get_conn() as conn:
        for entry in body.entries:
            conn.execute(
                "INSERT INTO archive (source, ref_id, actor, action, resource, details, outcome, archived_at, original_ts) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (entry.source, entry.ref_id, entry.actor, entry.action, entry.resource,
                 json.dumps(entry.details), entry.outcome, now, entry.original_ts or now),
            )
            inserted += 1
        conn.commit()
    return {"inserted": inserted}


@_router.get("/archive")
async def search_archive(
    actor: Optional[str] = None,
    action: Optional[str] = None,
    outcome: Optional[str] = None,
    source: Optional[str] = None,
    q: Optional[str] = None,
    since: Optional[float] = None,
    until: Optional[float] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        if q:
            rows = conn.execute(
                "SELECT archive.* FROM archive_fts fts "
                "JOIN archive ON archive.id = fts.rowid "
                "WHERE archive_fts MATCH ? ORDER BY archive.id DESC LIMIT ? OFFSET ?",
                (q, limit, offset),
            ).fetchall()
            total = len(rows)
        else:
            clauses, params = [], []
            if actor:
                clauses.append("actor = ?"); params.append(actor)
            if action:
                clauses.append("action = ?"); params.append(action)
            if outcome:
                clauses.append("outcome = ?"); params.append(outcome)
            if source:
                clauses.append("source = ?"); params.append(source)
            if since:
                clauses.append("archived_at >= ?"); params.append(since)
            if until:
                clauses.append("archived_at <= ?"); params.append(until)
            where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
            total = conn.execute(f"SELECT COUNT(*) FROM archive {where}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM archive {where} ORDER BY id DESC LIMIT ? OFFSET ?",
                params + [limit, offset],
            ).fetchall()
    return {"total": total, "entries": [dict(r) for r in rows], "limit": limit, "offset": offset}


@_router.get("/archive/{entry_id}")
async def get_archive_entry(entry_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM archive WHERE id=?", (entry_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Entry not found")
    return dict(row)


@_router.post("/pull")
async def pull_from_audit(x_internal_secret: str = Header(default="")):
    """Pull recent audit entries from audit-service and archive them."""
    _auth(x_internal_secret)
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{AUDIT_SERVICE_URL}/audit",
                params={"limit": 500},
                headers={"X-Internal-Secret": INTERNAL_SECRET},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Audit-service unreachable: {exc}")

    now = time.time()
    inserted = 0
    with get_conn() as conn:
        for entry in data.get("entries", []):
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO archive (source, ref_id, actor, action, resource, details, outcome, archived_at, original_ts) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    ("audit-service", str(entry["id"]), entry["actor"], entry["action"],
                     entry.get("resource"), entry.get("details", "{}"), entry.get("outcome", "success"),
                     now, entry.get("timestamp", now)),
                )
                inserted += 1
            except Exception:
                pass
        conn.commit()
    return {"pulled": len(data.get("entries", [])), "inserted": inserted}


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM archive").fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) c FROM archive GROUP BY source ORDER BY c DESC"
        ).fetchall()
        by_outcome = conn.execute(
            "SELECT outcome, COUNT(*) c FROM archive GROUP BY outcome"
        ).fetchall()
    return {
        "total": total,
        "by_source": [dict(r) for r in by_source],
        "by_outcome": [dict(r) for r in by_outcome],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
