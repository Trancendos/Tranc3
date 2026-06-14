"""FastAPI application factory — zero-cost, no paid middleware."""

from __future__ import annotations

import os
from typing import Any

try:
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.middleware.gzip import GZipMiddleware
    from fastapi.middleware.trustedhost import TrustedHostMiddleware
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("fastapi is required: pip install fastapi") from exc

try:
    from api.health import router as health_router
except ImportError:
    health_router = None  # type: ignore[assignment]

try:
    from api.auth import router as auth_router
except ImportError:
    auth_router = None  # type: ignore[assignment]

try:
    from api.users import router as users_router
except ImportError:
    users_router = None  # type: ignore[assignment]

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:8000",
    "https://trancendos.com",
    "https://api.trancendos.com",
]


def create_app(
    *,
    allowed_origins: list[str] | None = None,
    allowed_hosts: list[str] | None = None,
    **kwargs: Any,
) -> FastAPI:
    """Build and return the configured FastAPI application."""
    origins = allowed_origins or os.getenv("ALLOWED_ORIGINS", ",".join(_DEFAULT_ORIGINS)).split(",")

    hosts = allowed_hosts or [
        h.strip()
        for h in os.environ.get(
            "ALLOWED_HOSTS", "localhost,trancendos.com,api.trancendos.com"
        ).split(",")
        if h.strip()
    ]

    app = FastAPI(
        title="Tranc3 API",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        **kwargs,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)
    if hosts:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)

    if health_router is not None:
        app.include_router(health_router)
    if auth_router is not None:
        app.include_router(auth_router)
    if users_router is not None:
        app.include_router(users_router)

    return app
