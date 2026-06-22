"""
T2ance REST API — Tier 2 Prime Level status endpoints.
Mounted at /primes on the main FastAPI app.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from t2ance.domain_authority import PrimeDomain
from t2ance.prime_registry import get_prime_registry
from t2ance.tier_relay import get_relay

router = APIRouter(prefix="/primes", tags=["t2ance"])


@router.get("/status")
async def prime_status():
    """Full T2ance prime registry status."""
    return get_prime_registry().status()


@router.get("/{domain}")
async def prime_domain_status(domain: str):
    """Status for a specific Domain Prime."""
    try:
        d = PrimeDomain(domain)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown prime domain: {domain}. Valid: {[p.value for p in PrimeDomain]}",
        ) from None
    registry = get_prime_registry()
    prime = registry.get_prime(d)
    return prime.status()


@router.get("/entity/{entity_id}")
async def entity_prime(entity_id: str):
    """Which Domain Prime governs this entity."""
    registry = get_prime_registry()
    prime = registry.prime_for_entity(entity_id)
    if not prime:
        raise HTTPException(
            status_code=404,
            detail=f"No Domain Prime governs entity: {entity_id}",
        ) from None
    return prime.status()


@router.post("/rotate/{entity_id}")
async def request_rotation(entity_id: str, reason: str = "manual request"):
    """Request rotation approval through the appropriate Domain Prime."""
    approved = get_relay().route_rotation_request(entity_id, reason)
    return {"entity_id": entity_id, "approved": approved, "reason": reason}


@router.get("/intelligence")
async def intelligence_report():
    """Full adaptive intelligence report across all 9 Domain Primes."""
    from t2ance.prime_intelligence import get_intelligence_hub

    return get_intelligence_hub().full_report()


@router.post("/intelligence/signal/{entity_id}")
async def ingest_signal(
    entity_id: str,
    latency_ms: float = 0.0,
    error_rate: float = 0.0,
    request_rate: float = 0.0,
):
    """Ingest a health signal for a Tier 3 entity into the Prime intelligence layer."""
    from t2ance.prime_intelligence import EntityHealthSignal, get_intelligence_hub

    signal = EntityHealthSignal(
        entity_id=entity_id,
        latency_ms=latency_ms,
        error_rate=error_rate,
        request_rate=request_rate,
    )
    get_intelligence_hub().ingest(entity_id, signal)
    return {"ingested": True, "entity_id": entity_id}
