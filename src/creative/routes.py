"""HTTP surface for the creative route table.

The front door a request for creative work goes through. Before this, nothing
mapped "make me a game" to a Location: The Spark's tool registry holds no
creative tool, and Imaginarium was reachable only by a caller that already
knew its address and its project-type vocabulary.

`POST /creative/resolve` answers *where*. It does not perform the work. That
separation is deliberate: the resolution names a capability whose status may
be DEGRADED or ABSENT, and a resolver that dispatched as a side effect could
not report "this Location owns this and does not implement it" without also
having tried to call it.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Body, HTTPException, Query

from src.creative.routing import (
    CAPABILITIES,
    RouteStatus,
    capability,
    endpoint_for,
    gaps,
    resolve,
)

router = APIRouter(prefix="/creative", tags=["creative"])


@router.get("/capabilities")
async def list_capabilities(status: Optional[str] = Query(None)) -> dict[str, Any]:
    """Every creative capability the estate claims, and what each really does."""
    if status is not None:
        try:
            wanted = RouteStatus(status)
        except ValueError as exc:
            valid = ", ".join(s.value for s in RouteStatus)
            raise HTTPException(
                400, f"unknown status {status!r}; expected one of: {valid}"
            ) from exc
        selected = [c for c in CAPABILITIES if c.status is wanted]
    else:
        selected = list(CAPABILITIES)
    return {
        "count": len(selected),
        "capabilities": [dict(c.to_dict(), url=endpoint_for(c)) for c in selected],
    }


@router.get("/capabilities/{capability_id}")
async def get_capability(capability_id: str) -> dict[str, Any]:
    cap = capability(capability_id)
    if cap is None:
        raise HTTPException(404, f"no capability {capability_id!r}")
    return dict(cap.to_dict(), url=endpoint_for(cap))


@router.get("/gaps")
async def list_gaps() -> dict[str, Any]:
    """What the creative estate cannot deliver today, and why.

    Separate from /capabilities because this is the working list: every entry
    here is either a defect to fix or a dependency to stand up.
    """
    entries = gaps()
    return {
        "count": len(entries),
        "absent": sum(1 for c in entries if c.status is RouteStatus.ABSENT),
        "degraded": sum(1 for c in entries if c.status is RouteStatus.DEGRADED),
        "gaps": [c.to_dict() for c in entries],
    }


@router.post("/resolve")
async def resolve_request(request: str = Body(..., embed=True)) -> dict[str, Any]:
    """Name the Location and endpoint that answer a creative request.

    Returns 200 for every outcome including "nowhere": an unroutable request
    is an answer about the estate, not a client error.
    """
    if not request.strip():
        raise HTTPException(400, "request text required")
    res = resolve(request)
    payload = res.to_dict()
    payload["routed"] = res.routed
    payload["url"] = endpoint_for(res.capability) if res.capability else None
    payload["deliverable"] = res.capability.status.value if res.capability else None
    return payload


# The Location a capability belongs to builds the thing; the deliverable kind
# is what the Town Hall gates it as. An image faces no build gate and a game
# faces every one, so the mapping has to be per capability rather than per
# Location — Fabulousa alone produces both a design system and a template.
_DELIVERABLE_KIND: dict[str, str] = {
    "image.create": "image",
    "image.edit": "image",
    "image.upscale": "image",
    "game.create": "game",
    "game.asset.add": "game",
    "model3d.create": "game",
    "video.create": "video",
    "design.create": "design_system",
    "design.component": "design_system",
    "design.accessibility": "design_system",
    "code.generate": "application",
    "music.create": "document",
    "creative.brief": "application",
}


@router.post("/commission", status_code=201)
async def commission(
    request: str = Body(..., embed=True),
    requested_by: str = Body("system", embed=True),
) -> dict[str, Any]:
    """Resolve a creative request *and* open its Town Hall deliverable.

    The brief's actual ask: work of every kind — an app, a game, an image —
    goes through the lifecycle rather than around it. Resolving alone does
    not do that, because a caller can read the answer and then call the
    worker directly.

    An unroutable request opens nothing. A deliverable naming a Location
    that cannot build it would enter the lifecycle and stall at a gate whose
    evidence nobody can produce, which is worse than a plain refusal: it
    puts a permanent blocked item in the register and calls it governance.
    """
    if not request.strip():
        raise HTTPException(400, "request text required")
    res = resolve(request)
    if res.capability is None:
        raise HTTPException(422, {"error": "unroutable", "reason": res.reason})

    kind = _DELIVERABLE_KIND.get(res.capability.id)
    if kind is None:  # pragma: no cover - the registry test forbids this
        raise HTTPException(500, f"no deliverable kind mapped for {res.capability.id}")

    from src.townhall.plm import get_plm  # noqa: PLC0415 - avoids an import cycle at startup

    item = get_plm().create(
        title=request.strip()[:200],
        kind=kind,
        location=res.capability.location,
        requested_by=requested_by,
    )
    return {
        "deliverable": item.to_dict(),
        "gate": get_plm().gate_status(item.id).to_dict(),
        "capability": res.capability.to_dict(),
        "url": endpoint_for(res.capability),
        # Carried forward so a caller cannot commission a DEGRADED or ABSENT
        # capability without having been told. The lifecycle will stop it at
        # a gate later; saying so now is cheaper.
        "deliverable_status": res.capability.status.value,
        "gap": res.capability.gap,
    }
