"""TranceFlow — FastAPI routes"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException, Query

import config
from database import TranceFlowDatabase
from models import (
    ExportRequest,
    ExportResponse,
    ProjectCreate,
    ProjectResponse,
    TranceFlowStatus,
)
from service import TranceFlowRouter


def _auth(x_internal_secret: Optional[str] = Header(default=None)) -> None:
    if not config.INTERNAL_SECRET:
        raise HTTPException(status_code=503, detail="Service auth not configured")
    if x_internal_secret != config.INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


def _make_tranceflow_router(db: TranceFlowDatabase, tf: TranceFlowRouter) -> APIRouter:
    router = APIRouter(prefix="/tranceflow", tags=["tranceflow"])

    @router.post("/projects", response_model=ProjectResponse, status_code=201)
    def create_project(
        req: ProjectCreate,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> ProjectResponse:
        _auth(_)
        return tf.create_project(req)

    @router.get("/projects", response_model=List[ProjectResponse])
    def list_projects(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> List[ProjectResponse]:
        _auth(_)
        return tf.list_projects(limit=limit, offset=offset)

    @router.get("/projects/{project_id}", response_model=ProjectResponse)
    def get_project(
        project_id: str,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> ProjectResponse:
        _auth(_)
        project = tf.get_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    @router.delete("/projects/{project_id}", status_code=204)
    def delete_project(
        project_id: str,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> None:
        _auth(_)
        if not tf.delete_project(project_id):
            raise HTTPException(status_code=404, detail="Project not found")

    @router.post("/export", response_model=ExportResponse, status_code=202)
    async def export_asset(
        req: ExportRequest,
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> ExportResponse:
        _auth(_)
        return await tf.export_asset(req)

    @router.get("/status", response_model=TranceFlowStatus)
    def get_status(
        _: Optional[str] = Header(default=None, alias="x-internal-secret"),
    ) -> TranceFlowStatus:
        _auth(_)
        return tf.status()

    return router
