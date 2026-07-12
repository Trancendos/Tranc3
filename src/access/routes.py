# src/access/routes.py
"""HTTP routes + reusable dependency for the Location Access & Subscription
Registry.

Self-service by design: a user consents to a Location's own Terms &
Conditions / Acceptable Use Policy on their own behalf, so `POST
/access/{location}/subscribe` and `DELETE /access/{location}/subscribe`
require only that the caller be authenticated as themselves — not `admin`,
unlike the Role Registry's mutating routes, which reassign a platform-wide
resource rather than a user's own opt-in. `GET /access/{location}/subscribers`
(the full subscriber list for a Location) is admin-only, since it's
compliance/audit data about other users, not self-service.

`require_location_subscription(location)` is the reusable gate other
routers should use to require an active subscription before serving a
Location's functionality — see its docstring for the admin-bypass rule.
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user
from src.access.registry import (
    CURRENT_TERMS_VERSION,
    LocationSubscription,
    StaleTermsVersionError,
    SubscriptionEvent,
    TermsNotAcceptedError,
    UnknownLocationError,
    get_access_registry,
)
from src.entities.platform import PLATFORM_ENTITIES

router = APIRouter(prefix="/access", tags=["access"])


class SubscribeRequest(BaseModel):
    accepted_terms: bool
    terms_version: str = CURRENT_TERMS_VERSION


def _user_id(current_user: dict) -> str:
    return str(current_user.get("sub") or current_user.get("id") or "anonymous")


def _serialize(sub: LocationSubscription) -> Dict[str, Any]:
    # `grants_access` is the gate-truth: a row can be status='active' yet fail
    # the gate because its terms_version is stale after a policy bump. Exposing
    # it (and `terms_current`) here keeps /access/me and /subscribers listings
    # from misleadingly presenting a stale subscriber as fully active.
    return {
        "user_id": sub.user_id,
        "location": sub.location,
        "status": sub.status,
        "terms_version": sub.terms_version,
        "terms_current": sub.terms_version == CURRENT_TERMS_VERSION,
        "grants_access": sub.is_active_on_current_terms(CURRENT_TERMS_VERSION),
        "subscribed_at": sub.subscribed_at,
        "revoked_at": sub.revoked_at,
    }


def _serialize_event(evt: SubscriptionEvent) -> Dict[str, Any]:
    return {
        "id": evt.id,
        "user_id": evt.user_id,
        "location": evt.location,
        "action": evt.action,
        "terms_version": evt.terms_version,
        "actor": evt.actor,
        "ts": evt.ts,
    }


def require_location_subscription(location: str):
    """Dependency factory: `Depends(require_location_subscription("The Lab"))`.

    Raises 402 (Payment/consent-style "you must opt in first" status — used
    here for "not subscribed", not billing) if the caller hasn't subscribed
    to `location`. Admins bypass the check entirely — they administer the
    platform and don't self-service-consent into it the way an end user
    does, matching the Role/Relations Registries' own "admin can always
    act" convention.

    Usage (in another router):
        @router.post("/some-location-scoped-endpoint")
        def do_thing(current_user: dict = Depends(require_location_subscription("The Lab"))):
            ...
    """

    def _dependency(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") == "admin":
            return current_user
        user_id = _user_id(current_user)
        if not get_access_registry().is_subscribed(user_id, location):
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Not subscribed to {location}. Accept its Terms & Conditions / "
                    f"Acceptable Use Policy via POST /access/{location}/subscribe first."
                ),
            )
        return current_user

    return _dependency


@router.get("/me")
def list_my_subscriptions(
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    subs = get_access_registry().list_user_subscriptions(
        _user_id(current_user), active_only=active_only
    )
    return [_serialize(s) for s in subs]


# NOTE ON ROUTE ORDER: FastAPI/Starlette tries routes in registration order,
# and `{location:path}` is a greedy match with no anchoring suffix — an
# unsuffixed `/{location:path}` GET route registered before a suffixed one
# (e.g. `/{location:path}/subscribers`) would swallow "<location>/subscribers"
# whole as a single `location` value. `/subscribers` (and the POST/DELETE
# `/subscribe` routes, different HTTP methods so order doesn't matter for
# them) must come before the bare `get_my_subscription` route below. Same
# reasoning as src/roles/routes.py and src/relations/routes.py.


@router.get("/{location:path}/subscribers")
def list_subscribers(
    location: str,
    active_only: bool = True,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        subs = get_access_registry().list_location_subscribers(location, active_only=active_only)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return [_serialize(s) for s in subs]


@router.delete("/{location:path}/subscribers/{user_id}")
def admin_revoke_subscription(
    location: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    """Admin-only: revoke another user's subscription on their behalf (e.g. a
    compliance-driven removal). Self-service revocation is DELETE
    /access/{location}/subscribe; this endpoint is the administrator path the
    Acceptable Use Policy references. The acting admin is recorded as the
    `actor` in the append-only consent audit trail."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required")
    try:
        sub = get_access_registry().unsubscribe(user_id, location, actor=_user_id(current_user))
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return _serialize(sub)


@router.get("/{location:path}/history")
def get_my_subscription_history(
    location: str,
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """The caller's own immutable consent audit trail for one Location —
    every subscribe/revoke event, newest first."""
    if location not in PLATFORM_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}")
    events = get_access_registry().get_subscription_history(_user_id(current_user), location)
    return [_serialize_event(e) for e in events]


@router.post("/{location:path}/subscribe")
def subscribe(
    location: str,
    body: SubscribeRequest,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        sub = get_access_registry().subscribe(
            _user_id(current_user),
            location,
            accepted_terms=body.accepted_terms,
            terms_version=body.terms_version,
        )
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    except (TermsNotAcceptedError, StaleTermsVersionError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _serialize(sub)


@router.delete("/{location:path}/subscribe")
def unsubscribe(
    location: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    try:
        sub = get_access_registry().unsubscribe(_user_id(current_user), location)
    except UnknownLocationError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}") from exc
    return _serialize(sub)


@router.get("/{location:path}")
def get_my_subscription(
    location: str,
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    # 404 for unknown/misspelled locations, aligning with every other
    # location-scoped route (subscribe/unsubscribe/subscribers), rather than
    # returning 200 status:'none' which can't be told apart from a known but
    # unsubscribed Location.
    if location not in PLATFORM_ENTITIES:
        raise HTTPException(status_code=404, detail=f"Unknown location: {location}")
    sub = get_access_registry().get_subscription(_user_id(current_user), location)
    if sub is None:
        return {
            "user_id": _user_id(current_user),
            "location": location,
            "status": "none",
            "terms_version": None,
            "subscribed_at": None,
            "revoked_at": None,
        }
    return _serialize(sub)
