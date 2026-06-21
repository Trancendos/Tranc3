"""
src/routers/aeonmind.py — AeonMind engine status and dispatch endpoints.
"""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/aeonmind", tags=["aeonmind"])


@router.get("/status")
async def aeonmind_status_endpoint():
    from src.aeonmind_bridge import aeonmind_status
    return aeonmind_status()


@router.get("/orchestrator/status")
async def orchestrator_status():
    from src.aeonmind_bridge import get_orchestrator
    orch = get_orchestrator()
    return orch.status() if hasattr(orch, "status") else {"mode": "unknown"}


@router.post("/evolve")
async def trigger_evolution(generations: int = 5):
    from src.aeonmind_bridge import get_evolution_engine
    engine = get_evolution_engine()
    if engine is None:
        return {"error": "aeonmind unavailable"}
    engine.evolve(lambda dna: float(sum(dna)), generations=generations)
    best = engine.best_dna()
    return {"best_dna_length": len(best), "best_dna_sum": float(best.sum())}


@router.post("/quantum/decide")
async def quantum_decide():
    from src.aeonmind_bridge import get_quantum_circuit
    qc = get_quantum_circuit()
    if qc is None:
        return {"error": "aeonmind unavailable"}
    return {"decision": qc.decide()}
