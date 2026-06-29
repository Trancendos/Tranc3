"""Warp Radio — Port 8057.

Music & audio streaming integration.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="Warp Radio", version="1.0.0")

PORT = int(os.getenv("PORT", "8057"))
START_TIME = time.time()
NAVIDROME_URL = os.getenv("NAVIDROME_URL", "http://navidrome:4533")


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "warp-radio", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "Warp Radio",
            "lead_ai": "Rocking Ricki",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
            "navidrome_url": NAVIDROME_URL,
        }
    )


@app.get("/now-playing")
async def now_playing() -> JSONResponse:
    return JSONResponse({"now_playing": None, "message": "Nothing playing yet."})


@app.get("/stations")
async def stations() -> JSONResponse:
    return JSONResponse({"stations": [], "total": 0, "message": "No stations configured."})


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
