# src/townhall/routes.py
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Query

from src.townhall.agile import get_kanban_service
from src.townhall.decision_bundles import DecisionIntent, get_bundle, validate_context
from src.townhall.documents import list_templates
from src.townhall.framework_registry import get_framework_registry
from src.townhall.governance import ComplianceResult, get_townhall, overall_compliance_result

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
    overall = overall_compliance_result(results)
    return {
        "overall": overall.value,
        "results": {k: v.value for k, v in results.items()},
    }


@router.post("/decisions/{intent}/preview")
async def townhall_decision_preview(
    intent: DecisionIntent,
    context: Dict[str, Any] = Body(...),
    actor: Optional[str] = Body(None),
):
    """Preview mandatory policy outcomes; never grant release or change authority.

    The intent determines the full server-owned policy set. Submitted evidence
    identifiers are unverified claims and cannot confer authorisation.
    """
    bundle = get_bundle(intent)
    input_errors = validate_context(intent, context)
    if input_errors:
        results = {policy_id: ComplianceResult.UNKNOWN for policy_id in bundle.policy_ids}
    else:
        evaluated = get_townhall().check(
            context, policy_ids=list(bundle.policy_ids), actor=actor
        )
        # Even a defective evaluator which omits a required policy cannot
        # accidentally turn an incomplete bundle into an overall PASS.
        results = {
            policy_id: evaluated.get(policy_id, ComplianceResult.UNKNOWN)
            for policy_id in bundle.policy_ids
        }

    overall = overall_compliance_result(results)
    return {
        "intent": intent.value,
        "bundle_version": bundle.version,
        "required_policies": list(bundle.policy_ids),
        "overall": overall.value,
        "results": {policy_id: status.value for policy_id, status in results.items()},
        "input_errors": list(input_errors),
        "preview_only": True,
        "authorization_granted": False,
    }
