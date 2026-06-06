"""
Trancendos cache-service — Self-Hosted Worker
==============================================
Distributed TTL key/value cache with SQLite persistence.
Compatible with a Redis-like GET/SET/DELETE API.

Port: 8023
Zero-cost: In-memory dict (fast) + SQLite (persistent on restart), no Redis needed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from src.database.encrypted_sqlite import connect as sqlite3_connect
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.entities.health_metadata import health_entity_block

WORKER_PORT = 8023
WORKER_NAME = "cache-service"
DB_PATH = Path(__file__).parent / "data" / "cache.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3_connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key       TEXT PRIMARY KEY,
                value     TEXT NOT NULL,
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (unixepoch('now'))
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
        conn.commit()


# ---------------------------------------------------------------------------
# In-memory layer (fast path) — backed by SQLite on startup
# ---------------------------------------------------------------------------

_store: Dict[str, tuple[Any, Optional[float]]] = {}  # key → (value, expires_at or None)


def _load_from_db() -> None:
    now = time.time()
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT key, value, expires_at FROM cache WHERE expires_at IS NULL OR expires_at > ?",
            (now,),
        ).fetchall()
    for row in rows:
        _store[row["key"]] = (json.loads(row["value"]), row["expires_at"])


def _persist(key: str, value: Any, expires_at: Optional[float]) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO cache (key, value, expires_at) VALUES (?, ?, ?)",
            (key, json.dumps(value), expires_at),
        )
        conn.commit()


def _delete_from_db(key: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        conn.commit()


def _flush_db() -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM cache")
        conn.commit()


async def _eviction_loop() -> None:
    """Periodically evict expired keys from in-memory store and DB."""
    while True:
        await asyncio.sleep(30)
        now = time.time()
        expired = [k for k, (_, exp) in list(_store.items()) if exp is not None and exp <= now]
        for k in expired:
            _store.pop(k, None)
        if expired:
            with get_conn() as conn:
                conn.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
                conn.commit()
            logger.info("Evicted %d expired keys", len(expired))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class SetRequest(BaseModel):
    value: Any
    ttl: Optional[int] = Field(None, description="TTL in seconds; omit for no expiry")


class SetResponse(BaseModel):
    key: str
    ttl: Optional[int]
    expires_at: Optional[str]


class GetResponse(BaseModel):
    key: str
    value: Any
    ttl_remaining: Optional[float]


class MultiSetRequest(BaseModel):
    entries: Dict[str, Any]
    ttl: Optional[int] = None


class KeysResponse(BaseModel):
    keys: List[str]
    count: int


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _load_from_db()
    logger.info("Cache loaded %d keys from DB", len(_store))
    task = asyncio.create_task(_eviction_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="cache-service",
    description="Distributed TTL cache (self-hosted)",
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
    now = time.time()
    active = sum(1 for _, (_, exp) in _store.items() if exp is None or exp > now)
    return {
        "entity": health_entity_block(8023, "cache-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "keys_active": active,
    }


@_router.get("/cache/{key}", response_model=GetResponse)
async def get_key(key: str):
    now = time.time()
    if key not in _store:
        raise HTTPException(status_code=404, detail="Key not found")
    value, expires_at = _store[key]
    if expires_at is not None and expires_at <= now:
        _store.pop(key, None)
        _delete_from_db(key)
        raise HTTPException(status_code=404, detail="Key expired")
    ttl_remaining = (expires_at - now) if expires_at is not None else None
    return GetResponse(key=key, value=value, ttl_remaining=ttl_remaining)


@_router.put("/cache/{key}", response_model=SetResponse)
async def set_key(key: str, req: SetRequest):
    expires_at = (time.time() + req.ttl) if req.ttl else None
    _store[key] = (req.value, expires_at)
    _persist(key, req.value, expires_at)
    exp_str = (
        datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at else None
    )
    return SetResponse(key=key, ttl=req.ttl, expires_at=exp_str)


@_router.delete("/cache/{key}")
async def delete_key(key: str):
    if key not in _store:
        raise HTTPException(status_code=404, detail="Key not found")
    _store.pop(key)
    _delete_from_db(key)
    return {"deleted": key}


@_router.get("/cache/{key}/exists")
async def key_exists(key: str):
    now = time.time()
    exists = key in _store
    if exists:
        _, exp = _store[key]
        if exp is not None and exp <= now:
            _store.pop(key, None)
            exists = False
    return {"key": key, "exists": exists}


@_router.post("/cache/mset")
async def mset(req: MultiSetRequest):
    results = []
    for k, v in req.entries.items():
        expires_at = (time.time() + req.ttl) if req.ttl else None
        _store[k] = (v, expires_at)
        _persist(k, v, expires_at)
        results.append(k)
    return {"set": results, "count": len(results)}


@_router.post("/cache/mget")
async def mget(keys: List[str]):
    now = time.time()
    result = {}
    for key in keys:
        if key in _store:
            value, expires_at = _store[key]
            if expires_at is None or expires_at > now:
                result[key] = value
    return result


@_router.get("/cache", response_model=KeysResponse)
async def list_keys(pattern: Optional[str] = Query(None, description="Glob-style prefix filter")):
    now = time.time()
    keys = [k for k, (_, exp) in _store.items() if exp is None or exp > now]
    if pattern:
        keys = [k for k in keys if k.startswith(pattern.rstrip("*"))]
    return KeysResponse(keys=keys, count=len(keys))


@_router.delete("/cache")
async def flush():
    count = len(_store)
    _store.clear()
    _flush_db()
    return {"flushed": count}


@_router.get("/stats")
async def stats():
    now = time.time()
    active = [(k, exp) for k, (_, exp) in _store.items() if exp is None or exp > now]
    expired_soon = [k for k, exp in active if exp is not None and exp - now < 60]
    return {
        "total_keys": len(active),
        "no_expiry": sum(1 for _, exp in active if exp is None),
        "with_expiry": sum(1 for _, exp in active if exp is not None),
        "expiring_in_60s": len(expired_soon),
    }


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
