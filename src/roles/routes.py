# src/roles/routes.py
"""HTTP routes for the Role Assignment Registry.

Read routes (list/get/history) are unauthenticated, same as most other
registry-style modules on this platform. Mutating routes (assign/unassign)
require an authenticated admin — reassigning which AI holds a platform-wide
Job Description is a governance action, not a per-user-owned resource, so
this does not follow the "owner or admin" pattern used by e.g. DevOcity;
only `role == "admin"` is accepted.

Handlers are plain `def`, not `async def` — they call the synchronous
SQLite-backed RoleRegistry directly, and FastAPI runs sync route handlers
in a threadpool instead of on the event loop, so this avoids blocking it.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from Dimensional.sanitize import sanitize_for_log
from src.roles.registry import RoleAssignment, UnknownLocationError, get_registry
from src.roles.suite_stewardship import (
    MatrixSuitesError,
    SuiteStewardship,
    get_suite_stewardship,
    list_suite_stewardships,
)

router = APIRouter(prefix="/roles", tags=["roles"])
logger = logging.getLogger("tranc3.roles.routes")


class AssignRequest(BaseModel):
    ai_name: str
    reason: str = ""
    # Which seat at this Location. Defaults to the headline role, so a caller
    # unaware that co-lead seats exist still does exactly what it did before.
    seat_id: str = "primary"


class UnassignRequest(BaseModel):
    reason: str = ""
    seat_id: str = "primary"


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail="Admin role required to modify role assignments"
        )


def _serialize(assignment: RoleAssignment) -> Dict[str, Any]:
    return {
        "location": assignment.location,
        "seat_id": assignment.seat_id,
        "designed_for": assignment.designed_for,
        "functions": list(assignment.functions),
        "mandate": assignment.mandate,
        "pillar": assignment.pillar,
        "primary_function": assignment.primary_function,
        "job_description": assignment.job_description,
        "assigned_ai": assignment.assigned_ai,
        "assigned_at": assignment.assigned_at,
        "assigned_by": assignment.assigned_by,
    }


@router.get("/")
def list_roles() -> List[Dict[str, Any]]:
    return [_serialize(r) for r in get_registry().list_roles()]


def _serialize_suite(stewardship: SuiteStewardship) -> Dict[str, Any]:
    return {
        "suite_id": stewardship.suite_id,
        "name": stewardship.name,
        "pillar": stewardship.pillar,
        "steward_location": stewardship.steward_location,
        "designed_steward_ai": stewardship.designed_steward_ai,
        "current_steward_ai": stewardship.current_steward_ai,
        "presiding_prime": stewardship.presiding_prime,
        "escalation": stewardship.escalation,
        "review_cadence": stewardship.review_cadence,
        "next_review": stewardship.next_review,
        "drifted": stewardship.drifted,
    }


# Matrix Suites Stage 7.5 (docs/governance/MATRIX-SUITES.md §7, Magna Carta
# submodule): the 8 Suites aren't their own Locations, so they don't get rows
# in role_assignments — this reads each Suite's designed steward baseline
# from Magna Carta's matrix_suites.yaml and cross-references it against the
# live Role Registry holder at that suite's steward_location (see
# src/roles/suite_stewardship.py's module docstring for the full reasoning).
# Registered before the `{location:path}` catch-all below, same reason as
# `role_history`/`assign_role`/`unassign_role`: an unsuffixed
# `{location:path}` GET route would otherwise swallow "suites" and
# "suites/<suite_id>" as if they were location names.


@router.get("/suites")
def list_suites() -> List[Dict[str, Any]]:
    try:
        return [_serialize_suite(s) for s in list_suite_stewardships()]
    except MatrixSuitesError as exc:
        logger.warning(
            "list_suites() rejected: %s",
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        raise HTTPException(status_code=404, detail="invalid_registry") from exc


@router.get("/suites/{suite_id}")
def get_suite(suite_id: str) -> Dict[str, Any]:
    try:
        stewardship = get_suite_stewardship(suite_id)
    except MatrixSuitesError as exc:
        logger.warning(
            "get_suite() rejected for suite_id=%s: %s",
            sanitize_for_log(suite_id),  # codeql[py/log-injection]
            sanitize_for_log(exc),  # codeql[py/log-injection]
        )
        raise HTTPException(status_code=404, detail="invalid_registry") from exc
    if stewardship is None:
        raise HTTPException(status_code=404, detail=f"Unknown suite: {suite_id}")
    return _serialize_suite(stewardship)


# One of the 43 canonical locations ("ChronosSphere / ArcStream") contains a
# literal "/". `{location:path}` lets these routes match it — Starlette's
# path converter is greedy but still backtracks to satisfy a route's
# trailing literal segment (e.g. "/history"), so it resolves correctly.
# That greediness is also why `role_history`/`assign_role`/`unassign_role`
# (which have a literal suffix after `location`) must be registered before
# the bare `get_role` route below: an unsuffixed `{location:path}` GET route
# would otherwise swallow "<location>/history" whole if tried first.


@router.get("/{location:path}/seats")
def location_seats(location: str) -> List[Dict[str, Any]]:
    """Every Job Description seat at one Location, primary first.

    The question the single-row model could not answer. At The Chaos Party this
    returns The Mad Hatter's adversarial-testing seat and Alice Dream's
    deterministic-assurance seat as separate roles with separate functions,
    rather than one title standing in for both.
    """
    seats = get_registry().get_location_seats(location)
    if not seats:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}")
    return [_serialize(s) for s in seats]


@router.get("/{location:path}/history")
def role_history(location: str, seat_id: Optional[str] = None) -> List[Dict[str, Any]]:
    """Assignment history, optionally narrowed to one seat.

    Without `seat_id` in the response a reader of TateKing's history sees two
    interleaved seat moves with no way to tell which seat moved -- the model
    became seat-aware and this endpoint was left behind.
    """
    try:
        history = get_registry().get_history(location, seat_id=seat_id)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return [
        {
            "location": h.location,
            "seat_id": h.seat_id,
            "previous_ai": h.previous_ai,
            "new_ai": h.new_ai,
            "changed_at": h.changed_at,
            "changed_by": h.changed_by,
            "reason": h.reason,
        }
        for h in history
    ]


@router.post("/{location:path}/assign")
def assign_role(
    location: str,
    body: AssignRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    changed_by = current_user.get("sub") or current_user.get("id") or "operator"
    try:
        role = get_registry().assign_ai(
            location,
            body.ai_name,
            changed_by=str(changed_by),
            reason=body.reason,
            seat_id=body.seat_id,
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize(role)


@router.delete("/{location:path}/assign")
def unassign_role(
    location: str,
    body: Optional[UnassignRequest] = None,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    changed_by = current_user.get("sub") or current_user.get("id") or "operator"
    reason = body.reason if body else ""
    seat_id = body.seat_id if body else "primary"
    try:
        role = get_registry().remove_ai(
            location, changed_by=str(changed_by), reason=reason, seat_id=seat_id
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return _serialize(role)


@router.get("/{location:path}")
def get_role(location: str) -> Dict[str, Any]:
    role = get_registry().get_role(location)
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}")
    return _serialize(role)
