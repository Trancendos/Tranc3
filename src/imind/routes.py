# src/imind/routes.py
# I-Mind — HTTP routes for sensitivity assessment.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.imind.protocol import get_imind

router = APIRouter(prefix="/imind", tags=["i-mind"])


@router.get("/status")
async def imind_status() -> Dict[str, Any]:
    return {"service": "i-mind", "status": "active"}


@router.post("/assess")
async def assess(
    body: Dict[str, Any] = Body(...),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    text: Optional[str] = body.get("text")
    actor: Optional[str] = body.get("actor")
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    assessment = get_imind().assess(text, actor=actor)
    return assessment.to_dict()
