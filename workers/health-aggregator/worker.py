"""
Trancendos health-aggregator — Self-Hosted Worker
==================================================
Polls all registered service /health endpoints on a configurable interval
and maintains a live registry of service health states. Provides a unified
status dashboard for the entire Trancendos platform.

Port: 8029
Zero-cost: FastAPI + SQLite + httpx polling, no external deps.
"""

from __future__ import annotations
from src.entities.health_metadata import health_entity_block

import asyncio
import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import httpx
from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8029
WORKER_NAME = "health-aggregator"
DB_PATH = Path(__file__).parent / "data" / "health.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

POLL_INTERVAL = 30  # seconds between polls
TIMEOUT = 5  # seconds per HTTP check

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# Default services to monitor (Trancendos worker map)
DEFAULT_SERVICES = [
    {"name": "infinity-ws", "url": "http://localhost:8004/health"},
    {"name": "infinity-auth", "url": "http://localhost:8005/health"},
    {"name": "users-service", "url": "http://localhost:8006/health"},
    {"name": "monitoring", "url": "http://localhost:8007/health"},
    {"name": "notifications", "url": "http://localhost:8008/health"},
    {"name": "infinity-ai", "url": "http://localhost:8009/health"},
    {"name": "the-grid", "url": "http://localhost:8010/health"},
    {"name": "products-service", "url": "http://localhost:8011/health"},
    {"name": "orders-service", "url": "http://localhost:8012/health"},
    {"name": "payments-service", "url": "http://localhost:8013/health"},
    {"name": "files-service", "url": "http://localhost:8014/health"},
    {"name": "identity-service", "url": "http://localhost:8015/health"},
    {"name": "analytics-service", "url": "http://localhost:8016/health"},
    {"name": "search-service", "url": "http://localhost:8017/health"},
    {"name": "email-service", "url": "http://localhost:8018/health"},
    {"name": "sms-service", "url": "http://localhost:8019/health"},
    {"name": "storage-service", "url": "http://localhost:8020/health"},
    {"name": "cron-service", "url": "http://localhost:8021/health"},
    {"name": "queue-service", "url": "http://localhost:8022/health"},
    {"name": "cache-service", "url": "http://localhost:8023/health"},
    {"name": "config-service", "url": "http://localhost:8024/health"},
    {"name": "audit-service", "url": "http://localhost:8025/health"},
    {"name": "rate-limit-service", "url": "http://localhost:8026/health"},
    {"name": "geo-service", "url": "http://localhost:8027/health"},
    {"name": "cdn-service", "url": "http://localhost:8028/health"},
]


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
            CREATE TABLE IF NOT EXISTS services (
                name        TEXT PRIMARY KEY,
                url         TEXT NOT NULL,
                enabled     INTEGER NOT NULL DEFAULT 1,
                added_at    REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS health_checks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                service     TEXT NOT NULL,
                status      TEXT NOT NULL,
                http_code   INTEGER,
                response_ms REAL,
                details     TEXT,
                checked_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hc_service ON health_checks(service, checked_at);
        """)
        conn.commit()
        # seed default services
        for svc in DEFAULT_SERVICES:
            conn.execute(
                "INSERT OR IGNORE INTO services (name, url, added_at) VALUES (?,?,?)",
                (svc["name"], svc["url"], time.time()),
            )
        conn.commit()


# In-memory latest status per service
_latest: Dict[str, dict] = {}


async def _check_one(name: str, url: str) -> dict:
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.get(url)
        ms = (time.time() - start) * 1000
        status = "healthy" if resp.status_code < 400 else "degraded"
        try:
            details = resp.json()
        except Exception:
            details = {"raw": resp.text[:200]}
        return {
            "service": name,
            "status": status,
            "http_code": resp.status_code,
            "response_ms": round(ms, 1),
            "details": details,
        }
    except Exception as exc:
        ms = (time.time() - start) * 1000
        return {
            "service": name,
            "status": "down",
            "http_code": None,
            "response_ms": round(ms, 1),
            "details": {"error": str(exc)},
        }


async def _poll_loop() -> None:
    while True:
        with get_conn() as conn:
            services = conn.execute("SELECT name, url FROM services WHERE enabled=1").fetchall()
        results = await asyncio.gather(*[_check_one(r["name"], r["url"]) for r in services])
        now = time.time()
        with get_conn() as conn:
            for r in results:
                _latest[r["service"]] = {**r, "checked_at": now}
                conn.execute(
                    "INSERT INTO health_checks (service, status, http_code, response_ms, details, checked_at) VALUES (?,?,?,?,?,?)",
                    (
                        r["service"],
                        r["status"],
                        r["http_code"],
                        r["response_ms"],
                        json.dumps(r["details"]),
                        now,
                    ),
                )
            conn.commit()
        healthy = sum(1 for r in results if r["status"] == "healthy")
        logger.info("Health poll: %d/%d healthy", healthy, len(results))
        await asyncio.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ServiceRegister(BaseModel):
    name: str
    url: str


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("health-aggregator DB ready")
    task = asyncio.create_task(_poll_loop())
    yield
    task.cancel()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="health-aggregator",
    description="Unified service health dashboard (self-hosted)",
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
    healthy = sum(1 for v in _latest.values() if v["status"] == "healthy")
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "monitored_services": len(_latest),
        "healthy": healthy,
        "degraded_or_down": len(_latest) - healthy,
        "entity": health_entity_block(8029, WORKER_NAME),
    }


@_router.get("/status")
async def status():
    summary = {
        "total": len(_latest),
        "healthy": sum(1 for v in _latest.values() if v["status"] == "healthy"),
        "degraded": sum(1 for v in _latest.values() if v["status"] == "degraded"),
        "down": sum(1 for v in _latest.values() if v["status"] == "down"),
    }
    return {"summary": summary, "services": list(_latest.values())}


@_router.get("/status/{service}")
async def service_status(service: str):
    if service not in _latest:
        raise HTTPException(status_code=404, detail="Service not found or not yet polled")
    return _latest[service]


@_router.post("/check/{service}")
async def force_check(service: str):
    with get_conn() as conn:
        row = conn.execute("SELECT url FROM services WHERE name = ?", (service,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Service not registered")
    result = await _check_one(service, row["url"])
    now = time.time()
    _latest[service] = {**result, "checked_at": now}
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO health_checks (service, status, http_code, response_ms, details, checked_at) VALUES (?,?,?,?,?,?)",
            (
                service,
                result["status"],
                result["http_code"],
                result["response_ms"],
                json.dumps(result["details"]),
                now,
            ),
        )
        conn.commit()
    return result


@_router.get("/history/{service}")
async def service_history(service: str, limit: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT status, http_code, response_ms, checked_at FROM health_checks WHERE service=? ORDER BY checked_at DESC LIMIT ?",
            (service, limit),
        ).fetchall()
    return {"service": service, "history": [dict(r) for r in rows]}


@_router.get("/services")
async def list_services():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM services ORDER BY name").fetchall()
    return {"services": [dict(r) for r in rows]}


@_router.post("/services", status_code=201)
async def register_service(req: ServiceRegister):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO services (name, url, added_at) VALUES (?,?,?)",
            (req.name, req.url, time.time()),
        )
        conn.commit()
    return {"registered": req.name, "url": req.url}


@_router.delete("/services/{name}")
async def unregister_service(name: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM services WHERE name = ?", (name,))
        conn.commit()
    _latest.pop(name, None)
    return {"unregistered": name}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
