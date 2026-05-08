# src/security/middleware.py
# Security headers middleware — 5 Whys #5 root cause fix
# Wires SecurityHeaders into every FastAPI response

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options":    "nosniff",
    "X-Frame-Options":           "DENY",
    "X-XSS-Protection":          "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy":   "default-src 'self'; connect-src 'self' https://api.tranc3.ai",
    "Referrer-Policy":           "strict-origin-when-cross-origin",
    "Permissions-Policy":        "geolocation=(), microphone=(), camera=()",
    "X-Powered-By":              "TRANC3-Conscious-AI",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Applies security headers to every response.
    Root cause fix: SecurityHeaders class existed but was never wired in.
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        logger.info("SecurityHeadersMiddleware active")

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


class GovernanceMiddleware(BaseHTTPMiddleware):
    """
    SCAMPER-C: Combined governance layer.
    Handles request ID injection and basic request logging.
    Auth, rate limiting, and compliance are handled as FastAPI dependencies.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        import os
        request_id = os.urandom(6).hex()
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
