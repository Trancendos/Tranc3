# src/citadel/routes.py
# The Citadel — HTTP routes for the Trancendos DevOps hub.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.citadel.devops_hub import DeployStatus, DeployTarget, ServiceHealthStatus, get_citadel

router = APIRouter(prefix="/citadel", tags=["the-citadel"])


@router.get("/status")
async def citadel_status() -> Dict[str, Any]:
    return get_citadel().stats()


@router.get("/inventory")
async def inventory() -> list:
    return get_citadel().inventory()


@router.post("/deploys")
async def record_deploy(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    raw_target = body.get("target")
    version = body.get("version", "unknown")
    if not raw_target:
        return JSONResponse({"error": "target is required"}, status_code=400)
    try:
        target = DeployTarget(raw_target)
    except ValueError:
        valid = [t.value for t in DeployTarget]
        return JSONResponse({"error": f"Unknown target. Valid: {valid}"}, status_code=400)
    record = get_citadel().record_deploy(
        target=target,
        version=version,
        triggered_by=body.get("triggered_by", "forgejo"),
        status=DeployStatus(body.get("status", "pending")),
    )
    return record.to_dict()


@router.get("/deploys")
async def list_deploys(target: Optional[str] = Query(None)) -> list:
    t = None
    if target:
        try:
            t = DeployTarget(target)
        except ValueError:
            return JSONResponse({"error": "Unknown target"}, status_code=400)
    return [d.to_dict() for d in get_citadel().list_deploys(target=t)]


@router.patch("/deploys/{deploy_id}")
async def update_deploy(
    deploy_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    raw_status = body.get("status")
    if not raw_status:
        return JSONResponse({"error": "status is required"}, status_code=400)
    try:
        status = DeployStatus(raw_status)
    except ValueError:
        valid = [s.value for s in DeployStatus]
        return JSONResponse({"error": f"Unknown status. Valid: {valid}"}, status_code=400)
    record = get_citadel().update_deploy(deploy_id, status=status, error=body.get("error"))
    if not record:
        return JSONResponse({"error": "Deploy not found"}, status_code=404)
    return record.to_dict()


@router.patch("/health/{service_name}")
async def update_health(
    service_name: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    raw_status = body.get("status", "unknown")
    try:
        status = ServiceHealthStatus(raw_status)
    except ValueError:
        valid = [s.value for s in ServiceHealthStatus]
        return JSONResponse({"error": f"Unknown health status. Valid: {valid}"}, status_code=400)
    get_citadel().update_health(service_name, status)
    return {"updated": service_name, "health": raw_status}
