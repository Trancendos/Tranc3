"""TranceFlow — Port 8052.

3D modeling & games creation studio.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="TranceFlow", version="1.0.0")

PORT = int(os.getenv("PORT", "8052"))
START_TIME = time.time()

STUB_SCENES = [
    {"id": "scene-001", "name": "Empty Scene", "objects": 0, "engine": "Godot 4"},
]


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "tranceflow", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "TranceFlow",
            "lead_ai": "Junior Cesar",
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
        {"id": scene_id, "found": False, "message": "Scene not found."}, status_code=404
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
