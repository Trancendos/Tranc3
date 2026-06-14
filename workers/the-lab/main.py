"""The Lab — Port 8055.

Code creation platform.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="The Lab", version="1.0.0")

PORT = int(os.getenv("PORT", "8055"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"service": "the-lab", "status": "ok", "uptime": time.time() - START_TIME})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "The Lab",
            "lead_ai": "The Dr. & Slime",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/workspaces")
async def workspaces() -> JSONResponse:
    return JSONResponse({"workspaces": [], "total": 0, "message": "No workspaces yet."})


@app.post("/execute")
async def execute() -> JSONResponse:
    return JSONResponse({"executed": False, "message": "Sandbox not ready."}, status_code=503)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
