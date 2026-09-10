"""HTTP surface for the Town Hall's product lifecycle gates.

Mounted under the Town Hall's own prefix, because the gate is a governance
control and not a creative one: the Location that builds a thing must not
also be the one that decides its gate has opened.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from auth import get_current_user
from src.townhall.plm import (
    CRITERIA,
    DeliverableKind,
    GateAlreadyPassed,
    GateBlocked,
    Outcome,
    Stage,
    UnknownCriterionError,
    UnknownDeliverableError,
    criteria_for,
    get_plm,
)

router = APIRouter(prefix="/townhall/plm", tags=["townhall", "plm"])


def _require_admin(current_user: dict) -> None:
    """Writes here are governance acts, so they take the admin gate.

    The same split `src/townhall/routing_routes.py` uses: reads are public
    because the estate's gate state is not a secret, writes are not because
    creating a deliverable, filing PASS evidence, waiving a criterion and
    advancing a stage are all ways of declaring that a control was satisfied.
    Until this existed, every one of those was an unauthenticated call.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")


def _actor(current_user: dict) -> str:
    """Who the record says did this — taken from the token, never from the body.

    `requested_by`, `recorded_by` and `approver` used to be request fields.
    They are durably written into the lifecycle history, so accepting them
    from the caller meant the audit trail recorded whatever name the caller
    typed. An attribution a caller chooses is not attribution.
    """
    for key in ("username", "sub", "id"):
        value = current_user.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise HTTPException(status_code=403, detail="authenticated principal has no identity")


def _enum(value: str, enum_cls, label: str):
    try:
        return enum_cls(value)
    except ValueError as exc:
        valid = ", ".join(m.value for m in enum_cls)
        raise HTTPException(400, f"unknown {label} {value!r}; expected one of: {valid}") from exc


@router.get("/criteria")
async def list_criteria(
    kind: Optional[str] = Query(None), stage: Optional[str] = Query(None)
) -> dict[str, Any]:
    """The gate criteria, optionally narrowed to one deliverable kind and stage."""
    if kind is None and stage is None:
        return {"count": len(CRITERIA), "criteria": [c.to_dict() for c in CRITERIA]}
    if kind is None or stage is None:
        raise HTTPException(400, "kind and stage must be given together")
    selected = criteria_for(_enum(kind, DeliverableKind, "kind"), _enum(stage, Stage, "stage"))
    return {"count": len(selected), "criteria": [c.to_dict() for c in selected]}


@router.post("/deliverables", status_code=201)
async def create_deliverable(
    title: str = Body(...),
    kind: str = Body(...),
    location: str = Body(...),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    item = get_plm().create(
        title=title,
        kind=_enum(kind, DeliverableKind, "kind"),
        location=location,
        requested_by=_actor(current_user),
    )
    return item.to_dict()


@router.get("/deliverables")
async def list_deliverables(stage: Optional[str] = Query(None)) -> dict[str, Any]:
    selected = get_plm().list_deliverables(
        _enum(stage, Stage, "stage") if stage is not None else None
    )
    return {"count": len(selected), "deliverables": [d.to_dict() for d in selected]}


@router.get("/deliverables/{deliverable_id}")
async def get_deliverable(deliverable_id: str) -> dict[str, Any]:
    try:
        item = get_plm().get(deliverable_id)
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc
    return dict(item.to_dict(), gate=get_plm().gate_status(deliverable_id).to_dict())


@router.post("/deliverables/{deliverable_id}/evidence", status_code=201)
async def submit_evidence(
    deliverable_id: str,
    criterion_id: str = Body(...),
    reference: str = Body(...),
    outcome: str = Body("pass"),
    detail: str = Body(""),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    try:
        ev = get_plm().submit_evidence(
            deliverable_id,
            criterion_id,
            reference,
            _enum(outcome, Outcome, "outcome"),
            _actor(current_user),
            detail,
        )
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc
    except UnknownCriterionError as exc:
        raise HTTPException(400, f"no criterion {criterion_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return ev.to_dict()


@router.post("/deliverables/{deliverable_id}/waivers", status_code=201)
async def waive_criterion(
    deliverable_id: str,
    criterion_id: str = Body(...),
    reason: str = Body(...),
    current_user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    _require_admin(current_user)
    try:
        waiver = get_plm().waive(deliverable_id, criterion_id, reason, _actor(current_user))
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc
    except UnknownCriterionError as exc:
        raise HTTPException(400, f"no criterion {criterion_id!r}") from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return waiver.to_dict()


@router.get("/deliverables/{deliverable_id}/gate")
async def gate(deliverable_id: str) -> dict[str, Any]:
    try:
        return get_plm().gate_status(deliverable_id).to_dict()
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc


@router.post("/deliverables/{deliverable_id}/advance")
async def advance(
    deliverable_id: str, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """Move through the gate, or answer 409 with what is still missing.

    409 Conflict, not 400: the request is well formed and the deliverable's
    own state is what refuses it. The unmet criteria come back in the body
    so a caller does not have to make a second call to find out why.
    """
    _require_admin(current_user)
    try:
        item = get_plm().advance(deliverable_id, approver=_actor(current_user))
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc
    except GateBlocked as exc:
        raise HTTPException(
            409,
            {
                "error": "gate blocked",
                "stage": exc.stage.value,
                "unmet": [c.to_dict() for c in exc.unmet],
            },
        ) from exc
    except GateAlreadyPassed as exc:
        # Two callers advanced the same deliverable; the conditional UPDATE in
        # advance() let exactly one win. The loser is not a server fault — the
        # gate did its job — so it gets the same 409 the blocked case gets,
        # carrying the stage it is now actually at.
        raise HTTPException(
            409,
            {
                "error": "gate already passed",
                "stage": exc.expected.value,
                "current_stage": exc.actual.value,
            },
        ) from exc
    return item.to_dict()


@router.get("/deliverables/{deliverable_id}/history")
async def history(deliverable_id: str) -> dict[str, Any]:
    try:
        entries = get_plm().history(deliverable_id)
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc
    return {"count": len(entries), "history": entries}
