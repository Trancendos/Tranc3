"""
Configuration — Infinity Portal Service
========================================
All environment-variable constants for the Infinity Portal.
"""

from __future__ import annotations

import logging
import os

# ---------------------------------------------------------------------------
# Port & Database
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("INFINITY_PORTAL_PORT", "8042"))
DB_PATH = os.environ.get("INFINITY_PORTAL_DB_PATH", "data/infinity_portal.db")

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

JWT_SECRET = os.environ.get("JWT_SECRET", "")

# ---------------------------------------------------------------------------
# Upstream service URLs
# ---------------------------------------------------------------------------

AUTH_SERVICE_PORT = int(os.environ.get("AUTH_SERVICE_PORT", "8005"))
AUTH_SERVICE_URL = os.environ.get("AUTH_SERVICE_URL", f"http://localhost:{AUTH_SERVICE_PORT}")

GATEWAY_SERVICE_PORT = int(os.environ.get("GATEWAY_SERVICE_PORT", "8040"))
GATEWAY_SERVICE_URL = os.environ.get(
    "GATEWAY_SERVICE_URL", f"http://localhost:{GATEWAY_SERVICE_PORT}"
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

CORS_ORIGINS: list[str] = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger = logging.getLogger("infinity-portal-service")
