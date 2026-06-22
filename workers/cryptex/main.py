"""Cryptex / The Ice Box — FastAPI app factory"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import _make_router as _make_cryptex_router
from service import SecurityEngineRouter

import config
from database import CryptexDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(config.WORKER_NAME)

_STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Cryptex / The Ice Box starting on port %d", config.WORKER_PORT)
    logger.info(
        "8-tier engine order: internal → wazuh → misp → openvas → clamav → yara → semgrep → offline"
    )
    yield
    logger.info("Cryptex / The Ice Box shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Cryptex / The Ice Box — Security API",
        description=(
            "8-tier adaptive security scanning engine. "
            "Cryptex (Renik): Cyber defense — threat intel, DDoS, CVE. "
            "The Ice Box (Neonach): Sandbox threat isolation & quarantine."
        ),
        version="1.0.0",
        lifespan=_lifespan,
    )

    # OpenTelemetry (optional — requires opentelemetry-sdk + OTEL_EXPORTER_OTLP_ENDPOINT)
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

    db = CryptexDatabase(config.DB_PATH)
    engine_router = SecurityEngineRouter(db)

    @app.get("/health")
    async def health():
        return {
            "status": "healthy",
            "service": config.WORKER_NAME,
            "port": config.WORKER_PORT,
            "uptime_seconds": (datetime.now(timezone.utc) - _STARTED_AT).total_seconds(),
            "engine_count": 8,
        }

    app.include_router(_make_cryptex_router(db, engine_router))
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.WORKER_PORT)
