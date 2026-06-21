"""
Infinity-Admin Service — App Factory & Lifespan
=================================================
Creates the FastAPI application, wires middleware, and manages the
startup/shutdown lifecycle.

Uvicorn/Docker entry point (backwards compat): worker:app
New modular entry point:                        main:app
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import init_router_deps, router
from service import seed_default_config

from config import JWT_SECRET, PORT, _cors_origins, logger
from Dimensional.dimensionals import (
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware
from Dimensional.infinity.nomenclature import ECOSYSTEM_NAME, UNIVERSE_NAME, SentinelChannel
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.rbac import RBACEngine
from Dimensional.infinity.sentinel_station import SentinelEvent, get_sentinel_station
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# ---------------------------------------------------------------------------
# Security Engines & Singletons
# ---------------------------------------------------------------------------

rbac_engine = RBACEngine()
sentinel = get_sentinel_station()
dimensional_registry = get_dimensional_registry()
dimensional_bus = get_dimensional_bus()
underverse_registry = get_underverse_registry()

# Phase 22.6: Smart adaptive worker kit (admin gets higher defense thresholds)
worker_kit = InfinityWorkerKit(
    "infinity-admin",
    defense_threshold=5,      # Stricter: only 5 violations before block
    defense_window_seconds=300,
    defense_block_seconds=1800,  # 30-min block for admin violations
)

# Wire singletons into the router module before any request is served
init_router_deps(sentinel=sentinel, worker_kit=worker_kit, rbac_engine=rbac_engine)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # OpenTelemetry instrumentation (optional — never block startup)
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        from src.observability.otel import init_otel

        init_otel(service_name="tranc3.infinity-admin-service")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass

    # ── Startup ──
    logger.info("Infinity-Admin starting on port %d", PORT)

    await sentinel.start()
    await dimensional_bus.start()
    await worker_kit.startup(app, sentinel=sentinel)

    # Register pulse daemons
    worker_kit.health.register_daemon("config_auditor", baseline_interval=120.0)
    worker_kit.health.register_daemon("defense_reporter", baseline_interval=300.0)
    worker_kit.health.register_daemon("health_reporter", baseline_interval=60.0)

    dimensional_registry.heartbeat("infinity_admin")
    underverse_registry.heartbeat("config_manager")

    # Seed default configuration values
    seed_default_config(ECOSYSTEM_NAME, UNIVERSE_NAME)

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="infinity_admin_started",
            source="infinity_admin",
            payload={
                "port": PORT,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "smart_adaptive": True,
            },
        )
    )

    logger.info("Infinity-Admin ready — management OS for the Trancendos Universe ✨")

    # Background health + defense reporting loop
    async def _background_loop():
        while True:
            try:
                await asyncio.sleep(15)

                # Health reporter
                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    summary_dict = summary.to_dict()
                    worker_kit.health.update_health(summary_dict.get("health_score", 1.0))
                    worker_kit.health.record_fire("health_reporter")
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="health_report",
                            source="infinity_admin",
                            payload=summary_dict,
                        )
                    )

                # Defense reporter — publish incidents to security channel
                if worker_kit.health.should_fire("defense_reporter"):
                    defense_incidents = worker_kit.health.get_defense_incidents()
                    defense_stats = worker_kit.defense.get_stats()
                    worker_kit.health.record_fire("defense_reporter")
                    if defense_stats.get("incidents", 0) > 0:
                        await sentinel.publish(
                            SentinelEvent(
                                channel=SentinelChannel.SECURITY,
                                event_type="defense_report",
                                source="infinity_admin",
                                payload={
                                    "stats": defense_stats,
                                    "incidents": defense_incidents[:10],
                                },
                            )
                        )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Admin background loop error: %s", exc)

    _bg_task = asyncio.create_task(_background_loop())

    yield

    # ── Shutdown ──
    logger.info("Infinity-Admin shutting down...")
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass

    await sentinel.publish(
        SentinelEvent(
            channel=SentinelChannel.PLATFORM,
            event_type="infinity_admin_stopping",
            source="infinity_admin",
            payload={"timestamp": datetime.now(timezone.utc).isoformat()},
        )
    )

    await worker_kit.shutdown()
    await dimensional_bus.stop()
    await sentinel.stop()
    logger.info("Infinity-Admin stopped")


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Infinity-Admin — Administrative Management OS",
    description=(
        "Infinity-Admin is the administrative management operating system for the "
        "Trancendos Universe. It provides centralized control over the Infinity "
        "Ecosystem, including system configuration, user management, dimensional "
        "services oversight, and infrastructure monitoring."
    ),
    version="1.0.0",
    lifespan=_lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# OWASP Hardening
app.add_middleware(OWASPHardeningMiddleware)

# Auth Gateway — Admin enforces authentication on most endpoints
app.add_middleware(
    AuthGatewayMiddleware,
    jwt_secret=JWT_SECRET,
    public_paths={
        "/",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    },
    enforced_paths={
        "/admin/config",
        "/admin/features",
        "/admin/dimensionals",
        "/admin/underverse",
        "/admin/primes",
        "/admin/pillars",
        "/admin/transfer",
        "/admin/audit",
        "/admin/actions",
        "/admin/entities",
    },
)


# Health endpoint (no auth required — listed in public_paths above)
@app.get("/health")
async def health():
    """Health check for the Infinity-Admin service."""
    health_summary = worker_kit.health.get_health_summary()
    return {
        "status": "healthy",
        "service": "infinity-admin",
        "location": "Infinity-Admin",
        "purpose": "Administrative Management OS for the Trancendos Universe",
        "dimensional_bus": dimensional_bus.is_running,
        "sentinel": sentinel.is_running,
        "health_score": health_summary.to_dict().get("health_score", 1.0),
        "health_tier": health_summary.to_dict().get("health_tier", "EXCELLENT"),
        "smart_adaptive": True,
        "defense_blocked_ips": len(worker_kit.defense.get_blocked_ips()),
    }


# All admin + stats routes
app.include_router(router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
