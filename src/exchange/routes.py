"""HTTP routes for the Arcadian Exchange's opportunity book.

Read routes are unauthenticated, matching the registry-style modules
elsewhere on this platform -- the inventory of what the estate *could* sell
carries no secrets, and an operator being able to read it without a token is
the point.

The two routes that change something require an authenticated admin.
Proposing what to sell and booking what a sale actually made are commercial
decisions about the platform as a whole, not per-user-owned resources, so
this follows `/roles` in accepting only `role == "admin"` rather than the
"owner or admin" pattern.

Handlers are plain `def`. They call the synchronous SQLite-backed engine
directly, and FastAPI runs sync handlers in a threadpool rather than on the
event loop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from Dimensional.sanitize import sanitize_for_log
from src.exchange.engine import Candidate, get_engine
from src.exchange.sources import SELLABLE_RESOURCES, by_seat, constrained_resources
from src.exchange.valuation import Basis

router = APIRouter(prefix="/exchange", tags=["exchange"])
logger = logging.getLogger("tranc3.exchange.routes")


def _require_admin(current_user: dict) -> None:
    """403 unless the caller holds the admin role.

    Deliberately not the "owner or admin" pattern used for per-user
    resources: what the platform sells is a decision about the platform,
    with no owner but the operator.
    """
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin role required to propose or settle Exchange opportunities",
        )


class CandidateRequest(BaseModel):
    """One proposed sale.

    The three constraint facts default to the unsafe-to-assume value, exactly
    as `Candidate` does, so a proposal that omits one is escalated or refused
    rather than cleared.
    """

    resource_id: str
    units: float = Field(0.0, ge=0)
    unit_price: Optional[float] = Field(None, ge=0)
    basis: Basis = Basis.NONE
    cost_to_serve: float = Field(0.0, ge=0)
    aggregation_cohort: Optional[int] = Field(None, ge=0)
    counterparty_authorisation: bool = False
    content_is_own_work: Optional[bool] = None

    def to_candidate(self) -> Candidate:
        """The engine's own input type, with the request's defaults intact."""
        return Candidate(
            resource_id=self.resource_id,
            units=self.units,
            unit_price=self.unit_price,
            basis=self.basis,
            cost_to_serve=self.cost_to_serve,
            aggregation_cohort=self.aggregation_cohort,
            counterparty_authorisation=self.counterparty_authorisation,
            content_is_own_work=self.content_is_own_work,
        )


class OutcomeRequest(BaseModel):
    resource_id: str
    estimated: float = Field(..., ge=0)
    realised: float = Field(..., ge=0)
    note: str = ""


@router.get("/inventory")
def inventory() -> Dict[str, Any]:
    """What the estate could sell, who owns selling it, and what is constrained."""
    return get_engine().inventory()


@router.get("/constraints")
def constraints() -> Dict[str, Any]:
    """What is not simply sellable, grouped by why.

    Deliberately its own route. "What can we not sell, and on whose say-so"
    is a question that should be answerable without reading a valuation.
    """
    return {
        constraint.value: [
            {
                "resource_id": r.resource_id,
                "location": r.location,
                "reason": r.constraint_note,
            }
            for r in resources
        ]
        for constraint, resources in constrained_resources().items()
    }


@router.get("/seats/{seat_id}")
def seat_portfolio(seat_id: str) -> Dict[str, Any]:
    """Everything one external seat is responsible for selling."""
    resources = by_seat(seat_id)
    if not resources:
        raise HTTPException(
            status_code=404,
            detail=f"No sellable resources are owned by seat {seat_id!r}",
        )
    engine = get_engine()
    return {
        "seat_id": seat_id,
        "resources": [
            {
                "resource_id": r.resource_id,
                "location": r.location,
                "description": r.description,
                "unit": r.unit,
                "revenue_stream": r.revenue_stream,
                "constraint": r.constraint.value,
                "realisation_ratio": round(engine.realisation_ratio(r.resource_id), 4),
            }
            for r in resources
        ],
        "total": len(resources),
    }


@router.post("/book")
def build_book(
    candidates: List[CandidateRequest],
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Value, rule on and rank a set of proposed sales.

    Refused opportunities come back in their own list, never merged into the
    ranking -- a forbidden sale must not appear in a sorted list of things to
    do next.
    """
    _require_admin(current_user)
    if not candidates:
        raise HTTPException(status_code=400, detail="At least one candidate is required")
    engine = get_engine()
    try:
        book = engine.build_book([c.to_candidate() for c in candidates])
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    snapshot_id = engine.snapshot_book(book)
    logger.info(
        "Exchange book built by %s: %d considered, %d ranked, %d escalated, %d refused",
        sanitize_for_log(str(current_user.get("username", "unknown"))),
        book["candidates_considered"],
        len(book["ranked"]),
        len(book["escalated"]),
        len(book["refused"]),
    )
    return {**book, "snapshot_id": snapshot_id}


@router.post("/outcome")
def record_outcome(
    req: OutcomeRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Book what an opportunity was estimated at against what it made.

    This does not book income. `PassiveRevenueEngine` owns the ledger; this
    only feeds the realisation ratio that calibrates future estimates.
    """
    _require_admin(current_user)
    try:
        ratio = get_engine().record_outcome(
            req.resource_id,
            estimated=req.estimated,
            realised=req.realised,
            note=req.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "recorded": True,
        "resource_id": req.resource_id,
        "realisation_ratio": round(ratio, 4),
        "note": (
            "Income is booked through /billing, not here -- this only calibrates "
            "future estimates for this source."
        ),
    }


@router.get("/health")
def health() -> Dict[str, Any]:
    """Liveness plus the two counts that say whether the catalogue loaded."""
    return {
        "status": "ok",
        "resources": len(SELLABLE_RESOURCES),
        "constrained": sum(len(v) for v in constrained_resources().values()),
    }
