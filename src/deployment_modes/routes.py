# src/deployment_modes/routes.py
"""HTTP routes for the Deployment Mode Registry.

Read routes (list/get/history) are unauthenticated, same as most other
registry-style modules on this platform (e.g. `src/roles/routes.py`).
Mutating routes (mode changes, provisioning) require an authenticated
admin — changing a Location's deployment mode or spinning up its Dev/UAT
is a platform-governance action, not a per-user-owned resource.

Handlers are plain `def`, not `async def` — they call the synchronous
SQLite-backed DeploymentModeRegistry directly, and FastAPI runs sync route
handlers in a threadpool instead of on the event loop, so this avoids
blocking it.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from src.deployment_modes.registry import (
    DeploymentMode,
    Environment,
    EnvironmentState,
    ModeState,
    ProdNotOnDemandError,
    UnknownLocationError,
    get_registry,
)

router = APIRouter(prefix="/deployment-modes", tags=["deployment-modes"])


class SetModeRequest(BaseModel):
    mode: DeploymentMode
    reason: str = ""


class ProvisionEnvironmentRequest(BaseModel):
    scoped_by: str
    reason: str = ""


class DeprovisionEnvironmentRequest(BaseModel):
    reason: str = ""


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")


def _serialize_mode(state: ModeState) -> Dict[str, Any]:
    return {
        "location": state.location,
        "mode": state.mode.value,
        "changed_at": state.changed_at,
        "changed_by": state.changed_by,
        "reason": state.reason,
    }


def _serialize_env(state: EnvironmentState) -> Dict[str, Any]:
    return {
        "location": state.location,
        "mode": state.mode.value,
        "environment": state.environment.value,
        "provisioned": state.provisioned,
        "provisioned_at": state.provisioned_at,
        "scoped_by": state.scoped_by,
        "changed_by": state.changed_by,
        "reason": state.reason,
    }


@router.get("/")
def list_modes() -> List[Dict[str, Any]]:
    return [_serialize_mode(m) for m in get_registry().list_modes()]


# One of the 43 canonical locations ("ChronosSphere / ArcStream") contains a
# literal "/". `{location:path}` lets these routes match it — see
# src/roles/routes.py for the identical rationale and the same ordering
# requirement: routes with a literal suffix after `{location:path}` must be
# registered before the bare `get_mode` route below, or it would swallow
# "<location>/history" (etc.) whole. That greediness also means, among GET
# routes sharing a "/history" suffix, the MORE specific one must be
# registered first: `environment_history`'s trailing "/history" is a subset
# of what `mode_history`'s bare `{location:path}/history` pattern would
# otherwise match first (treating "<location>/environments/<env>" as the
# whole `location`), so environment_history is registered ahead of it here.


@router.get("/{location:path}/environments/{environment}/history")
def environment_history(location: str, environment: Environment) -> List[Dict[str, Any]]:
    try:
        history = get_registry().get_environment_history(location, environment)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return [
        {
            "location": h.location,
            "mode": h.mode.value,
            "environment": h.environment.value,
            "action": h.action,
            "changed_at": h.changed_at,
            "changed_by": h.changed_by,
            "scoped_by": h.scoped_by,
            "reason": h.reason,
        }
        for h in history
    ]


@router.get("/{location:path}/environments")
def list_environments(location: str) -> List[Dict[str, Any]]:
    try:
        envs = get_registry().list_environments(location)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return [_serialize_env(e) for e in envs]


@router.get("/{location:path}/history")
def mode_history(location: str) -> List[Dict[str, Any]]:
    try:
        history = get_registry().get_mode_history(location)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return [
        {
            "location": h.location,
            "previous_mode": h.previous_mode.value if h.previous_mode else None,
            "new_mode": h.new_mode.value,
            "changed_at": h.changed_at,
            "changed_by": h.changed_by,
            "reason": h.reason,
        }
        for h in history
    ]


@router.post("/{location:path}/environments/{environment}/provision")
def provision_environment(
    location: str,
    environment: Environment,
    body: ProvisionEnvironmentRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    changed_by = current_user.get("sub") or current_user.get("id") or "operator"
    try:
        state = get_registry().provision_environment(
            location,
            environment,
            scoped_by=body.scoped_by,
            changed_by=str(changed_by),
            reason=body.reason,
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    except ProdNotOnDemandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize_env(state)


@router.delete("/{location:path}/environments/{environment}")
def deprovision_environment(
    location: str,
    environment: Environment,
    body: Optional[DeprovisionEnvironmentRequest] = None,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    changed_by = current_user.get("sub") or current_user.get("id") or "operator"
    reason = body.reason if body else ""
    try:
        state = get_registry().deprovision_environment(
            location, environment, changed_by=str(changed_by), reason=reason
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    except ProdNotOnDemandError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_env(state)


@router.put("/{location:path}")
def set_mode(
    location: str,
    body: SetModeRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_admin(current_user)
    changed_by = current_user.get("sub") or current_user.get("id") or "operator"
    try:
        state = get_registry().set_mode(
            location, body.mode, changed_by=str(changed_by), reason=body.reason
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return _serialize_mode(state)


@router.get("/{location:path}")
def get_mode(location: str) -> Dict[str, Any]:
    state = get_registry().get_mode(location)
    if state is None:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}")
    return _serialize_mode(state)
