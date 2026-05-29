# src/lab/routes.py
# The Lab — HTTP routes for AI-powered code creation platform.

from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Path, Query
from fastapi.responses import JSONResponse

from src.lab.code_lab import TaskType, get_lab

router = APIRouter(prefix="/lab", tags=["the-lab"])


@router.get("/status")
async def lab_status() -> Dict[str, Any]:
    return get_lab().stats()


@router.post("/sessions")
async def create_session(body: Dict[str, Any] = Body(default_factory=dict)) -> Dict[str, Any]:
    raw_task = body.get("task_type", "generate")
    try:
        task_type = TaskType(raw_task)
    except ValueError:
        valid = [t.value for t in TaskType]
        return JSONResponse({"error": f"Unknown task_type. Valid: {valid}"}, status_code=400)
    session = get_lab().create_session(
        user_id=body.get("user_id"),
        language=body.get("language", "python"),
        task_type=task_type,
    )
    return session.to_dict()


@router.get("/sessions")
async def list_sessions(user_id: Optional[str] = Query(None)) -> list:
    return [s.to_dict() for s in get_lab().list_sessions(user_id=user_id)]


@router.get("/sessions/{session_id}")
async def get_session(session_id: str = Path(...)) -> Dict[str, Any]:
    session = get_lab().get_session(session_id)
    if not session:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return session.to_dict()


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    content = body.get("content")
    if not content:
        return JSONResponse({"error": "content is required"}, status_code=400)
    msg = get_lab().send_message(
        session_id=session_id,
        content=content,
        role=body.get("role", "user"),
    )
    if msg is None:
        return JSONResponse({"error": "Session not found or not active"}, status_code=404)
    return {"role": msg.role, "content": msg.content, "timestamp": msg.timestamp}


@router.post("/sessions/{session_id}/context")
async def add_context(
    session_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    filename = body.get("filename")
    content = body.get("content", "")
    if not filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)
    ok = get_lab().add_context_file(session_id, filename, content)
    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"added": filename}


@router.post("/sessions/{session_id}/artifacts")
async def save_artifact(
    session_id: str = Path(...),
    body: Dict[str, Any] = Body(...),
) -> Dict[str, Any]:
    filename = body.get("filename")
    content = body.get("content", "")
    if not filename:
        return JSONResponse({"error": "filename is required"}, status_code=400)
    ok = get_lab().save_artifact(session_id, filename, content)
    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"saved": filename}


@router.post("/sessions/{session_id}/close")
async def close_session(session_id: str = Path(...)) -> Dict[str, Any]:
    ok = get_lab().close_session(session_id)
    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"closed": session_id}


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str = Path(...)) -> Dict[str, Any]:
    ok = get_lab().delete_session(session_id)
    if not ok:
        return JSONResponse({"error": "Session not found"}, status_code=404)
    return {"deleted": session_id}
