"""VRAR3D — Standalone 3D / VR immersion platform (Lead AI: Entari)"""

from __future__ import annotations

import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from database import VRARDatabase
from router import _make_vrar3d_router
from service import VRARRouter

_START = time.time()


def _build_app() -> FastAPI:
    app = FastAPI(
        title="VRAR3D",
        description="Standalone 3D / VR immersion — Lead AI: Entari",
        version="1.0.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if config.OTEL_ENDPOINT:
        try:
            from opentelemetry import trace
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            provider = TracerProvider()
            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=config.OTEL_ENDPOINT))
            )
            trace.set_tracer_provider(provider)
            FastAPIInstrumentor.instrument_app(app)
        except Exception:  # OTel is optional — never block startup
            pass

    db = VRARDatabase(config.DB_PATH)
    vrar = VRARRouter(db)
    app.include_router(_make_vrar3d_router(db, vrar))

    @app.get("/health", include_in_schema=False)
    def health() -> JSONResponse:
        return JSONResponse(
            {
                "service": config.WORKER_NAME,
                "entity": "VRAR3D",
                "lead_ai": "Entari",
                "status": "ok",
                "uptime_s": round(time.time() - _START, 1),
            }
        )

    return app


app = _build_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=config.WORKER_PORT)
