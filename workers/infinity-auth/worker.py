"""
Infinity Auth — Backwards-compatibility shim
=============================================
This file previously contained the full 1,142-line monolith.
It has been refactored into a modular structure:

    config.py    — env vars and constants
    database.py  — AuthDatabase SQLite class
    models.py    — Pydantic models
    service.py   — business logic (hashing, JWT, TOTP, rate limiting)
    router.py    — FastAPI routes via APIRouter
    main.py      — app factory + lifespan

Uvicorn deployments that reference ``worker:app`` continue to work
because this shim re-exports ``app`` from ``main``.
"""

from main import app  # noqa: F401  re-exported for uvicorn worker:app
from service import (  # noqa: F401
    RateLimiter,
    create_access_token,
    create_refresh_token,
    decode_access_token,
    hash_password,
    verify_password,
)

from database import AuthDatabase  # noqa: F401

__all__ = [
    "app",
    "AuthDatabase",
    "RateLimiter",
    "create_access_token",
    "create_refresh_token",
    "decode_access_token",
    "hash_password",
    "verify_password",
]
