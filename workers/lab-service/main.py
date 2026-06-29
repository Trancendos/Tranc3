"""The Lab — FastAPI app factory (Lead AI: The Dr. & Slime)"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import _make_lab_router

import config
from database import LabDatabase
from service import LabRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(config.WORKER_NAME)

_STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("The Lab starting on port %d", config.WORKER_PORT)
    logger.info(
        "6-backend ACO routing: Ollama/DeepSeek (primary) → Ollama/CodeLlama → "
        "Ollama/Qwen → Tabby (self-hosted) → HuggingFace (free, capped %d/hr) → "
        "OpenRouter (free, capped %d/hr) → Offline",
        config.HF_HOURLY_LIMIT,
        config.OPENROUTER_HOURLY_LIMIT,
    )
    logger.info("OpenAI-compat endpoint for Continue.dev/Cline/Aider: %s", config.OPENAI_COMPAT_URL)
    yield
    logger.info("The Lab shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="The Lab — Code Generation API",
        description=(
            "ACO pheromone routing across 6 free code AI backends. "
            "Primary: Ollama (zero-cost, local). "
            "Fallbacks: Tabby (self-hosted), HuggingFace free tier, OpenRouter free models. "
            "Compatible with Continue.dev, Cline, Aider via OpenAI-compat endpoint. "
            "Lead AI: The Dr. & Slime."
        ),
        version="1.0.0",
        lifespan=_lifespan,
    )

    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        logger.info("OpenTelemetry instrumentation active → %s", config.OTEL_ENDPOINT)
    except Exception as exc:  # OpenTelemetry is optional; proceed without it
        logger.debug("OpenTelemetry not available: %s", exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": config.WORKER_NAME,
            "named": "The Lab",
            "lead_ai": "The Dr. & Slime",
            "port": config.WORKER_PORT,
            "uptime_seconds": (datetime.now(timezone.utc) - _STARTED_AT).total_seconds(),
            "backends": 6,
            "openai_compat_url": config.OPENAI_COMPAT_URL,
        }

    db = LabDatabase()
    lab = LabRouter()
    app.include_router(_make_lab_router(db, lab))
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.WORKER_PORT)  # nosec B104 — containerised service
