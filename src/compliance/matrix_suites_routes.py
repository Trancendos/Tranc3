# src/compliance/matrix_suites_routes.py
from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from Dimensional.sanitize import sanitize_for_log
from Dimensional.security import constant_time_compare
from src.compliance.matrix_suites import (
    MatrixSuitesError,
    MatrixSuitesValidationError,
    emit_overdue_events,
    list_suite_health,
    record_escalated,
    record_matrix_changed,
    record_review_completed,
)

logger = logging.getLogger("tranc3.compliance.matrix_suites_routes")

router = APIRouter(prefix="/compliance/suites", tags=["matrix-suites"])

# Same internal-service-auth model as POST /observatory/events
# (src/observability/routes.py): these routes emit governance audit events
# on behalf of the caller (ChronosSphere cron, CI, an admin panel), so they
# require X-Internal-Secret whenever INTERNAL_SECRET is configured, rather
# than being open to any unauthenticated caller.
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


def _require_internal_secret(x_internal_secret: Optional[str]) -> None:
    if _INTERNAL_SECRET and not constant_time_compare(x_internal_secret or "", _INTERNAL_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


class ReviewCompletedRequest(BaseModel):
    reviewer: str
    notes: str = ""


class MatrixChangedRequest(BaseModel):
    matrix_id: str


class EscalateRequest(BaseModel):
    from_role: str
    to_role: str
    reason: str = ""


# Plain `def` (not `async def`) throughout this router, matching
# src/roles/routes.py: every handler here does synchronous file/YAML I/O and
# an in-memory Observatory.record() call, none of it awaited — under an
# `async def` handler that work would run inline on the event loop and block
# concurrent requests, whereas FastAPI dispatches a sync `def` handler to its
# threadpool automatically.


@router.get("")
def suites():
    """Health of all 8 Matrix Suites (overdue reviews) from the registry."""
    try:
        return [asdict(h) for h in list_suite_health()]
    except MatrixSuitesError as exc:
        logger.warning(  # codeql[py/log-injection] -- value is sanitize_for_log()'d
            "suites() rejected: %s", sanitize_for_log(exc)
        )
        return JSONResponse({"error": "invalid_registry"}, status_code=404)


@router.get("/{suite_id}")
def suite_detail(suite_id: str):
    try:
        health_list = list_suite_health()
    except MatrixSuitesError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "suite_detail() rejected for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "invalid_registry"}, status_code=404)
    for health in health_list:
        if health.suite_id == suite_id:
            return asdict(health)
    return JSONResponse({"error": f"Unknown suite_id: {suite_id}"}, status_code=404)


@router.post("/check-overdue", summary="Scan for overdue suite reviews (internal)")
def check_overdue(x_internal_secret: Optional[str] = Header(None)):
    """Scan all suites and emit review.overdue events for any past next_review.
    Intended to be hit on a cadence by ChronosSphere; throttled to one
    emission per suite per day regardless of call frequency."""
    _require_internal_secret(x_internal_secret)
    try:
        events = emit_overdue_events()
    except MatrixSuitesError as exc:
        logger.warning(  # codeql[py/log-injection] -- value is sanitize_for_log()'d
            "check_overdue() rejected: %s", sanitize_for_log(exc)
        )
        return JSONResponse({"error": "invalid_registry"}, status_code=404)
    return {"emitted": len(events), "suite_ids": [e.target for e in events]}


@router.post("/{suite_id}/review", summary="Record a completed suite review (internal)")
def complete_review(
    suite_id: str,
    body: ReviewCompletedRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    _require_internal_secret(x_internal_secret)
    try:
        event = record_review_completed(suite_id, body.reviewer, body.notes)
    except MatrixSuitesValidationError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "complete_review rejected (invalid request) for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "invalid_suite_request"}, status_code=400)
    except MatrixSuitesError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "complete_review rejected (unknown suite) for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "unknown_suite"}, status_code=404)
    return event.to_dict()


@router.post("/{suite_id}/matrix-changed", summary="Record a member matrix change (internal)")
def matrix_changed(
    suite_id: str,
    body: MatrixChangedRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    _require_internal_secret(x_internal_secret)
    try:
        event = record_matrix_changed(suite_id, body.matrix_id)
    except MatrixSuitesValidationError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "matrix_changed rejected (invalid request) for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "invalid_suite_request"}, status_code=400)
    except MatrixSuitesError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "matrix_changed rejected (unknown suite) for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "unknown_suite"}, status_code=404)
    return event.to_dict()


@router.post("/{suite_id}/escalate", summary="Record a suite escalation (internal)")
def escalate(
    suite_id: str,
    body: EscalateRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    _require_internal_secret(x_internal_secret)
    try:
        event = record_escalated(suite_id, body.from_role, body.to_role, body.reason)
    except MatrixSuitesValidationError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "escalate rejected (invalid request) for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "invalid_suite_request"}, status_code=400)
    except MatrixSuitesError as exc:
        logger.warning(  # codeql[py/log-injection] -- values are sanitize_for_log()'d
            "escalate rejected (unknown suite) for suite_id=%s: %s",
            sanitize_for_log(suite_id),
            sanitize_for_log(exc),
        )
        return JSONResponse({"error": "unknown_suite"}, status_code=404)
    return event.to_dict()
