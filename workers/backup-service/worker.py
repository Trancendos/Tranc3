"""
Trancendos Backup Service — Automated DR Worker
=================================================
Self-hosted backup daemon for all SQLite worker databases.

Port: 8087
Zero-cost: FastAPI + asyncio scheduler + sqlite3 hot-backup API.

Schedules
---------
CRITICAL  every 15 min
HIGH      every 60 min
STANDARD  every 6 h
LOW       every 24 h

REST API
--------
GET  /health              — service health + last-run summary
GET  /backup/status       — backup health for all workers
GET  /backup/list         — list all backup files (optionally ?worker=X)
POST /backup/run          — trigger immediate backup (body: {"worker": "X"} or {"tier": "critical"})
POST /backup/run-all      — trigger full backup cycle for all tiers
POST /backup/verify       — verify latest backup for every worker
POST /backup/restore      — restore a worker DB (body: {"worker": "X", "dry_run": true})
GET  /backup/rpo-status   — RPO breach report
"""

from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.backup.engine import BackupEngine
from src.backup.registry import (
    REGISTRY_BY_TIER,
    REGISTRY_BY_WORKER,
    WORKER_DATABASE_REGISTRY,
    BackupTier,
)
from src.entities.health_metadata import health_entity_block

logger = logging.getLogger("tranc3.workers.backup-service")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")

WORKER_PORT = 8039
BACKUP_ROOT = Path(os.environ.get("BACKUP_ROOT", "/data/backups"))

engine = BackupEngine(backup_root=BACKUP_ROOT, encrypt=True)

# ── Schedule intervals (minutes) ────────────────────────────────────────────
_SCHEDULE: dict[BackupTier, int] = {
    BackupTier.CRITICAL: 15,
    BackupTier.HIGH: 60,
    BackupTier.STANDARD: 360,
    BackupTier.LOW: 1440,
}

_last_run: dict[str, str] = {}  # worker → ISO timestamp of last backup attempt
_run_stats: dict[str, dict] = {}


# ── Background scheduler ─────────────────────────────────────────────────────


async def _backup_tier(tier: BackupTier) -> None:
    workers = REGISTRY_BY_TIER.get(tier, [])
    for worker_db in workers:
        result = await asyncio.to_thread(engine.backup, worker_db)
        ts = datetime.now(timezone.utc).isoformat()
        _last_run[worker_db.worker] = ts
        _run_stats[worker_db.worker] = {
            "success": result.success,
            "timestamp": ts,
            "error": result.error,
            "size_bytes": result.meta.compressed_size_bytes if result.meta else None,
            "verified": result.meta.verified if result.meta else False,
        }


async def _scheduler() -> None:
    """Asyncio scheduler — fires each tier on its interval."""
    counters: dict[BackupTier, int] = dict.fromkeys(BackupTier, 0)
    tick_seconds = 60  # check every minute

    while True:
        await asyncio.sleep(tick_seconds)
        for tier, interval_minutes in _SCHEDULE.items():
            counters[tier] += 1
            if counters[tier] >= interval_minutes:
                counters[tier] = 0
                logger.info("scheduler: running %s tier backups", tier.value)
                asyncio.create_task(_backup_tier(tier))


@asynccontextmanager
async def lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.backup-service")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass  # OTel is optional — never block startup
    asyncio.create_task(_scheduler())
    logger.info("backup-service started on port %d — scheduler active", WORKER_PORT)
    yield


# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(title="Trancendos Backup Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/backup")


# ── Pydantic models ───────────────────────────────────────────────────────────


class BackupRunRequest(BaseModel):
    worker: Optional[str] = None
    tier: Optional[str] = None


class RestoreRequest(BaseModel):
    worker: str
    backup_path: Optional[str] = None
    target_path: Optional[str] = None
    dry_run: bool = True  # safe default


# ── Endpoints ─────────────────────────────────────────────────────────────────


@app.get("/health")
async def health():
    status = engine.status()
    return {
        "status": "healthy" if status["health_pct"] >= 80 else "degraded",
        "service": "backup-service",
        "port": WORKER_PORT,
        "backup_root": str(BACKUP_ROOT),
        "registered_workers": len(WORKER_DATABASE_REGISTRY),
        "healthy_workers": status["healthy"],
        "health_pct": status["health_pct"],
        "entity": health_entity_block(WORKER_PORT, "backup-service"),
    }


@router.get("/status")
async def backup_status():
    return engine.status()


@router.get("/rpo-status")
async def rpo_status():
    status = engine.status()
    breached = [w for w in status["workers"] if w["rpo_breached"]]
    return {
        "total_workers": status["total_workers"],
        "rpo_compliant": status["total_workers"] - len(breached),
        "rpo_breached": len(breached),
        "breached_workers": breached,
    }


@router.get("/list")
async def list_backups(worker: Optional[str] = None):
    return {"backups": engine.list_backups(worker)}


@router.post("/run")
async def run_backup(req: BackupRunRequest):
    if req.worker:
        worker_db = REGISTRY_BY_WORKER.get(req.worker)
        if not worker_db:
            raise HTTPException(status_code=404, detail=f"Worker '{req.worker}' not in registry")
        result = await asyncio.to_thread(engine.backup, worker_db)
        if result.meta:
            _run_stats[req.worker] = {
                "success": result.success,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "size_bytes": result.meta.compressed_size_bytes,
                "verified": result.meta.verified,
            }
        return {
            "success": result.success,
            "meta": result.meta.__dict__ if result.meta else None,
            "error": result.error,
        }

    if req.tier:
        try:
            tier = BackupTier(req.tier)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown tier '{req.tier}'") from None
        await _backup_tier(tier)
        return {"success": True, "tier": req.tier, "workers": len(REGISTRY_BY_TIER.get(tier, []))}

    raise HTTPException(status_code=400, detail="Provide either 'worker' or 'tier'")


@router.post("/run-all")
async def run_all():
    results = await asyncio.to_thread(engine.backup_all)
    ok = sum(1 for r in results if r.success)
    return {
        "total": len(results),
        "success": ok,
        "failed": len(results) - ok,
        "results": [
            {"worker": r.meta.worker if r.meta else "?", "success": r.success, "error": r.error}
            for r in results
        ],
    }


@router.post("/verify")
async def verify_all():
    results = await asyncio.to_thread(engine.verify_all)
    ok = sum(1 for v in results.values() if v)
    return {
        "total": len(results),
        "verified": ok,
        "failed": len(results) - ok,
        "workers": results,
    }


@router.post("/restore")
async def restore(req: RestoreRequest):
    result = await asyncio.to_thread(
        engine.restore,
        req.worker,
        req.backup_path,
        req.target_path,
        req.dry_run,
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error or "Restore failed")
    return {
        "success": result.success,
        "worker": result.worker,
        "restored_to": result.restored_to,
        "backup_path": result.backup_path,
        "verified": result.verified,
        "dry_run": req.dry_run,
    }


app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
