"""
Trancendos cache-service — ACO pheromone router, 7 zero-cost backends
======================================================================
Backends (priority order):
  1. In-memory dict   — ultra-fast, volatile
  2. Valkey           — Redis-fork, persistent (docker-compose)
  3. SQLite WAL       — durable, always available
  4. DuckDB           — in-process OLAP, zero-setup
  5. diskcache        — disk-backed LRU (stdlib-style)
  6. Dragonfly        — Redis-compatible (optional self-hosted)
  7. Offline stub     — final fallback, never blocks

Port: 8023
Zero-cost: no paid cloud APIs; all backends self-hosted or in-process.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import time
from collections import deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ── Config ────────────────────────────────────────────────────────────────────
WORKER_PORT = int(os.environ.get("CACHE_PORT", "8023"))
WORKER_NAME = "cache-service"
DB_PATH = Path(os.environ.get("CACHE_DB_PATH", "/data/cache.db"))
DUCKDB_PATH = os.environ.get("CACHE_DUCKDB_PATH", "/data/cache.duckdb")
DISKCACHE_DIR = os.environ.get("CACHE_DISKCACHE_DIR", "/data/diskcache")
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

VALKEY_URL = os.environ.get("VALKEY_URL", "redis://valkey:6379/0")
VALKEY_ENABLED = os.environ.get("CACHE_VALKEY", "1") == "1"
DRAGONFLY_URL = os.environ.get("DRAGONFLY_URL", "redis://dragonfly:6379/1")
DRAGONFLY_ENABLED = os.environ.get("CACHE_DRAGONFLY", "0") == "1"
DUCKDB_ENABLED = os.environ.get("CACHE_DUCKDB", "1") == "1"
DISKCACHE_ENABLED = os.environ.get("CACHE_DISKCACHE", "1") == "1"

PHEROMONE_DECAY = float(os.environ.get("CACHE_PHEROMONE_DECAY", "0.05"))
QUOTA_WINDOW = int(os.environ.get("CACHE_QUOTA_WINDOW", "3600"))
QUOTA_MAX = int(os.environ.get("CACHE_QUOTA_MAX_CALLS", "100000"))
OP_TIMEOUT = float(os.environ.get("CACHE_OP_TIMEOUT", "5.0"))

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


_GUARDS: Dict[str, ThresholdGuard] = {
    "memory": ThresholdGuard("memory", QUOTA_MAX, QUOTA_WINDOW),
    "valkey": ThresholdGuard("valkey", QUOTA_MAX, QUOTA_WINDOW),
    "sqlite": ThresholdGuard("sqlite", QUOTA_MAX, QUOTA_WINDOW),
    "duckdb": ThresholdGuard("duckdb", QUOTA_MAX, QUOTA_WINDOW),
    "diskcache": ThresholdGuard("diskcache", QUOTA_MAX, QUOTA_WINDOW),
    "dragonfly": ThresholdGuard("dragonfly", QUOTA_MAX, QUOTA_WINDOW),
    "offline": ThresholdGuard("offline", 999_999, QUOTA_WINDOW),
}

_ENABLED: Dict[str, bool] = {
    "memory": True,
    "valkey": VALKEY_ENABLED,
    "sqlite": True,
    "duckdb": DUCKDB_ENABLED,
    "diskcache": DISKCACHE_ENABLED,
    "dragonfly": DRAGONFLY_ENABLED,
    "offline": True,
}

_PRIORITY = ["memory", "valkey", "sqlite", "duckdb", "diskcache", "dragonfly", "offline"]


def _select_backend() -> str:
    available = [b for b in _PRIORITY if _ENABLED[b] and _GUARDS[b].can_allow()]
    return max(available, key=lambda b: _GUARDS[b].pheromone) if available else "offline"


# ── In-memory store ───────────────────────────────────────────────────────────

_mem: Dict[str, Tuple[Any, Optional[float]]] = {}  # key → (value, expires_at)


# ── SQLite backend ────────────────────────────────────────────────────────────


def _db_conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    return c


def _init_sqlite() -> None:
    with _db_conn() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key        TEXT PRIMARY KEY,
                value      TEXT NOT NULL,
                expires_at REAL,
                created_at REAL NOT NULL DEFAULT (unixepoch('now'))
            )
        """)
        c.execute("CREATE INDEX IF NOT EXISTS idx_expires ON cache(expires_at)")
        c.commit()


def _sqlite_set(key: str, value: Any, expires_at: Optional[float]) -> bool:
    try:
        with _db_conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO cache (key,value,expires_at) VALUES (?,?,?)",
                (key, json.dumps(value), expires_at),
            )
            c.commit()
        return True
    except Exception:  # SQLite write failure
        return False


def _sqlite_get(key: str) -> Optional[Any]:
    try:
        now = time.time()
        with _db_conn() as c:
            row = c.execute("SELECT value,expires_at FROM cache WHERE key=?", (key,)).fetchone()
        if not row:
            return None
        if row["expires_at"] is not None and row["expires_at"] <= now:
            return None
        return json.loads(row["value"])
    except Exception:  # SQLite read failure
        return None


def _load_from_sqlite() -> None:
    now = time.time()
    try:
        with _db_conn() as c:
            rows = c.execute(
                "SELECT key,value,expires_at FROM cache WHERE expires_at IS NULL OR expires_at > ?",
                (now,),
            ).fetchall()
        for row in rows:
            _mem[row["key"]] = (json.loads(row["value"]), row["expires_at"])
    except Exception:  # non-fatal on startup
        pass


# ── DuckDB backend ────────────────────────────────────────────────────────────


def _duckdb_set(key: str, value: Any, expires_at: Optional[float]) -> bool:
    try:
        import duckdb  # type: ignore[import-untyped]

        con = duckdb.connect(DUCKDB_PATH)
        con.execute("""
            CREATE TABLE IF NOT EXISTS cache (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                expires_at DOUBLE
            )
        """)
        con.execute(
            "INSERT OR REPLACE INTO cache VALUES (?,?,?)",
            [key, json.dumps(value), expires_at],
        )
        con.close()
        return True
    except Exception:  # DuckDB failure
        return False


def _duckdb_get(key: str) -> Optional[Any]:
    try:
        import duckdb  # type: ignore[import-untyped]

        con = duckdb.connect(DUCKDB_PATH)
        row = con.execute("SELECT value,expires_at FROM cache WHERE key=?", [key]).fetchone()
        con.close()
        if not row:
            return None
        if row[1] is not None and row[1] <= time.time():
            return None
        return json.loads(row[0])
    except Exception:  # DuckDB failure
        return None


# ── Valkey/Redis backend ──────────────────────────────────────────────────────


async def _valkey_set(key: str, value: Any, ttl: Optional[int], url: str) -> bool:
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        r = aioredis.from_url(url, socket_timeout=OP_TIMEOUT)
        payload = json.dumps(value)
        if ttl:
            await r.setex(key, ttl, payload)
        else:
            await r.set(key, payload)
        await r.aclose()
        return True
    except Exception:  # Valkey unreachable
        return False


async def _valkey_get(key: str, url: str) -> Optional[Any]:
    try:
        import redis.asyncio as aioredis  # type: ignore[import-untyped]

        r = aioredis.from_url(url, socket_timeout=OP_TIMEOUT)
        data = await r.get(key)
        await r.aclose()
        return json.loads(data) if data else None
    except Exception:  # Valkey unreachable
        return None


# ── diskcache backend ─────────────────────────────────────────────────────────
# SECURITY: diskcache's DEFAULT on-disk format is pickle, which is unsafe to
# deserialize (CVE-2025-69872, no fixed release). We eliminate that risk by
# using diskcache.JSONDisk — values are stored/read as JSON, never unpickled, so
# a maliciously crafted on-disk entry cannot execute code. This is fully
# compatible: every other backend here (SQLite, DuckDB, Valkey) already
# round-trips values through json.dumps/json.loads, so all cached values are
# JSON-serializable. (The pinned diskcache==5.6.3 is still version-flagged by
# scanners since no patched release exists — see the .trivyignore justification —
# but the vulnerable pickle code path is not used.)


def _diskcache_set(key: str, value: Any, ttl: Optional[int]) -> bool:
    try:
        import diskcache  # type: ignore[import-untyped]

        # disk=JSONDisk → values stored as JSON, never pickle (CVE-2025-69872).
        with diskcache.Cache(DISKCACHE_DIR, disk=diskcache.JSONDisk) as dc:
            dc.set(key, value, expire=ttl)
        return True
    except Exception:  # diskcache not installed or failure
        return False


def _diskcache_get(key: str) -> Optional[Any]:
    try:
        import diskcache  # type: ignore[import-untyped]

        # disk=JSONDisk → values read as JSON, never unpickled (CVE-2025-69872).
        # Legacy pickle-written entries (if any) fail to decode and are treated
        # as a cache miss by the except below — safe for an ephemeral, TTL'd cache.
        with diskcache.Cache(DISKCACHE_DIR, disk=diskcache.JSONDisk) as dc:
            val = dc.get(key, default=None)
        return val
    except Exception:  # diskcache not installed or failure
        return None


# ── Eviction loop ─────────────────────────────────────────────────────────────


async def _eviction_loop() -> None:
    while True:
        await asyncio.sleep(30)
        now = time.time()
        expired = [k for k, (_, exp) in list(_mem.items()) if exp is not None and exp <= now]
        for k in expired:
            _mem.pop(k, None)
        if expired:
            try:
                with _db_conn() as c:
                    c.execute("DELETE FROM cache WHERE expires_at <= ?", (now,))
                    c.commit()
            except Exception:  # non-fatal cleanup
                pass
            logger.info("Evicted %d expired keys", len(expired))


# ── Models ────────────────────────────────────────────────────────────────────


class SetRequest(BaseModel):
    value: Any
    ttl: Optional[int] = Field(None, description="TTL in seconds")


class SetResponse(BaseModel):
    key: str
    backend: str
    ttl: Optional[int]
    expires_at: Optional[str]


class GetResponse(BaseModel):
    key: str
    value: Any
    ttl_remaining: Optional[float]


class MultiSetRequest(BaseModel):
    entries: Dict[str, Any]
    ttl: Optional[int] = None


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
    _init_sqlite()
    _load_from_sqlite()
    logger.info("cache-service ready — %d keys loaded from SQLite", len(_mem))
    task = asyncio.create_task(_eviction_loop())
    yield
    task.cancel()


# ── App ───────────────────────────────────────────────────────────────────────

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="cache-service",
    description="Multi-backend ACO cache (7 zero-cost backends)",
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
    now = time.time()
    active = sum(1 for _, (_, exp) in _mem.items() if exp is None or exp > now)
    return JSONResponse(
        {
            "service": WORKER_NAME,
            "status": "ok",
            "uptime_s": round((datetime.now(timezone.utc) - STARTED_AT).total_seconds(), 1),
            "keys_active": active,
            "active_backend": _select_backend(),
        }
    )


@_router.get("/cache/{key}", response_model=GetResponse)
async def get_key(key: str) -> GetResponse:
    now = time.time()

    if key in _mem:
        value, expires_at = _mem[key]
        if expires_at is None or expires_at > now:
            ttl_rem = (expires_at - now) if expires_at else None
            return GetResponse(key=key, value=value, ttl_remaining=ttl_rem)
        _mem.pop(key, None)

    backend = _select_backend()
    _GUARDS[backend].record()
    value = None

    if backend == "valkey":
        value = await _valkey_get(key, VALKEY_URL)
    elif backend == "dragonfly":
        value = await _valkey_get(key, DRAGONFLY_URL)
    elif backend == "sqlite":
        value = _sqlite_get(key)
    elif backend == "duckdb":
        value = _duckdb_get(key)
    elif backend == "diskcache":
        value = _diskcache_get(key)

    if value is not None:
        _GUARDS[backend].reinforce()
        _mem[key] = (value, None)
        return GetResponse(key=key, value=value, ttl_remaining=None)

    _GUARDS[backend].decay()
    raise HTTPException(status_code=404, detail="Key not found")


@_router.put("/cache/{key}", response_model=SetResponse)
async def set_key(key: str, req: SetRequest) -> SetResponse:
    expires_at = (time.time() + req.ttl) if req.ttl else None
    _mem[key] = (req.value, expires_at)

    backend = _select_backend()
    _GUARDS[backend].record()
    success = True

    if backend in ("valkey", "memory"):
        success = await _valkey_set(key, req.value, req.ttl, VALKEY_URL)
    elif backend == "dragonfly":
        success = await _valkey_set(key, req.value, req.ttl, DRAGONFLY_URL)
    elif backend in ("sqlite", "offline"):
        success = _sqlite_set(key, req.value, expires_at)
    elif backend == "duckdb":
        success = _duckdb_set(key, req.value, expires_at)
    elif backend == "diskcache":
        success = _diskcache_set(key, req.value, req.ttl)

    if success:
        _GUARDS[backend].reinforce()
    else:
        _GUARDS[backend].decay()
        _sqlite_set(key, req.value, expires_at)

    exp_str = (
        datetime.fromtimestamp(expires_at, tz=timezone.utc).isoformat() if expires_at else None
    )
    return SetResponse(key=key, backend=backend, ttl=req.ttl, expires_at=exp_str)


@_router.delete("/cache/{key}", status_code=204)
async def delete_key(key: str) -> None:
    if key not in _mem:
        raise HTTPException(status_code=404, detail="Key not found")
    _mem.pop(key, None)
    try:
        with _db_conn() as c:
            c.execute("DELETE FROM cache WHERE key=?", (key,))
            c.commit()
    except Exception:  # non-fatal on delete
        pass


@_router.get("/cache/{key}/exists")
def key_exists(key: str) -> Dict[str, Any]:
    now = time.time()
    in_mem = key in _mem and (_mem[key][1] is None or _mem[key][1] > now)
    if not in_mem:
        val = _sqlite_get(key)
        in_mem = val is not None
    return {"key": key, "exists": in_mem}


@_router.post("/cache/mset")
async def mset(req: MultiSetRequest) -> Dict[str, Any]:
    results = []
    for k, v in req.entries.items():
        expires_at = (time.time() + req.ttl) if req.ttl else None
        _mem[k] = (v, expires_at)
        _sqlite_set(k, v, expires_at)
        results.append(k)
    return {"set": results, "count": len(results)}


@_router.post("/cache/mget")
def mget(keys: List[str]) -> Dict[str, Any]:
    now = time.time()
    result: Dict[str, Any] = {}
    for key in keys:
        if key in _mem:
            value, expires_at = _mem[key]
            if expires_at is None or expires_at > now:
                result[key] = value
    return result


@_router.get("/cache")
def list_keys(pattern: Optional[str] = Query(None)) -> Dict[str, Any]:
    now = time.time()
    keys = [k for k, (_, exp) in _mem.items() if exp is None or exp > now]
    if pattern:
        keys = [k for k in keys if k.startswith(pattern.rstrip("*"))]
    return {"keys": keys, "count": len(keys)}


@_router.delete("/cache", status_code=204)
def flush() -> None:
    _mem.clear()
    try:
        with _db_conn() as c:
            c.execute("DELETE FROM cache")
            c.commit()
    except Exception:  # non-fatal on flush
        pass


@_router.get("/cache/status")
def cache_status() -> Dict[str, Any]:
    now = time.time()
    active = sum(1 for _, (_, exp) in _mem.items() if exp is None or exp > now)
    return {
        "active_backend": _select_backend(),
        "keys_in_memory": active,
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
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
