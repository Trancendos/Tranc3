# src/resonate/routes.py
# Resonate — HTTP routes for empathy and understanding services.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path
from fastapi.responses import Response, JSONResponse

from src.resonate.empathy import get_resonate

router = APIRouter(prefix="/resonate", tags=["resonate"])


@router.get("/status")
async def resonate_status() -> Dict[str, Any]:
    return get_resonate().stats()


@router.post("/wrap")
async def wrap_response(body: Dict[str, Any] = Body(...)) -> Response:
    response: Optional[str] = body.get("response")
    if not response:
        return JSONResponse({"error": "response text is required"}, status_code=400)
    wrapped = get_resonate().wrap_response(
        response=response,
        sensitivity_level=body.get("sensitivity_level", "none"),
        user_mood=body.get("user_mood"),
        crisis_resources=bool(body.get("crisis_resources", False)),
    )
    return {"wrapped_response": wrapped}  # type: ignore[return-value]


@router.post("/escalate/{user_id}")
async def escalate(
    user_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    context: str = body.get("context", "")
    return get_resonate().escalate_to_human(user_id=user_id, context=context)