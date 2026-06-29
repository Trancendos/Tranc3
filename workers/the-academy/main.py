"""The Academy — Port 8040.

Learning management — education & skill training.
"""

from __future__ import annotations

import os
import time

from fastapi import FastAPI
from fastapi.responses import JSONResponse

app = FastAPI(title="The Academy", version="1.0.0")

PORT = int(os.getenv("PORT", "8040"))
START_TIME = time.time()


@app.get("/health")
async def health() -> JSONResponse:
    return JSONResponse(
        {"service": "the-academy", "status": "ok", "uptime": time.time() - START_TIME}
    )


@app.get("/status")
async def status() -> JSONResponse:
    return JSONResponse(
        {
            "entity": "The Academy",
            "lead_ai": "Shimshi",
            "status": "initialising",
            "uptime": time.time() - START_TIME,
        }
    )


@app.get("/courses")
async def courses() -> JSONResponse:
    return JSONResponse({"courses": [], "total": 0, "message": "No courses available yet."})


@app.post("/enroll")
async def enroll() -> JSONResponse:
    return JSONResponse({"enrolled": False, "message": "Enrollment not yet open."}, status_code=202)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)  # nosec B104 — containerised service
