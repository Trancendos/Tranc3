# src/taimra/routes.py
# tAimra — HTTP routes for digital twin management.

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Path
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.taimra.digital_twin import get_taimra

router = APIRouter(prefix="/taimra", tags=["taimra"])


def _require_self_or_enterprise(user_id: str, current_user: dict) -> None:
    """Mirrors api.py's gdpr_erase() ownership check: users may act on their
    own twin; enterprise-tier users may act on any user's twin."""
    if current_user["id"] != user_id and current_user.get("tier") != "enterprise":
        raise HTTPException(status_code=403, detail="Can only access your own digital twin")


@router.get("/status")
async def taimra_status() -> Dict[str, Any]:
    return get_taimra().stats()


@router.post("/activate/{user_id}")
async def activate(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    twin = get_taimra().activate(user_id)
    return twin.to_dict()


@router.post("/deactivate/{user_id}")
async def deactivate(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    get_taimra().deactivate(user_id)
    return {"deactivated": user_id}


@router.get("/twin/{user_id}")
async def get_twin(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    twin = get_taimra()._twins.get(user_id)
    if not twin:
        return JSONResponse({"error": "Twin not found"}, status_code=404)
    return twin.to_dict()


@router.post("/record/{user_id}")
async def record_interaction(
    user_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    get_taimra().record_interaction(
        user_id,
        message=body.get("message", ""),
        topics=body.get("topics"),
        personality_used=body.get("personality_used"),
    )
    return {"recorded": True}


@router.get("/suggest/{user_id}")
async def suggest_personality(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    suggestion = get_taimra().suggest_personality(user_id)
    return {"suggested_personality": suggestion}


@router.get("/export/{user_id}")
async def export_twin(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    data = get_taimra().export(user_id)
    if data is None:
        return JSONResponse({"error": "Twin not found"}, status_code=404)
    return data


@router.delete("/twin/{user_id}")
async def delete_twin(
    user_id: str = Path(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    _require_self_or_enterprise(user_id, current_user)
    deleted = get_taimra().delete(user_id)
    if not deleted:
        return JSONResponse({"error": "Twin not found"}, status_code=404)
    return {"deleted": user_id}
