"""
Master Worker API Router
========================
Exposes MAPE-K status, platform registry, zero-cost reports, and
blueprint generation via FastAPI routes.

Routes:
  GET  /master/status              — MAPE-K loop status
  GET  /master/platforms           — Platform registry snapshot
  GET  /master/zero-cost/status    — Current zero-cost assertion
  POST /master/platforms/{name}/rotate — Manually trigger rotation
  POST /master/blueprints/generate  — Generate deployment blueprint
  POST /master/zero-cost/assert     — Run zero-cost assertion now
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .adaptive_blueprints import BlueprintEngine, BlueprintSpec, BlueprintType
from .mape_k import MapeKLoop
from .platform_registry import PlatformCategory, PlatformRegistry
from .zero_cost_enforcer import ZeroCostEnforcer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/master", tags=["Master Worker"])

# Shared singleton instances (initialised on first access)
_registry: Optional[PlatformRegistry] = None
_loop: Optional[MapeKLoop] = None
_blueprint_engine = BlueprintEngine()


def get_registry() -> PlatformRegistry:
    global _registry
    if _registry is None:
        _registry = PlatformRegistry()
    return _registry


def get_loop() -> MapeKLoop:
    global _loop
    if _loop is None:
        _loop = MapeKLoop(registry=get_registry())
    return _loop


def get_enforcer() -> ZeroCostEnforcer:
    """Return the enforcer running inside the active MapeKLoop singleton."""
    return get_loop()._enforcer


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class BlueprintRequest(BaseModel):
    name: str
    blueprint_type: BlueprintType = BlueprintType.FASTAPI_WORKER
    port: int = 8000
    description: str = ""
    env_vars: list[str] = []
    dependencies: list[str] = []
    schedule: Optional[str] = None
    health_entity: Optional[str] = None
    platform_target: str = "fly_io"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/status")
async def master_status() -> Dict[str, Any]:
    """MAPE-K control loop status and recent events."""
    loop = get_loop()
    return {
        "master_worker": "Tranc3 Sovereign Orchestration Engine",
        "ci_provider": "forgejo",
        "edge_provider": "self_hosted_python",
        "github_actions": "DECOMMISSIONED",
        "cloudflare_workers": "DECOMMISSIONED — migrating to self-hosted Python",
        **loop.status(),
    }


@router.get("/platforms")
async def platform_registry() -> Dict[str, Any]:
    """Full platform registry snapshot with quota utilisation."""
    registry = get_registry()
    return {
        "platforms": registry.snapshot(),
        "best_ai_llm": (p.name if (p := registry.best_for(PlatformCategory.AI_LLM)) else None),
        "best_hosting": (p.name if (p := registry.best_for(PlatformCategory.HOSTING)) else None),
        "best_database": (p.name if (p := registry.best_for(PlatformCategory.DATABASE)) else None),
    }


@router.post("/platforms/{platform_name}/rotate")
async def rotate_platform(platform_name: str) -> Dict[str, Any]:
    """Manually trigger rotation away from the named platform."""
    enforcer = get_enforcer()
    fallback = await enforcer.rotate_platform(platform_name)
    if fallback is None:
        raise HTTPException(
            status_code=404,
            detail=f"Platform {platform_name!r} not found or no fallback available",
        )
    return {"rotated_from": platform_name, "rotated_to": fallback}


@router.get("/zero-cost/status")
async def zero_cost_status() -> Dict[str, Any]:
    """Current zero-cost enforcement status."""
    enforcer = get_enforcer()
    return enforcer.status()


@router.post("/zero-cost/assert")
async def zero_cost_assert() -> Dict[str, Any]:
    """Run the zero-cost assertion immediately."""
    enforcer = get_enforcer()
    result = enforcer.assert_zero_cost()
    return {
        "passed": result.passed,
        "total_estimated_cost_gbp": result.total_estimated_cost_gbp,
        "violations": result.violations,
        "checked_at": result.checked_at,
    }


@router.post("/blueprints/generate")
async def generate_blueprint(req: BlueprintRequest) -> Dict[str, Any]:
    """
    Generate a self-hosted Python worker blueprint.
    Returns rendered worker.py, Dockerfile, docker-compose snippet,
    requirements.txt, and Forgejo CI workflow.
    """
    spec = BlueprintSpec(
        name=req.name,
        blueprint_type=req.blueprint_type,
        port=req.port,
        description=req.description,
        env_vars=req.env_vars,
        dependencies=req.dependencies,
        schedule=req.schedule,
        health_entity=req.health_entity,
        platform_target=req.platform_target,
    )
    blueprint = _blueprint_engine.render(spec)
    return {
        "name": req.name,
        "blueprint_type": req.blueprint_type.value,
        "worker_py": blueprint.worker_py,
        "dockerfile": blueprint.dockerfile,
        "compose_snippet": blueprint.compose_snippet,
        "requirements_txt": blueprint.requirements_txt,
        "forgejo_workflow": blueprint.forgejo_workflow,
        "note": (
            "All CI/CD via Forgejo (The Workshop) — GitHub Actions decommissioned. "
            "All edge via self-hosted Python workers — Cloudflare Workers decommissioned."
        ),
    }


@router.post("/loop/start")
async def start_loop() -> Dict[str, Any]:
    """Start the MAPE-K control loop."""
    loop = get_loop()
    if loop._running:
        return {"status": "already_running", "cycle_count": loop._cycle_count}
    await loop.start()
    return {"status": "started", "message": "MAPE-K loop started"}


@router.post("/loop/stop")
async def stop_loop() -> Dict[str, Any]:
    """Stop the MAPE-K control loop."""
    loop = get_loop()
    await loop.stop()
    return {"status": "stopped", "cycles_completed": loop._cycle_count}
