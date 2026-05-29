"""
Trancendos geo-service — Self-Hosted Worker
===========================================
IP geolocation with multi-tier fallback:
  1. Local SQLite lookup cache (previous results)
  2. ip-api.com free JSON API (no key, 45 req/min limit)
  3. ipapi.co free JSON API (fallback, 1000 req/day)
  4. Stub response (always works offline)

Also provides distance calculation and country/timezone utilities.

Port: 8027
Zero-cost: FastAPI + SQLite cache + free public APIs, no paid deps.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8027
WORKER_NAME = "geo-service"
DB_PATH = Path(__file__).parent / "data" / "geo.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
CACHE_TTL = 86400  # 24h cache for IP lookups

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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ip_cache (
                ip          TEXT PRIMARY KEY,
                country     TEXT,
                country_code TEXT,
                region      TEXT,
                city        TEXT,
                lat         REAL,
                lon         REAL,
                timezone    TEXT,
                isp         TEXT,
                org         TEXT,
                source      TEXT,
                cached_at   REAL NOT NULL
            )
        """)
        conn.commit()


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------


def _get_cached(ip: str) -> Optional[dict]:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM ip_cache WHERE ip = ?", (ip,)).fetchone()
    if row and (time.time() - row["cached_at"]) < CACHE_TTL:
        return dict(row)
    return None


def _save_cache(ip: str, data: dict, source: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ip_cache (ip, country, country_code, region, city, lat, lon, timezone, isp, org, source, cached_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                ip,
                data.get("country"),
                data.get("country_code"),
                data.get("region"),
                data.get("city"),
                data.get("lat"),
                data.get("lon"),
                data.get("timezone"),
                data.get("isp"),
                data.get("org"),
                source,
                time.time(),
            ),
        )
        conn.commit()


async def _lookup_ip_api(ip: str) -> Optional[dict]:
    url = f"http://ip-api.com/json/{ip}?fields=status,country,countryCode,regionName,city,lat,lon,timezone,isp,org"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            d = resp.json()
            if d.get("status") == "success":
                return {
                    "country": d.get("country"),
                    "country_code": d.get("countryCode"),
                    "region": d.get("regionName"),
                    "city": d.get("city"),
                    "lat": d.get("lat"),
                    "lon": d.get("lon"),
                    "timezone": d.get("timezone"),
                    "isp": d.get("isp"),
                    "org": d.get("org"),
                }
    except Exception as exc:
        logger.debug("ip-api.com error: %s", exc)
    return None


async def _lookup_ipapi_co(ip: str) -> Optional[dict]:
    url = f"https://ipapi.co/{ip}/json/"
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(url, headers={"User-Agent": "trancendos-geo-service/1.0"})
        if resp.status_code == 200:
            d = resp.json()
            if "error" not in d:
                return {
                    "country": d.get("country_name"),
                    "country_code": d.get("country_code"),
                    "region": d.get("region"),
                    "city": d.get("city"),
                    "lat": d.get("latitude"),
                    "lon": d.get("longitude"),
                    "timezone": d.get("timezone"),
                    "isp": d.get("org"),
                    "org": d.get("org"),
                }
    except Exception as exc:
        logger.debug("ipapi.co error: %s", exc)
    return None


def _stub_result(ip: str) -> dict:
    return {
        "country": "Unknown",
        "country_code": "XX",
        "region": "Unknown",
        "city": "Unknown",
        "lat": 0.0,
        "lon": 0.0,
        "timezone": "UTC",
        "isp": "Unknown",
        "org": "Unknown",
    }


async def lookup_ip(ip: str) -> dict:
    cached = _get_cached(ip)
    if cached:
        return {**cached, "cached": True}

    # Try ip-api.com first, then ipapi.co
    data = await _lookup_ip_api(ip)
    source = "ip-api.com"
    if not data:
        data = await _lookup_ipapi_co(ip)
        source = "ipapi.co"
    if not data:
        data = _stub_result(ip)
        source = "stub"

    _save_cache(ip, data, source)
    return {**data, "ip": ip, "source": source, "cached": False}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Returns distance in km between two coordinates."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DistanceIn(BaseModel):
    lat1: float
    lon1: float
    lat2: float
    lon2: float


class BatchIpIn(BaseModel):
    ips: list[str]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("geo-service DB ready")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="geo-service",
    description="IP geolocation with SQLite cache and free API fallback (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    with get_conn() as conn:
        cached = conn.execute("SELECT COUNT(*) FROM ip_cache").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "cached_ips": cached,
        "entity": {
            "location": "The Dutchy",
            "pillar": "DevOps",
            "lead_ai": "Predictive lore",
            "primes": ["Trancendos"],
            "primary_function": "Intelligence & Market Analysis",
        },
    }


@app.get("/lookup/{ip}")
async def lookup(ip: str):
    if ip in ("localhost", "127.0.0.1", "::1"):
        return {
            "ip": ip,
            "country": "Local",
            "country_code": "LO",
            "city": "Localhost",
            "lat": 0.0,
            "lon": 0.0,
            "timezone": "UTC",
            "source": "local",
            "cached": True,
        }
    result = await lookup_ip(ip)
    return {"ip": ip, **result}


@app.post("/lookup/batch")
async def lookup_batch(req: BatchIpIn):
    results = await asyncio.gather(*[lookup_ip(ip) for ip in req.ips[:100]])
    return {"results": [{"ip": ip, **r} for ip, r in zip(req.ips, results, strict=False)]}


@app.post("/distance")
async def distance(req: DistanceIn):
    km = _haversine(req.lat1, req.lon1, req.lat2, req.lon2)
    return {
        "distance_km": round(km, 3),
        "distance_miles": round(km * 0.621371, 3),
        "from": {"lat": req.lat1, "lon": req.lon1},
        "to": {"lat": req.lat2, "lon": req.lon2},
    }


@app.get("/cache")
async def cache_stats():
    now = time.time()
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM ip_cache").fetchone()[0]
        fresh = conn.execute(
            "SELECT COUNT(*) FROM ip_cache WHERE cached_at > ?", (now - CACHE_TTL,)
        ).fetchone()[0]
        by_source = conn.execute(
            "SELECT source, COUNT(*) as c FROM ip_cache GROUP BY source"
        ).fetchall()
    return {
        "total_cached": total,
        "fresh": fresh,
        "stale": total - fresh,
        "by_source": [dict(r) for r in by_source],
    }


@app.delete("/cache/{ip}")
async def evict(ip: str):
    with get_conn() as conn:
        conn.execute("DELETE FROM ip_cache WHERE ip = ?", (ip,))
        conn.commit()
    return {"evicted": ip}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
