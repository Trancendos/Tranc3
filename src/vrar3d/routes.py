# src/vrar3d/routes.py
# VRAR3D — HTTP routes for AR/VR wellbeing centre.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.vrar3d.wellbeing_centre import SceneType, get_vrar3d

router = APIRouter(prefix="/vrar3d", tags=["vrar3d"])


def _require_self_or_admin(user_id: str, current_user: dict) -> None:
    caller_id = current_user.get("id") or current_user.get("sub")
    if caller_id != user_id and current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Can only access your own data")


@router.get("/status")
async def vrar3d_status() -> Dict[str, Any]:
    return get_vrar3d().stats()


@router.get("/scenes")
async def list_scenes(
    type: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
) -> list:
    stype = None
    if type:
        try:
            stype = SceneType(type)
        except ValueError:
            valid = [t.value for t in SceneType]
            return JSONResponse({"error": f"Unknown type. Valid: {valid}"}, status_code=400)
    return [s.to_dict() for s in get_vrar3d().list_scenes(scene_type=stype)]


@router.get("/scenes/{scene_id}")
async def get_scene(
    scene_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    scene = get_vrar3d().get_scene(scene_id)
    if not scene:
        return JSONResponse({"error": "Scene not found"}, status_code=404)
    return scene.to_dict()


@router.get("/recommend")
async def recommend(
    mood: Optional[int] = Query(None),
    sensitivity_level: str = Query("none"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    scene = get_vrar3d().recommend_scene(mood=mood, sensitivity_level=sensitivity_level)
    if not scene:
        return JSONResponse({"error": "No suitable scene found"}, status_code=404)
    return scene.to_dict()


@router.post("/sessions")
async def start_session(
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    user_id = body.get("user_id")
    scene_id = body.get("scene_id")
    if not user_id or not scene_id:
        return JSONResponse({"error": "user_id and scene_id are required"}, status_code=400)
    _require_self_or_admin(user_id, current_user)
    session = get_vrar3d().start_session(
        user_id=user_id,
        scene_id=scene_id,
        mood_before=body.get("mood_before"),
    )
    if not session:
        return JSONResponse({"error": "Scene not found"}, status_code=404)
    return session.to_dict()


@router.post("/sessions/{session_id}/end")
async def end_session(
    session_id: str = Path(...),
    body: Dict[str, Any] = Body(default_factory=dict),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    session = get_vrar3d().end_session(session_id, mood_after=body.get("mood_after"))
    if not session:
        return JSONResponse({"error": "Session not found or already ended"}, status_code=404)
    return session.to_dict()
