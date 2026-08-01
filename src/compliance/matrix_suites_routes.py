# src/compliance/matrix_suites_routes.py
from __future__ import annotations

import logging
import os
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from Dimensional.sanitize import sanitize_for_log
from Dimensional.security import constant_time_compare
from src.compliance.matrix_suites import (
    MatrixSuitesError,
    MatrixSuitesRegistryError,
    MatrixSuitesValidationError,
    _find_suite,
    emit_overdue_events,
    list_suite_health,
    load_suites,
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
    reviewer: str = Field(..., max_length=256)
    notes: str = Field("", max_length=4096)

    @field_validator("reviewer")
    @classmethod
    def _reviewer_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("reviewer must not be blank")
        return v


class MatrixChangedRequest(BaseModel):
    matrix_id: str = Field(..., max_length=256)

    @field_validator("matrix_id")
    @classmethod
    def _matrix_id_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("matrix_id must not be blank")
        return v


class EscalateRequest(BaseModel):
    from_role: str = Field(..., max_length=256)
    to_role: str = Field(..., max_length=256)
    reason: str = Field("", max_length=4096)

    @field_validator("from_role", "to_role")
    @classmethod
    def _role_not_blank(cls, v: str) -> str:
        # A blank from_role matters beyond input hygiene: a registry entry
        # with no steward_ai builds chain = [""] + escalation, so "" would
        # otherwise pass the membership check in record_escalated() and the
        # event would record an empty actor.
        v = v.strip()
        if not v:
            raise ValueError("role must not be blank")
        return v


# Plain `def` (not `async def`) throughout this router, matching
# src/roles/routes.py: every handler here does synchronous file/YAML I/O and
# an in-memory Observatory.record() call, none of it awaited — under an
# `async def` handler that work would run inline on the event loop and block
# concurrent requests, whereas FastAPI dispatches a sync `def` handler to its
# threadpool automatically.


def _handle_suite_error(action: str, suite_id: str, exc: MatrixSuitesError) -> JSONResponse:
    """Map a MatrixSuitesError raised by the compliance layer to the route's
    JSON error response, logging a sanitized warning first. Shared by
    complete_review/matrix_changed/escalate so the registry-vs-request-vs-
    unknown-suite classification lives in one place instead of being
    repeated (and having to be kept in lockstep) per handler.

    isinstance checks, not a dict lookup, because MatrixSuitesRegistryError
    and MatrixSuitesValidationError are both subclasses of MatrixSuitesError
    — order matters, matching the original except-clause ordering (registry
    misconfiguration takes precedence over a request being also invalid;
    see the reasoning on _require_prefix() callers in matrix_suites.py)."""
    if isinstance(exc, MatrixSuitesRegistryError):
        logger.warning(
            "%s rejected (registry misconfigured) for suite_id=%s: %s",
            action,
            sanitize_for_log(suite_id),  # codeql[py/log-injection]
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "invalid_registry"}, status_code=404)
    if isinstance(exc, MatrixSuitesValidationError):
        logger.warning(
            "%s rejected (invalid request) for suite_id=%s: %s",
            action,
            sanitize_for_log(suite_id),  # codeql[py/log-injection]
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "invalid_suite_request"}, status_code=400)
    logger.warning(
        "%s rejected (unknown suite) for suite_id=%s: %s",
        action,
        sanitize_for_log(suite_id),  # codeql[py/log-injection]
        sanitize_for_log(exc),  # codeql[py/log-injection]
    )
    return JSONResponse({"error": "unknown_suite"}, status_code=404)


@router.get("")
def suites():
    """Health of all 8 Matrix Suites (overdue reviews) from the registry."""
    try:
        return [asdict(h) for h in list_suite_health()]
    except MatrixSuitesError as exc:
        logger.warning(
            "suites() rejected: %s",
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "invalid_registry"}, status_code=404)


@router.get("/{suite_id}")
def suite_detail(suite_id: str):
    try:
        health_list = list_suite_health()
    except MatrixSuitesError as exc:
        logger.warning(
            "suite_detail() rejected for suite_id=%s: %s",
            sanitize_for_log(suite_id),  # codeql[py/log-injection]
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "invalid_registry"}, status_code=404)
    for health in health_list:
        if health.suite_id == suite_id:
            return asdict(health)
    # Not in the health list -- either genuinely unknown, or a duplicate/
    # malformed entry that list_suite_health() silently excludes (its own
    # dedicated check, distinct from raising). Reuse _find_suite()'s
    # classification, same as the POST routes via _handle_suite_error(), so
    # a broken registry reads as invalid_registry here too instead of the
    # misleading "suite not found" this endpoint used to return verbatim.
    try:
        _find_suite(load_suites(), suite_id)
    except MatrixSuitesError as exc:
        return _handle_suite_error("suite_detail", suite_id, exc)
    # _find_suite() found exactly one match yet list_suite_health() excluded
    # it for some other reason -- the two apply the same filters, so this
    # shouldn't be reachable, but fall back to the canonical shape rather
    # than assume it can't happen.
    return JSONResponse({"error": "unknown_suite"}, status_code=404)


@router.post("/check-overdue", summary="Scan for overdue suite reviews (internal)")
def check_overdue(x_internal_secret: Optional[str] = Header(None)):
    """Scan all suites and emit review.overdue events for any past next_review.
    Intended to be hit on a cadence by ChronosSphere; throttled to one
    emission per suite per day regardless of call frequency."""
    _require_internal_secret(x_internal_secret)
    try:
        events = emit_overdue_events()
    except MatrixSuitesError as exc:
        logger.warning(
            "check_overdue() rejected: %s",
            sanitize_for_log(exc),  # codeql[py/log-injection]
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
    except MatrixSuitesError as exc:
        # record_review_completed() only ever raises MatrixSuitesError (unknown
        # suite) or MatrixSuitesRegistryError — it never raises
        # MatrixSuitesValidationError, unlike matrix_changed/escalate below, but
        # _handle_suite_error() covers that branch too since it's a no-op here.
        return _handle_suite_error("complete_review", suite_id, exc)
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
    except MatrixSuitesError as exc:
        return _handle_suite_error("matrix_changed", suite_id, exc)
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
    except MatrixSuitesError as exc:
        return _handle_suite_error("escalate", suite_id, exc)
    return event.to_dict()
