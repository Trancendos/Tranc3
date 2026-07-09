"""VRAR3D — FastAPI routes"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from models import (
    AssetProcessRequest,
    AssetProcessResponse,
    SceneCreate,
    SceneResponse,
    VRARStatus,
)
from service import VRARRouter

import config
from database import VRARDatabase


def _auth(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    if not config.INTERNAL_SECRET:
        raise HTTPException(status_code=503, detail="Service auth not configured")
    if x_internal_secret != config.INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


def _make_vrar3d_router(db: VRARDatabase, vrar: VRARRouter) -> APIRouter:
    router = APIRouter(prefix="/vrar3d", tags=["vrar3d"])

    @router.post("/scenes", response_model=SceneResponse, status_code=201)
    def create_scene(req: SceneCreate, _: None = Header(default=None)) -> SceneResponse:
        _auth(_)
        return vrar.create_scene(req)

    @router.get("/scenes", response_model=List[SceneResponse])
    def list_scenes(
        scene_type: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> List[SceneResponse]:
        _auth(_)
        return vrar.list_scenes(scene_type=scene_type, limit=limit, offset=offset)

    @router.get("/scenes/{scene_id}", response_model=SceneResponse)
    def get_scene(
        scene_id: str,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> SceneResponse:
        _auth(_)
        scene = vrar.get_scene(scene_id)
        if scene is None:
            raise HTTPException(status_code=404, detail="Scene not found")
        return scene

    @router.delete("/scenes/{scene_id}", status_code=204)
    def delete_scene(
        scene_id: str,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> None:
        _auth(_)
        if not vrar.delete_scene(scene_id):
            raise HTTPException(status_code=404, detail="Scene not found")

    @router.post("/assets/process", response_model=AssetProcessResponse, status_code=202)
    async def process_asset(
        req: AssetProcessRequest,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> AssetProcessResponse:
        _auth(_)
        return await vrar.process_asset(req)

    @router.get("/status", response_model=VRARStatus)
    def get_status(
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> VRARStatus:
        _auth(_)
        return vrar.status()

    return router
