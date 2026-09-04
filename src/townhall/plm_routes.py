"""HTTP surface for the Town Hall's product lifecycle gates.

Mounted under the Town Hall's own prefix, because the gate is a governance
control and not a creative one: the Location that builds a thing must not
also be the one that decides its gate has opened.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from src.townhall.plm import (
    CRITERIA,
    DeliverableKind,
    GateBlocked,
    Outcome,
    Stage,
    UnknownCriterionError,
    UnknownDeliverableError,
    criteria_for,
    get_plm,
)

router = APIRouter(prefix="/townhall/plm", tags=["townhall", "plm"])


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
    requested_by: str = Body("system"),
) -> dict[str, Any]:
    item = get_plm().create(
        title=title,
        kind=_enum(kind, DeliverableKind, "kind"),
        location=location,
        requested_by=requested_by,
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
    recorded_by: str = Body("system"),
    detail: str = Body(""),
) -> dict[str, Any]:
    try:
        ev = get_plm().submit_evidence(
            deliverable_id,
            criterion_id,
            reference,
            _enum(outcome, Outcome, "outcome"),
            recorded_by,
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
    approver: str = Body(...),
) -> dict[str, Any]:
    try:
        waiver = get_plm().waive(deliverable_id, criterion_id, reason, approver)
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
    deliverable_id: str, approver: str = Body("system", embed=True)
) -> dict[str, Any]:
    """Move through the gate, or answer 409 with what is still missing.

    409 Conflict, not 400: the request is well formed and the deliverable's
    own state is what refuses it. The unmet criteria come back in the body
    so a caller does not have to make a second call to find out why.
    """
    try:
        item = get_plm().advance(deliverable_id, approver=approver)
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
    return item.to_dict()


@router.get("/deliverables/{deliverable_id}/history")
async def history(deliverable_id: str) -> dict[str, Any]:
    try:
        entries = get_plm().history(deliverable_id)
    except UnknownDeliverableError as exc:
        raise HTTPException(404, f"no deliverable {deliverable_id!r}") from exc
    return {"count": len(entries), "history": entries}
