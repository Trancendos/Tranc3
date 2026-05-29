# src/taimra/routes.py
# tAimra — HTTP routes for digital twin management.

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body, Path
from fastapi.responses import JSONResponse, Response

from src.taimra.digital_twin import get_taimra

router = APIRouter(prefix="/taimra", tags=["taimra"])


@router.get("/status")
async def taimra_status() -> Dict[str, Any]:
    return get_taimra().stats()


@router.post("/activate/{user_id}")
async def activate(user_id: str = Path(...)) -> Dict[str, Any]:
    twin = get_taimra().activate(user_id)
    return twin.to_dict()


@router.post("/deactivate/{user_id}")
async def deactivate(user_id: str = Path(...)) -> Dict[str, Any]:
    get_taimra().deactivate(user_id)
    return {"deactivated": user_id}


@router.get("/twin/{user_id}")
async def get_twin(user_id: str = Path(...)) -> Response:
    twin = get_taimra()._twins.get(user_id)
    if not twin:
        return JSONResponse({"error": "Twin not found"}, status_code=404)
    return twin.to_dict()  # type: ignore[return-value]


@router.post("/record/{user_id}")
async def record_interaction(
    user_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    get_taimra().record_interaction(
        user_id,
        message=body.get("message", ""),
        topics=body.get("topics"),
        personality_used=body.get("personality_used"),
    )
    return {"recorded": True}


@router.get("/suggest/{user_id}")
async def suggest_personality(user_id: str = Path(...)) -> Dict[str, Any]:
    suggestion = get_taimra().suggest_personality(user_id)
    return {"suggested_personality": suggestion}


@router.get("/export/{user_id}")
async def export_twin(user_id: str = Path(...)) -> Response:
    data = get_taimra().export(user_id)
    if data is None:
        return JSONResponse({"error": "Twin not found"}, status_code=404)
    return data  # type: ignore[return-value]


@router.delete("/twin/{user_id}")
async def delete_twin(user_id: str = Path(...)) -> Response:
    deleted = get_taimra().delete(user_id)
    if not deleted:
        return JSONResponse({"error": "Twin not found"}, status_code=404)
    return {"deleted": user_id}  # type: ignore[return-value]
