# src/compliance/governance_routes.py
# AI Governance Constitution Phase 2 — FastAPI routes for the escalation FSM
# (src/compliance/escalation_fsm.py). See docs/governance/AI-GOVERNANCE-CONSTITUTION.md.
#
# Mutating routes require X-Internal-Secret when INTERNAL_SECRET is set, mirroring
# src/observability/routes.py's POST /events pattern — not a new auth mechanism.

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Dimensional.sanitize import sanitize_for_log
from src.compliance.escalation_fsm import (
    ActionRequest,
    CharterNotFoundError,
    EscalationError,
    EscalationFSM,
    RecordNotFoundError,
    get_charter_registry,
)

logger = logging.getLogger("tranc3.compliance.governance_routes")

router = APIRouter(prefix="/governance", tags=["governance"])

_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")
_fsm = EscalationFSM()


def _require_internal_secret(x_internal_secret: Optional[str]) -> None:
    if _INTERNAL_SECRET and x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=403, detail="Forbidden")


class SubmitActionRequest(BaseModel):
    tier: int = Field(..., ge=0, le=5)
    domain: str
    action: str
    requestor: str
    confidence: Optional[float] = Field(None, ge=0, le=1)
    context: Dict[str, Any] = Field(default_factory=dict)


class CABDecisionRequest(BaseModel):
    approver: str
    approved: bool


class HaltRequest(BaseModel):
    reason: str


@router.get("/charters")
def list_charters():
    """List every loaded per-capability-class charter."""
    registry = get_charter_registry()
    return [
        {
            "charter_id": c.charter_id,
            "tier": c.tier,
            "domain": c.domain,
            "mission": c.mission,
            "risk_tier": c.risk_tier,
            "approval_required": c.approval_required,
        }
        for c in registry.list_all()
    ]


@router.get("/charters/{charter_id}")
def get_charter(charter_id: str):
    registry = get_charter_registry()
    try:
        charter = registry.get(charter_id)
    except CharterNotFoundError:
        return JSONResponse({"error": "unknown_charter"}, status_code=404)
    return {
        "charter_id": charter.charter_id,
        "version": charter.version,
        "tier": charter.tier,
        "domain": charter.domain,
        "mission": charter.mission,
        "allowed_actions": charter.allowed_actions,
        "forbidden_actions": charter.forbidden_actions,
        "risk_tier": charter.risk_tier,
        "approval_required": charter.approval_required,
        "escalation_triggers": charter.escalation_triggers,
        "escalation_severity": charter.escalation_severity,
        "fallback_behavior": charter.fallback_behavior,
    }


@router.get("/halted")
def list_halted():
    """The Hard Stop Matrix aggregation point — everything currently halted, in one place."""
    return [r.to_dict() for r in _fsm.list_halted()]


@router.get("/actions/{record_id}")
def get_action(record_id: str):
    try:
        record = _fsm.get(record_id)
    except RecordNotFoundError:
        return JSONResponse({"error": "unknown_record"}, status_code=404)
    return record.to_dict()


@router.get("/actions/{record_id}/transitions")
def get_action_transitions(record_id: str):
    """The durable transition history for a record (escalation_transitions table) —
    survives a process restart or an Observatory ring-buffer rotation, unlike the
    current-state-only row GET /actions/{record_id} returns."""
    try:
        _fsm.get(record_id)
    except RecordNotFoundError:
        return JSONResponse({"error": "unknown_record"}, status_code=404)
    return _fsm.list_transitions(record_id)


@router.post("/actions")
def submit_action(body: SubmitActionRequest, x_internal_secret: Optional[str] = Header(None)):
    """Resolve an action request against its charter. See EscalationFSM.submit()."""
    _require_internal_secret(x_internal_secret)
    request = ActionRequest(
        tier=body.tier,
        domain=body.domain,
        action=body.action,
        requestor=body.requestor,
        confidence=body.confidence,
        context=body.context,
    )
    record = _fsm.submit(request)
    return record.to_dict()


@router.post("/actions/{record_id}/cab-decision")
def cab_decision(
    record_id: str,
    body: CABDecisionRequest,
    x_internal_secret: Optional[str] = Header(None),
):
    """Apply a CAB Gate decision to a pending_cab record."""
    _require_internal_secret(x_internal_secret)
    try:
        record = _fsm.resolve_cab(record_id, body.approver, body.approved)
    except RecordNotFoundError:
        return JSONResponse({"error": "unknown_record"}, status_code=404)
    except EscalationError as exc:
        logger.warning(
            "cab_decision rejected | record_id=%s | reason=%s",
            sanitize_for_log(record_id),  # codeql[py/log-injection]
            sanitize_for_log(str(exc)),  # codeql[py/log-injection]
        )
        return JSONResponse({"error": "invalid_state"}, status_code=409)
    return record.to_dict()


@router.post("/actions/{record_id}/halt")
def halt_action(record_id: str, body: HaltRequest, x_internal_secret: Optional[str] = Header(None)):
    """Irreversible: no transition leads out of 'halted' except a fresh submit()."""
    _require_internal_secret(x_internal_secret)
    try:
        record = _fsm.halt(record_id, body.reason)
    except RecordNotFoundError:
        return JSONResponse({"error": "unknown_record"}, status_code=404)
    return record.to_dict()
