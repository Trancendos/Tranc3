"""Observatory — The Observatory (Norman Hawkins) FastAPI app factory."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from router import _make_observatory_router

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(config.WORKER_NAME)

_STARTED_AT = datetime.now(timezone.utc)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    logger.info("Observatory starting on port %d", config.WORKER_PORT)
    logger.info(
        "7-backend ACO routing: Tempo→Jaeger (traces) | Victoria→Prometheus (metrics) | "
        "Loki (logs) | Netdata→Victoria (node) | SigNoz (unified APM)"
    )
    yield
    logger.info("Observatory shutting down")


def create_app() -> FastAPI:
    app = FastAPI(
        title="The Observatory — Observability API",
        description=(
            "ACO pheromone routing across 7 free observability backends. "
            "Signal routing: Traces→Tempo/Jaeger, Metrics→VictoriaMetrics/Prometheus, "
            "Logs→Loki, Node→Netdata/VictoriaMetrics, APM→SigNoz. "
            "Lead AI: Norman Hawkins."
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
            "named": "The Observatory",
            "lead_ai": "Norman Hawkins",
            "port": config.WORKER_PORT,
            "uptime_seconds": (datetime.now(timezone.utc) - _STARTED_AT).total_seconds(),
            "backends": 7,
            "signal_types": ["traces", "metrics", "logs", "node"],
        }

    app.include_router(_make_observatory_router())
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.WORKER_PORT)  # nosec B104 — containerised service
