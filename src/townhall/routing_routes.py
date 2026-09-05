"""HTTP surface for the Town Hall's backlog routing decisions.

Under the Town Hall's prefix for the same reason the PLM gate is: the
Location that will do the work must not be the one that decides the work is
theirs. `POST` records a decision or refuses it; there is no endpoint that
routes an item without a named authority and a written reason, because that
endpoint would be the guess this register exists to replace.

Reads are public, writes require an admin — the same split
`src/townhall/itsm_routes.py` uses. A routing decision is durable, it
supersedes an earlier one, and it changes a file CI reads; an anonymous
caller must not be able to make one.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from src.townhall.routing import EXPORT, REPO, RoutingRefused, get_routing_registry

router = APIRouter(prefix="/townhall/routing", tags=["townhall", "routing"])


class RouteItemRequest(BaseModel):
    """A routing decision, typed so absent and null are refused as such.

    Coercing the body with `str(payload.get(...))` turned a JSON `null` into
    the string `"None"` — non-empty, so it passed the registry's own
    validation and recorded a decision with no written reason and no named
    authority. That is the register's whole point, defeated by a coercion.
    """

    item_key: str = Field(min_length=1)
    location: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    authority: str = Field(min_length=1)


def _require_admin(current_user: dict) -> None:
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin role required for this action")


# ── reads ───────────────────────────────────────────────────────────────────


@router.get("/decisions")
async def list_decisions() -> dict[str, Any]:
    """Every item the Town Hall has routed, and where."""
    decisions = get_routing_registry().decisions()
    return {"count": len(decisions), "decisions": [d.to_dict() for d in decisions]}


@router.get("/decisions/{item_key:path}")
async def get_decision(item_key: str) -> dict[str, Any]:
    """The current decision for one item, with the decisions it superseded."""
    registry = get_routing_registry()
    current = registry.decision(item_key)
    if current is None:
        raise HTTPException(404, f"no routing decision recorded for {item_key!r}")
    return {
        "decision": current.to_dict(),
        "history": [d.to_dict() for d in registry.history(item_key)],
    }


# ── writes ──────────────────────────────────────────────────────────────────


@router.post("/decisions")
async def route_item(
    body: RouteItemRequest, current_user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    """Record where a backlog item belongs.

    A refusal is a 400 carrying the reason, not a 200 with a warning field:
    the caller has to deal with it.
    """
    _require_admin(current_user)
    try:
        decision = get_routing_registry().route(
            item_key=body.item_key,
            location=body.location,
            reason=body.reason,
            authority=body.authority,
        )
    except (RoutingRefused, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"decision": decision.to_dict()}


@router.post("/export")
async def export_decisions(current_user: dict = Depends(get_current_user)) -> dict[str, Any]:
    """Write the decisions to the file the backlog generator reads."""
    _require_admin(current_user)
    path = get_routing_registry().export()
    # Repository-relative: the absolute path is the server's filesystem
    # layout, which a caller has no need for and an attacker does.
    return {"exported": _relative(path)}


def _relative(path) -> str:
    try:
        return str(path.relative_to(REPO))
    except ValueError:
        return EXPORT.name
