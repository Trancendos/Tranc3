# src/cryptex/routes.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import JSONResponse

from src.cryptex.threat_detector import ThreatSeverity, get_cryptex

router = APIRouter(prefix="/cryptex", tags=["cryptex"])


@router.get("/stats")
async def cryptex_stats():
    return get_cryptex().stats()


@router.get("/signals")
async def list_signals(
    limit: int = Query(50, ge=1, le=200),
    min_severity: Optional[str] = Query(None),
):
    cx = get_cryptex()
    sev = None
    if min_severity:
        try:
            sev = ThreatSeverity(min_severity)
        except ValueError:
            return JSONResponse({"error": f"Unknown severity: {min_severity}"}, status_code=400)
    signals = cx.recent_signals(limit=limit, min_severity=sev)
    return [s.to_dict() for s in signals]


@router.post("/analyse")
async def analyse_context(context: Dict[str, Any] = Body(...), actor: Optional[str] = Body(None)):
    """Run threat analysis on an arbitrary context dict."""
    signals = get_cryptex().analyse(context, actor=actor)
    return {
        "threats_detected": len(signals),
        "signals": [s.to_dict() for s in signals],
    }


@router.post("/analyse/request")
async def analyse_request(request: Request, actor: Optional[str] = Query(None)):
    """Analyse an incoming HTTP request for threats."""
    path = str(request.url.path)
    try:
        body = (await request.body()).decode("utf-8", errors="replace")[:2000]
    except Exception:
        body = ""
    headers = dict(request.headers)
    ip = request.client.host if request.client else None
    signals = get_cryptex().analyse_request(path=path, body=body, headers=headers, actor=actor, ip=ip)
    return {
        "threats_detected": len(signals),
        "blocked": get_cryptex().is_blocked(actor=actor, ip=ip),
        "signals": [s.to_dict() for s in signals],
    }


@router.post("/block/{ip}")
async def block_ip(ip: str):
    get_cryptex().block_ip(ip)
    return {"blocked": ip}


@router.delete("/block/{ip}")
async def unblock_ip(ip: str):
    get_cryptex().unblock_ip(ip)
    return {"unblocked": ip}
