# src/cryptex/routes.py
from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from auth import get_current_user
from src.cryptex.threat_detector import ThreatSeverity, get_cryptex

router = APIRouter(prefix="/cryptex", tags=["cryptex"])


def _require_admin(current_user: dict = Depends(get_current_user)) -> None:
    """IP blocking and bounty-scan triggering are platform-wide security actions,
    not per-user data — gate them to admins rather than a self-or-enterprise check."""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="admin_required")


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
    signals = get_cryptex().analyse_request(
        path=path, body=body, headers=headers, actor=actor, ip=ip
    )
    return {
        "threats_detected": len(signals),
        "blocked": get_cryptex().is_blocked(actor=actor, ip=ip),
        "signals": [s.to_dict() for s in signals],
    }


@router.post("/block/{ip}")
async def block_ip(ip: str, _admin: None = Depends(_require_admin)):
    get_cryptex().block_ip(ip)
    return {"blocked": ip}


@router.delete("/block/{ip}")
async def unblock_ip(ip: str, _admin: None = Depends(_require_admin)):
    get_cryptex().unblock_ip(ip)
    return {"unblocked": ip}


# ─── Bug Bounty / CVE scanning ────────────────────────────────────────────────


@router.post("/bounty/scan")
async def run_bounty_scan(
    background_tasks: BackgroundTasks, _admin: None = Depends(_require_admin)
):
    """Trigger a full bounty scan (nuclei + pip-audit) against own infrastructure
    in the background. The scan target is fixed server-side (BOUNTY_TARGET_URL) —
    no caller-supplied target is accepted, per this module's own "own infrastructure
    only, never scan third parties" invariant."""
    from src.cryptex.bounty_hunter import run_full_scan

    background_tasks.add_task(run_full_scan)
    return {"status": "scan_started"}


@router.get("/bounty/candidates")
async def bounty_candidates(_admin: None = Depends(_require_admin)):
    """Return bounty-eligible findings not yet reported."""
    from src.cryptex.bounty_hunter import get_bounty_candidates

    return get_bounty_candidates()


@router.get("/bounty/summary")
async def bounty_summary(_admin: None = Depends(_require_admin)):
    """Return aggregate finding statistics."""
    from src.cryptex.bounty_hunter import get_summary

    return get_summary()
