# workers/rate-limit-service/app.py
# Self-hosted token-bucket rate limiter — port 8026
# Replaces in-process rate limiting scattered across workers; all services call this.

from __future__ import annotations

import sqlite3
import time
import threading
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

import structlog
from cachetools import LRUCache
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    rate_limit_default: int = 60
    rate_limit_window: int = 60
    rate_limit_port: int = 8026

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

structlog.configure(
    processors=[
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger("rate-limit-service")

# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_DB_PATH = Path(__file__).parent / "data" / "rate_limit.db"
_DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    with _get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS buckets (
                key          TEXT PRIMARY KEY,
                tokens       REAL NOT NULL,
                last_refill  REAL NOT NULL,
                capacity     INTEGER NOT NULL,
                window_secs  INTEGER NOT NULL,
                hit_count    INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Hot-path cache — avoids a SQLite round-trip for every request.
# Evicted entries fall back to DB on next read.
# ---------------------------------------------------------------------------

_CACHE_SIZE = 2048
_cache: LRUCache = LRUCache(maxsize=_CACHE_SIZE)
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Token-bucket helpers
# ---------------------------------------------------------------------------


def _load_bucket(key: str, capacity: int, window_secs: int) -> dict:
    """Return live bucket state, initialising from DB or creating fresh."""
    with _lock:
        if key in _cache:
            return _cache[key]

    with _get_conn() as conn:
        row = conn.execute("SELECT * FROM buckets WHERE key = ?", (key,)).fetchone()

    if row:
        bucket = dict(row)
    else:
        bucket = {
            "key": key,
            "tokens": float(capacity),
            "last_refill": time.time(),
            "capacity": capacity,
            "window_secs": window_secs,
            "hit_count": 0,
        }

    with _lock:
        _cache[key] = bucket
    return bucket


def _save_bucket(bucket: dict) -> None:
    with _get_conn() as conn:
        conn.execute(
            """
            INSERT INTO buckets (key, tokens, last_refill, capacity, window_secs, hit_count)
            VALUES (:key, :tokens, :last_refill, :capacity, :window_secs, :hit_count)
            ON CONFLICT(key) DO UPDATE SET
                tokens       = excluded.tokens,
                last_refill  = excluded.last_refill,
                capacity     = excluded.capacity,
                window_secs  = excluded.window_secs,
                hit_count    = excluded.hit_count
            """,
            bucket,
        )
        conn.commit()


def _peek_tokens(bucket: dict, now: float) -> float:
    rate = bucket["capacity"] / max(bucket["window_secs"], 1)
    return min(float(bucket["capacity"]), bucket["tokens"] + (now - bucket["last_refill"]) * rate)


def _peek_bucket(key: str, capacity: int, window_secs: int) -> dict:
    """Return current token count without mutating any state."""
    bucket = _load_bucket(key, capacity, window_secs)
    now = time.time()
    with _lock:
        tokens_now = _peek_tokens(bucket, now)
        reset_at = bucket["last_refill"] + bucket["window_secs"]
    return {"tokens": tokens_now, "reset_at": reset_at}


def _do_consume(key: str, capacity: int, window_secs: int) -> dict:
    """Consume one token atomically. Returns allowed, remaining, reset_at."""
    bucket = _load_bucket(key, capacity, window_secs)
    now = time.time()

    with _lock:
        # Re-fetch under lock — another thread may have just updated this entry
        bucket = _cache.get(key, bucket)
        rate = bucket["capacity"] / max(bucket["window_secs"], 1)
        bucket["tokens"] = min(
            float(bucket["capacity"]), bucket["tokens"] + (now - bucket["last_refill"]) * rate
        )
        bucket["last_refill"] = now

        allowed = bucket["tokens"] >= 1.0
        if allowed:
            bucket["tokens"] -= 1.0
        bucket["hit_count"] += 1
        reset_at = now + bucket["window_secs"]
        remaining = int(max(0, bucket["tokens"]))
        _cache[key] = bucket

    _save_bucket(dict(bucket))
    log.debug("rate_check", key=key, allowed=allowed, remaining=remaining)
    return {"allowed": allowed, "remaining": remaining, "reset_at": reset_at}


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CheckRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=512)
    limit: int = Field(default_factory=lambda: settings.rate_limit_default, ge=1)
    window_seconds: int = Field(default_factory=lambda: settings.rate_limit_window, ge=1)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    _init_db()
    log.info("rate-limit-service ready", db=str(_DB_PATH), port=settings.rate_limit_port)
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

_STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="rate-limit-service",
    description="Token-bucket rate limiter — port 8026",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "rate-limit-service"}


@app.post("/check")
async def check(req: CheckRequest) -> dict:
    """Non-consuming peek: report allowed + remaining without spending a token."""
    state = _peek_bucket(req.key, req.limit, req.window_seconds)
    allowed = state["tokens"] >= 1.0
    return {
        "allowed": allowed,
        "remaining": int(max(0, state["tokens"])),
        "reset_at": state["reset_at"],
    }


@app.post("/consume")
async def consume(req: CheckRequest) -> dict:
    """Consume one token. Returns allowed + remaining."""
    result = _do_consume(req.key, req.limit, req.window_seconds)
    return {"allowed": result["allowed"], "remaining": result["remaining"]}


@app.get("/stats")
async def stats(top_n: int = 20) -> dict:
    """Return top-N keys by total hit count."""
    with _get_conn() as conn:
        rows = conn.execute(
            "SELECT key, hit_count, tokens, capacity FROM buckets ORDER BY hit_count DESC LIMIT ?",
            (top_n,),
        ).fetchall()
    return {
        "top_keys": [dict(r) for r in rows],
        "cache_size": len(_cache),
        "uptime_seconds": (datetime.now(timezone.utc) - _STARTED_AT).total_seconds(),
    }


@app.delete("/reset/{key}")
async def reset(key: str) -> dict:
    """Evict key from cache and DB — bucket resets to full on next request."""
    with _lock:
        evicted = key in _cache
        _cache.pop(key, None)
    with _get_conn() as conn:
        conn.execute("DELETE FROM buckets WHERE key = ?", (key,))
        conn.commit()
    log.info("bucket_reset", key=key)
    return {"key": key, "reset": True, "was_cached": evicted}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=settings.rate_limit_port)
