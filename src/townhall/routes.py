# src/townhall/routes.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, HTTPException, Query
from pydantic import BaseModel, Field

from src.townhall.agile import KanbanColumn, get_kanban_service
from src.townhall.documents import get_template, list_templates, render_template
from src.townhall.framework_registry import get_framework_registry
from src.townhall.governance import ComplianceResult, get_townhall
from src.townhall.itsm import IncidentPriority, IncidentStatus, get_itsm_service
from src.townhall.rooms import RoomKind, get_room_manager

router = APIRouter(prefix="/townhall", tags=["townhall"])


class RoomOpenRequest(BaseModel):
    title: str
    chair: str | None = None
    agenda: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class KanbanCardRequest(BaseModel):
    title: str
    column: str = "backlog"
    description: str = ""
    assignee: str | None = None


class KanbanMoveRequest(BaseModel):
    column: str


class IncidentCreateRequest(BaseModel):
    title: str
    description: str
    priority: str = "p3"
    service: str = "tranc3-backend"


class DocumentRenderRequest(BaseModel):
    variables: Dict[str, str] = Field(default_factory=dict)


@router.get("/status")
async def townhall_status():
    th = get_townhall()
    kanban = get_kanban_service()
    itsm = get_itsm_service()
    rooms = get_room_manager()
    return {
        **th.status(),
        "kanban_boards": len(kanban.list_boards()),
        "open_incidents": len(itsm.list_incidents(open_only=True)),
        "active_room_sessions": len(rooms.list_sessions(active_only=True)),
    }


@router.get("/policies")
async def list_policies(active_only: bool = Query(True)):
    th = get_townhall()
    policies = th.active_policies() if active_only else list(th._policies.values())
    return [
        {
            "id": p.id,
            "name": p.name,
            "framework": p.framework,
            "status": p.status.value,
            "score": p.score,
            "articles": p.articles,
            "description": p.description,
        }
        for p in policies
    ]


@router.post("/check")
async def compliance_check(
    context: Dict[str, Any] = Body(...),
    policy_ids: Optional[List[str]] = Body(None),
    actor: Optional[str] = Body(None),
):
    results = get_townhall().check(context, policy_ids=policy_ids, actor=actor)
    overall = ComplianceResult.PASS
    for r in results.values():
        if r == ComplianceResult.FAIL:
            overall = ComplianceResult.FAIL
            break
        if r == ComplianceResult.WARN:
            overall = ComplianceResult.WARN
    return {
        "overall": overall.value,
        "results": {k: v.value for k, v in results.items()},
    }


@router.get("/frameworks")
async def list_frameworks():
    return get_framework_registry().to_dict()


@router.get("/frameworks/{framework_id}")
async def get_framework(framework_id: str):
    entry = get_framework_registry().get(framework_id)
    if not entry:
        raise HTTPException(404, "Framework not found")
    policy = get_townhall().get(framework_id)
    return {
        **entry.to_dict(),
        "policy_score": policy.score if policy else None,
        "policy_status": policy.status.value if policy else None,
    }


@router.get("/rooms")
async def list_room_definitions():
    reg = get_framework_registry()
    sessions = get_room_manager().list_sessions(active_only=True)
    return {
        "definitions": [r.to_dict() for r in reg.rooms],
        "active_sessions": [s.to_dict() for s in sessions],
    }


@router.post("/rooms/{room_id}/sessions")
async def open_room_session(room_id: str, body: RoomOpenRequest):
    try:
        kind = RoomKind(room_id)
    except ValueError as exc:
        raise HTTPException(400, f"room_id must be one of: {[r.value for r in RoomKind]}") from exc
    session = get_room_manager().open_session(
        kind,
        body.title,
        chair=body.chair,
        agenda=body.agenda,
        metadata=body.metadata,
    )
    return session.to_dict()


@router.post("/rooms/sessions/{session_id}/end")
async def end_room_session(session_id: str):
    session = get_room_manager().end_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found or already ended")
    return session.to_dict()


@router.get("/documents/templates")
async def document_templates(category: str | None = Query(None)):
    return {"templates": list_templates(category=category)}


@router.get("/documents/templates/{template_id}")
async def document_template_detail(template_id: str):
    tpl = get_template(template_id)
    if not tpl:
        raise HTTPException(404, "Template not found")
    return {
        "id": tpl.id,
        "title": tpl.title,
        "category": tpl.category,
        "framework_id": tpl.framework_id,
        "available": tpl.path().is_file(),
    }


@router.post("/documents/templates/{template_id}/render")
async def document_render(template_id: str, body: DocumentRenderRequest | None = None):
    try:
        text = render_template(template_id, (body.variables if body else None))
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"template_id": template_id, "content": text}


@router.get("/kanban/boards")
async def kanban_list_boards():
    return [b.to_dict() for b in get_kanban_service().list_boards()]


@router.get("/kanban/boards/{board_id}")
async def kanban_board(board_id: str):
    board = get_kanban_service().get_board(board_id)
    if not board:
        raise HTTPException(404, "Board not found")
    return board.to_dict()


@router.post("/kanban/boards")
async def kanban_create_board(name: str = Body(..., embed=True)):
    board = get_kanban_service().create_board(name)
    return board.to_dict()


@router.post("/kanban/boards/{board_id}/cards")
async def kanban_add_card(board_id: str, body: KanbanCardRequest):
    board = get_kanban_service().get_board(board_id)
    if not board:
        raise HTTPException(404, "Board not found")
    try:
        col = KanbanColumn(body.column)
    except ValueError as exc:
        raise HTTPException(400, "Invalid column") from exc
    card = board.add_card(
        body.title,
        column=col,
        description=body.description,
        assignee=body.assignee,
    )
    return card.to_dict()


@router.patch("/kanban/boards/{board_id}/cards/{card_id}")
async def kanban_move_card(board_id: str, card_id: str, body: KanbanMoveRequest):
    board = get_kanban_service().get_board(board_id)
    if not board:
        raise HTTPException(404, "Board not found")
    try:
        col = KanbanColumn(body.column)
    except ValueError as exc:
        raise HTTPException(400, "Invalid column") from exc
    card = board.move_card(card_id, col)
    if not card:
        raise HTTPException(404, "Card not found")
    return card.to_dict()


@router.get("/itsm/incidents")
async def itsm_incidents(open_only: bool = Query(False)):
    return [i.to_dict() for i in get_itsm_service().list_incidents(open_only=open_only)]


@router.post("/itsm/incidents")
async def itsm_create_incident(body: IncidentCreateRequest):
    try:
        pri = IncidentPriority(body.priority.lower())
    except ValueError as exc:
        raise HTTPException(400, "priority must be p1–p4") from exc
    inc = get_itsm_service().create_incident(
        body.title,
        body.description,
        priority=pri,
        service=body.service,
    )
    return inc.to_dict()


@router.patch("/itsm/incidents/{incident_id}")
async def itsm_update_incident(incident_id: str, status: str = Body(..., embed=True)):
    try:
        st = IncidentStatus(status.lower())
    except ValueError as exc:
        raise HTTPException(400, "Invalid status") from exc
    inc = get_itsm_service().update_incident_status(incident_id, st)
    if not inc:
        raise HTTPException(404, "Incident not found")
    return inc.to_dict()
