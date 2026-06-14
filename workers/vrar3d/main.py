"""VRAR3D — Port 8063.

Standalone 3D / VR immersion.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="VRAR3D", version="1.0.0")

PORT = int(os.getenv("PORT", "8063"))
START_TIME = time.time()

STUB_SCENES = [
    {"id": "vr-scene-001", "name": "Default VR Space", "type": "vr", "engine": "Three.js"},
]


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"service": "vrar3d", "status": "ok", "uptime": time.time() - START_TIME})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "VRAR3D",
            "lead_ai": "Entari",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/scenes")
async def scenes() -> JSONResponse:
    return JSONResponse({"scenes": STUB_SCENES, "total": len(STUB_SCENES)})


@app.get("/scenes/{scene_id}")
async def get_scene(scene_id: str) -> JSONResponse:
    for scene in STUB_SCENES:
        if scene["id"] == scene_id:
            return JSONResponse(scene)
    return JSONResponse(
        {"id": scene_id, "found": False, "message": "VR scene not found."}, status_code=404
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
