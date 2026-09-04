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
