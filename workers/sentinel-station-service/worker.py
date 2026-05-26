"""
Trancendos Sentinel Station Service — Event Bus Bridge (Interplexus Hub)
========================================================================
Dedicated service for the Sentinel Station event distribution system.
Provides a standalone API for publishing, subscribing, and monitoring
events across the Infinity Ecosystem via Redis Pub/Sub with in-process
fallback.

This service acts as the central nervous system for cross-gateway event
distribution. Other services and gateways connect here to publish events
or subscribe to channels for real-time event consumption.

Architecture:
    Publisher → Sentinel Station → Redis Pub/Sub → Subscribers
                                  ↓ (fallback)
                          In-Process Pub/Sub → Local Subscribers

Features:
    - REST API for event publishing and subscription management
    - SSE endpoint for real-time event streaming
    - Health monitoring and circuit breaker status
    - Channel statistics and configuration
    - JWT/OAuth2 authentication with tier-aware access (Phase 22)
    - RBAC endpoint authorization
    - OWASP Top 10 hardening middleware

Port: 8041
Zero-cost: FastAPI + SQLite, Redis optional (graceful fallback).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# Phase 22: Infinity Ecosystem security integration
from shared_core.infinity.auth_gateway import AuthGatewayMiddleware
from shared_core.infinity.nomenclature import InfinityRole, SentinelChannel, Tier
from shared_core.infinity.owasp_hardening import OWASPHardeningMiddleware
from shared_core.infinity.rbac import Permission, RBACEngine

# Sentinel Station core
from shared_core.infinity.sentinel_config import sentinel_config
from shared_core.infinity.sentinel_station import (
    SentinelEvent,
    SentinelStation,
    SharedSSEGenerator,
    get_sentinel_station,
)

# Phase 22.4: Dimensional Services integration
from shared_core.dimensionals import (
    DimensionalServiceBus,
    get_dimensional_bus,
    get_dimensional_registry,
    get_underverse_registry,
)

# Phase 22.6: Smart Adaptive Intelligence + ReactiveState
from shared_core.infinity.worker_integration import InfinityWorkerKit

# Optional: ReactiveState for live Sentinel topology
try:
    from src.fluidic.reactive_state import StateStore
    _REACTIVE_AVAILABLE = True
except ImportError:
    _REACTIVE_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("SENTINEL_PORT", "8041"))
DB_PATH = os.environ.get("SENTINEL_DB_PATH", "data/sentinel_station.db")
JWT_SECRET = os.environ.get("JWT_SECRET", "")

logger = logging.getLogger("sentinel-station-service")

# ---------------------------------------------------------------------------
# Security Engines
# ---------------------------------------------------------------------------

rbac_engine = RBACEngine()

# ---------------------------------------------------------------------------
# Sentinel Station Instance
# ---------------------------------------------------------------------------

sentinel = get_sentinel_station()
sse_generator: SharedSSEGenerator | None = None

# Phase 22.4: Dimensional Services
dimensional_bus = get_dimensional_bus()
dimensional_registry = get_dimensional_registry()
underverse_registry = get_underverse_registry()

# Phase 22.6: Smart adaptive worker kit + ReactiveState for live topology
worker_kit = InfinityWorkerKit(
    "sentinel-station",
    defense_threshold=20,
    defense_window_seconds=300,
    defense_block_seconds=900,
)

# ReactiveState for live Sentinel topology observable by other services
if _REACTIVE_AVAILABLE:
    sentinel_topology_state = StateStore()
    # Set initial state
    try:
        sentinel_topology_state.set({
            "channels": {},
            "subscribers": 0,
            "events_published": 0,
            "redis_connected": False,
        })
    except Exception:
        sentinel_topology_state = None
else:
    sentinel_topology_state = None


# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS event_log (
            id          TEXT PRIMARY KEY,
            channel     TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            source      TEXT NOT NULL,
            payload     TEXT NOT NULL DEFAULT '{}',
            compressed  INTEGER NOT NULL DEFAULT 0,
            created_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id          TEXT PRIMARY KEY,
            channel     TEXT NOT NULL,
            subscriber  TEXT NOT NULL,
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_event_log_channel ON event_log(channel);
        CREATE INDEX IF NOT EXISTS idx_event_log_created ON event_log(created_at);
        """
    )
    conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> dict[str, Any]:
    """Extract the authenticated user dict from request.state."""
    user = getattr(request.state, "user", None)
    return user or {"sub": "anonymous", "tier": "human", "role": "user", "is_active": False}


def _check_rbac(request: Request, endpoint: str, method: str) -> None:
    """Check RBAC access for the given endpoint/method. Raises 403 if denied."""
    user = _get_user(request)
    if not rbac_engine.check_access(user, endpoint, method):
        raise HTTPException(
            status_code=403,
            detail=f"Access denied: insufficient permissions for {method} {endpoint}",
        )


# ---------------------------------------------------------------------------
# Lifespan — starts/stops Sentinel Station
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    global sse_generator

    _init_db()

    # Start Sentinel Station (connects to Redis or falls back)
    await sentinel.start()
    logger.info(
        "Sentinel Station started (backend: %s, port: %d)",
        "redis" if sentinel.is_redis_connected else "fallback",
        PORT,
    )

    # Create shared SSE generator for broadcasting events
    sse_generator = SharedSSEGenerator(sentinel)
    await sse_generator.start()
    logger.info("Shared SSE generator started")

    # Start Dimensional Service Bus (Phase 22.4)
    await dimensional_bus.start()
    logger.info("Dimensional Service Bus started")

    # Phase 22.6: Start smart adaptive worker kit
    await worker_kit.startup(app, sentinel=sentinel)
    worker_kit.health.register_daemon("topology_updater", baseline_interval=30.0)
    worker_kit.health.register_daemon("health_reporter", baseline_interval=60.0)
    logger.info("Smart adaptive layer started for sentinel-station")

    # Register sentinel station heartbeat
    dimensional_registry.heartbeat("sentinel_station")
    underverse_registry.heartbeat("event_persister")
    underverse_registry.heartbeat("channel_manager")
    logger.info("Dimensional services heartbeat registered")

    # Background loop: topology state updates
    async def _bg_loop():
        while True:
            try:
                await asyncio.sleep(10)
                if worker_kit.health.should_fire("topology_updater"):
                    stats = sentinel.get_stats()
                    worker_kit.health.record_metric(
                        "sentinel_events_published",
                        float(stats.get("events_published", 0)),
                    )
                    worker_kit.health.record_metric(
                        "sentinel_subscribers",
                        float(stats.get("total_subscribers", 0)),
                    )
                    # Update reactive topology state
                    if sentinel_topology_state is not None:
                        sentinel_topology_state.set({
                            "channels": stats.get("channel_stats", {}),
                            "subscribers": stats.get("total_subscribers", 0),
                            "events_published": stats.get("events_published", 0),
                            "redis_connected": sentinel.is_redis_connected,
                        })
                    worker_kit.health.record_fire("topology_updater")

                if worker_kit.health.should_fire("health_reporter"):
                    summary = worker_kit.health.get_health_summary()
                    if hasattr(summary, "to_dict"): summary = summary.to_dict()
                    worker_kit.health.update_health(summary.get("health_score", 1.0))
                    worker_kit.health.record_fire("health_reporter")
                    # Broadcast sentinel health to the platform channel
                    await sentinel.publish(SentinelEvent(
                        channel=SentinelChannel.PLATFORM,
                        event_type="sentinel_health_report",
                        source="sentinel_station",
                        payload=summary,
                    ))
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("Sentinel background loop error: %s", exc)

    _bg_task = asyncio.create_task(_bg_loop())

    yield

    # Shutdown
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass
    await worker_kit.shutdown()
    # Shutdown Dimensional Service Bus
    await dimensional_bus.stop()
    logger.info("Dimensional Service Bus stopped")

    # Shutdown Sentinel Station
    await sentinel.stop()
    logger.info("Sentinel Station stopped")


# ---------------------------------------------------------------------------
# FastAPI App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Tranc3 Sentinel Station Service",
    version="0.7.0",
    lifespan=_lifespan,
)

# Middleware Stack (ordered outermost to innermost)
app.add_middleware(
    OWASPHardeningMiddleware,
    csrf_enabled=True,
    input_validation_enabled=True,
    remove_server_header=True,
)

app.add_middleware(
    AuthGatewayMiddleware,
    jwt_secret=JWT_SECRET,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get("CORS_ORIGINS", "*")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Pydantic Schemas
# ---------------------------------------------------------------------------


class EventPublish(BaseModel):
    """Schema for publishing an event to a Sentinel channel."""

    channel: str = Field(..., description="Sentinel channel name (e.g., 'agents', 'workflows')")
    event_type: str = Field(..., description="Event type (e.g., 'agent_created')")
    source: str = Field(default="api", description="Source service identifier")
    payload: dict[str, Any] = Field(default_factory=dict, description="Event data")


class SubscriptionCreate(BaseModel):
    """Schema for creating a subscription to a Sentinel channel."""

    channel: str = Field(..., description="Sentinel channel name")
    subscriber: str = Field(default="api_client", description="Subscriber identifier")


# ---------------------------------------------------------------------------
# Health & Stats
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    """Health check endpoint."""
    sentinel_health = await sentinel.health_check()
    health_summary_obj = worker_kit.health.get_health_summary()
    health_summary = health_summary_obj.to_dict() if hasattr(health_summary_obj, "to_dict") else health_summary_obj
    return {
        "status": "ok",
        "service": "sentinel-station-service",
        "version": "0.7.0",
        "sentinel": sentinel_health,
        "dimensional_bus": {
            "running": dimensional_bus.is_running,
        },
        # Phase 22.6: Smart health
        "health_score": health_summary.get("health_score", 1.0),
        "health_tier": health_summary.get("tier", "EXCELLENT"),
        "smart_adaptive": True,
        "reactive_topology": sentinel_topology_state is not None,
    }


@app.get("/stats")
async def stats():
    """Service statistics endpoint."""
    return {
        "service": "sentinel-station-service",
        "version": "0.7.0",
        "sentinel": sentinel.get_stats(),
        "dimensional_bus": dimensional_bus.get_stats(),
        "dimensional_registry": dimensional_registry.get_stats(),
        "underverse": underverse_registry.get_stats(),
        "config": {
            "service_name": sentinel_config.service_name,
            "service_port": sentinel_config.service_port,
            "redis_host": sentinel_config.redis.host,
            "redis_port": sentinel_config.redis.port,
            "redis_channel_prefix": sentinel_config.redis_channel_prefix,
            "fallback_enabled": sentinel_config.fallback.enabled,
            "compression_threshold": sentinel_config.compression_threshold,
        },
        # Phase 22.6: Smart adaptive layer stats
        "smart_adaptive": worker_kit.get_kit_stats(),
    }


# ---------------------------------------------------------------------------
# Event Publishing API
# ---------------------------------------------------------------------------


@app.post("/api/events/publish")
async def publish_event(body: EventPublish, request: Request):
    """Publish an event to a Sentinel channel.

    The event is distributed to all subscribers on the channel,
    both via Redis Pub/Sub (cross-gateway) and in-process fallback (local).
    """
    _check_rbac(request, "/api/events", "POST")

    # Validate channel name
    valid_channels = [ch.value for ch in SentinelChannel]
    if body.channel not in valid_channels:
        raise HTTPException(
            400,
            detail=f"Invalid channel: {body.channel}. Valid channels: {', '.join(valid_channels)}",
        )

    # Publish through Sentinel Station
    event = await sentinel.publish(
        channel=body.channel,
        payload=body.payload,
        event_type=body.event_type,
        source=body.source,
    )

    # Persist event to database for audit trail
    db = _get_db()
    try:
        db.execute(
            "INSERT INTO event_log (id, channel, event_type, source, payload, compressed, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.id,
                event.channel,
                event.event_type,
                event.source,
                json.dumps(event.payload),
                1 if event.compressed else 0,
                event.timestamp,
            ),
        )
        db.commit()
    except Exception:
        logger.debug("Failed to persist event to database", exc_info=True)
    finally:
        db.close()

    return {
        "id": event.id,
        "channel": event.channel,
        "event_type": event.event_type,
        "source": event.source,
        "timestamp": event.timestamp,
        "compressed": event.compressed,
        "status": "published",
    }


@app.post("/api/events/publish/batch")
async def publish_events_batch(events: list[EventPublish], request: Request):
    """Publish multiple events to Sentinel channels in batch."""
    _check_rbac(request, "/api/events", "POST")

    valid_channels = [ch.value for ch in SentinelChannel]
    published = []
    errors = []

    for i, body in enumerate(events):
        if body.channel not in valid_channels:
            errors.append({"index": i, "error": f"Invalid channel: {body.channel}"})
            continue

        event = await sentinel.publish(
            channel=body.channel,
            payload=body.payload,
            event_type=body.event_type,
            source=body.source,
        )
        published.append({
            "id": event.id,
            "channel": event.channel,
            "event_type": event.event_type,
        })

    return {
        "published": published,
        "errors": errors,
        "total_requested": len(events),
        "total_published": len(published),
        "total_errors": len(errors),
    }


# ---------------------------------------------------------------------------
# Event History API
# ---------------------------------------------------------------------------


@app.get("/api/events/history")
async def event_history(
    channel: str = Query(None, description="Filter by channel"),
    limit: int = Query(50, ge=1, le=500),
    request: Request = None,
):
    """Retrieve recent event history from the database."""
    _check_rbac(request, "/api/events", "GET")

    db = _get_db()
    try:
        if channel:
            rows = db.execute(
                "SELECT * FROM event_log WHERE channel = ? ORDER BY created_at DESC LIMIT ?",
                (channel, limit),
            ).fetchall()
        else:
            rows = db.execute(
                "SELECT * FROM event_log ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Subscription Management API
# ---------------------------------------------------------------------------


@app.post("/api/subscriptions")
async def create_subscription(body: SubscriptionCreate, request: Request):
    """Register a subscription to a Sentinel channel."""
    _check_rbac(request, "/api/subscriptions", "POST")

    valid_channels = [ch.value for ch in SentinelChannel]
    if body.channel not in valid_channels:
        raise HTTPException(
            400,
            detail=f"Invalid channel: {body.channel}. Valid channels: {', '.join(valid_channels)}",
        )

    # Subscribe through Sentinel Station
    queue = await sentinel.subscribe(body.channel)

    # Persist subscription record
    sub_id = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    db = _get_db()
    try:
        db.execute(
            "INSERT INTO subscriptions (id, channel, subscriber, created_at) VALUES (?, ?, ?, ?)",
            (sub_id, body.channel, body.subscriber, now),
        )
        db.commit()
    except Exception:
        logger.debug("Failed to persist subscription", exc_info=True)
    finally:
        db.close()

    return {
        "id": sub_id,
        "channel": body.channel,
        "subscriber": body.subscriber,
        "created_at": now,
        "status": "subscribed",
    }


@app.get("/api/subscriptions")
async def list_subscriptions(request: Request):
    """List all active subscriptions."""
    _check_rbac(request, "/api/subscriptions", "GET")

    db = _get_db()
    try:
        rows = db.execute(
            "SELECT * FROM subscriptions ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        db.close()


@app.delete("/api/subscriptions/{subscription_id}")
async def delete_subscription(subscription_id: str, request: Request):
    """Remove a subscription."""
    _check_rbac(request, "/api/subscriptions", "DELETE")

    db = _get_db()
    try:
        row = db.execute(
            "SELECT * FROM subscriptions WHERE id = ?",
            (subscription_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, "Subscription not found")
        db.execute("DELETE FROM subscriptions WHERE id = ?", (subscription_id,))
        db.commit()
        return {"id": subscription_id, "status": "unsubscribed"}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Channel Management API
# ---------------------------------------------------------------------------


@app.get("/api/channels")
async def list_channels(request: Request):
    """List all available Sentinel channels and their configuration."""
    _check_rbac(request, "/api/events", "GET")

    channels = {}
    for ch in SentinelChannel:
        cfg = sentinel_config.channels.get(ch.value)
        channels[ch.value] = {
            "name": cfg.name if cfg else ch.value,
            "description": cfg.description if cfg else "",
            "max_message_size": cfg.max_message_size if cfg else 1024 * 1024,
            "persistent": cfg.persistent if cfg else True,
            "retry_on_failure": cfg.retry_on_failure if cfg else True,
            "redis_key": f"{sentinel_config.redis_channel_prefix}{ch.value}",
        }

    return {
        "channels": channels,
        "total": len(channels),
        "redis_prefix": sentinel_config.redis_channel_prefix,
        "redis_connected": sentinel.is_redis_connected,
        "circuit_breaker": sentinel.circuit_breaker_state.value,
    }


@app.get("/api/channels/{channel_name}/stats")
async def channel_stats(channel_name: str, request: Request):
    """Get statistics for a specific Sentinel channel."""
    _check_rbac(request, "/api/events", "GET")

    valid_channels = [ch.value for ch in SentinelChannel]
    if channel_name not in valid_channels:
        raise HTTPException(
            400,
            detail=f"Invalid channel: {channel_name}. Valid channels: {', '.join(valid_channels)}",
        )

    stats = sentinel.get_stats()
    fallback_stats = stats.get("fallback", {})

    return {
        "channel": channel_name,
        "redis_key": f"{sentinel_config.redis_channel_prefix}{channel_name}",
        "fallback_subscribers": fallback_stats.get("channels", 0),
        "total_subscribers": fallback_stats.get("total_subscribers", 0),
        "events_published": stats.get("events_published", 0),
        "events_received": stats.get("events_received", 0),
    }


# ---------------------------------------------------------------------------
# SSE Events Stream
# ---------------------------------------------------------------------------


async def _sentinel_event_generator():
    """Generate SSE events from Sentinel Station for real-time streaming."""
    if sse_generator is not None:
        async for event in sse_generator.generate():
            yield event
    else:
        # Fallback: yield periodic keepalive events
        while True:
            try:
                yield {
                    "event": "keepalive",
                    "data": json.dumps({
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "service": "sentinel-station",
                    }),
                }
                await asyncio.sleep(30)
            except asyncio.CancelledError:
                break


@app.get("/events")
async def sse_events():
    """SSE endpoint for real-time Sentinel Station event streaming."""
    return EventSourceResponse(_sentinel_event_generator())


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "workers.sentinel_station_service.worker:app",
        host="0.0.0.0",
        port=PORT,
        reload=False,
    )
