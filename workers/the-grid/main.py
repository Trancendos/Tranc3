"""The Digital Grid — FastAPI app factory"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import _make_router as _make_grid_router
from service import WorkflowEngineRouter

import config
from database import GridDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(config.WORKER_NAME)

_STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("The Digital Grid starting on port %d", config.WORKER_PORT)
    logger.info("8-tier engine order: internal → n8n → prefect → temporal → airflow → dagster → luigi → offline")
    yield
    logger.info("The Digital Grid shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="The Digital Grid — Workflow API",
        description=(
            "8-tier adaptive workflow orchestration engine. "
            "Powers The Digital Grid (Tyler Towncroft). "
            "Replaces CF the-grid-api."
        ),
        version="2.0.0",
        lifespan=_lifespan,
    )

    # OpenTelemetry (optional — only if SDK + OTEL_EXPORTER_OTLP_ENDPOINT are set)
    try:
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
    except Exception as exc:  # OpenTelemetry is optional; proceed without it
        logger.debug("OpenTelemetry not available: %s", exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    db = GridDatabase(config.DB_PATH)
    engine_router = WorkflowEngineRouter(db)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": config.WORKER_NAME,
            "port": config.WORKER_PORT,
            "uptime_seconds": (datetime.now(timezone.utc) - _STARTED_AT).total_seconds(),
            "engine_count": 8,
        }

    app.include_router(_make_grid_router(db, engine_router))
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.WORKER_PORT)
