"""The Basement — Port 8041.

Archived information store from The Observatory.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="The Basement", version="1.0.0")

PORT = int(os.getenv("PORT", "8041"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"service": "basement", "status": "ok", "uptime": time.time() - START_TIME})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "The Basement",
            "lead_ai": "Gary Glowman (Glow-Worm)",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/archives")
async def archives() -> JSONResponse:
    return JSONResponse({"archives": [], "total": 0, "message": "Archive store initialising."})


@app.get("/archive/{archive_id}")
async def get_archive(archive_id: str) -> JSONResponse:
    return JSONResponse(
        {"id": archive_id, "found": False, "message": "Archive not found."}, status_code=404
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
