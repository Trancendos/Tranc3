"""
Trance-One REST API — Tier 1 Sovereign status endpoints.
Mounted at /sovereign on the main FastAPI app.
"""

from __future__ import annotations

from fastapi import APIRouter

from trance_one.platform_manifest import Pillar, get_manifest
from trance_one.sovereign_controller import get_sovereign
from trance_one.tier_bridge import get_tier_bridge

router = APIRouter(prefix="/sovereign", tags=["trance-one"])


@router.get("/status")
async def sovereign_status():
    """Full Trance-One sovereign platform status."""
    return get_sovereign().status()


@router.get("/manifest")
async def platform_manifest():
    """Full 43-entity platform manifest."""
    manifest = get_manifest()
    return {
        "summary": manifest.summary(),
        "entities": [
            {
                "entity_id": e.entity_id,
                "display_name": e.display_name,
                "lead_ai": e.lead_ai,
                "pillar": e.pillar.value,
                "status": e.status,
                "src_path": e.src_path,
                "foundations": e.foundation_keys,
            }
            for e in manifest.all_entities()
        ],
    }


@router.get("/manifest/pillar/{pillar}")
async def manifest_by_pillar(pillar: str):
    """Entities in a specific pillar."""
    try:
        p = Pillar(pillar)
    except ValueError:
        from fastapi import HTTPException

        raise HTTPException(
            status_code=404,
            detail=f"Unknown pillar: {pillar}. Valid: {[p.value for p in Pillar]}",
        ) from None
    manifest = get_manifest()
    entities = manifest.by_pillar(p)
    return {
        "pillar": pillar,
        "count": len(entities),
        "entities": [
            {
                "entity_id": e.entity_id,
                "display_name": e.display_name,
                "lead_ai": e.lead_ai,
                "status": e.status,
            }
            for e in entities
        ],
    }


@router.post("/emergency/rotate/{entity_id}")
async def emergency_rotate(entity_id: str):
    """Sovereign-level emergency entity rotation (highest priority)."""
    get_sovereign().emergency_rotate(entity_id)
    return {"entity_id": entity_id, "action": "emergency_rotate", "tier": 1}


@router.get("/tier-bridge/commands")
async def recent_commands():
    """Recent inter-tier commands from the tier bridge."""
    return {"commands": get_tier_bridge().recent_commands(25)}


@router.get("/tier-bridge/events")
async def recent_events():
    """Recent inter-tier events from the tier bridge."""
    return {"events": get_tier_bridge().recent_events(25)}


@router.get("/intelligence")
async def sovereign_intelligence():
    """Pull full T2ance Prime Intelligence report as seen from Sovereign (Tier 1)."""
    try:
        from t2ance.prime_intelligence import get_intelligence_hub
        t2ance_report = get_intelligence_hub().full_report()
    except Exception as exc:
        t2ance_report = {"error": str(exc)}
    return {
        "sovereign_status": get_sovereign().status(),
        "t2ance_intelligence": t2ance_report,
    }


@router.post("/dispatch/{command_type}")
async def dispatch_command(
    command_type: str,
    target_tier: int = 2,
    target_entity: str | None = None,
    priority: int = 5,
):
    """Issue a tier command from Sovereign down the hierarchy."""
    from fastapi import HTTPException

    from trance_one.tier_bridge import TierCommand, TierCommandType

    try:
        cmd_type = TierCommandType(command_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown command type: {command_type}. Valid: {[c.value for c in TierCommandType]}",
        ) from None

    get_tier_bridge().issue_command(
        TierCommand(
            command_type=cmd_type,
            source_tier=1,
            target_tier=target_tier,
            target_entity=target_entity,
            priority=priority,
        )
    )
    return {
        "dispatched": command_type,
        "target_tier": target_tier,
        "target_entity": target_entity,
        "priority": priority,
    }
