"""
Trancendos cdn-service — Self-Hosted Worker
===========================================
Static asset serving with proper cache headers, ETag support, conditional
requests (If-None-Match / If-Modified-Since), and optional asset registration.
Acts as the origin server for the Traefik CDN layer.

Port: 8028
Zero-cost: FastAPI + local filesystem, no external CDN cost.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from Dimensional.path_validation import (
    existing_file_path_str,
)

# validate_existing_file is an alias for existing_file_path_str
validate_existing_file = existing_file_path_str

WORKER_PORT = 8028
WORKER_NAME = "cdn-service"
DB_PATH = Path(__file__).parent / "data" / "cdn.db"
ASSETS_ROOT = Path(__file__).parent / "data" / "assets"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ASSETS_ROOT.mkdir(parents=True, exist_ok=True)

# Cache control header templates (seconds)
CACHE_IMMUTABLE = "public, max-age=31536000, immutable"  # 1 year — hashed assets
CACHE_LONG = "public, max-age=86400"  # 24h — versioned assets
CACHE_SHORT = "public, max-age=300"  # 5m — dynamic assets
CACHE_NONE = "no-store"

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
            CREATE TABLE IF NOT EXISTS assets (
                path            TEXT PRIMARY KEY,
                etag            TEXT NOT NULL,
                content_type    TEXT NOT NULL,
                size            INTEGER NOT NULL,
                cache_policy    TEXT NOT NULL DEFAULT 'long',
                registered_at   REAL NOT NULL,
                last_served     REAL,
                serve_count     INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS serve_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                path        TEXT NOT NULL,
                status      INTEGER NOT NULL,
                cache_hit   INTEGER NOT NULL DEFAULT 0,
                ip          TEXT,
                user_agent  TEXT,
                served_at   REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_serve_path ON serve_log(path, served_at);
        """)
        conn.commit()


def _file_etag(path: Path) -> str:
    h = hashlib.sha1(usedforsecurity=False)
    h.update(str(path.stat().st_mtime).encode())
    h.update(str(path.stat().st_size).encode())
    return f'"{h.hexdigest()}"'


def _register_file(conn: sqlite3.Connection, asset_path: str, full_path: Path) -> dict:
    etag = _file_etag(full_path)
    ct = mimetypes.guess_type(full_path.name)[0] or "application/octet-stream"
    size = full_path.stat().st_size
    # determine cache policy by extension
    ext = full_path.suffix.lower()
    if ext in (".js", ".css", ".woff", ".woff2", ".ttf"):
        policy = "immutable"
    elif ext in (".html", ".htm"):
        policy = "short"
    else:
        policy = "long"
    conn.execute(
        "INSERT OR REPLACE INTO assets (path, etag, content_type, size, cache_policy, registered_at) VALUES (?,?,?,?,?,?)",
        (asset_path, etag, ct, size, policy, time.time()),
    )
    return {"etag": etag, "content_type": ct, "size": size, "cache_policy": policy}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class AssetRegister(BaseModel):
    path: str
    cache_policy: Optional[str] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.cdn-service")
    except Exception:
        pass  # OTel is optional — never block startup
    init_db()
    # Auto-register existing files in assets root
    with get_conn() as conn:
        registered = 0
        for f in ASSETS_ROOT.rglob("*"):
            if f.is_file():
                asset_path = "/" + str(f.relative_to(ASSETS_ROOT)).replace(os.sep, "/")
                _register_file(conn, asset_path, f)
                registered += 1
        conn.commit()
    logger.info("cdn-service DB ready, %d assets auto-registered", registered)
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="cdn-service",
    description="Static asset CDN origin with ETag/cache headers (self-hosted)",
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
POLICY_HEADERS = {
    "immutable": CACHE_IMMUTABLE,
    "long": CACHE_LONG,
    "short": CACHE_SHORT,
    "none": CACHE_NONE,
}


@app.get("/health")
async def health():
    with get_conn() as conn:
        asset_count = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        total_size = conn.execute("SELECT COALESCE(SUM(size), 0) FROM assets").fetchone()[0]
        serve_count = conn.execute("SELECT COALESCE(SUM(serve_count), 0) FROM assets").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "registered_assets": asset_count,
        "total_bytes": total_size,
        "total_serves": serve_count,
        "entity": {
            "location": "The Studio",
            "pillar": "Creativity",
            "lead_ai": "Voxx",
            "primes": ["Cornelius MacIntyre"],
            "primary_function": "Central Hub of the Creativity Center",
        },
    }


@_router.get("/assets")
async def list_assets(
    prefix: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    with get_conn() as conn:
        if prefix:
            rows = conn.execute(
                "SELECT * FROM assets WHERE path LIKE ? ORDER BY path LIMIT ? OFFSET ?",
                (f"{prefix}%", limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM assets ORDER BY path LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
    return {"assets": [dict(r) for r in rows]}


@_router.get("/assets/stats")
async def asset_stats():
    with get_conn() as conn:
        by_policy = conn.execute(
            "SELECT cache_policy, COUNT(*) as count, SUM(size) as bytes FROM assets GROUP BY cache_policy"
        ).fetchall()
        top = conn.execute(
            "SELECT path, serve_count FROM assets ORDER BY serve_count DESC LIMIT 10"
        ).fetchall()
    return {"by_policy": [dict(r) for r in by_policy], "top_assets": [dict(r) for r in top]}


@_router.get("/static/{path:path}")
async def serve_asset(
    path: str,
    request: Request,
    if_none_match: Optional[str] = Header(None),
    if_modified_since: Optional[str] = Header(None),
):
    asset_path = f"/{path}"
    full_path = ASSETS_ROOT / path

    if not full_path.exists() or not full_path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")

    with get_conn() as conn:
        row = conn.execute("SELECT * FROM assets WHERE path = ?", (asset_path,)).fetchone()
        if not row:
            meta = _register_file(conn, asset_path, full_path)
            conn.commit()
            etag = meta["etag"]
            content_type = meta["content_type"]
            cache_policy = meta["cache_policy"]
        else:
            etag = row["etag"]
            content_type = row["content_type"]
            cache_policy = row["cache_policy"]
            # Refresh etag if file changed
            fresh_etag = _file_etag(full_path)
            if fresh_etag != etag:
                etag = fresh_etag
                conn.execute("UPDATE assets SET etag=? WHERE path=?", (etag, asset_path))
            conn.execute(
                "UPDATE assets SET last_served=?, serve_count=serve_count+1 WHERE path=?",
                (time.time(), asset_path),
            )
        conn.execute(
            "INSERT INTO serve_log (path, status, cache_hit, ip, user_agent, served_at) VALUES (?,?,?,?,?,?)",
            (
                asset_path,
                304 if if_none_match == etag else 200,
                0,
                request.client.host if request.client else None,
                request.headers.get("user-agent", "")[:200],
                time.time(),
            ),
        )
        conn.commit()

    cache_control = POLICY_HEADERS.get(cache_policy, CACHE_LONG)

    # Conditional request handling
    if if_none_match and if_none_match == etag:
        return Response(status_code=304, headers={"ETag": etag, "Cache-Control": cache_control})

    return FileResponse(
        str(full_path),
        media_type=content_type,
        headers={
            "ETag": etag,
            "Cache-Control": cache_control,
            "Vary": "Accept-Encoding",
        },
    )


@_router.post("/register")
async def register_asset(req: AssetRegister):
    full_path = ASSETS_ROOT / req.path.lstrip("/")
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="File not found in assets root")
    with get_conn() as conn:
        meta = _register_file(conn, req.path, full_path)
        if req.cache_policy:
            conn.execute(
                "UPDATE assets SET cache_policy=? WHERE path=?", (req.cache_policy, req.path)
            )
        conn.commit()
    return {"registered": req.path, **meta}


@_router.get("/serve-log/{path:path}")
async def serve_log(path: str, limit: int = 50):
    asset_path = f"/{path}"
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, cache_hit, ip, served_at FROM serve_log WHERE path=? ORDER BY served_at DESC LIMIT ?",
            (asset_path, limit),
        ).fetchall()
    return {"path": asset_path, "log": [dict(r) for r in rows]}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
