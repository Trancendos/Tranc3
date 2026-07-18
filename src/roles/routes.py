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

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from src.roles.registry import RoleAssignment, UnknownLocationError, get_registry

router = APIRouter(prefix="/roles", tags=["roles"])


class AssignRequest(BaseModel):
    ai_name: str
    reason: str = ""


class UnassignRequest(BaseModel):
    reason: str = ""


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(
            status_code=403, detail="Admin role required to modify role assignments"
        )


def _serialize(assignment: RoleAssignment) -> Dict[str, Any]:
    return {
        "location": assignment.location,
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


# One of the 43 canonical locations ("ChronosSphere / ArcStream") contains a
# literal "/". `{location:path}` lets these routes match it — Starlette's
# path converter is greedy but still backtracks to satisfy a route's
# trailing literal segment (e.g. "/history"), so it resolves correctly.
# That greediness is also why `role_history`/`assign_role`/`unassign_role`
# (which have a literal suffix after `location`) must be registered before
# the bare `get_role` route below: an unsuffixed `{location:path}` GET route
# would otherwise swallow "<location>/history" whole if tried first.


@router.get("/{location:path}/history")
def role_history(location: str) -> List[Dict[str, Any]]:
    try:
        history = get_registry().get_history(location)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return [
        {
            "location": h.location,
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
            location, body.ai_name, changed_by=str(changed_by), reason=body.reason
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
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
    try:
        role = get_registry().remove_ai(location, changed_by=str(changed_by), reason=reason)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return _serialize(role)


@router.get("/{location:path}")
def get_role(location: str) -> Dict[str, Any]:
    role = get_registry().get_role(location)
    if role is None:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}")
    return _serialize(role)
