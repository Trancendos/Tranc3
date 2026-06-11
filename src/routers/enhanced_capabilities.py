"""
src/routers/enhanced_capabilities.py — Enhanced Capabilities Router

Migrates routes that previously lived exclusively in api_enhanced.py into
the canonical api.py router tree. Covers:
  - /code/*      (The Lab — code generation, improvement, explanation)
  - /skills/*    (Turing's Hub — skill search, stats, bundle detection)
  - /plan, /reason  (Think Tank — DeepMind planning + chain-of-thought)
  - /healing/*   (self-repair dashboard, repair trigger, bot stats)

Auth: Endpoints that mutate state use `get_current_user`; read-only
endpoints are unauthenticated to support monitoring tools.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import get_current_user
from Dimensional.error_handlers import safe_error_detail
from Dimensional.sanitize import sanitize_for_log

_log = logging.getLogger("tranc3.enhanced_capabilities")

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────


class CodeGenRequest(BaseModel):
    description: str = Field(..., min_length=1, max_length=2048)
    language: str = Field(default="python", pattern=r"^[a-zA-Z0-9_+#-]{1,32}$")
    context: str = Field(default="", max_length=4096)
    constraints: List[str] = Field(default_factory=list, max_length=20)


class CodeImproveRequest(BaseModel):
    code: str = Field(..., min_length=1, max_length=32768)
    feedback: str = Field(default="", max_length=2048)
    language: str = Field(default="python", pattern=r"^[a-zA-Z0-9_+#-]{1,32}$")


class SkillSearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=512)
    top_k: int = Field(default=10, ge=1, le=50)
    category: Optional[str] = None


class DetectBundleRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2048)


class PlanRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=2048)
    state: Dict[str, Any] = Field(default_factory=dict)
    constraints: List[str] = Field(default_factory=list, max_length=20)


# ── Code Generation (The Lab) ─────────────────────────────────────────────────


@router.post("/code/generate", tags=["code"])
async def generate_code(
    req: CodeGenRequest,
    _: dict = Depends(get_current_user),
):
    """Generate code from a natural-language description."""
    try:
        from src.skills.code_generator import CodeGenerationRequest, code_generator

        result = await code_generator.generate(
            CodeGenerationRequest(
                language=req.language,
                description=req.description,
                context=req.context,
                constraints=req.constraints,
            ),
        )
        return {
            "code": result.code,
            "tests": result.tests,
            "explanation": result.explanation,
            "quality_score": result.quality_score,
            "issues": result.issues,
            "improvements": result.improvements,
        }
    except Exception as exc:
        _log.error("code.generate error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/code/improve", tags=["code"])
async def improve_code(
    req: CodeImproveRequest,
    _: dict = Depends(get_current_user),
):
    """Improve existing code based on feedback."""
    try:
        from src.skills.code_generator import code_generator

        result = await code_generator.improver.improve(req.code, req.feedback, req.language)
        return {
            "code": result.code,
            "explanation": result.explanation,
            "quality_score": result.quality_score,
            "improvements": result.improvements,
        }
    except Exception as exc:
        _log.error("code.improve error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/code/explain", tags=["code"])
async def explain_code(req: CodeImproveRequest):
    """Explain a code snippet (public — no auth required)."""
    try:
        from src.skills.code_generator import code_generator

        explanation = await code_generator.explain_code(req.code)
        return {"explanation": explanation}
    except Exception as exc:
        _log.error("code.explain error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


# ── Skills (Turing's Hub) ─────────────────────────────────────────────────────


@router.post("/skills/search", tags=["skills"])
async def search_skills(req: SkillSearchRequest):
    """Semantic skill search (public — no auth required)."""
    try:
        from src.skills.enhanced_registry import registry

        results = await registry.search(req.query, top_k=req.top_k, category=req.category)
        return {
            "results": [
                {
                    "skill": r.skill.to_dict(),
                    "score": r.score,
                    "match_reason": r.match_reason,
                }
                for r in results
            ],
            "total": len(results),
        }
    except Exception as exc:
        _log.error("skills.search error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.get("/skills/stats", tags=["skills"])
async def skill_stats():
    """Return skill registry statistics (public)."""
    try:
        from src.skills.enhanced_registry import registry

        return registry.get_stats()
    except Exception as exc:
        _log.error("skills.stats error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/skills/detect-bundle", tags=["skills"])
async def detect_bundle(req: DetectBundleRequest):
    """Detect the best skill bundle for a natural-language prompt (public)."""
    try:
        from src.skills.enhanced_registry import registry

        bundle = await registry.detect_and_load_bundle(req.prompt)
        if bundle:
            return {"bundle": bundle.id, "name": bundle.name, "skills": bundle.skills}
        return {"bundle": None}
    except Exception as exc:
        _log.error("skills.detect-bundle error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


# ── DeepMind — Planning + Reasoning (Think Tank) ─────────────────────────────


@router.post("/plan", tags=["deepmind"])
async def plan(
    req: PlanRequest,
    _: dict = Depends(get_current_user),
):
    """Generate an action plan for a goal using Think Tank's DeepMind planner."""
    try:
        from src.deepmind.planning import planner

        return await planner.plan_action(req.goal, req.state, req.constraints)
    except Exception as exc:
        _log.error("plan error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/reason", tags=["deepmind"])
async def chain_of_thought(
    req: PlanRequest,
    _: dict = Depends(get_current_user),
):
    """Chain-of-thought reasoning over a goal using Think Tank's reasoner."""
    try:
        from src.deepmind.planning import ChainOfThoughtReasoner

        return await ChainOfThoughtReasoner().reason(req.goal)
    except Exception as exc:
        _log.error("reason error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


# ── Self-Healing ──────────────────────────────────────────────────────────────


@router.get("/healing/dashboard", tags=["healing"])
async def healing_dashboard():
    """Public health dashboard — intended for monitoring tools."""
    try:
        from src.healing.health_monitor import health_monitor

        return await health_monitor.get_system_health()
    except Exception as exc:
        _log.warning("healing.dashboard error: %s", sanitize_for_log(exc))
        return {"status": "degraded", "error": "Health monitor unavailable"}


@router.post("/healing/repair", tags=["healing"])
async def trigger_repair(
    _: dict = Depends(get_current_user),
):
    """Trigger the self-repair engine (auth required)."""
    try:
        from src.healing.self_repair import repair_engine

        results = await repair_engine.evaluate_and_repair({"triggered_by": "api"})
        return {"repairs_applied": results}
    except Exception as exc:
        _log.error("healing.repair error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.get("/healing/bots", tags=["healing"])
async def bot_stats():
    """Return nanocode bot statistics (public)."""
    try:
        from src.healing.nanocode_bots import dispatcher

        return dispatcher.get_bot_stats()
    except Exception as exc:
        _log.warning("healing.bots error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc
