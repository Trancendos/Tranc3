"""TateKing — Port 8053.

Video creation & editing platform.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="TateKing", version="1.0.0")

PORT = int(os.getenv("PORT", "8053"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"service": "tateking", "status": "ok", "uptime": time.time() - START_TIME})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "TateKing",
            "lead_ai": "Benji Tate & Sam King",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/projects")
async def projects() -> JSONResponse:
    return JSONResponse({"projects": [], "total": 0, "message": "No video projects yet."})


@app.post("/render")
async def render() -> JSONResponse:
    return JSONResponse(
        {"rendered": False, "message": "Render pipeline not yet ready."}, status_code=202
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
