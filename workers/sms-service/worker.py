"""
Trancendos sms-service — Self-Hosted Worker (STUB)
===================================================
SMS messaging API
**STUB**: This worker provides basic health and placeholder endpoints.
Full implementation is TODO — replace with domain-specific logic.

Port: 8019
Zero-cost: FastAPI + SQLite pattern, no external dependencies.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8019
WORKER_NAME = "sms-service"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
app = FastAPI(
    title="sms-service",
    description="SMS messaging API (Stub — TODO: Full implementation)",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "note": "Stub worker — full implementation TODO",
    }


@app.get("/")
async def root():
    """Placeholder root endpoint."""
    return {
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "status": "stub",
        "message": "This worker is a stub. Full implementation is TODO.",
        "endpoints": ["/health", "/", "/docs"],
    }


# TODO: Implement domain-specific endpoints for sms-service
# - Add SQLite database class following the standard pattern
# - Add Pydantic models for request/response validation
# - Add CRUD endpoints specific to this service
# - Add any domain-specific business logic


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
