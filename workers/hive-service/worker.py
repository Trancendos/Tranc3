"""
Tranc3 HIVE Service — Worker Entry Point
==========================================
Self-hosted worker that launches The HIVE as a standalone service.

The HIVE is ONE of the three bridges that route traffic through Sentinel Station:

    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus      : AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE (THIS): Data movement and swarm system coordination

The HIVE provides data pipeline management, swarm coordination for
distributed data processing, flow monitoring with throughput/latency tracking,
and data chunk routing with priority and replication.

Port: 8060
Zero-cost: FastAPI + SQLite + in-process routing. No external deps.

IMPORTANT: This is The HIVE — for data movement and swarm coordination ONLY.
AI/Agent/Bot traffic uses The Nexus. User traffic uses InfinityBridge.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from fastapi import Request
from fastapi.responses import JSONResponse

# Ensure the project root is on sys.path so Dimensional package is importable
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from Dimensional.hive.hive_core import (  # noqa: E402
    DataPriority,
    create_hive_app,
    get_hive,
)

WORKER_PORT = int(os.environ.get("HIVE_PORT", "8060"))
WORKER_NAME = "hive"
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

# The app is created by the hive_core module
app = create_hive_app()


@app.middleware("http")
async def _internal_auth(request: Request, call_next):
    if _INTERNAL_SECRET and request.url.path != "/health":
        token = request.headers.get("x-internal-secret", "")
        if token != _INTERNAL_SECRET:
            return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.get("/health")
async def health():
    """Standard health check — required by CI worker-validation and Docker healthcheck."""
    return {"status": "ok", "service": "hive", "port": WORKER_PORT}


@app.on_event("startup")
async def _worker_startup():
    # OpenTelemetry instrumentation
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.hive-service")
    except Exception:
        pass  # OTel is optional — never block startup
    """Initialize the HIVE with default data sources, sinks, and pipelines on startup."""
    hive = get_hive()
    logger.info(f"HIVE worker starting on port {WORKER_PORT}")
    logger.info(f"Node ID: {hive.node_id}")
    logger.info("Bridge type: hive — Data movement and swarm system coordination")

    # Register default data sources
    default_sources = [
        {"name": "model-weights-source", "data_type": "model_weights", "pillar": "ai"},
        {"name": "config-source", "data_type": "config", "pillar": "infrastructure"},
        {"name": "metrics-source", "data_type": "metrics", "pillar": "monitoring"},
        {"name": "logs-source", "data_type": "logs", "pillar": "monitoring"},
    ]

    sources = {}
    for src_def in default_sources:
        try:
            source = await hive.register_source(**src_def)
            sources[src_def["name"]] = source
            logger.info(f"Registered HIVE source: {src_def['name']} ({source.source_id})")
        except Exception as e:
            logger.warning(f"Failed to register source {src_def['name']}: {e}")

    # Register default data sinks
    default_sinks = [
        {"name": "training-cluster", "data_type": "model_weights", "pillar": "ai"},
        {"name": "config-distributor", "data_type": "config", "pillar": "infrastructure"},
        {"name": "metrics-dashboard", "data_type": "metrics", "pillar": "monitoring"},
        {"name": "log-aggregator", "data_type": "logs", "pillar": "monitoring"},
    ]

    sinks = {}
    for sink_def in default_sinks:
        try:
            sink = await hive.register_sink(**sink_def)
            sinks[sink_def["name"]] = sink
            logger.info(f"Registered HIVE sink: {sink_def['name']} ({sink.sink_id})")
        except Exception as e:
            logger.warning(f"Failed to register sink {sink_def['name']}: {e}")

    # Create default data pipelines
    pipeline_configs = [
        {
            "name": "model-weights-pipeline",
            "source_name": "model-weights-source",
            "sink_name": "training-cluster",
            "priority": DataPriority.HIGH,
        },
        {
            "name": "config-sync-pipeline",
            "source_name": "config-source",
            "sink_name": "config-distributor",
            "priority": DataPriority.CRITICAL,
        },
        {
            "name": "metrics-stream-pipeline",
            "source_name": "metrics-source",
            "sink_name": "metrics-dashboard",
            "priority": DataPriority.NORMAL,
        },
        {
            "name": "log-aggregation-pipeline",
            "source_name": "logs-source",
            "sink_name": "log-aggregator",
            "priority": DataPriority.LOW,
        },
    ]

    for pipe_cfg in pipeline_configs:
        try:
            src = sources.get(pipe_cfg["source_name"])
            snk = sinks.get(pipe_cfg["sink_name"])
            if src and snk:
                pipeline = await hive.create_pipeline(
                    name=pipe_cfg["name"],
                    source_id=src.source_id,
                    sink_ids=[snk.sink_id],
                    priority=pipe_cfg["priority"],
                )
                await hive.start_pipeline(pipeline.pipeline_id)
                logger.info(
                    f"Created and started pipeline: {pipe_cfg['name']} ({pipeline.pipeline_id})"
                )
        except Exception as e:
            logger.warning(f"Failed to create pipeline {pipe_cfg['name']}: {e}")

    # Create default ETL swarm
    try:
        swarm = await hive.create_swarm(
            name="default-etl-swarm",
            purpose="ETL",
            data_type="dataset",
        )
        logger.info(f"Created default swarm: {swarm.swarm_id}")
    except Exception as e:
        logger.warning(f"Failed to create default swarm: {e}")

    # Emit startup event through The HIVE
    try:
        await hive.emit_event(
            channel="HIVE",
            source="hive-service",
            event_type="hive_startup",
            payload={
                "port": WORKER_PORT,
                "sources": len(sources),
                "sinks": len(sinks),
                "pipelines": len(pipeline_configs),
            },
        )
        logger.info("HIVE startup event emitted")
    except Exception as e:
        logger.warning(f"Failed to emit startup event: {e}")

    logger.info(
        f"HIVE ready: {len(sources)} sources, {len(sinks)} sinks, "
        f"{len(pipeline_configs)} pipelines, port {WORKER_PORT}"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
