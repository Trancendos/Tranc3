"""
Trancendos AI API — Self-Hosted Worker (infinity-ai)
====================================================
Backwards-compatibility shim.

The monolith has been refactored into a modular structure:
  config.py   — env-var constants
  database.py — AIDatabase (SQLite)
  models.py   — Pydantic models
  service.py  — AIGatewayRouter + provider clients + LRU cache
  router.py   — FastAPI routes (APIRouter)
  main.py     — app factory + lifespan

This file re-exports `app` so that existing `uvicorn worker:app` launch
commands continue to work without any change.
"""

from main import app  # noqa: F401  re-export for `uvicorn worker:app`

__all__ = ["app"]
