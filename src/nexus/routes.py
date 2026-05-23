# src/nexus/routes.py
# The Nexus — HTTP routes for AI communications and transfer hub.

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from shared_core.error_handlers import safe_error_detail

router = APIRouter(prefix="/nexus", tags=["the-nexus"])


def _nexus():
    from src.nexus.hub import get_nexus

    return get_nexus()


@router.get("/status")
async def nexus_status() -> Dict[str, Any]:
    return _nexus().status()


@router.post("/publish")
async def publish(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    topic = body.get("topic")
    payload = body.get("payload", {})
    sender = body.get("sender", "api")
    if not topic:
        return JSONResponse({"error": "topic is required"}, status_code=400)
    try:
        from src.nexus.hub import MessagePriority

        raw_priority = body.get("priority", "normal")
        priority_map = {
            "low": MessagePriority.LOW,
            "normal": MessagePriority.NORMAL,
            "high": MessagePriority.HIGH,
            "critical": MessagePriority.CRITICAL,
        }
        priority = priority_map.get(raw_priority, MessagePriority.NORMAL)
        msg = _nexus().publish(
            topic=topic,
            payload=payload,
            sender=sender,
            priority=priority,
            ttl_seconds=float(body.get("ttl_seconds", 30.0)),
        )
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)
    return {"published": msg.id, "topic": topic, "priority": priority.name}


@router.post("/send")
async def send_direct(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    recipient = body.get("recipient")
    payload = body.get("payload", {})
    sender = body.get("sender", "api")
    if not recipient:
        return JSONResponse({"error": "recipient is required"}, status_code=400)
    try:
        msg = await _nexus().send(recipient=recipient, payload=payload, sender=sender)
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)
    if msg is None:
        return JSONResponse({"error": "Recipient service not registered"}, status_code=404)
    return {"sent": msg.id, "recipient": recipient}


@router.post("/route/inference")
async def route_inference(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    prompt = body.get("prompt")
    if not prompt:
        return JSONResponse({"error": "prompt is required"}, status_code=400)
    try:
        result = await _nexus().route_inference(
            prompt=prompt,
            personality=body.get("personality"),
            sender=body.get("sender", "api"),
        )
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)
    return result
