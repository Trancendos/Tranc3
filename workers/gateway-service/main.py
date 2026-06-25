"""
main.py — Gateway Service application factory + lifespan
=========================================================
Wires up middleware, the router, and all startup/shutdown hooks.
Uvicorn entry-point:  main:app  (or worker:app via the shim).
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import router as _router_module
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import router
from service import (
    dimensional_bus,
    dimensional_registry,
    evict_expired_cache,
    get_cache_size,
    get_circuit_breaker_states,
    init_circuit_breakers,
    sentinel,
    underverse_registry,
)

from config import CORS_ORIGINS, JWT_SECRET, logger
from database import init_db

# Dimensional middleware
from Dimensional.infinity.auth_gateway import AuthGatewayMiddleware
from Dimensional.infinity.nomenclature import SentinelChannel
from Dimensional.infinity.owasp_hardening import OWASPHardeningMiddleware
from Dimensional.infinity.sentinel_station import SentinelEvent, SharedSSEGenerator

# Phase 22.6: Smart Adaptive Intelligence
from Dimensional.infinity.worker_integration import InfinityWorkerKit

# ---------------------------------------------------------------------------
# Phase 22.6: Smart Adaptive worker kit (module-level singleton)
# ---------------------------------------------------------------------------

worker_kit = InfinityWorkerKit(
    "gateway-service",
    defense_threshold=20,
    defense_window_seconds=300,
    defense_block_seconds=900,
)


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # Optional OpenTelemetry instrumentation
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.gateway-service")
    except Exception:
        pass  # OTel is optional — never block startup

    # Database
    init_db()

    # Circuit breakers
    init_circuit_breakers()

    # Sentinel Station
    await sentinel.start()
    logger.info(
        "Sentinel Station started (backend: %s)",
        "redis" if sentinel.is_redis_connected else "fallback",
    )

    # Shared SSE generator
    sse_gen = SharedSSEGenerator(sentinel)
    await sse_gen.start()
    _router_module.sse_generator = sse_gen
    logger.info("Shared SSE generator started")

    # Dimensional Service Bus
    await dimensional_bus.start()
    logger.info("Dimensional Service Bus started")

    # Smart adaptive layer
    await worker_kit.startup(app, sentinel=sentinel)
    worker_kit.health.register_daemon("cache_janitor", baseline_interval=60.0)
    worker_kit.health.register_daemon("circuit_monitor", baseline_interval=30.0)
    worker_kit.health.register_daemon("gateway_reporter", baseline_interval=60.0)
    logger.info("Smart adaptive layer started for gateway-service")

    # Dimensional heartbeats
    dimensional_registry.heartbeat("gateway")
    underverse_registry.heartbeat("cache_manager")
    underverse_registry.heartbeat("circuit_monitor")
    logger.info("Dimensional services heartbeat registered")

    # Background adaptive loop
    async def _bg_loop():
        while True:
            try:
                await asyncio.sleep(10)

                if worker_kit.health.should_fire("cache_janitor"):
                    evict_expired_cache()
                    worker_kit.health.record_metric("gateway_cache_size", float(get_cache_size()))
                    worker_kit.health.record_fire("cache_janitor")

                if worker_kit.health.should_fire("circuit_monitor"):
                    states = get_circuit_breaker_states()
                    open_circuits = sum(1 for s in states.values() if s == "open")
                    worker_kit.health.record_metric("gateway_open_circuits", float(open_circuits))
                    if open_circuits > 0:
                        worker_kit.health.update_health(max(0.3, 1.0 - open_circuits * 0.2))
                    worker_kit.health.record_fire("circuit_monitor")

                if worker_kit.health.should_fire("gateway_reporter"):
                    summary = worker_kit.health.get_health_summary().to_dict()
                    worker_kit.health.record_fire("gateway_reporter")
                    await sentinel.publish(
                        SentinelEvent(
                            channel=SentinelChannel.PLATFORM,
                            event_type="gateway_health_report",
                            source="gateway",
                            payload=summary,
                        )
                    )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Gateway background loop error: %s", exc)

    _bg_task = asyncio.create_task(_bg_loop())

    yield  # Application runs here

    # Shutdown
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass

    await worker_kit.shutdown()
    await dimensional_bus.stop()
    logger.info("Dimensional Service Bus stopped")
    await sentinel.stop()
    logger.info("Sentinel Station stopped")


# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Tranc3 Gateway Service",
        version="0.8.0",
        lifespan=_lifespan,
    )

    # Middleware stack — added in reverse execution order
    # CORS must be added last (executes first as innermost)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Auth Gateway — JWT/OAuth2 authentication, sets request.state.user
    app.add_middleware(
        AuthGatewayMiddleware,
        jwt_secret=JWT_SECRET,
    )

    # OWASP Hardening — outermost: security headers, input validation, CSRF
    app.add_middleware(
        OWASPHardeningMiddleware,
        csrf_enabled=True,
        input_validation_enabled=True,
        remove_server_header=True,
    )

    app.include_router(router)
    return app


# Module-level app instance (uvicorn entry-point: main:app)
app = create_app()
