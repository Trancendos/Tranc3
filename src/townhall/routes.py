# src/townhall/routes.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query
from fastapi.responses import JSONResponse

from src.townhall.governance import ComplianceResult, PolicyStatus, get_townhall

router = APIRouter(prefix="/townhall", tags=["townhall"])


@router.get("/status")
async def townhall_status():
    return get_townhall().status()


@router.get("/policies")
async def list_policies(active_only: bool = Query(True)):
    th = get_townhall()
    policies = th.active_policies() if active_only else list(th._policies.values())
    return [
        {
            "id": p.id,
            "name": p.name,
            "framework": p.framework,
            "status": p.status.value,
            "score": p.score,
            "articles": p.articles,
            "description": p.description,
        }
        for p in policies
    ]


@router.post("/check")
async def compliance_check(
    context: Dict[str, Any] = Body(...),
    policy_ids: Optional[List[str]] = Body(None),
    actor: Optional[str] = Body(None),
):
    """Run a governance check against the context dict."""
    results = get_townhall().check(context, policy_ids=policy_ids, actor=actor)
    overall = ComplianceResult.PASS
    for r in results.values():
        if r == ComplianceResult.FAIL:
            overall = ComplianceResult.FAIL
            break
        if r == ComplianceResult.WARN:
            overall = ComplianceResult.WARN
    return {"overall": overall.value, "results": {k: v.value for k, v in results.items()}}
