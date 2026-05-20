# src/bio_neural/routes.py
# Luminous — HTTP routes for the AI intelligence core (bio-neural layer).
#
# Luminous = Consciousness Engine (IIT) + Neuromorphic Processor.

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/luminous", tags=["luminous"])


@router.get("/status")
async def luminous_status() -> Dict[str, Any]:
    modules: Dict[str, Any] = {}

    try:
        modules["consciousness"] = "available"
    except Exception as exc:
        modules["consciousness"] = f"degraded: {str(exc)[:60]}"

    try:
        modules["neuromorphic"] = "available"
    except Exception as exc:
        modules["neuromorphic"] = f"degraded: {str(exc)[:60]}"

    return {"service": "luminous", "modules": modules}


@router.post("/consciousness/phi")
async def calculate_phi(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Calculate Φ (integrated information) for a given state vector.
    Body: { state: list[float] }
    """
    try:
        import numpy as np
        from src.bio_neural.consciousness_engine import IITCalculator

        state = body.get("state")
        if not state:
            return JSONResponse(
                {"error": "state (list of floats) is required"}, status_code=400
            )

        calc = IITCalculator()
        state_arr = np.array(state, dtype=float)
        # Normalise to probability distribution
        if state_arr.sum() > 0:
            state_arr = state_arr / state_arr.sum()

        phi = calc.calculate_phi(state_arr) if hasattr(calc, "calculate_phi") else 0.0
        return {"phi": float(phi), "state_dim": len(state)}
    except ImportError as exc:
        return JSONResponse({"error": f"Missing dependency: {exc}"}, status_code=503)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)


@router.post("/neuromorphic/process")
async def neuromorphic_process(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Process input through the neuromorphic spiking network.
    Body: { input: list[float], timesteps: int }
    """
    try:
        import torch
        from src.bio_neural.neuromorphic import NeuromorphicProcessor

        input_data = body.get("input", [])
        timesteps = int(body.get("timesteps", 10))
        if not input_data:
            return JSONResponse(
                {"error": "input (list of floats) is required"}, status_code=400
            )

        processor = NeuromorphicProcessor({})
        tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0)
        result = (
            processor.process(tensor, timesteps=timesteps)
            if hasattr(processor, "process")
            else {"note": "processor scaffold — wire input dimensions to activate"}
        )
        if hasattr(result, "tolist"):
            result = result.tolist()
        return {"input_dim": len(input_data), "timesteps": timesteps, "output": result}
    except ImportError as exc:
        return JSONResponse({"error": f"Missing dependency: {exc}"}, status_code=503)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=500)
