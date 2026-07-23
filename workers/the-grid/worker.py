"""
The Digital Grid — Backwards-compatibility shim
================================================
Refactored into a modular structure:

    config.py   — env vars, engine URLs, thresholds
    database.py — GridDatabase SQLite class
    models.py   — Pydantic models, EngineType enum
    service.py  — 8-tier adaptive WorkflowEngineRouter + ACO pheromone + ThresholdGuard
    router.py   — FastAPI routes via APIRouter
    main.py     — app factory + lifespan

Engines (waterfall fallback + ACO adaptive selection):
  Tier 1: Internal Python DAG executor
  Tier 2: n8n              REST API  (port 5678)
  Tier 3: Prefect          REST API  (port 4200)
  Tier 4: Temporal         gRPC      (port 7233)
  Tier 5: Apache Airflow   REST API  (port 8089)
  Tier 6: Dagster          GraphQL   (port 3002)
  Tier 7: Luigi            in-process
  Tier 8: Offline stub     (always works)

Uvicorn deployments that reference ``worker:app`` continue to work
because this shim re-exports ``app`` from ``main``.
"""

from main import app, db, engine  # noqa: F401  re-exported for uvicorn worker:app
from service import WorkflowEngineRouter  # noqa: F401

from database import GridDatabase  # noqa: F401

__all__ = ["app", "db", "engine", "GridDatabase", "WorkflowEngineRouter"]
