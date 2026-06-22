"""
Sashas Photo Studio — Port 8051
================================
Photo & image generation centre. Full ComfyUI pipeline integration.

Adaptive fallback chain:
  1. ComfyUI (self-hosted) — primary
  2. AUTOMATIC1111 WebUI (/sdapi/v1/txt2img) — secondary
  3. Offline placeholder — stub

Zero-cost mandate: local ComfyUI first, then A1111, then placeholder.

Entity: Sashas Photo Studio
Lead AI: Madam Krystal
Foundation: Stable Diffusion + ComfyUI
"""

from __future__ import annotations

import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PORT = int(os.getenv("PORT", "8051"))
WORKER_NAME = "sashas-photo-studio"
VERSION = "2.0.0"

COMFYUI_URL = os.getenv("COMFYUI_URL", "http://localhost:8188").rstrip("/")
A1111_URL = os.getenv("A1111_URL", "http://localhost:7860").rstrip("/")

STARTED_AT = datetime.now(timezone.utc)
START_TIME = time.time()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_http_timeout = httpx.Timeout(120.0, connect=5.0)
_jobs: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=2000)
    negative_prompt: str = ""
    width: int = Field(512, ge=64, le=2048)
    height: int = Field(512, ge=64, le=2048)
    steps: int = Field(20, ge=1, le=150)
    cfg_scale: float = Field(7.0, ge=1.0, le=30.0)
    model: str = "v1-5-pruned-emaonly"
    seed: int = -1


class UpscaleRequest(BaseModel):
    job_id: str
    scale_factor: float = Field(2.0, ge=1.5, le=4.0)


# ---------------------------------------------------------------------------
# ComfyUI helpers
# ---------------------------------------------------------------------------

_COMFYUI_WORKFLOW_TEMPLATE: dict[str, Any] = {
    "3": {
        "class_type": "KSampler",
        "inputs": {
            "cfg": 7,
            "denoise": 1,
            "latent_image": ["5", 0],
            "model": ["4", 0],
            "negative": ["7", 0],
            "positive": ["6", 0],
            "sampler_name": "euler",
            "scheduler": "normal",
            "seed": 12345,
            "steps": 20,
        },
    },
    "4": {
        "class_type": "CheckpointLoaderSimple",
        "inputs": {"ckpt_name": "v1-5-pruned-emaonly.safetensors"},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "inputs": {"batch_size": 1, "height": 512, "width": 512},
    },
    "6": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": "beautiful landscape"}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"clip": ["4", 1], "text": ""}},
    "8": {"class_type": "VAEDecode", "inputs": {"samples": ["3", 0], "vae": ["4", 2]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "tranc3", "images": ["8", 0]}},
}


async def _comfyui_generate(req: GenerateRequest) -> str:
    workflow = json.loads(json.dumps(_COMFYUI_WORKFLOW_TEMPLATE))
    workflow["3"]["inputs"]["cfg"] = req.cfg_scale
    workflow["3"]["inputs"]["steps"] = req.steps
    workflow["3"]["inputs"]["seed"] = (
        req.seed if req.seed >= 0 else int(time.time() * 1000) % 2**32
    )
    workflow["4"]["inputs"]["ckpt_name"] = f"{req.model}.safetensors"
    workflow["5"]["inputs"]["width"] = req.width
    workflow["5"]["inputs"]["height"] = req.height
    workflow["6"]["inputs"]["text"] = req.prompt
    workflow["7"]["inputs"]["text"] = req.negative_prompt

    payload = {"prompt": workflow, "client_id": str(uuid.uuid4())}
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.post(f"{COMFYUI_URL}/prompt", json=payload)
        resp.raise_for_status()
        return resp.json()["prompt_id"]


async def _comfyui_poll(prompt_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{COMFYUI_URL}/history/{prompt_id}")
        resp.raise_for_status()
        return resp.json()


async def _comfyui_fetch_image(
    filename: str, subfolder: str = "", folder_type: str = "output"
) -> bytes:
    params = {"filename": filename, "subfolder": subfolder, "type": folder_type}
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{COMFYUI_URL}/view", params=params)
        resp.raise_for_status()
        return resp.content


async def _comfyui_list_models() -> list[str]:
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.get(f"{COMFYUI_URL}/object_info")
        resp.raise_for_status()
        data = resp.json()
        checkpoints = (
            data.get("CheckpointLoaderSimple", {})
            .get("input", {})
            .get("required", {})
            .get("ckpt_name", [[], {}])[0]
        )
        return checkpoints if isinstance(checkpoints, list) else []


# ---------------------------------------------------------------------------
# AUTOMATIC1111 fallback
# ---------------------------------------------------------------------------


async def _a1111_generate(req: GenerateRequest) -> str:
    payload = {
        "prompt": req.prompt,
        "negative_prompt": req.negative_prompt,
        "width": req.width,
        "height": req.height,
        "steps": req.steps,
        "cfg_scale": req.cfg_scale,
        "seed": req.seed,
    }
    async with httpx.AsyncClient(timeout=_http_timeout) as client:
        resp = await client.post(f"{A1111_URL}/sdapi/v1/txt2img", json=payload)
        resp.raise_for_status()
        data = resp.json()
        images_b64 = data.get("images", [])
        job_id = str(uuid.uuid4())
        _jobs[job_id] = {
            "status": "completed",
            "source": "a1111",
            "images_b64": images_b64,
            "prompt": req.prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return job_id


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------
app = FastAPI(title="Sashas Photo Studio", description="Photo & image generation centre", version=VERSION)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict[str, Any]:
    return {
        "service": WORKER_NAME,
        "status": "ok",
        "version": VERSION,
        "uptime": time.time() - START_TIME,
    }


@app.get("/status")
async def status() -> dict[str, Any]:
    comfyui_ok = False
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(3.0)) as client:
            r = await client.get(f"{COMFYUI_URL}/system_stats")
            comfyui_ok = r.status_code == 200
    except Exception:
        pass
    return {
        "entity": "Sashas Photo Studio",
        "lead_ai": "Madam Krystal",
        "version": VERSION,
        "comfyui_reachable": comfyui_ok,
        "comfyui_url": COMFYUI_URL,
        "uptime": time.time() - START_TIME,
    }


@app.post("/photo/generate")
async def generate(req: GenerateRequest) -> dict[str, Any]:
    """Submit an image generation job. Returns a job_id to poll."""
    job_id = str(uuid.uuid4())

    # Primary: ComfyUI
    try:
        prompt_id = await _comfyui_generate(req)
        _jobs[job_id] = {
            "status": "queued",
            "source": "comfyui",
            "prompt_id": prompt_id,
            "prompt": req.prompt,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.info("ComfyUI job %s -> prompt_id %s", job_id, prompt_id)
        return {"job_id": job_id, "status": "queued", "source": "comfyui"}
    except Exception as exc:
        logger.warning("ComfyUI unavailable: %s -- trying A1111", exc)

    # Fallback: AUTOMATIC1111
    try:
        job_id = await _a1111_generate(req)
        return {"job_id": job_id, "status": "completed", "source": "a1111"}
    except Exception as exc2:
        logger.warning("A1111 unavailable: %s -- using offline stub", exc2)

    # Offline stub
    _jobs[job_id] = {
        "status": "completed",
        "source": "offline",
        "prompt": req.prompt,
        "placeholder": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"job_id": job_id, "status": "completed", "source": "offline", "placeholder": True}


@app.post("/generate")
async def generate_compat(req: GenerateRequest) -> dict[str, Any]:
    """Legacy endpoint — delegates to /photo/generate."""
    return await generate(req)


@app.get("/photo/status/{job_id}")
async def get_job_status(job_id: str) -> dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["source"] == "comfyui" and job["status"] == "queued":
        try:
            history = await _comfyui_poll(job["prompt_id"])
            if job["prompt_id"] in history:
                entry = history[job["prompt_id"]]
                status_info = entry.get("status", {})
                if status_info.get("completed"):
                    outputs = entry.get("outputs", {})
                    images = [
                        img
                        for node_out in outputs.values()
                        for img in node_out.get("images", [])
                    ]
                    job["status"] = "completed"
                    job["images"] = images
                elif status_info.get("status_str") == "error":
                    job["status"] = "failed"
        except Exception as exc:
            logger.warning("ComfyUI poll failed: %s", exc)

    return {"job_id": job_id, **job}


@app.get("/photo/result/{job_id}")
async def get_result(job_id: str) -> Response:
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=202, detail=f"Job not ready: {job['status']}")

    if job["source"] == "comfyui":
        images = job.get("images", [])
        if not images:
            raise HTTPException(status_code=404, detail="No images found in job")
        img_info = images[0]
        try:
            image_bytes = await _comfyui_fetch_image(
                img_info["filename"],
                img_info.get("subfolder", ""),
                img_info.get("type", "output"),
            )
            return Response(content=image_bytes, media_type="image/png")
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Failed to fetch image: {exc}") from exc

    if job["source"] == "a1111":
        images_b64 = job.get("images_b64", [])
        if images_b64:
            return Response(content=base64.b64decode(images_b64[0]), media_type="image/png")

    # Offline placeholder -- 1x1 transparent PNG
    placeholder_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    return Response(content=base64.b64decode(placeholder_b64), media_type="image/png")


@app.get("/photo/models")
async def list_models() -> dict[str, Any]:
    try:
        models = await _comfyui_list_models()
        return {"models": models, "source": "comfyui", "total": len(models)}
    except Exception as exc:
        logger.warning("ComfyUI models unavailable: %s", exc)
        return {
            "models": ["v1-5-pruned-emaonly", "dreamshaper", "realvisxl"],
            "source": "offline",
            "total": 3,
        }


@app.post("/photo/upscale")
async def upscale(req: UpscaleRequest) -> dict[str, Any]:
    job = _jobs.get(req.job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="Job not completed yet")

    upscale_job_id = str(uuid.uuid4())
    _jobs[upscale_job_id] = {
        "status": "queued",
        "source": "comfyui",
        "parent_job_id": req.job_id,
        "scale_factor": req.scale_factor,
        "type": "upscale",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    return {"job_id": upscale_job_id, "status": "queued", "scale_factor": req.scale_factor}


@app.get("/gallery")
async def gallery() -> dict[str, Any]:
    completed = [
        {"job_id": k, "prompt": v.get("prompt"), "source": v.get("source")}
        for k, v in _jobs.items()
        if v.get("status") == "completed"
    ]
    return {"images": completed, "total": len(completed)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
