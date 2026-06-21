"""
worker.py — Backwards-compatibility shim
========================================
The canonical implementation has been refactored into:

    main.py      — app factory + lifespan
    config.py    — environment variables and constants
    database.py  — SQLite helpers (cache, events, access_audit)
    models.py    — Pydantic schemas
    service.py   — Business logic: circuit breaker, upstream proxy, cache, ABAC/RBAC
    router.py    — All FastAPI routes (HTTP, SSE, WebSocket)

This file re-exports ``app`` so that existing uvicorn invocations continue to work:

    uvicorn worker:app --port 8040
"""
from main import app  # noqa: F401
