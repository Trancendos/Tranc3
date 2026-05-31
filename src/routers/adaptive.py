"""Adaptive rotation and proactive management API (zero-cost)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/adaptive", tags=["adaptive"])


class ChainSwitchRequest(BaseModel):
    chain: str = Field(
        ...,
        description="zero_cost_full | zero_cost_cloud | zero_cost_reasoning | zero_cost_high_throughput",
    )


@router.get("/status")
async def adaptive_status():
    from src.adaptive.proactive_orchestrator import get_proactive_orchestrator
    from src.adaptive.provider_rotator import get_provider_rotator

    rotator = get_provider_rotator()
    proactive = get_proactive_orchestrator()
    return {
        "rotation": rotator.status(),
        "proactive": proactive.status(),
        "active_provider": rotator.active_provider(),
    }


@router.post("/rotate")
async def force_rotate():
    from src.adaptive.provider_rotator import get_provider_rotator

    rotator = get_provider_rotator()
    rotator._rotate()
    return rotator.status()


@router.post("/chain")
async def switch_chain(body: ChainSwitchRequest):
    from src.adaptive.provider_rotator import get_provider_rotator

    if not get_provider_rotator().switch_chain(body.chain):
        raise HTTPException(400, "Invalid or paid chain name")
    return get_provider_rotator().status()


@router.post("/proactive/run")
async def proactive_run_once():
    from src.adaptive.proactive_orchestrator import get_proactive_orchestrator

    run = await get_proactive_orchestrator().run_once()
    return {
        "health_rc": run.health_rc,
        "audit_rc": run.audit_rc,
        "swarm_rc": run.swarm_rc,
        "errors": run.errors,
    }
