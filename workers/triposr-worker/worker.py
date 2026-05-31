"""
Trancendos triposr-worker — Self-Hosted Worker
================================================
Image-to-3D mesh reconstruction using TripoSR (MIT licence,
Stability AI + Tripo AI) for Sashas Photo Studio.

Port: 8051
Zero-cost: FastAPI + TripoSR, no external service deps.
Gracefully degrades to 503 when the `tsr` package is not installed.
Model is loaded lazily on the first /reconstruct request.
"""

from __future__ import annotations
from src.entities.health_metadata import health_entity_block

import base64
import io
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

WORKER_PORT = 8051
WORKER_NAME = "triposr-worker"

OUTPUTS_DIR = Path(os.environ.get("OUTPUTS_DIR", "/app/outputs"))
MODELS_DIR = Path(os.environ.get("MODELS_DIR", "/app/models"))
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
MODELS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

STARTED_AT = datetime.now(timezone.utc)

# ---------------------------------------------------------------------------
# TripoSR availability + lazy loader
# ---------------------------------------------------------------------------

_TSR_AVAILABLE: bool | None = None
_MODEL: Any = None  # TripoSR model instance, loaded on first use
_MODEL_LOADING: bool = False


def _check_tsr_available() -> bool:
    global _TSR_AVAILABLE
    if _TSR_AVAILABLE is not None:
        return _TSR_AVAILABLE
    try:
        import importlib

        importlib.import_module("tsr")
        _TSR_AVAILABLE = True
    except ImportError:
        _TSR_AVAILABLE = False
    return _TSR_AVAILABLE


def _unavailable_response() -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={
            "available": False,
            "model": "TripoSR",
            "reason": "tsr package not installed",
            "hint": (
                "Install TripoSR: pip install git+https://github.com/VAST-AI-Research/TripoSR.git "
                "and its dependencies (torch, trimesh, etc.).  "
                "See https://github.com/VAST-AI-Research/TripoSR for full setup instructions."
            ),
        },
    )


def _get_model() -> Any:
    """Lazily load the TripoSR model.  Thread-unsafe but acceptable for single-worker usage."""
    global _MODEL, _MODEL_LOADING

    if _MODEL is not None:
        return _MODEL

    if _MODEL_LOADING:
        raise RuntimeError("Model is currently loading; please retry in a moment.")

    _MODEL_LOADING = True
    try:
        logger.info("Loading TripoSR model (this may take a minute)…")
        t0 = time.time()
        # TripoSR public API — import lazily so missing package doesn't crash on startup
        from tsr.system import TSR  # type: ignore[import]

        device = os.environ.get("TSR_DEVICE", "cpu")
        model_pretrained = os.environ.get(
            "TSR_MODEL",
            "stabilityai/TripoSR",
        )
        _MODEL = TSR.from_pretrained(
            model_pretrained,
            config_name="config.yaml",
            weight_name="model.ckpt",
        )
        _MODEL = _MODEL.to(device)
        _MODEL.eval()
        elapsed = time.time() - t0
        logger.info("TripoSR model loaded in %.1fs on device=%s", elapsed, device)
        return _MODEL
    finally:
        _MODEL_LOADING = False


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ReconstructRequest(BaseModel):
    image_b64: str
    output_format: str = "obj"  # "obj" or "glb"
    foreground_ratio: float = 0.85
    mc_resolution: int = 256


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _check_tsr_available():
        logger.info("TripoSR package detected; model will be loaded on first request.")
    else:
        logger.warning(
            "tsr package not found — /reconstruct will return 503 until TripoSR is installed."
        )
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="triposr-worker",
    description="Image-to-3D mesh reconstruction for Sashas Photo Studio (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    tsr_ok = _check_tsr_available()
    model_loaded = _MODEL is not None
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "available": tsr_ok,
        "model": "TripoSR",
        "model_loaded": model_loaded,
        "entity": health_entity_block(8051, WORKER_NAME),
    }


@app.post("/reconstruct")
async def reconstruct(req: ReconstructRequest):
    """Reconstruct a 3D mesh from a single base64-encoded image.

    Accepts ``{"image_b64": "<base64 PNG/JPEG>"}`` and returns the path
    to the generated .obj or .glb file.
    Returns 503 if the ``tsr`` package is not installed.
    """
    if not _check_tsr_available():
        return _unavailable_response()

    # Decode image
    try:
        image_bytes = base64.b64decode(req.image_b64)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid base64 image data: {exc}"},
        )

    try:
        from PIL import Image  # type: ignore[import]
    except ImportError:
        return JSONResponse(
            status_code=503,
            content={
                "available": False,
                "reason": "Pillow not installed",
                "hint": "pip install pillow",
            },
        )

    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": f"Cannot decode image: {exc}"},
        )

    # Load model (lazy)
    try:
        model = _get_model()
    except RuntimeError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": str(exc)},
        )
    except Exception as exc:
        logger.exception("Failed to load TripoSR model")
        return JSONResponse(
            status_code=500,
            content={"error": f"Model load failed: {exc}"},
        )

    # Run reconstruction
    run_id = uuid.uuid4().hex[:12]
    output_dir = OUTPUTS_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    ext = req.output_format.lower().lstrip(".")
    if ext not in ("obj", "glb"):
        ext = "obj"
    output_path = output_dir / f"mesh.{ext}"

    try:
        import torch  # type: ignore[import]

        logger.info("Running TripoSR reconstruction (run_id=%s)…", run_id)
        t0 = time.time()

        with torch.no_grad():
            scene_codes = model([image], device=os.environ.get("TSR_DEVICE", "cpu"))
            meshes = model.extract_mesh(
                scene_codes,
                resolution=req.mc_resolution,
            )

        mesh = meshes[0]

        if ext == "glb":
            mesh.export(str(output_path))
        else:
            # trimesh obj export
            mesh.export(str(output_path))

        elapsed = time.time() - t0
        logger.info(
            "Reconstruction complete in %.1fs → %s",
            elapsed,
            output_path,
        )

        return {
            "success": True,
            "run_id": run_id,
            "output_path": str(output_path),
            "output_format": ext,
            "elapsed_seconds": round(elapsed, 2),
        }

    except Exception as exc:
        logger.exception("TripoSR reconstruction failed (run_id=%s)", run_id)
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(exc), "run_id": run_id},
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
