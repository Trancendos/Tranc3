# src/townhall/routes.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from src.townhall.agile import get_kanban_service
from src.townhall.documents import list_templates
from src.townhall.framework_registry import get_framework_registry
from src.townhall.governance import ComplianceResult, get_townhall

router = APIRouter(prefix="/townhall", tags=["townhall"])


@router.get("/status")
async def townhall_status():
    status = get_townhall().status()
    status["kanban_boards"] = len(get_kanban_service().list_boards())
    return status


@router.get("/frameworks")
async def townhall_frameworks():
    return get_framework_registry().to_dict()


@router.get("/documents/templates")
async def townhall_document_templates(category: Optional[str] = Query(None)):
    return {"templates": list_templates(category=category)}


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
    return {
        "overall": overall.value,
        "results": {k: v.value for k, v in results.items()},
    }
