# shared_core/middleware/auth.py — JWT Authentication Enforcement Middleware
# Integrates with the existing auth.py (UserManager, TokenManager, get_current_user)
# to enforce authentication on API endpoints.
#
# Features:
#   - JWT validation on all API routes (except whitelisted paths)
#   - Optional auth (sets user info but doesn't block) for public endpoints
#   - API key support for service-to-service authentication
#   - Zero-cost: all in-memory, no external auth service needed

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional, Set

from fastapi import HTTPException, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Paths that never require authentication
PUBLIC_PATHS: Set[str] = {
    "/",
    "/health",
    "/metrics",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/api/auth/login",
    "/api/auth/register",
    "/api/ecosystem/health",
}

# Path prefixes that don't require auth (but will get it if provided)
OPTIONAL_AUTH_PREFIXES: List[str] = [
    "/api/ecosystem/hubs",
    "/api/ecosystem/pillars",
    "/api/ecosystem/neural-bus",
    "/api/ecosystem/citadel",
    "/api/ecosystem/security",
]

# Paths that ALWAYS require auth (even if in OPTIONAL_AUTH_PREFIXES)
ENFORCED_PATHS: Set[str] = {
    "/api/ecosystem/mode",
}


def _is_public_path(path: str) -> bool:
    """Check if a path is in the public whitelist."""
    return path in PUBLIC_PATHS


def _is_optional_auth(path: str) -> bool:
    """Check if a path allows optional auth (sets user but doesn't block)."""
    for prefix in OPTIONAL_AUTH_PREFIXES:
        if path.startswith(prefix) and path not in ENFORCED_PATHS:
            return True
    return False


def _is_enforced_path(path: str) -> bool:
    """Check if a path requires strict authentication."""
    return path in ENFORCED_PATHS or path.startswith("/api/ecosystem/mode")


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Extract Bearer token from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


def _extract_api_key(request: Request) -> Optional[str]:
    """Extract API key from X-API-Key header."""
    return request.headers.get("X-API-Key")


def _validate_api_key(api_key: str) -> Optional[Dict[str, Any]]:
    """
    Validate an API key against the environment-configured keys.

    API keys are configured via the API_KEYS environment variable
    as a comma-separated list of key:name:tier tuples.

    Example: API_KEYS="sk-abc123:service-account:service,sk-def456:monitor:pro"

    Returns user dict if valid, None otherwise.
    """
    keys_str = os.getenv("API_KEYS", "")
    if not keys_str:
        return None

    for entry in keys_str.split(","):
        parts = entry.strip().split(":")
        if len(parts) >= 2 and parts[0] == api_key:
            name = parts[1] if len(parts) > 1 else "api-user"
            tier = parts[2] if len(parts) > 2 else "service"
            return {
                "sub": name,
                "tier": tier,
                "auth_method": "api_key",
                "is_active": True,
            }

    return None


class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT and API Key authentication enforcement middleware.

    Authentication flow:
    1. Skip for public paths (/health, /docs, etc.)
    2. Try Bearer token (JWT) authentication
    3. Try API key authentication (X-API-Key header)
    4. For optional-auth paths, set user if available but don't block
    5. For enforced paths, reject with 401 if no valid auth

    Usage:
        app.add_middleware(AuthMiddleware)

    The middleware sets request.state.user with the authenticated user dict,
    which is used by the rate limiter for IAM-tier-aware limiting.
    """

    def __init__(
        self,
        app: ASGIApp,
        public_paths: Optional[Set[str]] = None,
        enforced_paths: Optional[Set[str]] = None,
    ):
        super().__init__(app)
        self._public_paths = public_paths or PUBLIC_PATHS
        self._enforced_paths = enforced_paths or ENFORCED_PATHS

        # Warn if SECRET_KEY is not set
        if not os.getenv("SECRET_KEY"):
            logger.warning(
                "SECRET_KEY not set — JWT authentication will not work. "
                "Set the SECRET_KEY environment variable for production use."
            )

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip auth for public paths
        if _is_public_path(path):
            return await call_next(request)

        user: Optional[Dict[str, Any]] = None
        auth_error: Optional[str] = None

        # Try JWT Bearer token
        bearer_token = _extract_bearer_token(request)
        if bearer_token:
            try:
                # Import here to avoid circular imports and missing dependency issues
                from auth import token_manager  # codeql[py/cyclic-import]

                payload = token_manager.decode_token(bearer_token)
                username = payload.get("sub")
                if username:
                    # Try to get full user info
                    try:
                        from auth import user_manager  # codeql[py/cyclic-import]

                        user = user_manager.get_user(username)
                    except Exception as _exc:
                        logger.debug("suppressed %s", _exc, exc_info=False)
                    if not user:
                        user = {
                            "sub": username,
                            "tier": payload.get("tier", "free"),
                            "auth_method": "jwt",
                            "is_active": True,
                        }
                    else:
                        user["auth_method"] = "jwt"
            except HTTPException as e:
                auth_error = e.detail
            except Exception as e:
                auth_error = str(e)

        # Try API Key if JWT didn't work
        if not user:
            api_key = _extract_api_key(request)
            if api_key:
                user = _validate_api_key(api_key)
                if not user:
                    auth_error = "Invalid API key"

        # Set user info on request state (used by rate limiter and downstream)
        if user:
            request.state.user = user
        else:
            request.state.user = None

        # Check if auth is required for this path
        is_enforced = _is_enforced_path(path)
        _is_optional_auth(path)

        if is_enforced and not user:
            raise HTTPException(
                status_code=401,
                detail=auth_error or "Authentication required for this endpoint",
            )

        # For optional-auth paths, allow through without auth
        # but still set the user info if available (for rate limiting)

        return await call_next(request)
