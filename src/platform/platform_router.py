"""
Platform Router — REST API for entity rotation, scanning, and detection.
Mounted at /platform on the main FastAPI app.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException

from src.platform.entity_rotation import EntityID, get_entity_rotator
from src.platform.intelligent_scanner import get_scanner
from src.platform.smart_detector import get_detector
from src.platform.zero_cost_service_map import audit_zero_cost, get_foundation

router = APIRouter(prefix="/platform", tags=["platform"])


# ---------------------------------------------------------------------------
# Entity Rotation endpoints
# ---------------------------------------------------------------------------

@router.get("/rotation/status")
async def rotation_status():
    """Full rotation status for all 43 entities."""
    rotator = get_entity_rotator()
    return {
        "entities": rotator.status_all(),
        "zero_cost_audit": rotator.zero_cost_audit(),
    }


@router.get("/rotation/{entity_id}")
async def entity_rotation_status(entity_id: str):
    """Rotation status for a specific entity."""
    try:
        eid = EntityID(entity_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {entity_id}") from None
    rotator = get_entity_rotator()
    pool = rotator.get_pool(eid)
    if not pool:
        raise HTTPException(status_code=404, detail="No rotation pool found")
    return pool.to_status()


@router.post("/rotation/{entity_id}/failover")
async def trigger_failover(entity_id: str):
    """Manually trigger failover for an entity (emergency rotation)."""
    try:
        eid = EntityID(entity_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=f"Unknown entity: {entity_id}") from None
    rotator = get_entity_rotator()
    pool = rotator.get_pool(eid)
    if not pool:
        raise HTTPException(status_code=404, detail="No rotation pool found")
    new_instance = pool.rotate()
    return {
        "entity": entity_id,
        "rotated_to": new_instance.url if new_instance else None,
        "rotation_count": pool.rotation_count,
    }


@router.get("/zero-cost/audit")
async def zero_cost_audit():
    """Verify all 43 entities use only zero-cost foundations."""
    rotation_audit = get_entity_rotator().zero_cost_audit()
    foundation_audit = audit_zero_cost()
    return {
        "rotation_instances_compliant": rotation_audit["compliant"],
        "foundation_map_compliant": foundation_audit["compliant"],
        "fully_compliant": rotation_audit["compliant"] and foundation_audit["compliant"],
        "rotation_audit": rotation_audit,
        "foundation_audit": foundation_audit,
    }


@router.get("/foundations/{entity_id}")
async def entity_foundations(entity_id: str):
    """Return the zero-cost open-source foundations for an entity."""
    foundations = get_foundation(entity_id)
    return {
        "entity_id": entity_id,
        "foundations": [
            {
                "name": f.name,
                "license": f.license,
                "github_url": f.github_url,
                "docker_image": f.docker_image,
                "self_hosted_free": f.self_hosted_free,
                "notes": f.notes,
            }
            for f in foundations
        ],
    }


# ---------------------------------------------------------------------------
# Intelligent Scanner endpoints
# ---------------------------------------------------------------------------

@router.get("/scan/last")
async def last_scan_report():
    """Return the last completed scan report."""
    scanner = get_scanner()
    report = scanner.last_report()
    if not report:
        return {"message": "No scan has been run yet. POST /platform/scan/run to trigger one."}
    return report


@router.post("/scan/run")
async def run_scan(background_tasks: BackgroundTasks):
    """Trigger a full intelligent security scan (runs in background)."""
    scanner = get_scanner()
    background_tasks.add_task(scanner.run_full_scan)
    return {"message": "Full platform scan started", "status": "running"}


# ---------------------------------------------------------------------------
# Smart Detector endpoints
# ---------------------------------------------------------------------------

@router.get("/detector/alerts")
async def get_alerts():
    """Return all pending smart detector alerts."""
    detector = get_detector()
    return {
        "alerts": detector.peek_alerts(),
        "count": len(detector.peek_alerts()),
    }


@router.get("/detector/health")
async def platform_health():
    """Platform-wide smart health summary from the detector."""
    detector = get_detector()
    return detector.platform_health_summary()


@router.get("/detector/health/{entity_id}")
async def entity_health(entity_id: str):
    """Health snapshot for a specific entity from the detector."""
    detector = get_detector()
    return detector.entity_health(entity_id)


@router.post("/detector/flush")
async def flush_alerts():
    """Flush (clear) all pending alerts after they've been processed."""
    detector = get_detector()
    alerts = detector.flush_alerts()
    return {"flushed": len(alerts)}
