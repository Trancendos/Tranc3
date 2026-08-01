# src/compliance/matrix_suites_routes.py
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from src.compliance.matrix_suites import (
    MatrixSuitesError,
    emit_overdue_events,
    list_suite_health,
    record_escalated,
    record_matrix_changed,
    record_review_completed,
)

router = APIRouter(prefix="/compliance/suites", tags=["matrix-suites"])


class ReviewCompletedRequest(BaseModel):
    reviewer: str
    notes: str = ""


class MatrixChangedRequest(BaseModel):
    matrix_id: str


class EscalateRequest(BaseModel):
    from_role: str
    to_role: str
    reason: str = ""


@router.get("")
async def suites():
    """Health of all 8 Matrix Suites (overdue reviews) from the registry."""
    return [asdict(h) for h in list_suite_health()]


@router.get("/{suite_id}")
async def suite_detail(suite_id: str):
    for health in list_suite_health():
        if health.suite_id == suite_id:
            return asdict(health)
    return JSONResponse({"error": f"Unknown suite_id: {suite_id}"}, status_code=404)


@router.post("/check-overdue")
async def check_overdue():
    """Scan all suites and emit review.overdue events for any past next_review.
    Intended to be hit on a cadence by ChronosSphere; throttled to one
    emission per suite per day regardless of call frequency."""
    events = emit_overdue_events()
    return {"emitted": len(events), "suite_ids": [e.target for e in events]}


@router.post("/{suite_id}/review")
async def complete_review(suite_id: str, body: ReviewCompletedRequest):
    try:
        event = record_review_completed(suite_id, body.reviewer, body.notes)
    except MatrixSuitesError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return event.to_dict()


@router.post("/{suite_id}/matrix-changed")
async def matrix_changed(suite_id: str, body: MatrixChangedRequest):
    try:
        event = record_matrix_changed(suite_id, body.matrix_id)
    except MatrixSuitesError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return event.to_dict()


@router.post("/{suite_id}/escalate")
async def escalate(suite_id: str, body: EscalateRequest):
    try:
        event = record_escalated(suite_id, body.from_role, body.to_role, body.reason)
    except MatrixSuitesError as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    return event.to_dict()
