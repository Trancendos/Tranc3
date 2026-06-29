"""
Trancendos rate-limit-service — Self-Hosted Worker
===================================================
Centralized token-bucket rate limiter. Other services call this to check
whether a given client/key is allowed to proceed.

Port: 8026
Zero-cost: In-memory token buckets (fast), SQLite for policy persistence.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_PORT = 8026
WORKER_NAME = "rate-limit-service"
DB_PATH = Path(__file__).parent / "data" / "ratelimit.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database — policy storage
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS policies (
                name        TEXT PRIMARY KEY,
                capacity    INTEGER NOT NULL,
                refill_rate REAL NOT NULL,
                description TEXT,
                created_at  REAL NOT NULL
            )
        """)
        conn.commit()
        # seed default policy
        conn.execute(
            "INSERT OR IGNORE INTO policies (name, capacity, refill_rate, description, created_at) VALUES (?,?,?,?,?)",
            ("default", 100, 10.0, "100 tokens, refill 10/s", time.time()),
        )
        conn.commit()


def _get_policy(name: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM policies WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Token-bucket in-memory state
# ---------------------------------------------------------------------------

_buckets: Dict[str, dict] = {}  # key → {tokens, last_refill, policy}
_lock = threading.Lock()


def _check_and_consume(key: str, policy_name: str, tokens_requested: int = 1) -> dict:
    policy = _get_policy(policy_name) or _get_policy("default")
    if not policy:
        raise HTTPException(status_code=500, detail="No policy found")

    capacity = policy["capacity"]
    refill_rate = policy["refill_rate"]
    now = time.time()

    with _lock:
        bucket = _buckets.get(key)
        if bucket is None or bucket["policy"] != policy_name:
            bucket = {"tokens": float(capacity), "last_refill": now, "policy": policy_name}
            _buckets[key] = bucket

        elapsed = now - bucket["last_refill"]
        bucket["tokens"] = min(capacity, bucket["tokens"] + elapsed * refill_rate)
        bucket["last_refill"] = now

        allowed = bucket["tokens"] >= tokens_requested
        if allowed:
            bucket["tokens"] -= tokens_requested

        return {
            "allowed": allowed,
            "tokens_remaining": bucket["tokens"],
            "capacity": capacity,
            "refill_rate": refill_rate,
            "policy": policy_name,
        }


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class CheckIn(BaseModel):
    key: str
    policy: str = "default"
    tokens: int = Field(1, ge=1, le=1000)


class PolicyCreate(BaseModel):
    name: str
    capacity: int = Field(..., ge=1)
    refill_rate: float = Field(..., gt=0)
    description: Optional[str] = None


class PolicyUpdate(BaseModel):
    capacity: Optional[int] = Field(None, ge=1)
    refill_rate: Optional[float] = Field(None, gt=0)
    description: Optional[str] = None


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.rate-limit-service")
    except Exception:
        pass  # OTel is optional — never block startup
    init_db()
    logger.info("rate-limit-service DB ready")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="rate-limit-service",
    description="Token-bucket rate limiter (self-hosted)",
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
    with _lock:
        active_buckets = len(_buckets)
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "active_buckets": active_buckets,
        "entity": {
            "location": "Cryptex",
            "pillar": "Security",
            "lead_ai": "Renik",
            "primes": ["The Guardian (Marcus Magnolia)"],
            "primary_function": "Cyber Defense (Threat Intel, DDoS, CVE)",
        },
    }


@_router.post("/check")
async def check(req: CheckIn):
    result = _check_and_consume(req.key, req.policy, req.tokens)
    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail={**result, "message": "Rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Policy": req.policy},
        )
    return result


@_router.post("/peek")
async def peek(req: CheckIn):
    """Check without consuming tokens."""
    policy = _get_policy(req.policy) or _get_policy("default")
    if not policy:
        raise HTTPException(status_code=500, detail="No policy found")
    now = time.time()
    with _lock:
        bucket = _buckets.get(req.key)
        if bucket is None:
            tokens = float(policy["capacity"])
        else:
            elapsed = now - bucket["last_refill"]
            tokens = min(policy["capacity"], bucket["tokens"] + elapsed * policy["refill_rate"])
    return {
        "key": req.key,
        "tokens_available": tokens,
        "capacity": policy["capacity"],
        "policy": req.policy,
    }


@_router.delete("/buckets/{key}")
async def reset_bucket(key: str):
    with _lock:
        removed = _buckets.pop(key, None) is not None
    return {"key": key, "reset": removed}


@_router.get("/policies")
async def list_policies():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM policies ORDER BY name").fetchall()
    return {"policies": [dict(r) for r in rows]}


@_router.post("/policies", status_code=201)
async def create_policy(req: PolicyCreate):
    with get_conn() as conn:
        if conn.execute("SELECT name FROM policies WHERE name = ?", (req.name,)).fetchone():
            raise HTTPException(status_code=409, detail="Policy already exists")
        conn.execute(
            "INSERT INTO policies (name, capacity, refill_rate, description, created_at) VALUES (?,?,?,?,?)",
            (req.name, req.capacity, req.refill_rate, req.description, time.time()),
        )
        conn.commit()
    return {"name": req.name, "capacity": req.capacity, "refill_rate": req.refill_rate}


@_router.patch("/policies/{name}")
async def update_policy(name: str, req: PolicyUpdate):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM policies WHERE name = ?", (name,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Policy not found")
        updates = dict(req.model_dump(exclude_none=True).items())
        if updates:
            set_clause = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(
                f"UPDATE policies SET {set_clause} WHERE name = ?", [*updates.values(), name]
            )
            conn.commit()
    # Evict cached buckets for this policy
    with _lock:
        evict = [k for k, v in _buckets.items() if v["policy"] == name]
        for k in evict:
            del _buckets[k]
    return {"updated": name, "evicted_buckets": len(evict)}


@_router.delete("/policies/{name}")
async def delete_policy(name: str):
    if name == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default policy")
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM policies WHERE name = ?", (name,)).fetchone():
            raise HTTPException(status_code=404, detail="Policy not found")
        conn.execute("DELETE FROM policies WHERE name = ?", (name,))
        conn.commit()
    return {"deleted": name}


@_router.get("/stats")
async def stats():
    with _lock:
        snapshot = {k: {"tokens": v["tokens"], "policy": v["policy"]} for k, v in _buckets.items()}
    return {"active_buckets": len(snapshot), "buckets": snapshot}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
