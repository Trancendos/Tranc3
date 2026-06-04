"""
Trancendos storage-service — Self-Hosted Worker
================================================
Local filesystem object storage with SQLite metadata index.
Compatible with a minimal S3-like API: buckets, objects, presigned-style
download links (local token-based).

Port: 8020
Zero-cost: FastAPI + SQLite + local filesystem, no cloud storage needed.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import secrets
import shutil
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.entities.health_metadata import health_entity_block

WORKER_PORT = 8020
WORKER_NAME = "storage-service"
DB_PATH = Path(__file__).parent / "data" / "storage.db"
STORAGE_ROOT = Path(__file__).parent / "data" / "objects"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
STORAGE_ROOT.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS buckets (
                name        TEXT PRIMARY KEY,
                description TEXT,
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS objects (
                id          TEXT NOT NULL,
                bucket      TEXT NOT NULL,
                key         TEXT NOT NULL,
                size        INTEGER NOT NULL,
                content_type TEXT,
                etag        TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}',
                path        TEXT NOT NULL,
                uploaded_at REAL NOT NULL,
                PRIMARY KEY (bucket, key)
            );
            CREATE INDEX IF NOT EXISTS idx_obj_bucket ON objects(bucket);

            CREATE TABLE IF NOT EXISTS download_tokens (
                token       TEXT PRIMARY KEY,
                bucket      TEXT NOT NULL,
                key         TEXT NOT NULL,
                expires_at  REAL NOT NULL
            );
        """)
        conn.commit()
        # seed default bucket
        conn.execute(
            "INSERT OR IGNORE INTO buckets (name, description, created_at) VALUES (?,?,?)",
            ("default", "Default storage bucket", time.time()),
        )
        conn.commit()


def _object_path(bucket: str, key: str) -> Path:
    safe_key = key.replace("/", os.sep)
    return STORAGE_ROOT / bucket / safe_key


def _etag(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class BucketCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ObjectMetadataUpdate(BaseModel):
    metadata: dict


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("storage-service DB ready, root=%s", STORAGE_ROOT)
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="storage-service",
    description="Local filesystem object storage (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    with get_conn() as conn:
        bucket_count = conn.execute("SELECT COUNT(*) FROM buckets").fetchone()[0]
        obj_count = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        total_size = conn.execute("SELECT COALESCE(SUM(size), 0) FROM objects").fetchone()[0]
    return {
        "entity": health_entity_block(8020, "storage-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "buckets": bucket_count,
        "objects": obj_count,
        "total_bytes": total_size,
    }


# --- Buckets ---


@_router.get("/buckets")
async def list_buckets():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM buckets ORDER BY name").fetchall()
    return {"buckets": [dict(r) for r in rows]}


@_router.post("/buckets", status_code=201)
async def create_bucket(req: BucketCreate):
    with get_conn() as conn:
        if conn.execute("SELECT name FROM buckets WHERE name = ?", (req.name,)).fetchone():
            raise HTTPException(status_code=409, detail="Bucket already exists")
        conn.execute(
            "INSERT INTO buckets (name, description, created_at) VALUES (?,?,?)",
            (req.name, req.description, time.time()),
        )
        conn.commit()
    (STORAGE_ROOT / req.name).mkdir(parents=True, exist_ok=True)
    return {"name": req.name}


@_router.delete("/buckets/{bucket}")
async def delete_bucket(bucket: str):
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM buckets WHERE name = ?", (bucket,)).fetchone():
            raise HTTPException(status_code=404, detail="Bucket not found")
        obj_count = conn.execute(
            "SELECT COUNT(*) FROM objects WHERE bucket=?", (bucket,),
        ).fetchone()[0]
        if obj_count > 0:
            raise HTTPException(status_code=409, detail=f"Bucket not empty ({obj_count} objects)")
        conn.execute("DELETE FROM buckets WHERE name = ?", (bucket,))
        conn.commit()
    bucket_dir = STORAGE_ROOT / bucket
    if bucket_dir.exists():
        shutil.rmtree(str(bucket_dir))
    return {"deleted": bucket}


def _ensure_bucket(bucket: str) -> None:
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM buckets WHERE name = ?", (bucket,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Bucket '{bucket}' not found")


# --- Objects ---


@_router.get("/buckets/{bucket}/objects")
async def list_objects(
    bucket: str,
    prefix: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
):
    _ensure_bucket(bucket)
    with get_conn() as conn:
        if prefix:
            rows = conn.execute(
                "SELECT id, key, size, content_type, etag, metadata, uploaded_at FROM objects WHERE bucket=? AND key LIKE ? ORDER BY key LIMIT ? OFFSET ?",
                (bucket, f"{prefix}%", limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM objects WHERE bucket=? AND key LIKE ?", (bucket, f"{prefix}%"),
            ).fetchone()[0]
        else:
            rows = conn.execute(
                "SELECT id, key, size, content_type, etag, metadata, uploaded_at FROM objects WHERE bucket=? ORDER BY key LIMIT ? OFFSET ?",
                (bucket, limit, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM objects WHERE bucket=?", (bucket,),
            ).fetchone()[0]
    return {"bucket": bucket, "total": total, "objects": [dict(r) for r in rows]}


@_router.put("/buckets/{bucket}/objects/{key:path}", status_code=201)
async def upload_object(bucket: str, key: str, file: UploadFile = File(...)):
    _ensure_bucket(bucket)
    data = await file.read()
    tag = _etag(data)
    content_type = file.content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"
    obj_path = _object_path(bucket, key)
    obj_path.parent.mkdir(parents=True, exist_ok=True)
    obj_path.write_bytes(data)
    now = time.time()
    import uuid

    obj_id = str(uuid.uuid4())
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO objects (id, bucket, key, size, content_type, etag, metadata, path, uploaded_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (obj_id, bucket, key, len(data), content_type, tag, "{}", str(obj_path), now),
        )
        conn.commit()
    return {
        "bucket": bucket,
        "key": key,
        "size": len(data),
        "etag": tag,
        "content_type": content_type,
    }


@_router.get("/buckets/{bucket}/objects/{key:path}/meta")
async def get_object_meta(bucket: str, key: str):
    _ensure_bucket(bucket)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM objects WHERE bucket=? AND key=?", (bucket, key),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Object not found")
    return dict(row)


@_router.get("/buckets/{bucket}/objects/{key:path}")
async def download_object(bucket: str, key: str):
    _ensure_bucket(bucket)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT path, content_type, etag FROM objects WHERE bucket=? AND key=?", (bucket, key),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Object not found")
    path = Path(row["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="Object file missing from storage")
    return FileResponse(str(path), media_type=row["content_type"], headers={"ETag": row["etag"]})


@_router.delete("/buckets/{bucket}/objects/{key:path}")
async def delete_object(bucket: str, key: str):
    _ensure_bucket(bucket)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT path FROM objects WHERE bucket=? AND key=?", (bucket, key),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Object not found")
        path = Path(row["path"])
        if path.exists():
            path.unlink()
        conn.execute("DELETE FROM objects WHERE bucket=? AND key=?", (bucket, key))
        conn.commit()
    return {"deleted": key, "bucket": bucket}


@_router.post("/buckets/{bucket}/objects/{key:path}/token")
async def create_download_token(bucket: str, key: str, ttl: int = Query(3600)):
    _ensure_bucket(bucket)
    with get_conn() as conn:
        if not conn.execute(
            "SELECT key FROM objects WHERE bucket=? AND key=?", (bucket, key),
        ).fetchone():
            raise HTTPException(status_code=404, detail="Object not found")
        token = secrets.token_urlsafe(32)
        conn.execute(
            "INSERT INTO download_tokens (token, bucket, key, expires_at) VALUES (?,?,?,?)",
            (token, bucket, key, time.time() + ttl),
        )
        conn.commit()
    return {"token": token, "expires_in": ttl}


@_router.get("/download/{token}")
async def download_via_token(token: str):
    now = time.time()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT bucket, key, expires_at FROM download_tokens WHERE token=?", (token,),
        ).fetchone()
    if not row or row["expires_at"] < now:
        raise HTTPException(status_code=403, detail="Token expired or invalid")
    return await download_object(row["bucket"], row["key"])


@_router.get("/stats")
async def storage_stats():
    with get_conn() as conn:
        by_bucket = conn.execute(
            "SELECT bucket, COUNT(*) as objects, SUM(size) as bytes FROM objects GROUP BY bucket",
        ).fetchall()
    return {"buckets": [dict(r) for r in by_bucket]}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
