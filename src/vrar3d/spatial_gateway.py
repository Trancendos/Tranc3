"""User-authenticated, fail-closed gateway for the standalone VRAR3D worker.

Browser Bearer tokens terminate at the platform API. The worker credential
is injected server-side only; legacy wellbeing routes remain independent.
"""

from __future__ import annotations

import os
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from src.auth.facade import get_current_user_dep

router = APIRouter(prefix="/spatial", tags=["VRAR3D spatial gateway"])


class SpatialSceneCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=120)
    scene_type: Literal["vr", "ar", "xr", "3d", "panorama", "spatial"] = "3d"
    description: str | None = Field(default=None, max_length=2000)


def _user_id(current_user: dict[str, Any]) -> str:
    value = str(current_user.get("sub") or current_user.get("id") or "").strip()
    if not value or value in ("anonymous", "None"):
        raise HTTPException(status_code=401, detail="Valid user identity required")
    return value


def _is_owned(scene: dict[str, Any], uid: str) -> bool:
    metadata = scene.get("metadata")
    return isinstance(metadata, dict) and metadata.get("owner_id") == uid


def _worker_settings() -> tuple[str, str]:
    """Permit only the private, fixed-port worker service target."""
    secret = os.environ.get("INTERNAL_SECRET", "").strip()
    if len(secret) < 32 or secret == "dev-secret":
        raise HTTPException(status_code=503, detail="VRAR3D gateway unavailable")
    value = os.environ.get("VRAR3D_WORKER_URL", "http://vrar3d:8060").strip()
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError as exc:
        raise ValueError("Invalid VRAR3D internal worker URL") from exc
    service_host = (
        host in {"vrar3d", "vrar3d.internal", "localhost"}
        or (host.startswith("vrar3d.") and host.endswith(".svc.cluster.local"))
        or host == "127.0.0.1"
    )
    if not service_host or parsed.scheme != "http" or port != 8060 or (
        parsed.path not in ("", "/") or parsed.query or parsed.fragment
        or parsed.username is not None or parsed.password is not None
    ):
        raise ValueError("Worker URL must target the private VRAR3D service on port 8060")
    return f"http://{host}:8060", secret


async def _worker_request(
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    params: dict[str, int] | None = None,
) -> Any:
    base, secret = _worker_settings()
    # Caller supplies only fixed paths or canonical UUIDs, never a full URL.
    try:
        async with httpx.AsyncClient(
            base_url=base, timeout=8.0, follow_redirects=False, trust_env=False,
        ) as client:
            response = await client.request(
                method, path, json=payload, params=params,
                headers={"X-Internal-Secret": secret},
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=502, detail="VRAR3D worker unavailable") from exc
    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Scene not found")
    if not 200 <= response.status_code < 300:
        raise HTTPException(status_code=502, detail="VRAR3D worker rejected request")
    if response.status_code == 204:
        return None
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Invalid VRAR3D worker response") from exc


@router.get("/scenes")
async def list_spatial_scenes(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict[str, Any] = Depends(get_current_user_dep),
) -> list[dict[str, Any]]:
    uid = _user_id(current_user)
    scenes = await _worker_request("GET", "/vrar3d/scenes", params={"limit": limit, "offset": offset})
    if not isinstance(scenes, list):
        raise HTTPException(status_code=502, detail="Invalid VRAR3D scene list")
    return [scene for scene in scenes if isinstance(scene, dict) and _is_owned(scene, uid)]


@router.post("/scenes", status_code=201)
async def create_spatial_scene(
    req: SpatialSceneCreate,
    current_user: dict[str, Any] = Depends(get_current_user_dep),
) -> dict[str, Any]:
    uid = _user_id(current_user)
    payload = {
        "name": req.name, "scene_type": req.scene_type, "description": req.description,
        "metadata": {"owner_id": uid, "source": "spatial_gateway"},
    }
    result = await _worker_request("POST", "/vrar3d/scenes", payload=payload)
    if not isinstance(result, dict) or not _is_owned(result, uid):
        raise HTTPException(status_code=502, detail="Invalid scene creation response")
    return result


@router.get("/scenes/{scene_id}")
async def get_spatial_scene(
    scene_id: str,
    current_user: dict[str, Any] = Depends(get_current_user_dep),
) -> dict[str, Any]:
    uid = _user_id(current_user)
    try:
        safe_id = str(UUID(scene_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Scene not found") from exc
    result = await _worker_request("GET", f"/vrar3d/scenes/{safe_id}")
    if not isinstance(result, dict) or not _is_owned(result, uid):
        raise HTTPException(status_code=404, detail="Scene not found")
    return result


@router.delete("/scenes/{scene_id}", status_code=204)
async def delete_spatial_scene(
    scene_id: str,
    current_user: dict[str, Any] = Depends(get_current_user_dep),
) -> None:
    # Fail closed: worker record ownership must be checked before deletion.
    await get_spatial_scene(scene_id, current_user)
    await _worker_request("DELETE", f"/vrar3d/scenes/{UUID(scene_id)}")
