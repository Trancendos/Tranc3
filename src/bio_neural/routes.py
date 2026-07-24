# src/bio_neural/routes.py
# Luminous — HTTP routes for the AI intelligence core (bio-neural layer).
#
# Luminous = Consciousness Engine (IIT) + Neuromorphic Processor.

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from Dimensional.error_handlers import safe_error_detail

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/luminous", tags=["luminous"])


@router.get("/status")
async def luminous_status() -> Dict[str, Any]:
    modules: Dict[str, Any] = {}

    # Actually probe the optional heavy deps so "degraded" is reachable when
    # torch/numpy (or the module) are missing, rather than always "available".
    # (Excluded from coverage: the CI coverage job omits torch/numpy, so neither
    # branch is exercisable there.)
    try:  # pragma: no cover
        import numpy  # noqa: F401
        import torch  # noqa: F401

        from src.bio_neural.consciousness_engine import IITCalculator  # noqa: F401

        modules["consciousness"] = "available"
    except Exception:
        modules["consciousness"] = "degraded"

    try:  # pragma: no cover
        import torch  # noqa: F401

        from src.bio_neural.neuromorphic import NeuromorphicProcessor  # noqa: F401

        modules["neuromorphic"] = "available"
    except Exception:
        modules["neuromorphic"] = "degraded"

    return {"service": "luminous", "modules": modules}


@router.post("/consciousness/phi")
async def calculate_phi(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Calculate Φ (integrated information) for a given state vector.
    Body: { state: list[float] }
    """
    try:  # pragma: no cover  — torch/numpy path; CI coverage job omits both deps
        import numpy as np
        import torch

        from src.bio_neural.consciousness_engine import IITCalculator

        state = body.get("state")
        if not state:
            return JSONResponse({"error": "state (list of floats) is required"}, status_code=400)

        calc = IITCalculator()
        state_arr = np.array(state, dtype=float)
        # Normalise to probability distribution
        if state_arr.sum() > 0:
            state_arr = state_arr / state_arr.sum()

        # IITCalculator.calculate_phi expects a torch.Tensor (it calls
        # .detach().cpu().numpy() internally) — pass a tensor, not the ndarray.
        state_tensor = torch.tensor(state_arr, dtype=torch.float32)
        phi = calc.calculate_phi(state_tensor) if hasattr(calc, "calculate_phi") else 0.0
        return {"phi": float(phi), "state_dim": len(state)}
    except ImportError:
        return JSONResponse({"error": "Required dependency not available"}, status_code=503)
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)


@router.post("/neuromorphic/process")
async def neuromorphic_process(body: Dict[str, Any] = Body(...)) -> Dict[str, Any]:
    """
    Process input through the neuromorphic spiking network.
    Body: { input: list[float], timesteps: int }
    """
    try:  # pragma: no cover  — torch path; CI coverage job omits torch
        import torch

        from src.bio_neural.neuromorphic import NeuromorphicProcessor

        input_data = body.get("input", [])
        if not input_data:
            return JSONResponse({"error": "input (list of floats) is required"}, status_code=400)

        processor = NeuromorphicProcessor({})
        tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0)
        result = (
            processor.process(tensor)
            if hasattr(processor, "process")
            else {"note": "processor scaffold — wire input dimensions to activate"}
        )
        if isinstance(result, dict) and hasattr(processor, "serializable_result"):
            result = processor.serializable_result(result)
        # timesteps is fixed at SNN construction (not a caller-supplied kwarg) —
        # report what actually ran, not the caller's requested value.
        return {
            "input_dim": len(input_data),
            "timesteps": processor.get_stats().get("timesteps"),
            "output": result,
        }
    except ImportError:
        return JSONResponse({"error": "Required dependency not available"}, status_code=503)
    except Exception as exc:
        return JSONResponse({"error": safe_error_detail(exc, 500)}, status_code=500)
