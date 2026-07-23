# src/admin_os/routes.py
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from src.admin_os import backups, domain_model, events, files_manager, system_viewer

logger = logging.getLogger("tranc3.admin_os")

router = APIRouter(prefix="/admin-os", tags=["admin-os"])

_FEATURES = ["domain-model", "system", "events", "files", "backups"]


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
    except (FileNotFoundError, NotADirectoryError, PermissionError):
        logger.info("admin-os /files: not found or not permitted", exc_info=True)
        return JSONResponse({"error": "Not found"}, status_code=404)


@router.get("/files/content")
async def read_file(path: str = Query(...)):
    try:
        return files_manager.read_file(path)
    except (FileNotFoundError, PermissionError):
        logger.info("admin-os /files/content: not found or not permitted", exc_info=True)
        return JSONResponse({"error": "Not found"}, status_code=404)


@router.get("/backups")
async def get_backups(limit: int = Query(30, ge=1, le=200)):
    return {"config": backups.backup_config(), "backups": backups.list_backups(limit=limit)}
