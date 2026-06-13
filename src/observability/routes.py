# src/observability/routes.py
# HTTP routes for The Observatory — audit log, event feed, and SSE stream.
#
# Router prefix: /observatory
#
# Routes:
#   GET  /observatory/              — info / redirect
#   GET  /observatory/recent        — last N events from ring buffer
#   GET  /observatory/stats         — counters by category, severity, service
#   GET  /observatory/search        — full-text search through messages/details
#   GET  /observatory/export        — export events as JSON or CSV
#   GET  /observatory/sse           — Server-Sent Events live stream
#   POST /observatory/events        — ingest an AuditEvent (service-to-service)
#   GET  /observatory/verify        — chain integrity placeholder
#   GET  /observatory/health        — buffer size + oldest/newest timestamps

from __future__ import annotations

import asyncio
import csv
import io
import json
import logging
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, RedirectResponse, StreamingResponse

from Dimensional.sanitize import sanitize_for_log
from src.observability.observatory import (
    AuditEvent,
    EventCategory,
    EventSeverity,
    get_observatory,
    observe,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/observatory", tags=["observatory"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_dt(value: Optional[str], param_name: str) -> Optional[float]:
    """Parse an ISO 8601 datetime string to a UTC timestamp (float)."""
    if value is None:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.timestamp()
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid ISO datetime for '{param_name}': {value!r}",
        ) from exc


# ---------------------------------------------------------------------------
# GET /
# ---------------------------------------------------------------------------


@router.get("/", include_in_schema=False)
async def observatory_root():
    """Redirect browser traffic to /observatory/recent for convenience."""
    return RedirectResponse(url="/observatory/recent")


# ---------------------------------------------------------------------------
# GET /recent
# ---------------------------------------------------------------------------


@router.get("/recent", summary="Last N audit events, newest first")
async def observatory_recent(
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return"),
    category: Optional[str] = Query(None, description="Filter by EventCategory value"),
    severity: Optional[str] = Query(None, description="Filter by EventSeverity value"),
):
    obs = get_observatory()

    cat: Optional[EventCategory] = None
    if category:
        try:
            cat = EventCategory(category)
        except ValueError:
            valid = [c.value for c in EventCategory]
            return JSONResponse(
                {"error": f"Unknown category: {category!r}", "valid": valid},
                status_code=400,
            )

    sev: Optional[EventSeverity] = None
    if severity:
        try:
            sev = EventSeverity(severity)
        except ValueError:
            valid = [s.value for s in EventSeverity]
            return JSONResponse(
                {"error": f"Unknown severity: {severity!r}", "valid": valid},
                status_code=400,
            )

    # Fetch with optional category filter (Observatory.recent supports it)
    events: List[AuditEvent] = obs.recent(limit=limit * 4 if sev else limit, category=cat)

    # Apply severity filter client-side (Observatory.recent doesn't support it)
    if sev:
        events = [e for e in events if e.severity == sev]

    return [e.to_dict() for e in events[:limit]]


# ---------------------------------------------------------------------------
# GET /stats
# ---------------------------------------------------------------------------


@router.get("/stats", summary="Event counts by category, severity, and service")
async def observatory_stats():
    """
    Returns aggregate counters for the in-memory ring buffer, extended with
    a per-service breakdown not available from the base Observatory.stats().
    """
    obs = get_observatory()
    base = obs.stats()

    by_service: dict = {}
    for e in obs._buffer:  # noqa: SLF001 — intentional internal access
        by_service[e.service] = by_service.get(e.service, 0) + 1

    return {**base, "by_service": by_service}


# ---------------------------------------------------------------------------
# GET /search
# ---------------------------------------------------------------------------


@router.get("/search", summary="Full-text search through event messages and details")
async def observatory_search(
    q: Optional[str] = Query(None, description="Free-text substring to match"),
    actor: Optional[str] = Query(None, description="Exact actor filter"),
    event_type: Optional[str] = Query(None, description="event_type prefix filter"),
    service: Optional[str] = Query(None, description="Exact service name filter"),
    limit: int = Query(20, ge=1, le=200),
):
    """
    Search recent events.  If *q* is provided it is matched case-insensitively
    against event_type, actor, target, service, outcome, and metadata values.
    Other parameters provide additional exact/prefix filters.
    """
    obs = get_observatory()
    results: List[AuditEvent] = []

    q_lower = q.lower() if q else None

    for e in reversed(list(obs._buffer)):  # noqa: SLF001
        # Prefix / exact filters
        if actor and e.actor != actor:
            continue
        if event_type and not e.event_type.startswith(event_type):
            continue
        if service and e.service != service:
            continue

        # Full-text match
        if q_lower:
            haystack = " ".join(
                filter(
                    None,
                    [
                        e.event_type,
                        e.actor or "",
                        e.target or "",
                        e.service,
                        e.outcome,
                        json.dumps(e.metadata),
                    ],
                )
            ).lower()
            if q_lower not in haystack:
                continue

        results.append(e)
        if len(results) >= limit:
            break

    return [e.to_dict() for e in results]


# ---------------------------------------------------------------------------
# GET /export
# ---------------------------------------------------------------------------


@router.get("/export", summary="Export events as JSON or CSV")
async def observatory_export(
    from_dt: Optional[str] = Query(None, alias="from", description="ISO datetime lower bound"),
    to_dt: Optional[str] = Query(None, alias="to", description="ISO datetime upper bound"),
    format: str = Query("json", regex="^(json|csv)$", description="Output format: json or csv"),
):
    obs = get_observatory()
    ts_from = _parse_dt(from_dt, "from")
    ts_to = _parse_dt(to_dt, "to")

    events: List[AuditEvent] = []
    for e in obs._buffer:  # noqa: SLF001
        if ts_from is not None and e.timestamp < ts_from:
            continue
        if ts_to is not None and e.timestamp > ts_to:
            continue
        events.append(e)

    dicts = [e.to_dict() for e in events]

    if format == "csv":
        if not dicts:
            return PlainTextResponse("", media_type="text/csv")
        columns = list(dicts[0].keys())
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in dicts:
            # Flatten metadata to a JSON string so CSV doesn't choke on dicts
            flat = {
                k: (json.dumps(v) if isinstance(v, (dict, list)) else v) for k, v in row.items()
            }
            writer.writerow(flat)
        content = buf.getvalue()
        return PlainTextResponse(
            content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=observatory_export.csv"},
        )

    return JSONResponse(
        {"count": len(dicts), "events": dicts},
        headers={"Content-Disposition": "attachment; filename=observatory_export.json"},
    )


# ---------------------------------------------------------------------------
# GET /sse  — Server-Sent Events live stream
# ---------------------------------------------------------------------------


@router.get("/sse", summary="Real-time AuditEvent stream (Server-Sent Events)")
async def observatory_sse(request: Request):
    """
    Push new AuditEvents to connected clients in real-time.
    Sends a 10-event backlog on connect, then streams live events.
    Sends a keepalive comment every 15 s so proxies don't close the connection.
    """
    obs = get_observatory()
    queue: asyncio.Queue = obs.subscribe(maxsize=200)

    async def event_stream():
        try:
            # Backlog — give the client initial data immediately
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
                    # Keepalive comment — keeps Nginx/Traefik from closing idle connections
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            logger.debug("SSE client disconnected")
        finally:
            obs.unsubscribe(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # disable Nginx proxy buffering
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# POST /events  — ingest an AuditEvent (service-to-service)
# ---------------------------------------------------------------------------


@router.post("/events", status_code=202, summary="Ingest an AuditEvent (internal)")
async def observatory_ingest(request: Request):
    """
    Internal endpoint — emit an event from any Trancendos service via HTTP.
    Accepts a JSON body matching the AuditEvent field names.
    """
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    event_type = body.get("event_type")
    if not event_type:
        return JSONResponse({"error": "'event_type' is required"}, status_code=422)

    # Coerce enum values gracefully
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
        actor_ip=body.get("actor_ip"),
        session_id=body.get("session_id"),
    )
    logger.debug(
        "observatory.ingest via HTTP: %s",
        sanitize_for_log(event_type),
    )  # codeql[py/cleartext-logging]
    return {"id": event.id, "timestamp": event.timestamp, "accepted": True}


# ---------------------------------------------------------------------------
# GET /verify  — chain integrity placeholder
# ---------------------------------------------------------------------------


@router.get("/verify", summary="Chain integrity check (placeholder)")
async def observatory_verify():
    """
    Placeholder for future Merkle-chain or hash-chain integrity verification.
    The current ring buffer implementation does not maintain a cryptographic
    chain; this endpoint exists to satisfy API contracts and future tooling.
    """
    obs = get_observatory()
    total = len(obs._buffer)  # noqa: SLF001
    return {
        "status": "ok",
        "message": "Ring buffer has no cryptographic chain — verification not applicable",
        "event_count": total,
        "future": "Merkle-chain audit log is planned for The Basement integration",
    }


# ---------------------------------------------------------------------------
# GET /health  — self health
# ---------------------------------------------------------------------------


@router.get("/health", summary="Observatory health")
async def observatory_health():
    obs = get_observatory()
    buf = list(obs._buffer)  # noqa: SLF001
    buffer_size = len(buf)

    oldest_at: Optional[str] = None
    newest_at: Optional[str] = None
    if buf:
        oldest_at = datetime.fromtimestamp(buf[0].timestamp, tz=timezone.utc).isoformat()
        newest_at = datetime.fromtimestamp(buf[-1].timestamp, tz=timezone.utc).isoformat()

    return {
        "status": "ok",
        "service": "The Observatory",
        "lead_ai": "Norman Hawkins",
        "buffer_size": buffer_size,
        "buffer_capacity": obs._buffer.maxlen,  # noqa: SLF001
        "subscribers": len(obs._subscribers),  # noqa: SLF001
        "oldest_event_at": oldest_at,
        "newest_event_at": newest_at,
    }
