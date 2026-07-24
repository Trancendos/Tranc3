# src/admin_os/routes.py
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

from auth import get_current_user
from Dimensional.sanitize import sanitize_for_log
from src.admin_os import backups, cells, domain_model, events, fabric, files_manager, system_viewer

logger = logging.getLogger("tranc3.admin_os")


def _require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """Admin OS exposes filesystem, backup, and system-internals access —
    every route requires an authenticated admin, not just mutations."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for Admin OS access")
    return current_user


router = APIRouter(prefix="/admin-os", tags=["admin-os"], dependencies=[Depends(_require_admin)])

_FEATURES = ["domain-model", "system", "events", "files", "backups", "cells", "fabric"]


class SpawnCellRequest(BaseModel):
    cell_type: str
    command: list[str]
    port: Optional[int] = None
    warmup_s: float = 5.0
    max_age_s: float = 0.0

    @field_validator("command")
    @classmethod
    def _command_not_empty(cls, v: list[str]) -> list[str]:
        if not v or not any(arg.strip() for arg in v):
            raise ValueError("command must contain at least one non-blank argument")
        return v

    @field_validator("warmup_s")
    @classmethod
    def _warmup_non_negative(cls, v: float) -> float:
        if v < 0:
            raise ValueError("warmup_s must be non-negative")
        return v


@router.get("/status")
async def admin_os_status():
    return {"service": "Infinity Admin OS", "features": _FEATURES}


@router.get("/domain-model")
async def get_domain_model(pillar: Optional[str] = Query(None)):
    return {
        "summary": domain_model.domain_model_summary(),
        "entities": domain_model.list_entities(pillar=pillar),
    }


@router.get("/domain-model/{pid}")
async def get_domain_model_entity(pid: str):
    detail = domain_model.get_entity_detail(pid)
    if not detail:
        return JSONResponse({"error": f"Unknown entity: {pid}"}, status_code=404)
    return detail


@router.get("/domain-model-graph")
async def get_domain_model_graph():
    return domain_model.graph_nodes_edges()


@router.get("/system")
async def get_system_snapshot():
    return system_viewer.system_snapshot()


@router.get("/events")
async def get_events(
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = Query(None),
    severity: Optional[str] = Query(None),
    actor: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
):
    return events.list_events(
        limit=limit,
        category=category,
        severity=severity,
        actor=actor,
        event_type=event_type,
    )


@router.get("/files")
async def list_files(path: str = Query("")):
    try:
        return files_manager.list_dir(path)
    except PermissionError:
        logger.info("admin-os /files: permission denied", exc_info=True)
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    except (FileNotFoundError, NotADirectoryError):
        logger.info("admin-os /files: not found", exc_info=True)
        return JSONResponse({"error": "Not found"}, status_code=404)


@router.get("/files/content")
async def read_file(path: str = Query(...)):
    try:
        return files_manager.read_file(path)
    except PermissionError:
        logger.info("admin-os /files/content: permission denied", exc_info=True)
        return JSONResponse({"error": "Forbidden"}, status_code=403)
    except FileNotFoundError:
        logger.info("admin-os /files/content: not found", exc_info=True)
        return JSONResponse({"error": "Not found"}, status_code=404)


@router.get("/backups")
async def get_backups(limit: int = Query(30, ge=1, le=200)):
    return {"config": backups.backup_config(), "backups": backups.list_backups(limit=limit)}


@router.get("/cells")
async def get_cells(state: Optional[str] = Query(None)):
    try:
        return cells.list_cells(state=state)
    except ValueError:
        return JSONResponse({"error": f"Unknown cell state: {state}"}, status_code=400)


@router.post("/cells")
async def post_cell(body: SpawnCellRequest):
    try:
        return cells.spawn_cell(
            cell_type=body.cell_type,
            command=body.command,
            port=body.port,
            warmup_s=body.warmup_s,
            max_age_s=body.max_age_s,
        )
    except RuntimeError as exc:
        logger.info("admin-os /cells spawn rejected: %s", sanitize_for_log(exc))
        return JSONResponse({"error": "Cell capacity limit reached"}, status_code=409)
    except (OSError, ValueError) as exc:
        logger.warning("admin-os /cells spawn failed to launch: %s", sanitize_for_log(exc))
        return JSONResponse({"error": "Failed to launch cell process"}, status_code=400)


@router.post("/cells/{cell_id}/apoptosis")
async def post_cell_apoptosis(cell_id: str):
    try:
        return await run_in_threadpool(cells.apoptosis_cell, cell_id)
    except KeyError:
        return JSONResponse({"error": f"Unknown cell: {cell_id}"}, status_code=404)


@router.post("/cells/{cell_id}/replicate")
async def post_cell_replicate(cell_id: str):
    try:
        return cells.replicate_cell(cell_id)
    except KeyError:
        return JSONResponse({"error": f"Unknown cell: {cell_id}"}, status_code=404)
    except RuntimeError as exc:
        logger.info("admin-os /cells replicate rejected: %s", sanitize_for_log(exc))
        return JSONResponse({"error": "Cell is not eligible for replication"}, status_code=409)


@router.get("/fabric")
async def get_fabric_status():
    return fabric.status()
