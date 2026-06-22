"""
config.py — Gateway Service configuration
All environment-variable constants for gateway-service.
"""

from __future__ import annotations

import logging
import os

# ---------------------------------------------------------------------------
# Core settings
# ---------------------------------------------------------------------------

PORT = int(os.environ.get("GATEWAY_PORT", "8040"))
DB_PATH = os.environ.get("GATEWAY_DB_PATH", "data/gateway.db")
CACHE_TTL = int(os.environ.get("GATEWAY_CACHE_TTL", "5"))

_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. This service cannot validate tokens without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw

# ---------------------------------------------------------------------------
# Upstream worker registry
# ---------------------------------------------------------------------------

UPSTREAM_WORKERS: dict[str, dict[str, str | int]] = {
    "vault": {"port": 8030, "health": "/health", "stats": "/stats"},
    "topology": {"port": 8031, "health": "/health", "stats": "/stats"},
    "ledger": {"port": 8032, "health": "/health", "stats": "/stats"},
    "model_router": {"port": 8033, "health": "/health", "stats": "/stats"},
    "workflow": {"port": 8034, "health": "/health", "stats": "/stats"},
    "benchmark": {"port": 8035, "health": "/health", "stats": "/stats"},
    "langchain": {"port": 8036, "health": "/health", "stats": "/stats"},
    "deepagents": {"port": 8037, "health": "/health", "stats": "/stats"},
}

# ---------------------------------------------------------------------------
# WebSocket settings
# ---------------------------------------------------------------------------

WS_MAX_CONNECTIONS = int(os.environ.get("WS_MAX_CONNECTIONS", "1000"))
WS_HEARTBEAT_INTERVAL = int(os.environ.get("WS_HEARTBEAT_INTERVAL", "30"))
WS_IDLE_TIMEOUT = int(os.environ.get("WS_IDLE_TIMEOUT", "300"))

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

logger = logging.getLogger("gateway-service")
