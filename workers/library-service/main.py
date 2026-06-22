"""The Library — FastAPI app factory (Lead AI: Zimik)"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import _make_router as _make_library_router
from service import LibraryRouter

import config
from database import LibraryDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(config.WORKER_NAME)

_STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("The Library (Zimik) starting on port %d", config.WORKER_PORT)
    logger.info(
        "8-backend ACO routing: Outline→BookStack→Wiki.js→Gollum→DokuWiki→MkDocs→Gitea→TiddlyWiki"
    )
    yield
    logger.info("The Library shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="The Library — Knowledge Base API",
        description=(
            "ACO pheromone routing across 8 free self-hosted wiki backends. "
            "Primary: Outline. Fallbacks: BookStack, Wiki.js, Gollum, DokuWiki, MkDocs, Gitea Wiki, TiddlyWiki. "
            "Lead AI: Zimik."
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
        provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=config.OTEL_ENDPOINT)))
        FastAPIInstrumentor.instrument_app(app, tracer_provider=provider)
        logger.info("OpenTelemetry instrumentation active → %s", config.OTEL_ENDPOINT)
    except Exception as exc:
        logger.debug("OpenTelemetry not available: %s", exc)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    db = LibraryDatabase(config.DB_PATH)
    router_svc = LibraryRouter(db)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": config.WORKER_NAME,
            "named": "The Library",
            "lead_ai": "Zimik",
            "port": config.WORKER_PORT,
            "uptime_seconds": (datetime.now(timezone.utc) - _STARTED_AT).total_seconds(),
            "backends": 8,
            "backend_order": ["outline", "bookstack", "wikijs", "gollum", "dokuwiki", "mkdocs", "gitea", "tiddlywiki"],
        }

    app.include_router(_make_library_router(db, router_svc))
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.WORKER_PORT)
