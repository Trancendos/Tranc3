"""
Trancendos Files Service — Self-Hosted Worker
=====================================================
File storage API with local filesystem + IPFS pinning. Replaces CF trancendos-files-service (R2).

Port: 8014
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations

import logging
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
WORKER_PORT = 8014
WORKER_NAME = "files-service"
DB_PATH = Path(__file__).parent / "data" / "files.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
class FilesDatabase:
    """SQLite-backed storage for files."""

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
                CREATE TABLE IF NOT EXISTS files (
                    file_id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT DEFAULT 'application/octet-stream',
                    size_bytes INTEGER DEFAULT 0,
                    path TEXT NOT NULL,
                    ipfs_cid TEXT,
                    user_id TEXT,
                    is_public INTEGER DEFAULT 0,
                    metadata TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                )
            """)

    def create(self, data: Dict[str, Any]) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        data.setdefault("created_at", now)
        cols = list(data.keys())
        vals = list(data.values())
        placeholders = ", ".join("?" for _ in cols)
        with self._cursor() as cur:
            cur.execute(f"INSERT INTO files ({', '.join(cols)}) VALUES ({placeholders})", vals)
        return data

    def get(self, id_field: str, id_value: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(f"SELECT * FROM files WHERE {id_field}=?", (id_value,)).fetchone()
        return dict(row) if row else None

    def list(self, limit: int = 50, offset: int = 0, **filters) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM files WHERE 1=1"
        params: list = []
        for key, val in filters.items():
            query += f" AND {key}=?"
            params.append(val)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update(self, id_field: str, id_value: str, data: Dict[str, Any]) -> bool:
        # files table doesn't have updated_at column
        sets = ", ".join(f"{k}=?" for k in data.keys())
        vals = list(data.values()) + [id_value]
        with self._cursor() as cur:
            cur.execute(f"UPDATE files SET {sets} WHERE {id_field}=?", vals)
            return cur.rowcount > 0

    def delete(self, id_field: str, id_value: str, soft: bool = True) -> bool:
        if soft:
            with self._cursor() as cur:
                cur.execute(f"UPDATE files SET is_public=0 WHERE {id_field}=?",
                            (id_value,))
                return cur.rowcount > 0
        else:
            with self._cursor() as cur:
                cur.execute(f"DELETE FROM files WHERE {id_field}=?", (id_value,))
                return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
db = FilesDatabase(DB_PATH)

app = FastAPI(
    title="Files Service",
    description="File storage API with local filesystem + IPFS pinning. Replaces CF trancendos-files-service (R2).",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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


# TODO: Add specific CRUD endpoints for files-service
# The database class above provides create(), get(), list(), update(), delete() methods
# Implement domain-specific endpoints based on business requirements

@app.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all files."""
    return {"data": db.list(limit=limit, offset=offset)}


@app.post("/")
async def create(data: Dict[str, Any]):
    """Create a new files entry."""
    item_id = data.get("file_id", str(uuid.uuid4()))
    data["file_id"] = item_id
    created = db.create(data)
    return {"ok": True, **created}


@app.get("/{file_id}")
async def get_by_id(file_id: str):
    """Get a files entry by ID."""
    item = db.get("file_id", file_id)
    if not item:
        raise HTTPException(404, f"Not found: {file_id}")
    return item


@app.patch("/{file_id}")
async def update_by_id(file_id: str, data: Dict[str, Any]):
    """Update a files entry."""
    if not db.update("file_id", file_id, data):
        raise HTTPException(404, f"Not found: {file_id}")
    return {"ok": True}


@app.delete("/{file_id}")
async def delete_by_id(file_id: str):
    """Delete a files entry (soft delete)."""
    if not db.delete("file_id", file_id):
        raise HTTPException(404, f"Not found: {file_id}")
    return {"ok": True}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
