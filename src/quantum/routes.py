# src/quantum/routes.py
# Think Tank — HTTP routes for quantum + deep research engines.
#
# Think Tank = The Quantum (qiskit) + The DeepMind (MCTS/planning) merged view.

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from Dimensional.error_handlers import safe_error_detail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/thinktank", tags=["think-tank"])


@lru_cache(maxsize=1)
def _quantum_status() -> Dict[str, Any]:
    # Cached: a missing dependency doesn't get added to sys.modules, so an
    # uncached call would re-attempt the full import machinery on every poll.
    try:
        import qiskit_aer  # noqa: F401

        return {"quantum_core": "available", "backend": "qiskit-aer"}
    except Exception as exc:
        return {"quantum_core": "degraded", "note": safe_error_detail(exc, 503)}


@lru_cache(maxsize=1)
def _deepmind_status() -> Dict[str, Any]:
    try:
        from src.deepmind.planning import StrategicPlanner  # noqa: F401

        return {"mcts": "available"}
    except Exception as exc:
        return {"mcts": "degraded", "note": safe_error_detail(exc, 503)}


@router.get("/status")
async def thinktank_status() -> Dict[str, Any]:
    return {
        "service": "think-tank",
        "modules": {
            "quantum": _quantum_status(),
            "deepmind": _deepmind_status(),
        },
    }


@router.post("/quantum/simulate")
async def quantum_simulate(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Run a quantum circuit simulation via Qiskit Aer.
    Body: { qubits: int, shots: int, circuit_type: str }
    """
    try:
        from qiskit import QuantumCircuit
        from qiskit_aer import AerSimulator

        qubits = int(body.get("qubits", 2))
        shots = int(body.get("shots", 1024))
        qc = QuantumCircuit(qubits, qubits)
        qc.h(0)
        for i in range(qubits - 1):
            qc.cx(i, i + 1)
        qc.measure_all()

        sim = AerSimulator()
        job = sim.run(qc, shots=shots)
        result = job.result()
        counts = result.get_counts()
        return {"qubits": qubits, "shots": shots, "counts": dict(counts)}
    except ImportError:
        return JSONResponse(
            {"error": "Required dependency not available"},
            status_code=503,
        )
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)


@router.post("/deepmind/plan")
async def deepmind_plan(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Generate a plan using MCTS.
    Body: { problem: str, depth: int }
    """
    try:
        from src.deepmind.planning import PlanningConfig, StrategicPlanner

        problem = body.get("problem", "")
        depth = max(1, min(int(body.get("depth", 3)), 10))
        engine = StrategicPlanner(PlanningConfig(horizon=depth))
        plan = await engine.plan_action(problem, state={}, constraints=[])
        return {"problem": problem, "depth": depth, "plan": plan}
    except Exception as exc:
        try:
            depth = max(1, min(int(body.get("depth", 3)), 10))
        except (TypeError, ValueError):
            depth = None
        return {
            "problem": body.get("problem", ""),
            "depth": depth,
            "plan": None,
            "error": safe_error_detail(exc, 500),
        }
