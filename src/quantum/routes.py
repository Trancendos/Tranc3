# src/quantum/routes.py
# Think Tank — HTTP routes for quantum + deep research engines.
#
# Think Tank = The Quantum (qiskit) + The DeepMind (MCTS/planning) merged view.

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/thinktank", tags=["think-tank"])


def _quantum_status() -> Dict[str, Any]:
    try:
        from src.quantum.quantum_core import QuantumNeuralCore
        return {"quantum_core": "available", "backend": "qiskit-aer"}
    except Exception as exc:
        return {"quantum_core": "degraded", "note": str(exc)[:80]}


def _deepmind_status() -> Dict[str, Any]:
    try:
        from src.deepmind.mcts import MCTS
        return {"mcts": "available"}
    except Exception as exc:
        return {"mcts": "degraded", "note": str(exc)[:80]}


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
        return JSONResponse({"error": "Qiskit not installed — install qiskit qiskit-aer"}, status_code=503)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/deepmind/plan")
async def deepmind_plan(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Generate a plan using MCTS.
    Body: { problem: str, depth: int }
    """
    try:
        from src.deepmind.planning import PlanningEngine
        engine = PlanningEngine()
        problem = body.get("problem", "")
        depth = int(body.get("depth", 3))
        plan = engine.plan(problem, depth=depth) if hasattr(engine, "plan") else {"note": "planning engine scaffold — wire problem space to activate"}
        return {"problem": problem, "depth": depth, "plan": plan}
    except Exception as exc:
        return {"problem": body.get("problem", ""), "plan": None, "error": str(exc)[:120]}
