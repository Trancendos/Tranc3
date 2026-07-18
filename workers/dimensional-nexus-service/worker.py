"""
Tranc3 Nexus Service — Worker Entry Point
==========================================
Self-hosted worker that launches The Nexus as a standalone service.

The Nexus is ONE of the three bridges that route traffic through Sentinel Station:

    Bridge 1 — InfinityBridge : User context / human traffic (Light bridges)
    Bridge 2 — The Nexus (THIS): AI, Agent, and Bot movement and traffic
    Bridge 3 — The HIVE       : Data movement and swarm system coordination

The Nexus provides causal event ordering, tier-aware access control,
real-time health aggregation, and cross-Nexus event routing for AI,
Agent, and Bot services (Tier 3–5).

Architecture:
    AI/Agent/Bot Services ──heartbeat──▸ Nexus ◂──events── Dimensional Services
                                          │
                            ┌─────────────┼─────────────┐
                            ▼             ▼             ▼
                      HealthAgg    EventRouter    TierAccess
                      (SQLite)     (Channels)     (RBAC+ABAC)
                            │             │             │
                            └─────────────┼─────────────┘
                                          ▼
                              CausalOrderingEngine
                              (Vector Clocks)
                                          │
                                          ▼
                              WebSocket Dashboard

Port: 8091
Zero-cost: FastAPI + SQLite + in-process routing. No external deps.

IMPORTANT: This is The Nexus — for AI/Agent/Bot traffic ONLY.
User traffic uses InfinityBridge. Data traffic uses The HIVE.
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

from Dimensional.nexus.nexus_core import (  # noqa: E402
    Nexus,
    create_nexus_app,
    get_nexus,
)

# Backward-compatible alias — only valid when referring to both Dimensional AND Nexus
DimensionalNexus = Nexus

WORKER_PORT = int(os.environ.get("NEXUS_PORT", "8050"))
WORKER_NAME = "nexus"
_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

# The app is created by the nexus_core module
app = create_nexus_app()


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
    return {"status": "ok", "service": WORKER_NAME, "port": WORKER_PORT}


@app.on_event("startup")
async def _worker_startup():
    # OpenTelemetry instrumentation
    try:
        from src.observability.worker_setup import instrument_worker

        instrument_worker(app, service_name="tranc3.dimensional-nexus-service")
    except Exception:
        pass  # OTel is optional — never block startup
    """Initialize the Nexus with default AI/Agent/Bot services and topology on startup."""
    nexus = get_nexus()
    logger.info(f"Nexus worker starting on port {WORKER_PORT}")
    logger.info(f"Node ID: {nexus.node_id}")
    logger.info("Bridge type: nexus — AI, Agent, and Bot traffic coordination")

    # Register core AI/Agent/Bot services that route through The Nexus
    core_services = [
        {
            "service_id": "nexus-self",
            "service_name": "The Nexus",
            "pillar": "nexus",
            "tier_requirement": 1,
        },
        {
            "service_id": "infinity-portal",
            "service_name": "Infinity Portal",
            "pillar": "infinity",
            "tier_requirement": 3,
        },
        {
            "service_id": "infinity-auth",
            "service_name": "Infinity Auth",
            "pillar": "infinity",
            "tier_requirement": 3,
        },
        {
            "service_id": "sentinel-station",
            "service_name": "Sentinel Station",
            "pillar": "infinity",
            "tier_requirement": 3,
        },
        {
            "service_id": "health-aggregator",
            "service_name": "Health Aggregator",
            "pillar": "monitoring",
            "tier_requirement": 5,
        },
        {
            "service_id": "the-grid",
            "service_name": "The Grid",
            "pillar": "infrastructure",
            "tier_requirement": 5,
        },
        {
            "service_id": "tranc3-ai",
            "service_name": "Tranc3 AI",
            "pillar": "ai",
            "tier_requirement": 3,
        },
        {
            "service_id": "deepagents-orchestrator",
            "service_name": "DeepAgents Orchestrator",
            "pillar": "agents",
            "tier_requirement": 4,
        },
    ]

    for svc in core_services:
        try:
            await nexus.register_service(**svc)
            logger.info(f"Registered Nexus service: {svc['service_id']}")
        except Exception as e:
            logger.warning(f"Failed to register {svc['service_id']}: {e}")

    # Build default Nexus topology edges for AI/Agent/Bot traffic
    edges = [
        ("nexus-self", "infinity-portal", "control"),
        ("nexus-self", "infinity-auth", "control"),
        ("nexus-self", "sentinel-station", "events"),
        ("nexus-self", "health-aggregator", "monitoring"),
        ("nexus-self", "tranc3-ai", "coordination"),
        ("nexus-self", "deepagents-orchestrator", "coordination"),
        ("infinity-portal", "infinity-auth", "auth-flow"),
        ("infinity-portal", "sentinel-station", "events"),
        ("tranc3-ai", "deepagents-orchestrator", "task-dispatch"),
        ("deepagents-orchestrator", "the-grid", "compute"),
        ("health-aggregator", "the-grid", "monitoring"),
    ]

    for src, tgt, edge_type in edges:
        try:
            await nexus.add_topology_edge(src, tgt, edge_type)
            logger.debug(f"Added topology edge: {src} → {tgt} ({edge_type})")
        except Exception as e:
            logger.warning(f"Failed to add edge {src}→{tgt}: {e}")

    # Emit startup event through The Nexus
    try:
        await nexus.emit_event(
            channel="NEXUS",
            source_dimension="nexus",
            source_tier=1,
            event_type="nexus_startup",
            payload={"port": WORKER_PORT, "services": len(core_services)},
        )
        logger.info("Nexus startup event emitted")
    except Exception as e:
        logger.warning(f"Failed to emit startup event: {e}")

    logger.info(
        f"Nexus ready: {len(core_services)} AI/Agent/Bot services, "
        f"{len(edges)} topology edges, port {WORKER_PORT}"
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
