# src/citadel/routes.py
# The Citadel — HTTP routes for the Trancendos DevOps hub.

from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Header, Path, Query, Request
from fastapi.responses import JSONResponse

from Dimensional.sanitize import sanitize_for_log
from src.citadel.devops_hub import DeployStatus, DeployTarget, ServiceHealthStatus, get_citadel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/citadel", tags=["the-citadel"])


@router.get("/status")
async def citadel_status() -> Dict[str, Any]:
    return get_citadel().stats()


@router.get("/inventory")
async def inventory() -> list:
    return get_citadel().inventory()


@router.post("/deploys")
async def record_deploy(body: Dict[str, Any] = Body(...)) -> Response:
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
async def list_deploys(target: Optional[str] = Query(None)) -> Response:
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
) -> Response:
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
) -> Response:
    raw_status = body.get("status", "unknown")
    try:
        status = ServiceHealthStatus(raw_status)
    except ValueError:
        valid = [s.value for s in ServiceHealthStatus]
        return JSONResponse({"error": f"Unknown health status. Valid: {valid}"}, status_code=400)
    get_citadel().update_health(service_name, status)
    return {"updated": service_name, "health": raw_status}


@router.post("/webhooks/forgejo")
async def forgejo_webhook(
    request: Request,
    x_forgejo_signature: Optional[str] = Header(None, alias="X-Forgejo-Signature-256"),
) -> Response:
    """
    Receive push/workflow events from The Workshop (Forgejo).
    Automatically records deploy state changes when CI pipelines complete.
    Configure in Forgejo: Settings → Webhooks → Add Webhook → Gitea-compatible
      URL: https://tranc3-backend.fly.dev/citadel/webhooks/forgejo
      Secret: CITADEL_WEBHOOK_SECRET env var
    """
    raw_body = await request.body()

    # Verify HMAC-SHA256 signature when secret is configured
    secret = os.environ.get("CITADEL_WEBHOOK_SECRET", "")
    if secret and x_forgejo_signature:
        mac = hmac.new(secret.encode(), raw_body, hashlib.sha256)
        expected = "sha256=" + mac.hexdigest()
        if not hmac.compare_digest(expected, x_forgejo_signature):
            return JSONResponse({"error": "invalid signature"}, status_code=401)

    try:
        payload: Dict[str, Any] = await request.json()
    except Exception:
        return JSONResponse({"error": "invalid JSON"}, status_code=400)

    event = request.headers.get("X-Gitea-Event", request.headers.get("X-Forgejo-Event", "unknown"))
    ref = payload.get("ref", "")
    sender = payload.get("pusher", {}).get(
        "login", payload.get("sender", {}).get("login", "forgejo")
    )

    logger.info(
        "citadel: forgejo webhook event=%s ref=%s sender=%s",
        sanitize_for_log(event),
        sanitize_for_log(ref),
        sanitize_for_log(sender),
    )  # codeql[py/cleartext-logging]

    # Map workflow_run / push on main branch → auto record deploy
    if event in ("workflow_run", "push") and ("main" in ref or "master" in ref):
        repo_name = payload.get("repository", {}).get("name", "")
        target_map = {
            "Tranc3": DeployTarget.BACKEND,
            "tranc3-backend": DeployTarget.BACKEND,
            "tranc3-bots": DeployTarget.BOTS,
        }
        target = target_map.get(repo_name)
        if target:
            version = payload.get("after", "unknown")[:8]
            status = DeployStatus.IN_PROGRESS if event == "push" else DeployStatus.SUCCESS
            record = get_citadel().record_deploy(
                target=target, version=version, triggered_by=sender, status=status
            )
            return {"accepted": True, "deploy_id": record.id, "target": target.value}

    return {"accepted": True, "event": event, "action": "logged"}