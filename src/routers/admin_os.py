"""Infinity Admin OS API — domain model, files, backups, system, events."""

from __future__ import annotations

from Dimensional.error_handlers import safe_error_detail
from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from src.admin_os import backups, domain_model, events, files_manager, system_viewer
from src.admin_os.db import upsert_override
from src.entities.override_store import invalidate_override_cache
from src.entities.platform import get_entity_by_pid
from src.observability.observatory import EventCategory, EventSeverity, observe

router = APIRouter(prefix="/admin-os", tags=["admin-os"])


class EntityRenameBody(BaseModel):
    new_name: str = Field(..., min_length=1, max_length=120)
    reason: str | None = Field(None, max_length=500)


class FileWriteBody(BaseModel):
    content: str
    create: bool = True


class BackupConfigBody(BaseModel):
    auto_backup_enabled: bool | None = None
    auto_backup_hours: float | None = Field(None, ge=1, le=168)


@router.get("/status")
async def admin_os_status():
    return {
        "service": "infinity-admin-os",
        "location": "Infinity Admin OS",
        "features": [
            "domain-model",
            "files",
            "backups",
            "system-viewer",
            "events",
        ],
        "domain": domain_model.domain_model_summary(),
        "backup": backups.backup_config(),
    }


@router.get("/domain-model")
async def get_domain_model():
    return {
        "summary": domain_model.domain_model_summary(),
        "entities": domain_model.list_entities(),
    }


@router.get("/domain-model/graph")
async def get_domain_graph():
    return domain_model.graph_nodes_edges()


@router.get("/domain-model/entities/{pid}")
async def get_domain_entity(pid: str):
    detail = domain_model.get_entity_detail(pid.upper())
    if not detail:
        raise HTTPException(404, f"Entity {pid} not found")
    return detail


@router.patch("/domain-model/entities/{pid}/location")
async def patch_entity_location(pid: str, body: EntityRenameBody):
    entity = get_entity_by_pid(pid.upper())
    if not entity:
        raise HTTPException(404, "Entity not found")
    upsert_override(pid.upper(), "location", None, entity.location, body.new_name)
    observe(
        "admin_os.entity.rename",
        actor="admin-os",
        target=f"entity:{pid}",
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.INFO,
        service="admin-os",
        metadata={"field": "location", "new_name": body.new_name, "reason": body.reason},
    )
    invalidate_override_cache()
    return domain_model.get_entity_detail(pid.upper())


@router.patch("/domain-model/entities/{pid}/lead-ai")
async def patch_entity_lead_ai(pid: str, body: EntityRenameBody):
    entity = get_entity_by_pid(pid.upper())
    if not entity:
        raise HTTPException(404, "Entity not found")
    upsert_override(pid.upper(), "lead_ai", None, entity.lead_ai, body.new_name)
    observe(
        "admin_os.entity.rename",
        actor="admin-os",
        target=f"entity:{pid}",
        category=EventCategory.GOVERNANCE,
        severity=EventSeverity.INFO,
        service="admin-os",
        metadata={"field": "lead_ai", "new_name": body.new_name},
    )
    invalidate_override_cache()
    return domain_model.get_entity_detail(pid.upper())


@router.get("/files")
async def files_list(path: str = Query("", description="Relative path under workspace")):
    try:
        return files_manager.list_dir(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, safe_error_detail(exc, 404)) from exc
    except (PermissionError, NotADirectoryError) as exc:
        raise HTTPException(400, safe_error_detail(exc, 400)) from exc


@router.get("/files/read")
async def files_read(path: str = Query(...)):
    try:
        return files_manager.read_file(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, safe_error_detail(exc, 404)) from exc
    except ValueError as exc:
        raise HTTPException(413, safe_error_detail(exc, 413)) from exc


@router.put("/files/write")
async def files_write(path: str = Query(...), body: FileWriteBody = Body(...)):
    try:
        return files_manager.write_file(path, body.content, create=body.create)
    except FileNotFoundError as exc:
        raise HTTPException(404, safe_error_detail(exc, 404)) from exc
    except IsADirectoryError as exc:
        raise HTTPException(400, safe_error_detail(exc, 400)) from exc


@router.post("/files/mkdir")
async def files_mkdir(path: str = Query(...)):
    try:
        return files_manager.mkdir(path)
    except PermissionError as exc:
        raise HTTPException(403, safe_error_detail(exc, 403)) from exc


@router.delete("/files")
async def files_delete(path: str = Query(...)):
    try:
        return files_manager.delete_path(path)
    except FileNotFoundError as exc:
        raise HTTPException(404, safe_error_detail(exc, 404)) from exc
    except PermissionError as exc:
        raise HTTPException(403, safe_error_detail(exc, 403)) from exc


@router.get("/backups")
async def backups_list(limit: int = Query(30, ge=1, le=100)):
    return {"backups": backups.list_backups(limit), "config": backups.backup_config()}


@router.get("/backups/config")
async def backups_get_config():
    return backups.backup_config()


@router.put("/backups/config")
async def backups_put_config(body: BackupConfigBody):
    return backups.update_backup_config(
        enabled=body.auto_backup_enabled,
        hours=body.auto_backup_hours,
    )


@router.post("/backups/run")
async def backups_run_now():
    result = backups.run_backup(trigger="manual")
    observe(
        "admin_os.backup.completed",
        actor="admin-os",
        target=result["path"],
        category=EventCategory.SYSTEM,
        severity=EventSeverity.INFO,
        service="admin-os",
        metadata=result,
    )
    return result


@router.get("/system")
async def system_view():
    return system_viewer.system_snapshot()


@router.get("/events")
async def event_viewer(
    limit: int = Query(100, ge=1, le=500),
    category: str | None = None,
    severity: str | None = None,
    actor: str | None = None,
    event_type: str | None = None,
):
    return events.list_events(
        limit=limit,
        category=category,
        severity=severity,
        actor=actor,
        event_type=event_type,
    )


@router.get("/events/stream")
async def event_stream_redirect():
    """SSE lives on The Observatory — redirect for Admin OS Event Viewer."""
    return RedirectResponse(url="/observatory/sse", status_code=307)


# Legacy alias: Admin OS JS used port 8044 — proxy entity list on main API
@router.get("/entities")
async def entities_alias():
    return {"entities": domain_model.list_entities(), "total": len(domain_model.list_entities())}
