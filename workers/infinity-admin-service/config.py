"""
Infinity-Admin Service — Configuration
=======================================
All environment variable constants and derived configuration values.
"""

from __future__ import annotations

import logging
import os

PORT = int(os.environ.get("INFINITY_ADMIN_PORT", "8044"))
DB_PATH = os.environ.get("INFINITY_ADMIN_DB_PATH", "data/infinity_admin.db")

_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. This service cannot validate tokens without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw

_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")

_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

logger = logging.getLogger("infinity-admin-service")
