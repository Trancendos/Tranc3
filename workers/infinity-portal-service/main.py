"""
Main — Infinity Portal Service
================================
App factory, lifespan, middleware, and router inclusion.
Uvicorn/Docker should point at   main:app   (or worker:app via shim).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import init_router_deps, router

from config import CORS_ORIGINS, JWT_SECRET, PORT, logger
from database import db
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware
from Dimensional.infinity.nomenclature import SentinelChannel
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.rbac import RBACEngine
from Dimensional.infinity.sentinel_station import SentinelEvent, get_sentinel_station
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# ---------------------------------------------------------------------------
# Security Engines
# ---------------------------------------------------------------------------

rbac_engine = RBACEngine()

# ---------------------------------------------------------------------------
# Sentinel Station & Dimensional Services
# ---------------------------------------------------------------------------

sentinel = get_sentinel_station()
dimensional_registry = get_dimensional_registry()
dimensional_bus = get_dimensional_bus()
underverse_registry = get_underverse_registry()

# Phase 22.6: Smart adaptive worker kit (health + defense + fluidic routing)
worker_kit = InfinityWorkerKit(
    "infinity-portal",
    defense_threshold=10,
    defense_window_seconds=300,
    defense_block_seconds=900,
)

# Inject dependencies into the router module so route handlers can reach them
init_router_deps(sentinel=sentinel, worker_kit=worker_kit)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # OpenTelemetry instrumentation
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.infinity-portal-service")
    except Exception:
        pass  # OTel is optional — never block startup

    # ── Startup ──
    logger.info("Infinity Portal starting on port %d", PORT)

    # Start Sentinel Station
    await sentinel.start()

    # Start Dimensional Service Bus
    await dimensional_bus.start()

    # Phase 22.6: Start smart adaptive worker kit
    await worker_kit.startup(app, sentinel=sentinel)

    # Register pulse daemons for background tasks
    worker_kit.health.register_daemon("session_cleaner", baseline_interval=300.0)
    worker_kit.health.register_daemon("routing_log_pruner", baseline_interval=3600.0)
    worker_kit.health.register_daemon("health_reporter", baseline_interval=60.0)

    # Register heartbeats
    dimensional_registry.heartbeat("infinity_portal")
    underverse_registry.heartbeat("gate_router")
    underverse_registry.heartbeat("session_manager")

    # Publish portal startup event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="portal_started",
            source="infinity_portal",
            payload={
                "port": PORT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "smart_adaptive": True,
                "subsystems": list(worker_kit.get_kit_stats().get("subsystems", {}).keys()),
            },
        )
    )

    logger.info("Infinity Portal ready — the front door to the Infinity Ecosystem ✨")

    # Background health reporting loop
    async def _background_loop():
        while True:
            try:
                await asyncio.sleep(10)
                # Session cleaner daemon
                if worker_kit.health.should_fire("session_cleaner"):
                    active = db.execute(
                        "SELECT COUNT(*) as cnt FROM portal_sessions WHERE is_active = 1"
                    ).fetchone()["cnt"]
                    worker_kit.health.record_metric("portal_active_sessions", float(active))
                    worker_kit.health.record_fire("session_cleaner")

                # Health reporter daemon
                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    summary_dict = summary.to_dict()
                    score = summary_dict.get("health_score", 1.0)
                    worker_kit.health.update_health(score)
                    worker_kit.health.record_fire("health_reporter")

                    # Publish health to Sentinel
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="health_report",
                            source="infinity_portal",
                            payload=summary_dict,
                        )
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Background loop error: %s", exc)

    _bg_task = asyncio.create_task(_background_loop())

    yield

    # ── Shutdown ──
    logger.info("Infinity Portal shutting down...")
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass

    # Publish shutdown event
    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="portal_stopping",
            source="infinity_portal",
            payload={"timestamp": datetime.now(timezone.utc).isoformat()},
        )
    )

    # Stop all layers
    await worker_kit.shutdown()
    await dimensional_bus.stop()
    await sentinel.stop()

    logger.info("Infinity Portal stopped")


# ---------------------------------------------------------------------------
# FastAPI Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Infinity Portal — The Front Door to Infinity",
    description=(
        "The Infinity Portal is the central login page and entry point for the "
        "entire Infinity Ecosystem. Users authenticate here and are routed through "
        "the Infinity Gate to their designated location based on their role."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OWASP Hardening (outer middleware)
app.add_middleware(OWASPHardeningMiddleware)

# Auth Gateway (inner middleware — allows public portal paths)
app.add_middleware(
    AuthGatewayMiddleware,
    jwt_secret=JWT_SECRET,
    public_paths={
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
        "/portal/login",
        "/portal/register",
        "/portal/status",
        "/portal/locations",
        "/portal/gate-info",
        "/portal/transfer-systems",
    },
    enforced_paths={
        "/portal/session",
        "/portal/route",
        "/portal/logout",
        "/gate/route",
    },
)

# Include all routes
app.include_router(router)

# ---------------------------------------------------------------------------
# Main entry point (direct script execution)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
