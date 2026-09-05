"""HTTP surface for the Town Hall's backlog routing decisions.

Under the Town Hall's prefix for the same reason the PLM gate is: the
Location that will do the work must not be the one that decides the work is
theirs. `POST` records a decision or refuses it; there is no endpoint that
routes an item without a named authority and a written reason, because that
endpoint would be the guess this register exists to replace.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, HTTPException

from src.townhall.routing import RoutingRefused, get_routing_registry

router = APIRouter(prefix="/townhall/routing", tags=["townhall", "routing"])


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


@router.post("/decisions")
async def route_item(payload: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Record where a backlog item belongs.

    A refusal is a 400 carrying the reason, not a 200 with a warning field:
    the caller has to deal with it.
    """
    try:
        decision = get_routing_registry().route(
            item_key=str(payload.get("item_key", "")),
            location=str(payload.get("location", "")),
            reason=str(payload.get("reason", "")),
            authority=str(payload.get("authority", "")),
        )
    except (RoutingRefused, ValueError) as exc:
        raise HTTPException(400, str(exc)) from exc
    return {"decision": decision.to_dict()}


@router.post("/export")
async def export_decisions() -> dict[str, Any]:
    """Write the decisions to the file the backlog generator reads."""
    path = get_routing_registry().export()
    return {"exported": str(path)}
