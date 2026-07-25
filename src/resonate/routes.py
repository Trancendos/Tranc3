# src/resonate/routes.py
# Resonate — HTTP routes for empathy and understanding services.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.resonate.empathy import get_resonate

router = APIRouter(prefix="/resonate", tags=["resonate"])


def _require_self_or_admin(user_id: str, current_user: dict) -> None:
    caller_id = current_user.get("id") or current_user.get("sub")
    if caller_id != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only access your own data")


@router.get("/status")
async def resonate_status() -> Dict[str, Any]:
    return get_resonate().stats()


@router.post("/wrap")
async def wrap_response(
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    response: Optional[str] = body.get("response")
    if not response:
        return JSONResponse({"error": "response text is required"}, status_code=400)
    wrapped = get_resonate().wrap_response(
        response=response,
        sensitivity_level=body.get("sensitivity_level", "none"),
        user_mood=body.get("user_mood"),
        crisis_resources=bool(body.get("crisis_resources", False)),
    )
    return {"wrapped_response": wrapped}


@router.post("/escalate/{user_id}")
async def escalate(
    user_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    context: str = body.get("context", "")
    return await get_resonate().escalate_to_human(user_id=user_id, context=context)
