"""
Trancendos Identity Service — Self-Hosted Worker
========================================================
Identity and access management API. Replaces CF infinity-identity-api.

Port: 8015
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8015
WORKER_NAME = "identity-service"
DB_PATH = Path(__file__).parent / "data" / "identities.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class IdentitiesDatabase:
    """SQLite-backed storage for identities."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

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
                CREATE TABLE IF NOT EXISTS identities (
                    identity_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    email TEXT,
                    display_name TEXT,
                    avatar_url TEXT,
                    metadata TEXT DEFAULT '{}',
                    verified INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT
                )
            """)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        data.setdefault("created_at", now)
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join("?" for _ in cols)
        with self._cursor() as cur:
            cur.execute(f"INSERT INTO identities ({', '.join(cols)}) VALUES ({placeholders})", vals)
        return data

    def get(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(f"SELECT * FROM identities WHERE {id_field}=?", (id_value,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, **filters) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM identities WHERE 1=1"
        params: list = []
        for key, val in filters.items():
            query += f" AND {key}=?"
            params.append(val)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update(self, id_field: str, id_value: str, data: Dict[str, Any]) -> bool:
        data["updated_at"] = datetime.now(timezone.utc).isoformat()
        sets = ", ".join(f"{k}=?" for k in data.keys())
        vals = list(data.values()) + [id_value]
        with self._cursor() as cur:
            cur.execute(f"UPDATE identities SET {sets} WHERE {id_field}=?", vals)
            return cur.rowcount > 0

    def delete(self, id_field: str, id_value: str, soft: bool = True) -> bool:
        if soft:
            with self._cursor() as cur:
                cur.execute(
                    f"UPDATE identities SET verified=0, updated_at=? WHERE {id_field}=?",
                    (datetime.now(timezone.utc).isoformat(), id_value),
                )
                return cur.rowcount > 0
        else:
            with self._cursor() as cur:
                cur.execute(f"DELETE FROM identities WHERE {id_field}=?", (id_value,))
                return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
db = IdentitiesDatabase(DB_PATH)

app = FastAPI(
    title="Identity Service",
    description="Identity and access management API. Replaces CF infinity-identity-api.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


@app.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all identities."""
    return {"data": db.list(limit=limit, offset=offset)}


@app.post("/")
async def create(data: Dict[str, Any]):
    """Create a new identities entry."""
    item_id = data.get("identity_id", str(uuid.uuid4()))
    data["identity_id"] = item_id
    created = db.create(data)
    return {"ok": True, **created}


@app.get("/{identity_id}")
async def get_by_id(identity_id: str):
    """Get a identities entry by ID."""
    item = db.get("identity_id", identity_id)
    if not item:
        raise HTTPException(404, f"Not found: {identity_id}")
    return item


@app.patch("/{identity_id}")
async def update_by_id(identity_id: str, data: Dict[str, Any]):
    """Update a identities entry."""
    if not db.update("identity_id", identity_id, data):
        raise HTTPException(404, f"Not found: {identity_id}")
    return {"ok": True}


@app.delete("/{identity_id}")
async def delete_by_id(identity_id: str):
    """Delete a identities entry (soft delete)."""
    if not db.delete("identity_id", identity_id):
        raise HTTPException(404, f"Not found: {identity_id}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Domain-specific endpoints
# ---------------------------------------------------------------------------


@app.get("/by-user/{user_id}")
async def get_by_user(user_id: str, limit: int = 50, offset: int = 0):
    """List all identities for a given user across all providers."""
    return {"data": db.list(limit=limit, offset=offset, user_id=user_id)}


@app.get("/by-provider/{provider}")
async def get_by_provider(provider: str, limit: int = 50, offset: int = 0):
    """List all identities registered via a specific OAuth provider."""
    return {"data": db.list(limit=limit, offset=offset, provider=provider)}


@app.get("/by-provider/{provider}/{provider_id}")
async def get_by_provider_id(provider: str, provider_id: str):
    """Lookup a specific identity by provider + provider_id (e.g. google + sub)."""
    conn = db._get_conn()
    row = conn.execute(
        "SELECT * FROM identities WHERE provider=? AND provider_id=?",
        (provider, provider_id),
    ).fetchone()
    if not row:
        raise HTTPException(404, f"Not found: {provider}/{provider_id}")
    return dict(row)


@app.post("/{identity_id}/verify")
async def verify_identity(identity_id: str):
    """Mark an identity as verified."""
    if not db.update("identity_id", identity_id, {"verified": 1}):
        raise HTTPException(404, f"Not found: {identity_id}")
    return {"ok": True, "verified": True}


@app.post("/{identity_id}/unverify")
async def unverify_identity(identity_id: str):
    """Remove verification from an identity."""
    if not db.update("identity_id", identity_id, {"verified": 0}):
        raise HTTPException(404, f"Not found: {identity_id}")
    return {"ok": True, "verified": False}


@app.get("/search")
async def search_identities(
    email: Optional[str] = None,
    display_name: Optional[str] = None,
    verified: Optional[int] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Search identities by email, display_name, or verified status."""
    conn = db._get_conn()
    query = "SELECT * FROM identities WHERE 1=1"
    params: list = []
    if email:
        query += " AND email LIKE ?"
        params.append(f"%{email}%")
    if display_name:
        query += " AND display_name LIKE ?"
        params.append(f"%{display_name}%")
    if verified is not None:
        query += " AND verified=?"
        params.append(verified)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()
    return {"data": [dict(r) for r in rows], "count": len(rows)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
