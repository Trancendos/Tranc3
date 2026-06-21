"""
Trancendos health-aggregator — Self-Hosted Worker (Port 8029)
=============================================================
Polls every registered Trancendos service /health endpoint every 30 s,
persists check results to SQLite, and exposes a unified status dashboard.

Zero-cost: FastAPI + SQLite + httpx — no paid external dependencies.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sqlite3
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

PORT: int = int(os.environ.get("PORT", 8029))
WORKER_NAME = "health-aggregator"
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
DB_PATH = Path(os.environ.get("DB_PATH", "/data/health_aggregator.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


POLL_INTERVAL = 30  # seconds between full polls
HTTP_TIMEOUT = 3.0  # per-service request timeout
HISTORY_LIMIT = 500  # rolling history rows kept per service

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Service registry — canonical Trancendos worker map (from CLAUDE.md)
# ---------------------------------------------------------------------------

SERVICE_REGISTRY: List[Dict[str, Any]] = [
    # Core backend
    {"name": "tranc3-backend", "port": 8000},
    {"name": "nanoservices", "port": 8001},
    # P0 — critical
    {"name": "infinity-ws", "port": 8004},
    {"name": "infinity-auth", "port": 8005},
    # P1 — important
    {"name": "users-service", "port": 8006},
    {"name": "monitoring", "port": 8007},
    {"name": "notifications", "port": 8008},
    {"name": "infinity-ai", "port": 8009},
    {"name": "the-grid", "port": 8010},
    {"name": "products-service", "port": 8011},
    {"name": "orders-service", "port": 8012},
    {"name": "payments-service", "port": 8013},
    {"name": "files-service", "port": 8014},
    {"name": "identity-service", "port": 8015},
    # P2
    {"name": "analytics-service", "port": 8016},
    {"name": "audit-service", "port": 8017},
    {"name": "cache-service", "port": 8018},
    {"name": "cdn-service", "port": 8019},
    {"name": "config-service", "port": 8020},
    {"name": "cron-service", "port": 8021},
    {"name": "email-service", "port": 8022},
    {"name": "geo-service", "port": 8023},
    {"name": "search-service", "port": 8024},
    {"name": "sms-service", "port": 8025},
    {"name": "storage-service", "port": 8026},
    {"name": "queue-service", "port": 8027},
    {"name": "rate-limit-service", "port": 8028},
    # self — skip polling ourselves to avoid infinite recursion
    # {"name": "health-aggregator",         "port": 8029},
    # P3
    {"name": "gbrain-bridge", "port": 8030},
    {"name": "topology-service", "port": 8031},
    {"name": "ledger-service", "port": 8032},
    {"name": "model-router-service", "port": 8033},
    {"name": "workflow-engine-service", "port": 8034},
    {"name": "skills-benchmark-service", "port": 8035},
    {"name": "langchain-integration-service", "port": 8036},
    {"name": "deepagents-orchestrator-service", "port": 8037},
    {"name": "vault-service", "port": 8038},
    # Infinity portal / admin cluster
    {"name": "infinity-portal-service", "port": 8042},
    {"name": "infinity-one-service", "port": 8043},
    {"name": "infinity-admin-service", "port": 8044},
    {"name": "infinity-shards-service", "port": 8045},
    # Bridge + Town Hall
    {"name": "infinity-bridge-service", "port": 8070},
    {"name": "cranbania", "port": 8071},
    # Bots
    {"name": "tranc3-bots", "port": 8080},
]

# Materialise the health URL for each entry
for _svc in SERVICE_REGISTRY:
    _svc["health_url"] = f"http://localhost:{_svc['port']}/health"

_REGISTRY_BY_NAME: Dict[str, Dict[str, Any]] = {s["name"]: s for s in SERVICE_REGISTRY}

# Dynamic services registered via POST /services
_dynamic_services: Dict[str, Dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# In-memory latest state
# ---------------------------------------------------------------------------

_latest: Dict[str, Dict[str, Any]] = {}
_poll_count: int = 0

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    return c


def _init_db() -> None:
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS health_checks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                service     TEXT    NOT NULL,
                port        INTEGER NOT NULL,
                url         TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                latency_ms  REAL,
                checked_at  TEXT    NOT NULL,
                error       TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_hc_svc_time
                ON health_checks (service, checked_at);

            CREATE TABLE IF NOT EXISTS health_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                service     TEXT    NOT NULL,
                status      TEXT    NOT NULL,
                latency_ms  REAL,
                checked_at  TEXT    NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_hh_svc_time
                ON health_history (service, checked_at);
        """)
        c.commit()
    logger.info("health-aggregator DB initialised at %s", DB_PATH)


init_db = _init_db  # public alias for tests


def _persist_check(result: Dict[str, Any]) -> None:
    now_iso = datetime.now(timezone.utc).isoformat()
    svc = result["name"]
    port = result["port"]
    url = result["health_url"]
    status = result["status"]
    latency = result.get("latency_ms")
    error = result.get("error")

    with _conn() as c:
        c.execute(
            """
            INSERT INTO health_checks (service, port, url, status, latency_ms, checked_at, error)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (svc, port, url, status, latency, now_iso, error),
        )
        c.execute(
            """
            INSERT INTO health_history (service, status, latency_ms, checked_at)
            VALUES (?, ?, ?, ?)
            """,
            (svc, status, latency, now_iso),
        )
        # Rolling trim — keep last HISTORY_LIMIT rows per service
        c.execute(
            """
            DELETE FROM health_history
            WHERE service = ?
              AND id NOT IN (
                SELECT id FROM health_history
                WHERE service = ?
                ORDER BY id DESC
                LIMIT ?
              )
            """,
            (svc, svc, HISTORY_LIMIT),
        )
        c.commit()


_http_client: httpx.AsyncClient | None = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
    return _http_client


# ---------------------------------------------------------------------------
# Health check logic
# ---------------------------------------------------------------------------


async def _check_one(svc: Dict[str, Any]) -> Dict[str, Any]:
    """Perform a single HTTP health check; return enriched result dict."""
    url = svc["health_url"]
    start = time.monotonic()
    svc_name = svc["name"]
    try:
        resp = await _get_http_client().get(url)
        ms = (time.time() - start) * 1000
        status = "healthy" if resp.status_code < 400 else "degraded"
        try:
            details = resp.json()
        except Exception:
            details = {"raw": resp.text[:200]}
        return {
            "name": svc_name,
            "port": svc["port"],
            "health_url": url,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "service": svc_name,
            "status": status,
            "http_code": resp.status_code,
            "response_ms": round(ms, 1),
            "details": details,
        }
    except Exception:
        ms = (time.time() - start) * 1000
        return {
            "name": svc_name,
            "port": svc["port"],
            "health_url": url,
            "last_checked": datetime.now(timezone.utc).isoformat(),
            "service": svc_name,
            "status": "down",
            "http_code": None,
            "response_ms": round(ms, 1),
            "details": {"error": "probe_failed"},
        }


async def _poll_all() -> None:
    """Poll all registered services once and update _latest."""
    global _poll_count
    results = await asyncio.gather(
        *[_check_one(svc) for svc in SERVICE_REGISTRY], return_exceptions=True
    )
    for svc, res in zip(SERVICE_REGISTRY, results, strict=False):
        if isinstance(res, Exception):
            res = {"name": svc["name"], "port": svc["port"], "status": "down", "error": str(res)}
        _latest[svc["name"]] = res
        try:
            _persist_check(res)
        except Exception:  # noqa: BLE001 — persist errors must not abort polling
            pass
    _poll_count += 1


async def _poll_loop() -> None:
    """Background task — poll on startup, then every POLL_INTERVAL seconds."""
    await _poll_all()
    while True:
        await asyncio.sleep(POLL_INTERVAL)
        await _poll_all()


# ---------------------------------------------------------------------------
# Pydantic response models
# ---------------------------------------------------------------------------


class ServiceStatus(BaseModel):
    name: str
    port: int
    status: str
    latency_ms: Optional[float] = None
    last_checked: Optional[str] = None
    error: Optional[str] = None


class PlatformStatus(BaseModel):
    overall_status: str
    healthy_count: int
    degraded_count: int
    unreachable_count: int
    total_count: int
    services: List[ServiceStatus]


class ServiceRegisterIn(BaseModel):
    name: str
    url: str
    interval_seconds: int = 30


class HistoryPoint(BaseModel):
    service: str
    status: str
    latency_ms: Optional[float]
    checked_at: str


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


_http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client
    # Shared HTTP client — reuses TCP connections across all health checks
    _http_client = httpx.AsyncClient(timeout=HTTP_TIMEOUT)
    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.health-aggregator")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel is optional — never block startup
    _init_db()
    task = asyncio.create_task(_poll_loop())
    logger.info("health-aggregator started on port %d", PORT)
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # expected on graceful shutdown; task was intentionally cancelled
    await _http_client.aclose()
    logger.info("health-aggregator stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="health-aggregator",
    description="Unified platform health dashboard — The Observatory sub-service",
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


def _overall_status() -> str:
    if not _latest:
        return "unknown"
    statuses = [v["status"] for v in _latest.values()]
    if all(s == "healthy" for s in statuses):
        return "healthy"
    if any(s == "unreachable" for s in statuses):
        return "degraded"
    return "degraded"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    uptime_s = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": PORT,
        "uptime_seconds": round(uptime_s, 1),
        "poll_count": _poll_count,
        "monitored_services": len(SERVICE_REGISTRY),
        "polled_so_far": len(_latest),
        "entity": {
            "location": "The Observatory",
            "lead_ai": "Norman Hawkins",
            "primary_function": "Platform Health Aggregation",
        },
    }


def _require_internal(x_internal_secret: Optional[str]) -> None:
    if INTERNAL_SECRET and x_internal_secret != INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


@app.post("/services", status_code=201, summary="Dynamically register a service to monitor")
async def register_service(
    body: ServiceRegisterIn,
    x_internal_secret: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    _dynamic_services[body.name] = {
        "name": body.name,
        "url": body.url,
        "interval_seconds": body.interval_seconds,
    }
    return {"registered": body.name, "url": body.url}


@app.get("/services", summary="List dynamically registered services")
async def list_services(x_internal_secret: Optional[str] = Header(None)) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    return {"services": list(_dynamic_services.values())}


@app.delete("/services/{name}", summary="Remove a dynamically registered service")
async def delete_service(
    name: str, x_internal_secret: Optional[str] = Header(None)
) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    _dynamic_services.pop(name, None)
    return {"deleted": name}


@app.get("/history/{name}", summary="Health check history for a named service")
async def service_history(
    name: str,
    limit: int = Query(20, ge=1, le=500),
    x_internal_secret: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    with _conn() as c:
        rows = c.execute(
            """
            SELECT service, status, latency_ms, checked_at
            FROM health_history
            WHERE service = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (name, limit),
        ).fetchall()
    return {"history": [dict(r) for r in rows], "service": name}


@app.get("/status", summary="Full platform status")
async def status(x_internal_secret: Optional[str] = Header(None)) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    services = []
    healthy = degraded = unreachable = 0
    for svc in SERVICE_REGISTRY:
        name = svc["name"]
        if name in _latest:
            d = _latest[name]
            st = d["status"]
            entry = {
                "name": name,
                "port": svc["port"],
                "status": st,
                "latency_ms": d.get("latency_ms"),
                "last_checked": d.get("last_checked"),
                "error": d.get("error"),
            }
        else:
            st = "unknown"
            entry = {"name": name, "port": svc["port"], "status": "unknown"}
        services.append(entry)
        if st == "healthy":
            healthy += 1
        elif st == "unreachable":
            unreachable += 1
        elif st in ("degraded", "unknown"):
            degraded += 1

    overall = _overall_status()
    return {
        "summary": overall,
        "overall_status": overall,
        "healthy_count": healthy,
        "degraded_count": degraded,
        "unreachable_count": unreachable,
        "total_count": len(SERVICE_REGISTRY),
        "services": services,
    }


@app.get("/status/{service}", summary="Single service detail with history")
async def service_detail(
    service: str, x_internal_secret: Optional[str] = Header(None)
) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    # Must have been polled (in _latest) to return data; 404 otherwise
    if service not in _latest:
        raise HTTPException(status_code=404, detail=f"Service '{service}' not yet polled")

    current = _latest[service]
    svc_meta = _REGISTRY_BY_NAME.get(service) or _dynamic_services.get(service) or {}

    with _conn() as c:
        rows = c.execute(
            """
            SELECT status, latency_ms, checked_at
            FROM health_history
            WHERE service = ?
            ORDER BY id DESC
            LIMIT 20
            """,
            (service,),
        ).fetchall()

    history = [dict(r) for r in rows]

    return {
        "service": service,
        "port": svc_meta.get("port"),
        "current": current,
        "history_last_20": history,
    }


@app.get("/history", summary="History for all or one service")
async def history(
    service: Optional[str] = Query(None, description="Filter to a single service"),
    limit: int = Query(20, ge=1, le=500),
    x_internal_secret: Optional[str] = Header(None),
) -> Dict[str, Any]:
    _require_internal(x_internal_secret)
    with _conn() as c:
        if service:
            rows = c.execute(
                """
                SELECT service, status, latency_ms, checked_at
                FROM health_history
                WHERE service = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (service, limit),
            ).fetchall()
        else:
            # Return the last `limit` rows PER SERVICE using ROW_NUMBER window fn.
            # A single LIMIT clause would give a globally-skewed subset biased
            # toward whichever service has the highest IDs.
            rows = c.execute(
                """
                SELECT service, status, latency_ms, checked_at
                FROM (
                    SELECT service, status, latency_ms, checked_at,
                           ROW_NUMBER() OVER (
                               PARTITION BY service ORDER BY id DESC
                           ) AS rn
                    FROM health_history
                )
                WHERE rn <= ?
                ORDER BY service, rn
                """,
                (limit,),
            ).fetchall()

    by_service: Dict[str, List[Dict]] = defaultdict(list)
    for r in rows:
        by_service[r["service"]].append(dict(r))

    return {"history": dict(by_service), "limit_per_service": limit}


@app.get("/predict", summary="Degradation forecast: at-risk services")
async def predict() -> Dict[str, Any]:
    """
    Services with more than 2 degraded or unreachable checks in the last
    10 checks are flagged as 'at_risk'.
    """
    at_risk = []
    stable = []

    with _conn() as c:
        for svc in SERVICE_REGISTRY:
            name = svc["name"]
            rows = c.execute(
                """
                SELECT status FROM health_history
                WHERE service = ?
                ORDER BY id DESC
                LIMIT 10
                """,
                (name,),
            ).fetchall()
            if not rows:
                continue
            bad = sum(1 for r in rows if r["status"] in ("degraded", "unreachable"))
            entry = {
                "service": name,
                "port": svc["port"],
                "checks_sampled": len(rows),
                "bad_checks": bad,
                "current_status": _latest.get(name, {}).get("status", "unknown"),
            }
            if bad > 2:
                at_risk.append(entry)
            else:
                stable.append(entry)

    return {
        "at_risk_count": len(at_risk),
        "stable_count": len(stable),
        "at_risk": at_risk,
        "stable": stable,
        "prediction_window": "last 10 checks per service",
        "threshold": "more than 2 bad checks",
    }


@app.get("/metrics", response_class=PlainTextResponse, summary="Prometheus text metrics")
async def metrics() -> str:
    """
    Expose service health as Prometheus gauge metrics.

    service_health_status gauge:
      1.0 = healthy, 0.5 = degraded, 0.0 = unreachable/unknown

    service_latency_ms gauge: last observed latency in milliseconds.
    """
    lines: List[str] = [
        "# HELP service_health_status Health status of each Trancendos service (1=healthy, 0.5=degraded, 0=unreachable)",
        "# TYPE service_health_status gauge",
    ]
    for svc in SERVICE_REGISTRY:
        name = svc["name"]
        data = _latest.get(name, {})
        st = data.get("status", "unknown")
        value = {"healthy": 1.0, "degraded": 0.5}.get(st, 0.0)
        lines.append(f'service_health_status{{service="{name}",port="{svc["port"]}"}} {value}')

    lines += [
        "",
        "# HELP service_latency_ms Last observed health-check latency in milliseconds",
        "# TYPE service_latency_ms gauge",
    ]
    for svc in SERVICE_REGISTRY:
        name = svc["name"]
        data = _latest.get(name, {})
        latency = data.get("latency_ms")
        if latency is not None:
            lines.append(f'service_latency_ms{{service="{name}",port="{svc["port"]}"}} {latency}')

    lines += [
        "",
        "# HELP health_aggregator_poll_total Total number of full poll cycles completed",
        "# TYPE health_aggregator_poll_total counter",
        f"health_aggregator_poll_total {_poll_count}",
    ]

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
