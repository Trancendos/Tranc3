"""
Trancendos Dimensional Nexus Service — Worker Entry Point
===========================================================
Self-hosted worker that launches the Dimensional Nexus as a standalone
service. The Nexus is the Central Nervous System of the Tranc3 platform,
providing causal event ordering, tier-aware access control, real-time
health aggregation, and cross-dimensional event routing.

Architecture:
    The Nexus sits at the center of the dimensional mesh:
    
    Workers ──heartbeat──▸ Nexus ◂──events── Dimensional Services
                              │
                    ┌─────────┼─────────┐
                    ▼         ▼         ▼
              HealthAgg   EventRouter  TierAccess
              (SQLite)    (Channels)   (RBAC+ABAC)
                    │         │         │
                    └─────────┼─────────┘
                              ▼
                    CausalOrderingEngine
                    (Vector Clocks)
                              │
                              ▼
                    WebSocket Dashboard

Port: 8050
Zero-cost: FastAPI + SQLite + in-process routing. No external deps.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Ensure the project root is on sys.path so Dimensional package is importable
_project_root = Path(__file__).resolve().parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from Dimensional.nexus.nexus_core import (
    DimensionalNexus,
    create_nexus_app,
    get_nexus,
)

WORKER_PORT = int(os.environ.get("NEXUS_PORT", "8050"))
WORKER_NAME = "dimensional-nexus"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
)
logger = logging.getLogger(WORKER_NAME)

# The app is created by the nexus_core module
app = create_nexus_app()


@app.on_event("startup")
async def _worker_startup():
    """Initialize the Nexus with default services and topology on startup."""
    nexus = get_nexus()
    logger.info(f"Dimensional Nexus worker starting on port {WORKER_PORT}")
    logger.info(f"Node ID: {nexus.node_id}")

    # Register core dimensional services
    core_services = [
        {
            "service_id": "nexus-self",
            "dimension": "nexus",
            "tier": 1,
            "service_type": "coordinator",
            "status": "healthy",
        },
        {
            "service_id": "infinity-portal",
            "dimension": "infinity",
            "tier": 3,
            "service_type": "gateway",
            "status": "healthy",
        },
        {
            "service_id": "infinity-auth",
            "dimension": "infinity",
            "tier": 3,
            "service_type": "auth",
            "status": "healthy",
        },
        {
            "service_id": "sentinel-station",
            "dimension": "infinity",
            "tier": 3,
            "service_type": "event-bus",
            "status": "healthy",
        },
        {
            "service_id": "health-aggregator",
            "dimension": "monitoring",
            "tier": 5,
            "service_type": "worker",
            "status": "healthy",
        },
        {
            "service_id": "the-grid",
            "dimension": "infrastructure",
            "tier": 5,
            "service_type": "worker",
            "status": "healthy",
        },
        {
            "service_id": "tranc3-ai",
            "dimension": "ai",
            "tier": 3,
            "service_type": "ai-complex",
            "status": "healthy",
        },
        {
            "service_id": "deepagents-orchestrator",
            "dimension": "agents",
            "tier": 4,
            "service_type": "orchestrator",
            "status": "healthy",
        },
    ]

    for svc in core_services:
        try:
            await nexus.register_service(**svc)
            logger.info(f"Registered core service: {svc['service_id']}")
        except Exception as e:
            logger.warning(f"Failed to register {svc['service_id']}: {e}")

    # Build default topology edges
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

    # Emit startup event
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
        f"Dimensional Nexus ready: {len(core_services)} services, "
        f"{len(edges)} edges, port {WORKER_PORT}"
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
