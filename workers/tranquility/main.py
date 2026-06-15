"""Tranquility — Port 8060.

Wellbeing central hub.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Tranquility", version="1.0.0")

PORT = int(os.getenv("PORT", "8060"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "tranquility", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "Tranquility",
            "lead_ai": "Savania",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/sessions")
async def sessions() -> JSONResponse:
    return JSONResponse({"sessions": [], "total": 0, "message": "No sessions available."})


@app.post("/checkin")
async def checkin() -> JSONResponse:
    return JSONResponse(
        {"checked_in": False, "message": "Check-in service not yet ready."}, status_code=202
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
