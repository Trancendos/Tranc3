"""
Main — Infinity AI Worker
==========================
App factory, lifespan, middleware, and router inclusion.
Uvicorn/Docker should point at   main:app   (or worker:app via shim).
"""
from __future__ import annotations
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from config import WORKER_PORT, WORKER_NAME
from database import db
from service import adaptive_rotation
from router import router

logger = logging.getLogger(WORKER_NAME)

@asynccontextmanager
async def _lifespan(app: FastAPI):
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from src.observability.otel import init_otel
        init_otel(service_name=f"tranc3.{WORKER_NAME}")
        FastAPIInstrumentor.instrument_app(app)
    except Exception:
        pass
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    db._init_tables()
    logger.info("%s ready — %d providers configured ✨", WORKER_NAME, len(adaptive_rotation.providers))
    async def _bg():
        while True:
            try:
                await asyncio.sleep(300)
                adaptive_rotation.reset_daily_counts_if_needed()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.debug("BG loop: %s", exc)
    _bg_task = asyncio.create_task(_bg())
    yield
    logger.info("%s shutting down...", WORKER_NAME)
    _bg_task.cancel()
    try:
        await _bg_task
    except asyncio.CancelledError:
        pass
    logger.info("%s stopped", WORKER_NAME)

app = FastAPI(
    title="Infinity AI — Adaptive Provider Gateway",
    description="OpenAI-compatible AI proxy with adaptive rotation across 8 free providers: Ollama, Groq, Cerebras, OpenRouter, HuggingFace, Together, DeepSeek, Offline.",
    version="1.0.0",
    lifespan=_lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
