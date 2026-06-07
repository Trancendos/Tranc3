"""
AuditMiddleware — auto-logs every HTTP request/response to The Observatory.

Every request through the platform gets:
  - A unique X-Request-ID header (UUID4, generated if not present)
  - An AuditEvent recorded in The Observatory with method, path, status, timing, actor
  - SECURITY/CRITICAL events forwarded to Cryptex via Observatory

Sensitive paths (e.g. /auth/token) mask the body but still log metadata.
Health-check paths (/health, /metrics, /favicon.ico) are skipped to reduce noise.
"""

from __future__ import annotations

import time
import uuid
from typing import Callable, Optional, Set

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from src.observability.observatory import EventCategory, EventSeverity

# Paths excluded from audit logging (health probes, metrics scrape, static assets)
_SKIP_PATHS: Set[str] = {
    "/health",
    "/health/",
    "/metrics",
    "/metrics/",
    "/favicon.ico",
    "/docs",
    "/redoc",
    "/openapi.json",
}

# Paths where request bodies should not be logged (may contain credentials)
_SENSITIVE_PATHS: Set[str] = {
    "/auth/token",
    "/auth/register",
    "/auth/change-password",
    "/admin/settings",
}


def _category_for_path(path: str) -> EventCategory:
    if path.startswith("/auth"):
        return EventCategory.AUTH
    if path.startswith("/admin"):
        return EventCategory.GOVERNANCE
    if path.startswith("/billing") or path.startswith("/payments"):
        return EventCategory.BILLING
    if path.startswith("/mcp") or path.startswith("/ai") or path.startswith("/chat"):
        return EventCategory.AI
    if path.startswith("/observatory"):
        return EventCategory.AUDIT
    if path.startswith("/workflow") or path.startswith("/grid"):
        return EventCategory.WORKFLOW
    if path.startswith("/secrets") or path.startswith("/vault"):
        return EventCategory.SECRETS
    if path.startswith("/security") or path.startswith("/scan"):
        return EventCategory.SECURITY
    return EventCategory.SYSTEM


def _severity_for_status(status: int) -> EventSeverity:
    if status < 400:
        return EventSeverity.INFO
    if status < 500:
        return EventSeverity.WARNING
    # 5xx
    return EventSeverity.CRITICAL


def _extract_actor(request: Request) -> Optional[str]:
    """Best-effort actor extraction from JWT sub claim or API key header."""
    auth: str = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        # Avoid importing jwt here to keep middleware import cost low;
        # use the pre-decoded user if middleware has already set it in state.
        user = getattr(request.state, "user", None)
        if user:
            uid = getattr(user, "id", None) or getattr(user, "sub", None)
            return f"user:{uid}" if uid else "user:authenticated"
        return "user:authenticated"
    if request.headers.get("x-api-key"):
        return "apikey:anonymous"
    return "anonymous"


class AuditMiddleware(BaseHTTPMiddleware):
    """ASGI middleware — records an AuditEvent for every non-skip HTTP request."""

    def __init__(self, app: ASGIApp, service_name: str = "tranc3-backend") -> None:
        super().__init__(app)
        self._service = service_name
        # Lazy observatory import to avoid circular imports at module load time
        self._observatory = None

    def _get_observatory(self):
        if self._observatory is None:
            from src.observability.observatory import get_observatory

            self._observatory = get_observatory()
        return self._observatory

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path

        # Skip noisy health / metrics paths
        if path in _SKIP_PATHS or path.startswith("/static"):
            return await call_next(request)

        # Assign or forward X-Request-ID
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        request.state.request_id = request_id

        start = time.perf_counter()
        status_code = 500
        outcome = "failure"

        try:
            response: Response = await call_next(request)
            status_code = response.status_code
            outcome = "success" if status_code < 400 else "failure"
        except Exception:
            outcome = "failure"
            raise
        finally:
            elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
            actor = _extract_actor(request)
            category = _category_for_path(path)
            severity = _severity_for_status(status_code)

            metadata: dict = {
                "method": request.method,
                "path": path,
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "user_agent": request.headers.get("user-agent", "")[:200],
                "request_id": request_id,
            }

            # Query params logged only for non-sensitive paths
            if path not in _SENSITIVE_PATHS and request.url.query:
                metadata["query"] = str(request.url.query)[:500]

            try:
                obs = self._get_observatory()
                obs.record(
                    f"http.{request.method.lower()}",
                    actor=actor,
                    actor_ip=request.client.host if request.client else None,
                    target=path,
                    category=category,
                    severity=severity,
                    service=self._service,
                    outcome=outcome,
                    metadata=metadata,
                    session_id=request_id,
                )
            except Exception:
                # Never let audit logging break request processing
                pass

        # Propagate request ID in response headers
        response.headers["x-request-id"] = request_id
        return response
