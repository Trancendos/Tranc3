# src/observability/routes.py
# HTTP routes for The Observatory — audit log and event feed.
#
# Routes:
#   GET  /observatory/recent          — last N events (JSON)
#   GET  /observatory/stats           — counters by category/severity
#   GET  /observatory/search          — filter events by actor/type
#   GET  /observatory/sse             — Server-Sent Events live stream
#   POST /observatory/record          — (internal) emit an event via HTTP

from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse

from Dimensional.sanitize import sanitize_for_log
from src.observability.observatory import (
    EventCategory,
    EventSeverity,
    get_observatory,
    observe,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/observatory", tags=["observatory"])


@router.get("/recent")
async def observatory_recent(
    limit: int = Query(50, ge=1, le=500),
    category: Optional[str] = Query(None),
):
    """Return recent audit events, newest first."""
    obs = get_observatory()
    cat = None
    if category:
        try:
            cat = EventCategory(category)
        except ValueError:
            return JSONResponse({"error": f"Unknown category: {category}"}, status_code=400)
    events = obs.recent(limit=limit, category=cat)
    return [e.to_dict() for e in events]


@router.get("/stats")
async def observatory_stats():
    """Return aggregate counters for the in-memory ring buffer."""
    return get_observatory().stats()


@router.get("/search")
async def observatory_search(
    actor: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Search events by actor or event_type prefix."""
    obs = get_observatory()
    events = obs.search(actor=actor, event_type=event_type, limit=limit)
    return [e.to_dict() for e in events]


@router.get("/sse")
async def observatory_sse(request: Request):
    """
    Server-Sent Events stream — pushes new AuditEvents to the browser as they arrive.
    The SparkDashboard connects here for the live event feed.
    """
    obs = get_observatory()
    queue: asyncio.Queue = obs.subscribe(maxsize=200)

    async def event_stream():
        try:
            # Send recent backlog so the browser has initial data
            backlog = obs.recent(limit=10)
            for ev in reversed(backlog):
                yield f"data: {json.dumps(ev.to_dict())}\n\n"

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=15.0)
                    yield f"data: {json.dumps(event.to_dict())}\n\n"
                except asyncio.TimeoutError:
                    # Keepalive comment so proxies don't close the connection
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            logger.debug("Graceful degradation: %s", "unknown")  # nosec B110
        finally:
            obs.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/record")
async def observatory_record(request: Request):
    """Internal endpoint — emit an event from external services (e.g. CF Workers)."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON"}, status_code=400)

    event_type = body.get("event_type")
    if not event_type:
        return JSONResponse({"error": "event_type required"}, status_code=400)

    severity_raw = body.get("severity", "info")
    category_raw = body.get("category", "system")

    try:
        severity = EventSeverity(severity_raw)
    except ValueError:
        severity = EventSeverity.INFO
    try:
        category = EventCategory(category_raw)
    except ValueError:
        category = EventCategory.SYSTEM

    event = observe(
        event_type,
        actor=body.get("actor"),
        target=body.get("target"),
        category=category,
        severity=severity,
        service=body.get("service", "external"),
        location=body.get("location"),
        outcome=body.get("outcome", "success"),
        metadata=body.get("metadata", {}),
        session_id=body.get("session_id"),
    )
    logger.debug(
        "observatory.record via HTTP: %s", sanitize_for_log(event_type)
    )  # codeql[py/cleartext-logging]
    return {"id": event.id, "timestamp": event.timestamp}
