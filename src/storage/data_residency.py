"""
Data Residency Enforcement — Trancendos Platform
=================================================
Enforces DATA_RESIDENCY_REGION at the storage layer so that write
operations targeting an out-of-region path or connection are blocked
(or warned) before any data is written.

Environment variables:
    DATA_RESIDENCY_REGION           Active region (default: eu-west)
    DATA_RESIDENCY_ALLOWED_REGIONS  Comma-separated whitelist (default: eu-west,eu-central)
    DATA_RESIDENCY_ENFORCE          "true" to hard-fail on violation (default: true)

Usage:
    from src.storage.data_residency import get_residency, enforce_residency

    # Check before a write
    enforce_residency()  # raises DataResidencyViolation if region not allowed

    # Namespace a storage path by region
    path = get_residency().namespaced_path("/data/users.db")
    # → "/data/eu-west/users.db"

    # FastAPI dependency
    from src.storage.data_residency import ResidencyCheckDep
    @router.post("/data")
    async def write_data(residency: ResidencyCheckDep): ...

    # Decorator for functions that perform writes
    @residency_required
    def store_record(record): ...
"""

from __future__ import annotations

import functools
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Callable, Optional

from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_REGION = os.environ.get("DATA_RESIDENCY_REGION", "eu-west").strip()
_ALLOWED_RAW = os.environ.get("DATA_RESIDENCY_ALLOWED_REGIONS", "eu-west,eu-central")
_ALLOWED_REGIONS: list[str] = [r.strip() for r in _ALLOWED_RAW.split(",") if r.strip()]
_ENFORCE = os.environ.get("DATA_RESIDENCY_ENFORCE", "true").lower() == "true"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class DataResidencyViolation(Exception):
    """Raised when a write is attempted outside the allowed residency regions."""

    def __init__(self, region: str, allowed: list[str]) -> None:
        self.region = region
        self.allowed = allowed
        super().__init__(
            f"Data residency violation: active region '{region}' is not in allowed regions {allowed}"
        )


# ---------------------------------------------------------------------------
# Core dataclass
# ---------------------------------------------------------------------------


@dataclass
class ResidencyConfig:
    region: str
    allowed_regions: list[str]
    enforce: bool
    checked_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @property
    def is_compliant(self) -> bool:
        return self.region in self.allowed_regions

    def assert_compliant(self) -> None:
        """Raise DataResidencyViolation if region is not in allowed list."""
        if not self.is_compliant:
            _audit_violation(self.region, self.allowed_regions)
            if self.enforce:
                raise DataResidencyViolation(self.region, self.allowed_regions)
            logger.warning(
                "data_residency: non-compliant region '%s' (allowed: %s) — enforcement disabled",
                self.region,
                self.allowed_regions,
            )

    def namespaced_path(self, base_path: str) -> str:
        """Return base_path with the active region inserted as a subdirectory."""
        p = Path(base_path)
        return str(p.parent / self.region / p.name)

    def as_dict(self) -> dict:
        return {
            "region": self.region,
            "allowed_regions": self.allowed_regions,
            "enforce": self.enforce,
            "is_compliant": self.is_compliant,
            "checked_at": self.checked_at,
        }


# ---------------------------------------------------------------------------
# Module-level singleton (re-reads env on each call so hot-reload works)
# ---------------------------------------------------------------------------


def get_residency() -> ResidencyConfig:
    """Return the current residency configuration (reads env at call time)."""
    region = os.environ.get("DATA_RESIDENCY_REGION", "eu-west").strip()
    allowed_raw = os.environ.get("DATA_RESIDENCY_ALLOWED_REGIONS", "eu-west,eu-central")
    allowed = [r.strip() for r in allowed_raw.split(",") if r.strip()]
    enforce = os.environ.get("DATA_RESIDENCY_ENFORCE", "true").lower() == "true"
    return ResidencyConfig(region=region, allowed_regions=allowed, enforce=enforce)


def enforce_residency(region: Optional[str] = None) -> ResidencyConfig:
    """
    Validate residency and raise DataResidencyViolation (or warn) on breach.

    Args:
        region: Override the env-configured region for this check.

    Returns the ResidencyConfig for the caller to inspect.
    """
    cfg = get_residency()
    if region is not None:
        cfg = ResidencyConfig(
            region=region,
            allowed_regions=cfg.allowed_regions,
            enforce=cfg.enforce,
        )
    cfg.assert_compliant()
    return cfg


# ---------------------------------------------------------------------------
# Audit helper (fires an Observatory event if available)
# ---------------------------------------------------------------------------


def _audit_violation(region: str, allowed: list[str]) -> None:
    try:
        from src.observability.observatory import (  # noqa: PLC0415
            AuditEvent,
            EventCategory,
            EventSeverity,
            get_observatory,
        )

        obs = get_observatory()
        obs.record(
            AuditEvent(
                event_type="data_residency_violation",
                actor="system",
                target=f"region:{region}",
                outcome="blocked",
                category=EventCategory.SECURITY,
                severity=EventSeverity.SECURITY,
                metadata={"active_region": region, "allowed_regions": allowed},
            )
        )
    except Exception:
        pass  # Observatory unavailable — log only


def _audit_write(region: str, path: str) -> None:
    try:
        from src.observability.observatory import (  # noqa: PLC0415
            AuditEvent,
            EventCategory,
            EventSeverity,
            get_observatory,
        )

        obs = get_observatory()
        obs.record(
            AuditEvent(
                event_type="data_residency_write",
                actor="system",
                target=path,
                outcome="allowed",
                category=EventCategory.DATA,
                severity=EventSeverity.INFO,
                metadata={"region": region},
            )
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------------------------


async def _residency_dependency() -> ResidencyConfig:
    try:
        cfg = enforce_residency()
        return cfg
    except DataResidencyViolation as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


ResidencyCheckDep = Annotated[ResidencyConfig, Depends(_residency_dependency)]


# ---------------------------------------------------------------------------
# Decorator
# ---------------------------------------------------------------------------


def residency_required(fn: Callable) -> Callable:
    """Decorator: enforce data residency before executing the wrapped function."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        enforce_residency()
        return fn(*args, **kwargs)

    @functools.wraps(fn)
    async def async_wrapper(*args, **kwargs):
        enforce_residency()
        return await fn(*args, **kwargs)

    import asyncio  # noqa: PLC0415

    if asyncio.iscoroutinefunction(fn):
        return async_wrapper
    return wrapper


# ---------------------------------------------------------------------------
# Storage path helper
# ---------------------------------------------------------------------------


def region_namespaced_path(base_path: str) -> str:
    """
    Return a region-namespaced storage path.

    Example:
        region_namespaced_path("/data/users.db")
        # → "/data/eu-west/users.db"  (when DATA_RESIDENCY_REGION=eu-west)
    """
    cfg = get_residency()
    return cfg.namespaced_path(base_path)


def ensure_region_dir(base_path: str) -> Path:
    """
    Create and return the region-namespaced directory for a given base path.

    Example:
        ensure_region_dir("/data")
        # Creates /data/eu-west/ and returns Path("/data/eu-west")
    """
    cfg = get_residency()
    region_dir = Path(base_path) / cfg.region
    region_dir.mkdir(parents=True, exist_ok=True)
    return region_dir


# ---------------------------------------------------------------------------
# Middleware (optional — add to FastAPI app)
# ---------------------------------------------------------------------------


class DataResidencyMiddleware:
    """
    ASGI middleware that adds X-Data-Residency-Region response header and
    blocks write requests (POST/PUT/PATCH/DELETE) when enforcement is active
    and the current region is not allowed.
    """

    WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        cfg = get_residency()

        if scope["method"] in self.WRITE_METHODS and not cfg.is_compliant:
            _audit_violation(cfg.region, cfg.allowed_regions)
            if cfg.enforce:
                from starlette.responses import JSONResponse  # noqa: PLC0415

                response = JSONResponse(
                    {"detail": f"Data residency violation: region '{cfg.region}' not allowed"},
                    status_code=403,
                )
                await response(scope, receive, send)
                return
            logger.warning(
                "data_residency_middleware: non-compliant write from region '%s' — enforcement disabled",
                cfg.region,
            )

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-data-residency-region", cfg.region.encode()))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
