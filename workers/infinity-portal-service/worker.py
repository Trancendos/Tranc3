"""
Backwards-compatibility shim — Infinity Portal Service
=======================================================
Docker / uvicorn startup command uses   worker:app
This module re-exports `app` from main so that command continues to work
without any infrastructure changes.

Do not add logic here — all code lives in:
    config.py    — environment variables
    database.py  — PortalDatabase + db singleton
    models.py    — Pydantic models
    service.py   — InfinityGate, call_auth_service, DB helpers
    router.py    — FastAPI APIRouter (all routes)
    main.py      — app factory, lifespan, middleware
"""

from main import app  # noqa: F401  — re-export for `uvicorn worker:app`

__all__ = ["app"]
