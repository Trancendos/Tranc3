# src/personality/turingshub/routes.py
# Turing's Hub — HTTP routes for AI personality creation centre.
#
# Exposes the PersonalitySpawner and EnhancedPersonalityMatrix via REST.

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse, Response

from Dimensional.error_handlers import safe_error_detail

router = APIRouter(prefix="/turingshub", tags=["turings-hub"])


def _spawner():
    from src.personality.spawner import PersonalitySpawner

    return PersonalitySpawner()


def _matrix():
    from src.personality.matrix import EnhancedPersonalityMatrix

    return EnhancedPersonalityMatrix()


@router.get("/status")
async def turings_hub_status() -> Dict[str, Any]:
    try:
        spawner = _spawner()
        profiles = (
            spawner.list_profiles()
            if hasattr(spawner, "list_profiles")
            else list(spawner._profiles.keys())
        )
    except Exception:
        profiles = []
    return {
        "service": "turings-hub",
        "status": "active",
        "personality_count": len(profiles),
        "personalities": profiles,
    }


@router.get("/personalities")
async def list_personalities() -> Response:
    spawner = _spawner()
    try:
        profiles = (
            spawner.list_profiles()
            if hasattr(spawner, "list_profiles")
            else list(spawner._profiles.keys())
        )
        return [{"id": pid, "profile": spawner._profiles.get(pid, {})} for pid in profiles]  # type: ignore[return-value]
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)


@router.get("/personalities/{personality_id}")
async def get_personality(personality_id: str = Path(...)) -> Response:
    spawner = _spawner()
    profile = spawner._profiles.get(personality_id)
    if not profile:
        return JSONResponse({"error": "Personality not found"}, status_code=404)
    return {"id": personality_id, "profile": profile}  # type: ignore[return-value]


@router.post("/spawn")
async def spawn_personality(body: Dict[str, Any] = Body(...)) -> Response:
    """
    Spawn a new repo scaffold for a personality instance.

    Body: { personality_id, repo_name, output_dir (optional) }
    """
    personality_id = body.get("personality_id")
    repo_name = body.get("repo_name")
    if not personality_id or not repo_name:
        return JSONResponse({"error": "personality_id and repo_name are required"}, status_code=400)
    output_dir = body.get("output_dir", "./spawned")
    try:
        result = _spawner().spawn(personality_id, repo_name, output_dir=output_dir)
        return result
    except ValueError as exc:
        return JSONResponse({"error": safe_error_detail(exc, 400)}, status_code=400)
    except FileExistsError as exc:
        return JSONResponse({"error": safe_error_detail(exc, 409)}, status_code=409)
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)


@router.get("/matrix/active")
async def active_personality() -> Dict[str, Any]:
    """Return the currently active personality from the matrix."""
    try:
        matrix = _matrix()
        active = getattr(matrix, "active_personality", None)
        if callable(active):
            active = active()
        return {"active_personality": active}
    except Exception as exc:
        return {"active_personality": None, "note": safe_error_detail(exc, 500)}
