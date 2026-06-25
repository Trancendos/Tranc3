"""
Main — Infinity Auth Service
==============================
App factory, lifespan, middleware, and router inclusion.
Uvicorn/Docker should point at   main:app   (or worker:app via shim).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import init_router_deps, router

from config import PORT, _cors_origins, logger
from shared_core.infinity.worker_integration import InfinityWorkerKit

worker_kit = InfinityWorkerKit(
    "infinity-auth", defense_threshold=3, defense_window_seconds=60, defense_block_seconds=900
)
init_router_deps(worker_kit=worker_kit)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.infinity-auth", worker_port=PORT)
    except Exception:
        pass
    logger.info("Infinity Auth starting on port %d", PORT)
    await worker_kit.startup(app, sentinel=None)
    logger.info("Infinity Auth ready ✨")

    async def _bg():
        while True:
            try:
                await asyncio.sleep(60)
                if worker_kit.health.should_fire("health_reporter"):
                    s = worker_kit.health.get_health_summary().to_dict()
                    worker_kit.health.update_health(s.get("health_score", 1.0))
                    worker_kit.health.record_fire("health_reporter")
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("BG loop: %s", exc)

    _bg_task = asyncio.create_task(_bg())
    yield
    logger.info("Infinity Auth shutting down...")
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass
    await worker_kit.shutdown()
    logger.info("Infinity Auth stopped")


cors_origins = _cors_origins()
app = FastAPI(
    title="Infinity — Authentication Service",
    description="OAuth2/JWT/TOTP authentication for the Trancendos platform.",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
