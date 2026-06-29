"""The Studio — Port 8050.

Central hub of the Creativity Center.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="The Studio", version="1.0.0")

PORT = int(os.getenv("PORT", "8050"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "the-studio", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "The Studio",
            "lead_ai": "Voxx",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/projects")
async def projects() -> JSONResponse:
    return JSONResponse({"projects": [], "total": 0, "message": "No projects yet."})


@app.get("/projects/{project_id}")
async def get_project(project_id: str) -> JSONResponse:
    return JSONResponse(
        {"id": project_id, "found": False, "message": "Project not found."}, status_code=404
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
