"""
Trancendos Files Service — Self-Hosted Worker
=====================================================
File storage API with local filesystem + IPFS pinning. Replaces CF trancendos-files-service (R2).

Port: 8014
Zero-cost: FastAPI + SQLite, no external dependencies.
"""

from __future__ import annotations
from src.entities.health_metadata import health_entity_block

import logging
import os
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
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
                cur.execute(f"UPDATE files SET is_public=0 WHERE {id_field}=?", (id_value,))
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
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {
        "entity": health_entity_block(8014, "files-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


@_router.get("/")
async def list_all(limit: int = 50, offset: int = 0):
    """List all files."""
    return {"data": db.list(limit=limit, offset=offset)}


@_router.post("/")
async def create(data: Dict[str, Any]):
    """Create a new files entry."""
    item_id = data.get("file_id", str(uuid.uuid4()))
    data["file_id"] = item_id
    created = db.create(data)
    return {"ok": True, **created}


@_router.get("/{file_id}")
async def get_by_id(file_id: str):
    """Get a files entry by ID."""
    item = db.get("file_id", file_id)
    if not item:
        raise HTTPException(404, f"Not found: {file_id}")
    return item


@_router.patch("/{file_id}")
async def update_by_id(file_id: str, data: Dict[str, Any]):
    """Update a files entry."""
    if not db.update("file_id", file_id, data):
        raise HTTPException(404, f"Not found: {file_id}")
    return {"ok": True}


@_router.delete("/{file_id}")
async def delete_by_id(file_id: str):
    """Delete a files entry (soft delete)."""
    if not db.delete("file_id", file_id):
        raise HTTPException(404, f"Not found: {file_id}")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Domain-specific endpoints
# ---------------------------------------------------------------------------


@_router.get("/by-user/{user_id}")
async def get_by_user(user_id: str, limit: int = 50, offset: int = 0):
    """List all files uploaded by a specific user."""
    return {"data": db.list(limit=limit, offset=offset, user_id=user_id)}


@_router.get("/public")
async def list_public(limit: int = 50, offset: int = 0):
    """List all publicly accessible files."""
    return {"data": db.list(limit=limit, offset=offset, is_public=1)}


@_router.get("/by-content-type/{content_type:path}")
async def get_by_content_type(content_type: str, limit: int = 50, offset: int = 0):
    """List files by MIME content type (e.g. image/png, application/pdf)."""
    conn = db._get_conn()
    rows = conn.execute(
        "SELECT * FROM files WHERE content_type=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (content_type, limit, offset),
    ).fetchall()
    return {"data": [dict(r) for r in rows]}


@_router.get("/by-ipfs/{ipfs_cid}")
async def get_by_ipfs_cid(ipfs_cid: str):
    """Lookup a file by its IPFS content identifier."""
    conn = db._get_conn()
    row = conn.execute("SELECT * FROM files WHERE ipfs_cid=?", (ipfs_cid,)).fetchone()
    if not row:
        raise HTTPException(404, f"No file with IPFS CID: {ipfs_cid}")
    return dict(row)


@_router.post("/{file_id}/publish")
async def publish_file(file_id: str):
    """Make a file publicly accessible."""
    if not db.update("file_id", file_id, {"is_public": 1}):
        raise HTTPException(404, f"Not found: {file_id}")
    return {"ok": True, "file_id": file_id, "is_public": True}


@_router.post("/{file_id}/unpublish")
async def unpublish_file(file_id: str):
    """Restrict a file to owner-only access."""
    if not db.update("file_id", file_id, {"is_public": 0}):
        raise HTTPException(404, f"Not found: {file_id}")
    return {"ok": True, "file_id": file_id, "is_public": False}


@_router.get("/stats/storage")
async def storage_stats():
    """Total storage used per user and overall."""
    conn = db._get_conn()
    total = conn.execute(
        "SELECT SUM(size_bytes) as total_bytes, COUNT(*) as file_count FROM files"
    ).fetchone()
    by_user = conn.execute(
        "SELECT user_id, SUM(size_bytes) as bytes, COUNT(*) as files FROM files GROUP BY user_id ORDER BY bytes DESC LIMIT 20"
    ).fetchall()
    return {
        "total_bytes": total["total_bytes"] or 0,
        "file_count": total["file_count"] or 0,
        "by_user": [dict(r) for r in by_user],
    }


@_router.get("/search")
async def search_files(
    filename: Optional[str] = None,
    user_id: Optional[str] = None,
    ipfs_cid: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """Search files by filename prefix, user, or IPFS CID."""
    conn = db._get_conn()
    query = "SELECT * FROM files WHERE 1=1"
    params: list = []
    if filename:
        query += " AND filename LIKE ?"
        params.append(f"%{filename}%")
    if user_id:
        query += " AND user_id=?"
        params.append(user_id)
    if ipfs_cid:
        query += " AND ipfs_cid=?"
        params.append(ipfs_cid)
    query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(query, params).fetchall()
    return {"data": [dict(r) for r in rows], "count": len(rows)}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
