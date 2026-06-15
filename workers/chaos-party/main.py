"""The Chaos Party — Port 8065.

Central testing platform (Alice in Wonderland themed).
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="The Chaos Party", version="1.0.0")

PORT = int(os.getenv("PORT", "8065"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "chaos-party", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "The Chaos Party",
            "lead_ai": "The Mad Hatter",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/tests")
async def tests() -> JSONResponse:
    return JSONResponse({"tests": [], "total": 0, "message": "No tests scheduled yet."})


@app.post("/run")
async def run() -> JSONResponse:
    return JSONResponse({"ran": False, "message": "Test runner not yet ready."}, status_code=202)


@app.get("/wonderland")
async def wonderland() -> JSONResponse:
    return JSONResponse(
        {
            "status": "curiouser and curiouser",
            "hatter": "We're all mad here.",
            "tea_party": "ongoing",
            "rabbit": "running late",
            "queen": "Off with their bugs!",
            "platform": "The Chaos Party — where every test is an adventure.",
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
