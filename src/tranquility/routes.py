# src/tranquility/routes.py
# Tranquility — HTTP routes for wellbeing hub.

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse

from src.tranquility.wellbeing import get_tranquility

router = APIRouter(prefix="/tranquility", tags=["tranquility"])


@router.get("/status")
async def tranquility_status() -> Dict[str, Any]:
    return get_tranquility().stats()


@router.post("/mood/{user_id}")
async def log_mood(
    user_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
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
async def record_message(user_id: str = Path(...)) -> Dict[str, Any]:
    get_tranquility().record_message(user_id)
    return {"recorded": True}


@router.get("/break/{user_id}")
async def get_break_prompt(user_id: str = Path(...)) -> Dict[str, Any]:
    prompt = get_tranquility().get_break_prompt(user_id)
    return {"break_prompt": prompt}


@router.get("/profile/{user_id}")
async def get_profile(user_id: str = Path(...)) -> Dict[str, Any]:
    profile = get_tranquility()._profiles.get(user_id)
    if not profile:
        return JSONResponse({"error": "Profile not found"}, status_code=404)
    return profile.to_dict()


@router.get("/export/{user_id}")
async def export_data(user_id: str = Path(...)) -> Dict[str, Any]:
    data = get_tranquility().export_user_data(user_id)
    if data is None:
        return JSONResponse({"error": "No data found"}, status_code=404)
    return data


@router.delete("/data/{user_id}")
async def delete_data(user_id: str = Path(...)) -> Dict[str, Any]:
    deleted = get_tranquility().delete_user_data(user_id)
    if not deleted:
        return JSONResponse({"error": "No data found"}, status_code=404)
    return {"deleted": user_id}
