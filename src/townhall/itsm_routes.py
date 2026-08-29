"""HTTP routes for The Town Hall's ITSM records.

`src/townhall/itsm.py` had no callers at all — not in the Town Hall router, not
anywhere else in `src/`. An incident service nothing can reach is the same
defect class as a control that runs without acting: present, correct, and
connected to nothing.

Read routes are unauthenticated, matching `src/roles/routes.py` and
`src/deployment_modes/routes.py`. Writes require an authenticated admin.
Raising and resolving incidents changes what the platform believes is broken
and feeds the events other domains react to, so it is a governance action
rather than a per-user-owned resource. The sibling Town Hall routes carry no
auth dependency at all; that convention is not extended to new write
endpoints here.

Handlers are plain `def`. They call the synchronous SQLite-backed ItsmService
directly, and FastAPI runs sync handlers in a threadpool rather than on the
event loop.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from auth import get_current_user
from src.cmdb.blast_radius import DEFAULT_MAX_HOPS, blast_radius
from src.cmdb.identity import IdentityResolutionError
from src.townhall.cir import (
    ClosureBlocked,
    ImprovementKind,
    UnknownImprovementError,
    get_cir_service,
)
from src.townhall.itsm import (
    IncidentPriority,
    IncidentStatus,
    UnknownIncidentError,
    get_itsm_service,
    resolve_ownership,
)

router = APIRouter(prefix="/townhall/itsm", tags=["townhall-itsm"])


class CreateIncidentRequest(BaseModel):
    title: str = Field(min_length=1)
    description: str = ""
    priority: IncidentPriority = IncidentPriority.P3
    service: str = "tranc3-backend"


class UpdateIncidentStatusRequest(BaseModel):
    status: IncidentStatus


class EscalateIncidentRequest(BaseModel):
    reason: str = Field(min_length=1)


class RaiseImprovementRequest(BaseModel):
    title: str = Field(min_length=1)
    kind: ImprovementKind = ImprovementKind.PROCESS
    rationale: str = ""
    raised_by: str = Field(min_length=1)
    incident_id: Optional[str] = None


class AcceptAsRiskRequest(BaseModel):
    """Closing an incident with nothing to learn — attributably.

    `accepted_by` and `rationale` are required at the schema boundary as well
    as in the service, so the route cannot be the softer of the two.
    """

    accepted_by: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    title: str = ""


class CreateChangeRequest(BaseModel):
    title: str = Field(min_length=1)
    change_type: str = "normal"
    service: Optional[str] = None


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")


# ── reads ───────────────────────────────────────────────────────────────────


@router.get("/incidents")
def list_incidents(open_only: bool = Query(False)) -> List[Dict[str, Any]]:
    return [i.to_dict() for i in get_itsm_service().list_incidents(open_only=open_only)]


@router.get("/incidents/{incident_id}")
def get_incident(incident_id: str) -> Dict[str, Any]:
    try:
        return get_itsm_service().get_incident(incident_id).to_dict()
    except UnknownIncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/locations/{location}/incidents")
def incidents_for_location(location: str) -> List[Dict[str, Any]]:
    """What is currently wrong at one Location.

    The question the ITIL4-AILP architecture asks of every incident and could
    not answer before the CMDB identity spine existed.
    """
    return [i.to_dict() for i in get_itsm_service().incidents_for_location(location)]


@router.get("/ownership/{service}")
def ownership(service: str) -> Dict[str, Any]:
    """Who answers for a service, without raising an incident to find out.

    Returns `resolved: false` with a reason rather than guessing. A plausible
    but wrong owner is worse than none — it routes the page to somebody who is
    not on the hook.
    """
    return resolve_ownership(service).to_dict()


def _impact(identifier: str, max_hops: int) -> Dict[str, Any]:
    """Impact assessment for one service identifier.

    Answers `resolved: false` rather than 404 when the identifier is not in
    the CMDB, and never conflates that with a service that resolves but has
    no recorded dependants -- the payload's `unknown_rather_than_empty` is
    the flag for the second case. Both are "we do not know", and an incident
    prioritiser that reads either as a genuine zero downgrades a real P1.
    """
    try:
        radius = blast_radius(identifier, max_hops=max_hops)
    except IdentityResolutionError as exc:
        return {
            "identifier": identifier,
            "resolved": False,
            "unresolved_reason": str(exc),
            "caveat": (
                f"{identifier!r} is not a known ServiceID, PID, Location name "
                "or port, so no impact can be assessed. This is not a finding "
                "that its impact is nil."
            ),
        }
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"identifier": identifier, "resolved": True, **radius.to_dict()}


@router.get("/impact/{identifier}")
def impact(identifier: str, max_hops: int = Query(DEFAULT_MAX_HOPS, ge=1, le=10)) -> Dict[str, Any]:
    """What else breaks if this service does -- ITIL impact assessment.

    Reachable before raising anything, so a change can be assessed rather
    than only an incident explained after the fact.
    """
    return _impact(identifier, max_hops)


@router.get("/incidents/{incident_id}/impact")
def incident_impact(
    incident_id: str, max_hops: int = Query(DEFAULT_MAX_HOPS, ge=1, le=10)
) -> Dict[str, Any]:
    """The blast radius of the service this incident is about."""
    try:
        incident = get_itsm_service().get_incident(incident_id)
    except UnknownIncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"incident_id": incident.id, **_impact(incident.service, max_hops)}


@router.get("/changes")
def list_changes() -> List[Dict[str, Any]]:
    return [c.to_dict() for c in get_itsm_service().list_changes()]


# ── writes ──────────────────────────────────────────────────────────────────


@router.post("/incidents", status_code=201)
def create_incident(
    body: CreateIncidentRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    incident = get_itsm_service().create_incident(
        body.title,
        body.description,
        priority=body.priority,
        service=body.service,
    )
    return incident.to_dict()


@router.post("/incidents/{incident_id}/status")
def update_incident_status(
    incident_id: str,
    body: UpdateIncidentStatusRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        return get_itsm_service().update_incident_status(incident_id, body.status).to_dict()
    except UnknownIncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ClosureBlocked as exc:
        # 409, not 422: the request is well-formed and the incident is real.
        # What is missing is the learning, and the detail says how to supply it.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/escalate")
def escalate_incident(
    incident_id: str,
    body: EscalateIncidentRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        return get_itsm_service().escalate_incident(incident_id, reason=body.reason).to_dict()
    except UnknownIncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/changes", status_code=201)
def create_change(
    body: CreateChangeRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    change = get_itsm_service().create_change(body.title, body.change_type, service=body.service)
    return change.to_dict()


# ── continual improvement register ──────────────────────────────────────────


@router.get("/improvements")
def list_improvements(open_only: bool = Query(False)) -> List[Dict[str, Any]]:
    return [e.to_dict() for e in get_cir_service().list_entries(open_only=open_only)]


@router.get("/incidents/{incident_id}/improvements")
def improvements_for_incident(incident_id: str) -> List[Dict[str, Any]]:
    """What was learned from this incident — and whether it can be closed."""
    return [e.to_dict() for e in get_cir_service().entries_for_incident(incident_id)]


@router.get("/incidents/{incident_id}/closable")
def closable(incident_id: str) -> Dict[str, Any]:
    """Whether the CIR would let this incident close, and why not if it would not.

    Readable before attempting the transition, so the gate can be satisfied
    deliberately rather than discovered as a 409.
    """
    allowed, reason = get_cir_service().may_close(incident_id)
    return {"incident_id": incident_id, "closable": allowed, "reason": reason}


@router.post("/improvements", status_code=201)
def raise_improvement(
    body: RaiseImprovementRequest, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        entry = get_cir_service().raise_improvement(
            body.title,
            kind=body.kind,
            rationale=body.rationale,
            raised_by=body.raised_by,
            incident_id=body.incident_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return entry.to_dict()


@router.post("/improvements/{improvement_id}/realise")
def realise_improvement(
    improvement_id: str, current_user: dict = Depends(get_current_user)
) -> Dict[str, Any]:
    _require_admin(current_user)
    try:
        return get_cir_service().realise(improvement_id).to_dict()
    except UnknownImprovementError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/incidents/{incident_id}/accept-as-risk", status_code=201)
def accept_as_risk(
    incident_id: str,
    body: AcceptAsRiskRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Record that there is nothing to change here, and who decided that."""
    _require_admin(current_user)
    try:
        get_itsm_service().get_incident(incident_id)
    except UnknownIncidentError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    try:
        entry = get_cir_service().accept_as_risk(
            body.title,
            accepted_by=body.accepted_by,
            rationale=body.rationale,
            incident_id=incident_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return entry.to_dict()
