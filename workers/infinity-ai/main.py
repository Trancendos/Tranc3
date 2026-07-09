"""
Main — Infinity AI Worker
==========================
App factory, lifespan, middleware, and router inclusion.
Uvicorn/Docker should point at   main:app   (or worker:app via shim).
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import init_router, protected_router, public_router
from service import AIGatewayRouter

from config import DB_PATH, WORKER_NAME, WORKER_PORT
from database import AIDatabase

db = AIDatabase(DB_PATH)
gateway = AIGatewayRouter(db)
init_router(db, gateway)

logger = logging.getLogger(WORKER_NAME)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name=f"tranc3.{WORKER_NAME}", worker_port=WORKER_PORT)
    except Exception:
        pass
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    logger.info("%s ready — %d providers configured ✨", WORKER_NAME, len(gateway.providers))
    yield
    logger.info("%s shutting down...", WORKER_NAME)


app = FastAPI(
    title="Infinity AI — Adaptive Provider Gateway",
    description="OpenAI-compatible AI proxy with adaptive rotation across 8 free providers: Ollama, Groq, Cerebras, OpenRouter, HuggingFace, Together, DeepSeek, Offline.",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(public_router)
app.include_router(protected_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
