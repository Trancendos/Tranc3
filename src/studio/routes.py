# src/studio/routes.py
# The Studio — HTTP routes for the Trancendos creativity hub.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.studio.hub import StudioServiceType, get_studio

router = APIRouter(prefix="/studio", tags=["the-studio"])


@router.get("/status")
async def studio_status() -> Dict[str, Any]:
    return get_studio().stats()


@router.get("/capabilities")
async def capabilities() -> Dict[str, Any]:
    return get_studio().capabilities()


@router.post("/jobs")
async def submit_job(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    raw_service = body.get("service", "imaginarium")
    try:
        service = StudioServiceType(raw_service)
    except ValueError:
        valid = [s.value for s in StudioServiceType]
        return JSONResponse({"error": f"Unknown service. Valid: {valid}"}, status_code=400)
    job = get_studio().submit_job(service=service, payload=body.get("payload", {}))
    return job.to_dict()


@router.get("/jobs")
async def list_jobs(
    service: Optional[str] = Query(None),
) -> list:
    svc = None
    if service:
        try:
            svc = StudioServiceType(service)
        except ValueError:
            return JSONResponse({"error": "Unknown service"}, status_code=400)
    return [j.to_dict() for j in get_studio().list_jobs(service=svc)]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str = Path(...)) -> Dict[str, Any]:
    job = get_studio().get_job(job_id)
    if not job:
        return JSONResponse({"error": "Job not found"}, status_code=404)
    return job.to_dict()
