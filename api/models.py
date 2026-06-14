"""Pydantic v2 response models for the Tranc3 API."""

from __future__ import annotations

from typing import Any, Optional

try:
    from pydantic import BaseModel, ConfigDict, Field
except ImportError as exc:  # pragma: no cover
    raise RuntimeError("pydantic v2 required: pip install 'pydantic>=2'") from exc

import time


class TokenResponse(BaseModel):
    """OAuth2 token pair returned by /auth/token."""

    model_config = ConfigDict(frozen=True)

    access_token: str
    token_type: str = "bearer"
    refresh_token: Optional[str] = None


class UserResponse(BaseModel):
    """Minimal user profile."""

    model_config = ConfigDict(frozen=True)

    id: Optional[str] = None
    username: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None


class HealthResponse(BaseModel):
    """Shallow liveness payload."""

    model_config = ConfigDict(frozen=True)

    status: str = "ok"
    timestamp: float = Field(default_factory=time.time)
    version: str = "1.0.0"


class WorkerHealth(BaseModel):
    """Single worker status within a deep health report."""

    model_config = ConfigDict(frozen=True)

    status: str
    http_status: Optional[int] = None
    error: Optional[str] = None


class DeepHealthResponse(BaseModel):
    """Readiness payload including P0 worker probes."""

    model_config = ConfigDict(frozen=True)

    status: str
    timestamp: float = Field(default_factory=time.time)
    version: str = "1.0.0"
    workers: dict[str, Any] = Field(default_factory=dict)
