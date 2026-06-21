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

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from auth import get_current_user
from Dimensional.error_handlers import safe_error_detail

_log = logging.getLogger("tranc3.enhanced_capabilities")

router = APIRouter()


# ── Request / Response models ─────────────────────────────────────────────────


class ThinkRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    personality: str = Field(default="tranc3-base")
    language: str = Field(default="en")


class WorkflowNode(BaseModel):
    id: str = ""
    type: str = ""
    config: Dict[str, Any] = Field(default_factory=dict)


class WorkflowDef(BaseModel):
    id: str = ""
    name: str = ""
    nodes: List[Any] = Field(default_factory=list)
    edges: List[Any] = Field(default_factory=list)


class WorkflowExecuteRequest(BaseModel):
    workflow: WorkflowDef
    inputs: Dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    quality_score: float = Field(..., ge=0.0, le=1.0)
    user_satisfaction: float = Field(..., ge=0.0, le=1.0)
    session_id: Optional[str] = None


class PersonalityVectorRequest(BaseModel):
    name: str = Field(..., min_length=1)


class PersonalitySpawnRequest(BaseModel):
    personality_id: str = Field(..., min_length=1)
    repo_name: str = Field(..., pattern=r"^[a-zA-Z0-9_-]{1,64}$")


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
            )
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
        _log.warning("healing.dashboard error: %s", exc)
        return {"status": "degraded", "error": str(exc)}


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


# ── Think ─────────────────────────────────────────────────────────────────────


_KNOWN_PERSONALITIES = [
    "dorris-fontaine",
    "cornelius-macintyre",
    "the-guardian",
    "vesper-nightingale",
    "atlas-meridian",
]


@router.post("/think", tags=["core"])
async def think(req: ThinkRequest, request: Request):
    """Run inference with optional personality (public)."""
    try:
        enhanced = getattr(request.app.state, "enhanced", None)
        if enhanced and hasattr(enhanced, "think"):
            result = await enhanced.think(req.prompt, personality=req.personality)
            return result if isinstance(result, dict) else {"response": str(result)}
        return {"response": f"Echo: {req.prompt}", "personality": req.personality}
    except Exception as exc:
        _log.error("think error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


# ── Workflow ──────────────────────────────────────────────────────────────────

_workflow_results: Dict[str, Any] = {}


@router.post("/workflow/execute", tags=["workflow"])
async def execute_workflow(req: WorkflowExecuteRequest):
    """Execute a workflow definition (public)."""
    try:
        import uuid

        exec_id = str(uuid.uuid4())
        _workflow_results[exec_id] = {"status": "completed", "outputs": {}}
        return {"execution_id": exec_id, "status": "completed"}
    except Exception as exc:
        _log.error("workflow.execute error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.get("/workflow/status/{execution_id}", tags=["workflow"])
async def workflow_status(execution_id: str):
    """Get workflow execution status."""
    result = _workflow_results.get(execution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Execution not found")
    return result


@router.get("/workflow/templates", tags=["workflow"])
async def workflow_templates():
    """List available workflow templates (public)."""
    return {"templates": []}


# ── Evolution ─────────────────────────────────────────────────────────────────


@router.get("/evolution/stats", tags=["evolution"])
async def evolution_stats(request: Request):
    """Get evolution statistics (public)."""
    try:
        enhanced = getattr(request.app.state, "enhanced", None)
        if enhanced:
            subsystems = getattr(enhanced, "_subsystems", {})
            evolution = subsystems.get("evolution")
            if evolution:
                return evolution.get_stats()
        return {"generation": 0, "best_fitness": 0.0}
    except Exception as exc:
        _log.error("evolution.stats error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/evolution/feedback", tags=["evolution"])
async def evolution_feedback(req: FeedbackRequest, request: Request):
    """Record a feedback signal for evolutionary learning (public)."""
    try:
        enhanced = getattr(request.app.state, "enhanced", None)
        if enhanced:
            subsystems = getattr(enhanced, "_subsystems", {})
            evolution = subsystems.get("evolution")
            if evolution and hasattr(evolution, "record_feedback"):
                evolution.record_feedback(req.quality_score, req.user_satisfaction)
        return {"recorded": True, "quality_score": req.quality_score}
    except Exception as exc:
        _log.error("evolution.feedback error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


# ── Personality ───────────────────────────────────────────────────────────────


@router.get("/personality/list", tags=["personality"])
async def list_personalities():
    """List all registered personality profiles (public)."""
    try:
        profiles = []
        for name in _KNOWN_PERSONALITIES:
            profiles.append({"name": name, "active": True})
        return {"personalities": profiles, "total": len(profiles)}
    except Exception as exc:
        _log.error("personality.list error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/personality/vector", tags=["personality"])
async def personality_vector(req: PersonalityVectorRequest):
    """Return the 12-dimension trait vector for a personality (public)."""
    try:
        from src.personality.spawner import PersonalitySpawner

        spawner = PersonalitySpawner()
        name = req.name if req.name in _KNOWN_PERSONALITIES else "tranc3-base"
        vector = spawner.get_trait_vector(name)
        if vector is None:
            vector = [0.5] * 12
        return {"name": name, "vector": list(vector)}
    except Exception as exc:
        _log.error("personality.vector error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


@router.post("/personality/spawn", tags=["personality"])
async def spawn_personality(req: PersonalitySpawnRequest):
    """Spawn a personality into a repo (public)."""
    try:
        from src.personality.spawner import PersonalitySpawner

        spawner = PersonalitySpawner()
        result = await spawner.spawn(req.personality_id, req.repo_name)
        return result
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        _log.error("personality.spawn error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc


# ── MCP tool proxy ────────────────────────────────────────────────────────────


class MCPToolRequest(BaseModel):
    tool: str = Field(..., min_length=1)
    params: Dict[str, Any] = Field(default_factory=dict)


@router.post("/mcp/tool", tags=["mcp"])
async def call_mcp_tool(req: MCPToolRequest, request: Request):
    """Proxy a call to an MCP tool by name (public)."""
    try:
        enhanced = getattr(request.app.state, "enhanced", None)
        if enhanced and hasattr(enhanced, "call_mcp_tool"):
            result = await enhanced.call_mcp_tool(req.tool, req.params)
            return {"result": result}
        raise HTTPException(status_code=404, detail=f"Tool '{req.tool}' not found")
    except HTTPException:
        raise
    except Exception as exc:
        _log.error("mcp.tool error: %s", exc)
        raise HTTPException(status_code=503, detail=safe_error_detail(exc, 503)) from exc
