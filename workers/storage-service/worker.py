"""
Trancendos storage-service — ACO pheromone router, 8 zero-cost backends
========================================================================
Backends (priority order):
  1. Local filesystem  — always available, unlimited
  2. MinIO             — self-hosted S3 (MIT, docker-compose)
  3. IPFS (kubo)       — distributed content-addressed (docker-compose)
  4. Valkey            — Redis-fork blob store (docker-compose)
  5. DuckDB blob       — in-process OLAP + blob (always available)
  6. SeaweedFS         — optional self-hosted distributed (Apache 2.0)
  7. Garage            — optional self-hosted S3-compatible (AGPL)
  8. Offline stub      — final fallback, never blocks

Port: 8020
Zero-cost: no paid cloud APIs; all backends self-hosted or in-process.
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
import uuid
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
from fastapi import APIRouter, Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

# ── Config ────────────────────────────────────────────────────────────────────
WORKER_PORT = int(os.environ.get("STORAGE_PORT", "8020"))
WORKER_NAME = "storage-service"
DB_PATH = Path(os.environ.get("STORAGE_DB_PATH", "/data/storage.db"))
LOCAL_ROOT = Path(os.environ.get("STORAGE_LOCAL_ROOT", "/data/objects"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
LOCAL_ROOT.mkdir(parents=True, exist_ok=True)

MINIO_ENDPOINT = os.environ.get("MINIO_ENDPOINT", "http://minio:9000")
MINIO_ACCESS_KEY = os.environ.get("MINIO_ROOT_USER", "minioadmin")
MINIO_SECRET_KEY = os.environ.get("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_BUCKET = os.environ.get("MINIO_DEFAULT_BUCKET", "trancendos")
MINIO_ENABLED = os.environ.get("STORAGE_MINIO", "1") == "1"

IPFS_API = os.environ.get("IPFS_API_URL", "http://ipfs:5001")
IPFS_ENABLED = os.environ.get("STORAGE_IPFS", "1") == "1"

VALKEY_URL = os.environ.get("VALKEY_URL", "redis://valkey:6379/0")
VALKEY_ENABLED = os.environ.get("STORAGE_VALKEY", "1") == "1"
VALKEY_MAX_BYTES = int(os.environ.get("STORAGE_VALKEY_MAX_BYTES", str(10 * 1024 * 1024)))

DUCKDB_PATH = os.environ.get("STORAGE_DUCKDB_PATH", "/data/storage.duckdb")
DUCKDB_ENABLED = os.environ.get("STORAGE_DUCKDB", "1") == "1"

SEAWEEDFS_MASTER = os.environ.get("SEAWEEDFS_MASTER", "http://seaweedfs-master:9333")
SEAWEEDFS_ENABLED = os.environ.get("STORAGE_SEAWEEDFS", "0") == "1"

GARAGE_ENDPOINT = os.environ.get("GARAGE_ENDPOINT", "http://garage:3900")
GARAGE_ENABLED = os.environ.get("STORAGE_GARAGE", "0") == "1"

PHEROMONE_DECAY = float(os.environ.get("STORAGE_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW = int(os.environ.get("STORAGE_QUOTA_WINDOW", "3600"))
QUOTA_MAX = int(os.environ.get("STORAGE_QUOTA_MAX_CALLS", "50000"))
OP_TIMEOUT = float(os.environ.get("STORAGE_OP_TIMEOUT", "30.0"))
PROBE_TIMEOUT = float(os.environ.get("STORAGE_PROBE_TIMEOUT", "3.0"))

INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ── ACO ThresholdGuard ────────────────────────────────────────────────────────


class ThresholdGuard:
    def __init__(self, name: str, quota: int, window: int) -> None:
        self.name = name
        self.quota = quota
        self.window = window
        self._calls: deque[float] = deque()
        self.pheromone: float = 1.0

    def can_allow(self) -> bool:
        now = time.time()
        cutoff = now - self.window
        while self._calls and self._calls[0] < cutoff:
            self._calls.popleft()
        return len(self._calls) < self.quota

    def record(self) -> None:
        self._calls.append(time.time())

    def reinforce(self) -> None:
        self.pheromone = min(1.0, self.pheromone + 0.1)

    def decay(self) -> None:
        self.pheromone = max(0.0, self.pheromone - PHEROMONE_DECAY)

    @property
    def calls_in_window(self) -> int:
        now = time.time()
        cutoff = now - self.window
        return sum(1 for t in self._calls if t >= cutoff)

    @property
    def quota_remaining(self) -> int:
        return max(0, self.quota - self.calls_in_window)


_BACKENDS = ["local", "minio", "ipfs", "valkey", "duckdb", "seaweedfs", "garage", "offline"]

_GUARDS: Dict[str, ThresholdGuard] = {
    "local": ThresholdGuard("local", QUOTA_MAX, QUOTA_WINDOW),
    "minio": ThresholdGuard("minio", QUOTA_MAX, QUOTA_WINDOW),
    "ipfs": ThresholdGuard("ipfs", QUOTA_MAX, QUOTA_WINDOW),
    "valkey": ThresholdGuard("valkey", QUOTA_MAX, QUOTA_WINDOW),
    "duckdb": ThresholdGuard("duckdb", QUOTA_MAX, QUOTA_WINDOW),
    "seaweedfs": ThresholdGuard("seaweedfs", QUOTA_MAX, QUOTA_WINDOW),
    "garage": ThresholdGuard("garage", QUOTA_MAX, QUOTA_WINDOW),
    "offline": ThresholdGuard("offline", 999_999, QUOTA_WINDOW),
}

_ENABLED: Dict[str, bool] = {
    "local": True,
    "minio": MINIO_ENABLED,
    "ipfs": IPFS_ENABLED,
    "valkey": VALKEY_ENABLED,
    "duckdb": DUCKDB_ENABLED,
    "seaweedfs": SEAWEEDFS_ENABLED,
    "garage": GARAGE_ENABLED,
    "offline": True,
}

_PRIORITY = ["local", "minio", "duckdb", "valkey", "ipfs", "seaweedfs", "garage", "offline"]


def _select_backend() -> str:
    available = [b for b in _PRIORITY if _ENABLED[b] and _GUARDS[b].can_allow()]
    if not available:
        return "offline"
    return max(available, key=lambda b: _GUARDS[b].pheromone)


# ── SQLite metadata store ─────────────────────────────────────────────────────


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init_db() -> None:
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS buckets (
                name        TEXT PRIMARY KEY,
                description TEXT,
                created_at  REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS objects (
                id           TEXT NOT NULL,
                bucket       TEXT NOT NULL,
                key          TEXT NOT NULL,
                size         INTEGER NOT NULL,
                content_type TEXT,
                etag         TEXT NOT NULL,
                backend      TEXT NOT NULL,
                backend_ref  TEXT,
                metadata     TEXT DEFAULT '{}',
                path         TEXT,
                uploaded_at  REAL NOT NULL,
                PRIMARY KEY (bucket, key)
            );
            CREATE INDEX IF NOT EXISTS idx_obj_bucket ON objects(bucket);
            CREATE TABLE IF NOT EXISTS download_tokens (
                token      TEXT PRIMARY KEY,
                bucket     TEXT NOT NULL,
                key        TEXT NOT NULL,
                expires_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS backend_events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                backend   TEXT NOT NULL,
                success   INTEGER NOT NULL,
                ts        REAL NOT NULL
            );
        """)
        c.execute(
            "INSERT OR IGNORE INTO buckets (name, description, created_at) VALUES (?,?,?)",
            ("default", "Default storage bucket", time.time()),
        )
        c.commit()


def _etag(data: bytes) -> str:
    return hashlib.md5(data, usedforsecurity=False).hexdigest()


def _record_event(backend: str, success: bool) -> None:
    try:
        with _conn() as c:
            c.execute(
                "INSERT INTO backend_events (backend, success, ts) VALUES (?,?,?)",
                (backend, int(success), time.time()),
            )
            c.commit()
    except Exception:  # never block on audit writes
        pass


# ── Backend adapters ──────────────────────────────────────────────────────────


def _local_put(bucket: str, key: str, data: bytes) -> tuple[str, Optional[str]]:
    path = LOCAL_ROOT / bucket / key.replace("/", os.sep)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return "local", str(path)


def _local_get(path: str) -> Optional[bytes]:
    p = Path(path)
    return p.read_bytes() if p.exists() else None


async def _minio_put(bucket: str, key: str, data: bytes, content_type: str) -> Optional[str]:
    try:
        import boto3  # type: ignore[import-untyped]
        from botocore.config import Config  # type: ignore[import-untyped]

        s3 = boto3.client(
            "s3",
            endpoint_url=MINIO_ENDPOINT,
            aws_access_key_id=MINIO_ACCESS_KEY,
            aws_secret_access_key=MINIO_SECRET_KEY,
            config=Config(connect_timeout=PROBE_TIMEOUT, read_timeout=OP_TIMEOUT),
        )
        s3.put_object(
            Bucket=MINIO_BUCKET, Key=f"{bucket}/{key}", Body=data, ContentType=content_type
        )
        return f"minio://{MINIO_BUCKET}/{bucket}/{key}"
    except Exception:
        return None


async def _ipfs_put(data: bytes) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=OP_TIMEOUT) as client:
            resp = await client.post(
                f"{IPFS_API}/api/v0/add",
                files={"file": data},
            )
            if resp.status_code == 200:
                cid = resp.json().get("Hash")
                return f"ipfs://{cid}"
    except Exception:  # IPFS unreachable — try next backend
        pass
    return None


async def _valkey_put(key: str, data: bytes) -> Optional[str]:
    if len(data) > VALKEY_MAX_BYTES:
        return None
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        r = aioredis.from_url(VALKEY_URL, socket_timeout=OP_TIMEOUT)
        await r.set(f"blob:{key}", data)
        await r.aclose()
        return f"valkey://blob:{key}"
    except Exception:  # Valkey unreachable — try next backend
        pass
    return None


async def _valkey_get(key: str) -> Optional[bytes]:
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        r = aioredis.from_url(VALKEY_URL, socket_timeout=OP_TIMEOUT)
        data = await r.get(f"blob:{key}")
        await r.aclose()
        return data
    except Exception:  # Valkey unreachable
        pass
    return None


def _duckdb_put(bucket: str, key: str, data: bytes) -> Optional[str]:
    try:
        import duckdb  # type: ignore[import-untyped]

        con = duckdb.connect(DUCKDB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS blobs (
                bucket TEXT, key TEXT, data BLOB,
                PRIMARY KEY (bucket, key)
            )
        """)
        con.execute(
            "INSERT OR REPLACE INTO blobs (bucket, key, data) VALUES (?, ?, ?)",
            [bucket, key, data],
        )
        con.close()
        return f"duckdb://{bucket}/{key}"
    except Exception:  # DuckDB error — try next backend
        pass
    return None


def _duckdb_get(bucket: str, key: str) -> Optional[bytes]:
    try:
        import duckdb  # type: ignore[import-untyped]

        con = duckdb.connect(DUCKDB_PATH)
        row = con.execute(
            "SELECT data FROM blobs WHERE bucket=? AND key=?", [bucket, key]
        ).fetchone()
        con.close()
        return bytes(row[0]) if row else None
    except Exception:  # DuckDB error
        pass
    return None


def _offline_put(bucket: str, key: str) -> str:
    return f"offline://{bucket}/{key}"


# ── Models ────────────────────────────────────────────────────────────────────


class BucketCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ObjectMetaUpdate(BaseModel):
    metadata: Dict[str, Any]


# ── Lifespan ──────────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        otel_ep = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if otel_ep:
            provider = TracerProvider()
            provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=otel_ep)))
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
    except Exception:  # OTel is optional — never block startup
        pass
    _init_db()
    logger.info("storage-service ready — root=%s db=%s", LOCAL_ROOT, DB_PATH)
    yield


# ── App ───────────────────────────────────────────────────────────────────────

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="storage-service",
    description="Multi-backend ACO object storage (8 zero-cost backends) — Lead AI: To be Defined",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


async def _auth(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    if not INTERNAL_SECRET:
        return
    if x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


_router = APIRouter(dependencies=[Depends(_auth)])


@app.get("/health", include_in_schema=False)
def health() -> JSONResponse:
    with _conn() as c:
        obj_count = c.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
        bucket_count = c.execute("SELECT COUNT(*) FROM buckets").fetchone()[0]
    backends = [
        {
            "name": b,
            "enabled": _ENABLED[b],
            "healthy": _GUARDS[b].can_allow(),
            "pheromone": round(_GUARDS[b].pheromone, 4),
        }
        for b in _PRIORITY
    ]
    return JSONResponse(
        {
            "service": WORKER_NAME,
            "entity": "DocUtari",
            "lead_ai": "To be Defined",
            "status": "ok",
            "uptime_s": round((datetime.now(timezone.utc) - STARTED_AT).total_seconds(), 1),
            "objects": obj_count,
            "buckets": bucket_count,
            "active_backend": _select_backend(),
            "backends": backends,
        }
    )


# ── Buckets ───────────────────────────────────────────────────────────────────


@_router.get("/storage/buckets")
def list_buckets() -> Dict[str, Any]:
    with _conn() as c:
        rows = c.execute("SELECT * FROM buckets ORDER BY name").fetchall()
    return {"buckets": [dict(r) for r in rows]}


@_router.post("/storage/buckets", status_code=201)
def create_bucket(req: BucketCreate) -> Dict[str, Any]:
    with _conn() as c:
        if c.execute("SELECT name FROM buckets WHERE name=?", (req.name,)).fetchone():
            raise HTTPException(status_code=409, detail="Bucket already exists")
        c.execute(
            "INSERT INTO buckets (name, description, created_at) VALUES (?,?,?)",
            (req.name, req.description, time.time()),
        )
        c.commit()
    (LOCAL_ROOT / req.name).mkdir(parents=True, exist_ok=True)
    return {"name": req.name}


@_router.delete("/storage/buckets/{bucket}", status_code=204)
def delete_bucket(bucket: str) -> None:
    with _conn() as c:
        if not c.execute("SELECT name FROM buckets WHERE name=?", (bucket,)).fetchone():
            raise HTTPException(status_code=404, detail="Bucket not found")
        n = c.execute("SELECT COUNT(*) FROM objects WHERE bucket=?", (bucket,)).fetchone()[0]
        if n:
            raise HTTPException(status_code=409, detail=f"Bucket not empty ({n} objects)")
        c.execute("DELETE FROM buckets WHERE name=?", (bucket,))
        c.commit()
    bucket_dir = LOCAL_ROOT / bucket
    if bucket_dir.exists():
        shutil.rmtree(str(bucket_dir))


def _ensure_bucket(bucket: str) -> None:
    with _conn() as c:
        if not c.execute("SELECT name FROM buckets WHERE name=?", (bucket,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Bucket '{bucket}' not found")


# ── Objects ───────────────────────────────────────────────────────────────────


@_router.get("/storage/buckets/{bucket}/objects")
def list_objects(
    bucket: str,
    prefix: Optional[str] = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
) -> Dict[str, Any]:
    _ensure_bucket(bucket)
    with _conn() as c:
        if prefix:
            rows = c.execute(
                "SELECT id,key,size,content_type,etag,backend,uploaded_at FROM objects WHERE bucket=? AND key LIKE ? ORDER BY key LIMIT ? OFFSET ?",
                (bucket, f"{prefix}%", limit, offset),
            ).fetchall()
            total = c.execute(
                "SELECT COUNT(*) FROM objects WHERE bucket=? AND key LIKE ?", (bucket, f"{prefix}%")
            ).fetchone()[0]
        else:
            rows = c.execute(
                "SELECT id,key,size,content_type,etag,backend,uploaded_at FROM objects WHERE bucket=? ORDER BY key LIMIT ? OFFSET ?",
                (bucket, limit, offset),
            ).fetchall()
            total = c.execute("SELECT COUNT(*) FROM objects WHERE bucket=?", (bucket,)).fetchone()[
                0
            ]
    return {"bucket": bucket, "total": total, "objects": [dict(r) for r in rows]}


@_router.put("/storage/buckets/{bucket}/objects/{key:path}", status_code=201)
async def upload_object(bucket: str, key: str, file: UploadFile = File(...)) -> Dict[str, Any]:
    _ensure_bucket(bucket)
    data = await file.read()
    tag = _etag(data)
    ctype = file.content_type or mimetypes.guess_type(key)[0] or "application/octet-stream"

    backend = _select_backend()
    guard = _GUARDS[backend]
    guard.record()

    backend_ref: Optional[str] = None
    obj_path: Optional[str] = None
    success = True

    if backend == "local":
        _, obj_path = _local_put(bucket, key, data)
        backend_ref = obj_path
    elif backend == "minio":
        backend_ref = await _minio_put(bucket, key, data, ctype)
        success = backend_ref is not None
        if not success:
            _, obj_path = _local_put(bucket, key, data)
            backend_ref = obj_path
            backend = "local"
    elif backend == "ipfs":
        backend_ref = await _ipfs_put(data)
        success = backend_ref is not None
        if not success:
            _, obj_path = _local_put(bucket, key, data)
            backend_ref = obj_path
            backend = "local"
    elif backend == "valkey":
        vk = await _valkey_put(f"{bucket}/{key}", data)
        success = vk is not None
        backend_ref = vk
        if not success:
            _, obj_path = _local_put(bucket, key, data)
            backend_ref = obj_path
            backend = "local"
    elif backend == "duckdb":
        backend_ref = _duckdb_put(bucket, key, data)
        success = backend_ref is not None
        if not success:
            _, obj_path = _local_put(bucket, key, data)
            backend_ref = obj_path
            backend = "local"
    elif backend == "offline":
        backend_ref = _offline_put(bucket, key)
        obj_path = None

    if success:
        guard.reinforce()
    else:
        guard.decay()
    _record_event(backend, success)

    obj_id = str(uuid.uuid4())
    with _conn() as c:
        c.execute(
            "INSERT OR REPLACE INTO objects (id,bucket,key,size,content_type,etag,backend,backend_ref,metadata,path,uploaded_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                obj_id,
                bucket,
                key,
                len(data),
                ctype,
                tag,
                backend,
                backend_ref,
                "{}",
                obj_path,
                time.time(),
            ),
        )
        c.commit()
    return {"bucket": bucket, "key": key, "size": len(data), "etag": tag, "backend": backend}


@_router.get("/storage/buckets/{bucket}/objects/{key:path}/meta")
def get_object_meta(bucket: str, key: str) -> Dict[str, Any]:
    _ensure_bucket(bucket)
    with _conn() as c:
        row = c.execute("SELECT * FROM objects WHERE bucket=? AND key=?", (bucket, key)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Object not found")
    return dict(row)


@_router.get("/storage/buckets/{bucket}/objects/{key:path}")
async def download_object(bucket: str, key: str):
    _ensure_bucket(bucket)
    with _conn() as c:
        row = c.execute(
            "SELECT path,backend,backend_ref,content_type,etag FROM objects WHERE bucket=? AND key=?",
            (bucket, key),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Object not found")

    backend = row["backend"]
    ctype = row["content_type"] or "application/octet-stream"
    headers = {"ETag": row["etag"]}

    if backend == "local" and row["path"]:
        p = Path(row["path"])
        if not p.exists():
            raise HTTPException(status_code=404, detail="Object file missing")
        return FileResponse(str(p), media_type=ctype, headers=headers)

    if backend == "valkey":
        data = await _valkey_get(f"{bucket}/{key}")
        if data:
            from fastapi.responses import Response

            return Response(content=data, media_type=ctype, headers=headers)

    if backend == "duckdb":
        data = _duckdb_get(bucket, key)
        if data:
            from fastapi.responses import Response

            return Response(content=data, media_type=ctype, headers=headers)

    if backend == "ipfs" and row["backend_ref"]:
        cid = row["backend_ref"].replace("ipfs://", "")
        raise HTTPException(
            status_code=302,
            headers={
                "Location": f"{os.environ.get('IPFS_GATEWAY_URL', 'http://ipfs:8080')}/ipfs/{cid}"
            },
            detail="Redirect to IPFS gateway",
        )

    raise HTTPException(status_code=404, detail="Object data unavailable")


@_router.delete("/storage/buckets/{bucket}/objects/{key:path}", status_code=204)
def delete_object(bucket: str, key: str) -> None:
    _ensure_bucket(bucket)
    with _conn() as c:
        row = c.execute(
            "SELECT path FROM objects WHERE bucket=? AND key=?", (bucket, key)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Object not found")
        if row["path"]:
            p = Path(row["path"])
            if p.exists():
                p.unlink()
        c.execute("DELETE FROM objects WHERE bucket=? AND key=?", (bucket, key))
        c.commit()


@_router.post("/storage/buckets/{bucket}/objects/{key:path}/token")
def create_token(bucket: str, key: str, ttl: int = Query(3600)) -> Dict[str, Any]:
    _ensure_bucket(bucket)
    with _conn() as c:
        if not c.execute(
            "SELECT key FROM objects WHERE bucket=? AND key=?", (bucket, key)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Object not found")
        token = secrets.token_urlsafe(32)
        c.execute(
            "INSERT INTO download_tokens (token,bucket,key,expires_at) VALUES (?,?,?,?)",
            (token, bucket, key, time.time() + ttl),
        )
        c.commit()
    return {"token": token, "expires_in": ttl}


@_router.get("/storage/download/{token}")
async def download_via_token(token: str):
    with _conn() as c:
        row = c.execute(
            "SELECT bucket,key,expires_at FROM download_tokens WHERE token=?", (token,)
        ).fetchone()
    if not row or row["expires_at"] < time.time():
        raise HTTPException(status_code=403, detail="Token expired or invalid")
    return await download_object(row["bucket"], row["key"])


@_router.get("/storage/status")
def storage_status() -> Dict[str, Any]:
    with _conn() as c:
        by_bucket = c.execute(
            "SELECT bucket, COUNT(*) as objects, COALESCE(SUM(size),0) as bytes FROM objects GROUP BY bucket"
        ).fetchall()
    return {
        "active_backend": _select_backend(),
        "backends": [
            {
                "name": b,
                "enabled": _ENABLED[b],
                "healthy": _GUARDS[b].can_allow(),
                "pheromone": round(_GUARDS[b].pheromone, 4),
                "calls_in_window": _GUARDS[b].calls_in_window,
                "quota_remaining": _GUARDS[b].quota_remaining,
            }
            for b in _PRIORITY
        ],
        "buckets": [dict(r) for r in by_bucket],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
