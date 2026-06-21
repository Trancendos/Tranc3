"""
Infinity Auth — Configuration
==============================
All environment variables and constants for the infinity-auth worker.
"""

from __future__ import annotations

import os
from pathlib import Path

# ── JWT ────────────────────────────────────────────────────────────────────────

_jwt_secret_raw = os.environ.get("JWT_SECRET")
if not _jwt_secret_raw:
    raise RuntimeError(
        "JWT_SECRET is not set. Infinity (auth service) cannot start without it. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
JWT_SECRET: str = _jwt_secret_raw
JWT_ALGORITHM = "HS256"
JWT_EXPIRY_MINUTES = int(os.environ.get("JWT_EXPIRY_MINUTES", "60"))
REFRESH_EXPIRY_DAYS = int(os.environ.get("REFRESH_EXPIRY_DAYS", "30"))

# ── Database ───────────────────────────────────────────────────────────────────

DATABASE_PATH = os.environ.get(
    "AUTH_DATABASE_PATH",
    str(Path(__file__).parent / "data" / "auth.db"),
)

# ── Rate limiting ──────────────────────────────────────────────────────────────

RATE_LIMIT_PER_MINUTE = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "10"))

# ── OIDC ───────────────────────────────────────────────────────────────────────

AUTH_ISSUER = os.environ.get("AUTH_ISSUER", "https://auth.trancendos.com")
AUTH_BASE_URL = os.environ.get("AUTH_BASE_URL", "http://localhost:8005")

PORT = int(os.environ.get("PORT", "8005"))


def _cors_origins() -> list[str]:
    raw = os.environ.get("CORS_ORIGINS")
    environment = os.environ.get("ENVIRONMENT", "development").lower()
    if not raw:
        if environment == "production":
            raise RuntimeError("CORS_ORIGINS must be set for Infinity in production.")
        return ["http://localhost:3000", "http://localhost:8000"]

    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    if environment == "production" and (not origins or "*" in origins):
        raise RuntimeError("CORS_ORIGINS cannot be '*' for Infinity in production.")
    return origins
