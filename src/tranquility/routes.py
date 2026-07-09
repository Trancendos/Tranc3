# src/tranquility/routes.py
# Tranquility — HTTP routes for wellbeing hub.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.tranquility.wellbeing import get_tranquility

router = APIRouter(prefix="/tranquility", tags=["tranquility"])


def _require_self_or_admin(user_id: str, current_user: dict) -> None:
    """Mirrors api.py's gdpr_erase() ownership check: users may act on their
    own data; admins may act on any user's data.

    Real JWT payloads (src/auth/tokens.py) carry the caller's identity under
    the standard "sub" claim, not "id" — accept either so this doesn't 500
    for genuine callers with real tokens. The "enterprise" override this
    originally mirrored from gdpr_erase() checked `tier == "enterprise"`, but
    real tokens carry `tier` as a numeric int (never that string) — checking
    `role == "admin"` instead uses a claim real tokens actually carry."""
    caller_id = current_user.get("id") or current_user.get("sub")
    if caller_id != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only access your own data")


@router.get("/status")
async def tranquility_status() -> Dict[str, Any]:
    return get_tranquility().stats()


@router.post("/mood/{user_id}")
async def log_mood(
    user_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    mood: Optional[int] = body.get("mood")
    if mood is None:
        return JSONResponse({"error": "mood (1-5) is required"}, status_code=400)
    entry = get_tranquility().log_mood(
        user_id,
        mood=int(mood),
        notes=body.get("notes", ""),
        tags=body.get("tags"),
    )
    return entry.to_dict()


@router.post("/message/{user_id}")
async def record_message(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    get_tranquility().record_message(user_id)
    return {"recorded": True}


@router.get("/break/{user_id}")
async def get_break_prompt(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    prompt = get_tranquility().get_break_prompt(user_id)
    return {"break_prompt": prompt}


@router.get("/profile/{user_id}")
async def get_profile(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    profile = get_tranquility()._profiles.get(user_id)
    if not profile:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    return profile.to_dict()


@router.get("/export/{user_id}")
async def export_data(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    data = get_tranquility().export_user_data(user_id)
    if data is None:
        return JSONResponse({"error": "No data found"}, status_code=404)
    return data


@router.delete("/data/{user_id}")
async def delete_data(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_admin(user_id, current_user)
    deleted = get_tranquility().delete_user_data(user_id)
    if not deleted:
        return JSONResponse({"error": "No data found"}, status_code=404)
    return {"deleted": user_id}
