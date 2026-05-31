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


@router.get("/mode")
async def infrastructure_mode_status():
    from src.platform.infrastructure_mode import infrastructure_status

    return infrastructure_status()


class ModeSwitchRequest(BaseModel):
    mode: str = Field(..., description="CLOUD_ONLY | HYBRID | LOCAL_ONLY")


@router.post("/mode")
async def set_infrastructure_mode(body: ModeSwitchRequest):
    import os

    from src.platform.infrastructure_mode import PlatformInfraMode, infrastructure_status

    key = body.mode.strip().upper()
    if key not in {m.value for m in PlatformInfraMode}:
        raise HTTPException(400, "mode must be CLOUD_ONLY, HYBRID, or LOCAL_ONLY")
    os.environ["PLATFORM_INFRA_MODE"] = key
    # Reset rotator so next request picks up chain for new mode
    import src.adaptive.provider_rotator as pr
    import src.platform.layer_rotator as lr

    pr._rotator = None
    lr._layer_rotator = None
    return {
        "message": "Mode updated for this process (set PLATFORM_INFRA_MODE in .env to persist)",
        "status": infrastructure_status(),
    }


@router.get("/status")
async def adaptive_status():
    from src.adaptive.proactive_orchestrator import get_proactive_orchestrator
    from src.adaptive.provider_rotator import get_provider_rotator
    from src.platform.layer_rotator import get_layer_rotator

    rotator = get_provider_rotator()
    proactive = get_proactive_orchestrator()
    layers = get_layer_rotator()
    return {
        "rotation": rotator.status(),
        "layers": layers.status(),
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
        "layers": run.layers,
        "errors": run.errors,
    }


class LayerRotateRequest(BaseModel):
    layer: str | None = Field(
        None,
        description="database | knowledge | blob | hosting | frontend — omit to rotate all",
    )


@router.get("/layers")
async def platform_layers_status():
    from src.platform.layer_rotator import get_layer_rotator

    return get_layer_rotator().status()


@router.post("/layers/rotate")
async def platform_layers_rotate(body: LayerRotateRequest | None = None):
    from src.platform.layer_rotator import PlatformLayer, get_layer_rotator

    rotator = get_layer_rotator()
    layer = (body.layer if body else None) or None
    if layer:
        key = layer.strip().lower()
        valid = {m.value for m in PlatformLayer}
        if key not in valid:
            raise HTTPException(
                400,
                f"layer must be one of: {', '.join(sorted(valid))}",
            )
        rotator.force_rotate(key)
    else:
        rotator.force_rotate()
    return rotator.status()


@router.get("/layers/{layer}/active")
async def platform_layer_active(layer: str):
    from src.platform.layer_rotator import PlatformLayer, get_layer_rotator

    key = layer.strip().lower()
    if key not in {m.value for m in PlatformLayer}:
        raise HTTPException(404, "Unknown layer")
    rotator = get_layer_rotator()
    return {"layer": key, "active_backend": rotator.active_backend(key)}
