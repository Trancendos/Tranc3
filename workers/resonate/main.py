"""Resonate — Port 8076.

Empathy engine.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Resonate", version="1.0.0")

PORT = int(os.getenv("PORT", "8076"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"service": "resonate", "status": "ok", "uptime": time.time() - START_TIME})


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "Resonate",
            "lead_ai": "Magdalena",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.post("/resonate")
async def resonate(body: dict) -> JSONResponse:
    message = body.get("message", "")
    return JSONResponse(
        {
            "echo": message,
            "empathy": "I hear you. Your feelings are valid.",
            "resonance": "initialising",
        }
    )


@app.get("/sessions")
async def sessions() -> JSONResponse:
    return JSONResponse({"sessions": [], "total": 0, "message": "No empathy sessions yet."})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
