# src/compliance/waivers_routes.py
from __future__ import annotations

import logging
import math
import os
from typing import List, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

from Dimensional.sanitize import sanitize_for_log
from Dimensional.security import constant_time_compare
from src.compliance.waivers import (
    WaiverError,
    WaiverNotFoundError,
    WaiverValidationError,
    emit_expiry_events,
    get_waiver,
    list_waivers,
    register_waiver,
    revoke_waiver,
)

logger = logging.getLogger("tranc3.compliance.waivers_routes")

router = APIRouter(prefix="/compliance/waivers", tags=["waivers"])

_VALID_STATUSES = frozenset({"pending", "active", "expired", "revoked"})

# Same internal-service-auth model as POST /compliance/suites/* (see
# matrix_suites_routes.py) and POST /observatory/events: these routes grant,
# revoke, and scan governance exceptions, so they require X-Internal-Secret
# whenever INTERNAL_SECRET is configured rather than being open to any caller.
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


def _require_internal_secret(x_internal_secret: Optional[str]) -> None:
    if _INTERNAL_SECRET and not constant_time_compare(x_internal_secret or "", _INTERNAL_SECRET):
        raise HTTPException(status_code=403, detail="Forbidden")


class RegisterWaiverRequest(BaseModel):
    subject: str = Field(..., max_length=512)
    justification: str = Field(..., max_length=4096)
    requestor: str = Field(..., max_length=256)
    approver: str = Field(..., max_length=256)
    expires_on: float
    compensating_controls: List[str] = Field(default_factory=list)
    effective_from: Optional[float] = None

    @field_validator("subject", "justification", "requestor", "approver")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v

    @field_validator("expires_on", "effective_from")
    @classmethod
    def _finite(cls, v: Optional[float]) -> Optional[float]:
        # cubic P1: Python's json.loads() accepts NaN/Infinity/-Infinity as an
        # extension of the JSON spec (and so does FastAPI's default decoder), so
        # a client can submit a timestamp that parses without error but defeats
        # the whole time-boxing guarantee this module exists for — NaN makes
        # every comparison against it false, and +inf never arrives.
        if v is not None and not math.isfinite(v):
            raise ValueError("must be a finite number")
        return v


class RevokeWaiverRequest(BaseModel):
    revoked_by: str = Field(..., max_length=256)
    reason: str = Field("", max_length=4096)

    @field_validator("revoked_by")
    @classmethod
    def _not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("revoked_by must not be blank")
        return v


def _handle_waiver_error(exc: WaiverError) -> JSONResponse:
    if isinstance(exc, WaiverNotFoundError):
        logger.warning(
            "waiver request rejected (not found): %s",
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "unknown_waiver"}, status_code=404)
    if isinstance(exc, WaiverValidationError):
        logger.warning(
            "waiver request rejected (invalid): %s",
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "invalid_waiver_request"}, status_code=400)
    logger.warning(
        "waiver request rejected: %s",
        sanitize_for_log(exc),  # codeql[py/log-injection]
    )
    return JSONResponse({"error": "waiver_error"}, status_code=400)


@router.get("")
def waivers(status: Optional[str] = None):
    """List waivers, optionally filtered by computed status
    ('pending' | 'active' | 'expired' | 'revoked')."""
    if status is not None and status not in _VALID_STATUSES:
        # cubic P2: an unrecognized status (e.g. a typo) previously matched
        # nothing and looked identical to a genuinely empty result set.
        return JSONResponse(
            {"error": "invalid_status", "valid_statuses": sorted(_VALID_STATUSES)},
            status_code=400,
        )
    return [w.to_dict() for w in list_waivers(status=status)]


@router.get("/{waiver_id}")
def waiver_detail(waiver_id: str):
    try:
        return get_waiver(waiver_id).to_dict()
    except WaiverError as exc:
        return _handle_waiver_error(exc)


@router.post("", summary="Grant a new time-boxed waiver (internal)")
def create_waiver(
    body: RegisterWaiverRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    _require_internal_secret(x_internal_secret)
    try:
        waiver = register_waiver(
            subject=body.subject,
            justification=body.justification,
            requestor=body.requestor,
            approver=body.approver,
            expires_on=body.expires_on,
            compensating_controls=body.compensating_controls,
            effective_from=body.effective_from,
        )
    except WaiverError as exc:
        return _handle_waiver_error(exc)
    return waiver.to_dict()


@router.post("/{waiver_id}/revoke", summary="Revoke an active waiver (internal)")
def revoke(
    waiver_id: str,
    body: RevokeWaiverRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    _require_internal_secret(x_internal_secret)
    try:
        waiver = revoke_waiver(waiver_id, body.revoked_by, body.reason)
    except WaiverError as exc:
        return _handle_waiver_error(exc)
    return waiver.to_dict()


@router.post("/check-expired", summary="Scan for newly expired waivers (internal)")
def check_expired(x_internal_secret: Optional[str] = Header(None)):
    """Intended to be hit on a cadence by ChronosSphere, mirroring
    POST /compliance/suites/check-overdue."""
    _require_internal_secret(x_internal_secret)
    events = emit_expiry_events()
    return {"emitted": len(events), "waiver_ids": [e.target for e in events]}
