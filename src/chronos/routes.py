# src/chronos/routes.py
# ChronosSphere — HTTP routes for time and schedule management.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.chronos.scheduler import ScheduleStatus, ScheduleType, get_chronos

router = APIRouter(prefix="/chronos", tags=["chronossphere"])


@router.get("/status")
async def chronos_status() -> Dict[str, Any]:
    return get_chronos().stats()


# ── Scheduled tasks ───────────────────────────────────────────────────────────


@router.post("/tasks")
async def create_task(body: Dict[str, Any] = Body(...)) -> Response:
    name = body.get("name")
    raw_type = body.get("schedule_type", "once")
    if not name:
        return JSONResponse({"error": "name is required"}, status_code=400)
    try:
        stype = ScheduleType(raw_type)
    except ValueError:
        valid = [t.value for t in ScheduleType]
        return JSONResponse({"error": f"Unknown schedule_type. Valid: {valid}"}, status_code=400)
    task = get_chronos().create_task(
        name=name,
        schedule_type=stype,
        cron_expression=body.get("cron_expression"),
        interval_seconds=body.get("interval_seconds"),
        fire_at=body.get("fire_at"),
        workflow_id=body.get("workflow_id"),
        metadata=body.get("metadata"),
    )
    return task.to_dict()


@router.get("/tasks")
async def list_tasks(status: Optional[str] = Query(None)) -> Response:
    ss = None
    if status:
        try:
            ss = ScheduleStatus(status)
        except ValueError:
            return JSONResponse({"error": "Unknown status"}, status_code=400)
    return [t.to_dict() for t in get_chronos().list_tasks(status=ss)]


@router.get("/tasks/{task_id}")
async def get_task(task_id: str = Path(...)) -> Response:
    task = get_chronos().get_task(task_id)
    if not task:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return task.to_dict()


@router.post("/tasks/{task_id}/pause")
async def pause_task(task_id: str = Path(...)) -> Response:
    ok = get_chronos().pause_task(task_id)
    if not ok:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return {"paused": task_id}


@router.post("/tasks/{task_id}/resume")
async def resume_task(task_id: str = Path(...)) -> Response:
    ok = get_chronos().resume_task(task_id)
    if not ok:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return {"resumed": task_id}


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str = Path(...)) -> Response:
    ok = get_chronos().delete_task(task_id)
    if not ok:
        return JSONResponse({"error": "Task not found"}, status_code=404)
    return {"deleted": task_id}


# ── Calendar events ───────────────────────────────────────────────────────────


@router.post("/events")
async def create_event(body: Dict[str, Any] = Body(...)) -> Response:
    user_id = body.get("user_id")
    title = body.get("title")
    start_ts = body.get("start_ts")
    end_ts = body.get("end_ts")
    if not all([user_id, title, start_ts, end_ts]):
        return JSONResponse(
            {"error": "user_id, title, start_ts, end_ts are required"}, status_code=400
        )
    event = get_chronos().create_event(
        user_id=user_id,  # type: ignore[arg-type]
        title=title,  # type: ignore[arg-type]
        start_ts=float(start_ts),  # type: ignore[arg-type]
        end_ts=float(end_ts),  # type: ignore[arg-type]
        description=body.get("description", ""),
        timezone=body.get("timezone", "UTC"),
        location=body.get("location"),
        attendees=body.get("attendees", []),
        metadata=body.get("metadata", {}),
    )
    return event.to_dict()


@router.get("/events")
async def list_events(
    user_id: str = Query(...),
    from_ts: Optional[float] = Query(None),
    to_ts: Optional[float] = Query(None),
) -> list:
    return [
        e.to_dict()
        for e in get_chronos().list_events(user_id=user_id, from_ts=from_ts, to_ts=to_ts)
    ]


@router.get("/events/{event_id}")
async def get_event(event_id: str = Path(...)) -> Response:
    event = get_chronos().get_event(event_id)
    if not event:
        return JSONResponse({"error": "Event not found"}, status_code=404)
    return event.to_dict()


@router.delete("/events/{event_id}")
async def delete_event(event_id: str = Path(...)) -> Response:
    ok = get_chronos().delete_event(event_id)
    if not ok:
        return JSONResponse({"error": "Event not found"}, status_code=404)
    return {"deleted": event_id}