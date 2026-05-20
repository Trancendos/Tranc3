# src/security/middleware.py
# Security headers middleware — 5 Whys #5 root cause fix
# Wires SecurityHeaders into every FastAPI response

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
import logging

logger = logging.getLogger(__name__)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Content-Security-Policy": "default-src 'self'; connect-src 'self' https://api.tranc3.ai",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
    "X-Powered-By": "TRANC3-Conscious-AI",
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
    Combined governance layer: request ID injection, basic logging,
    and Cryptex threat scanning on mutating requests.
    """

    # Paths exempt from Cryptex scanning (health checks, SSE streams)
    _SCAN_SKIP = frozenset({"/health", "/ready", "/observatory/sse", "/mcp/sse"})

    async def dispatch(self, request: Request, call_next) -> Response:
        import os
        from fastapi.responses import JSONResponse as _JSONResponse

        request_id = os.urandom(6).hex()
        request.state.request_id = request_id

        # Cryptex scan on POST/PUT/PATCH to non-exempt paths
        path = request.url.path
        if request.method in ("POST", "PUT", "PATCH") and path not in self._SCAN_SKIP:
            try:
                from src.cryptex.threat_detector import get_cryptex

                cx = get_cryptex()
                ip = request.client.host if request.client else None
                if cx.is_blocked(ip=ip):
                    return _JSONResponse(
                        {"error": "Access denied"},
                        status_code=403,
                        headers={"X-Request-ID": request_id},
                    )
                # Reject oversized bodies before buffering to prevent OOM
                MAX_BODY = 1 * 1024 * 1024  # 1 MB
                content_length = request.headers.get("content-length")
                if content_length and int(content_length) > MAX_BODY:
                    return _JSONResponse(
                        {"error": "Request body too large"},
                        status_code=413,
                        headers={"X-Request-ID": request_id},
                    )
                body_bytes = await request.body()
                body_text = body_bytes.decode("utf-8", errors="replace")[:1000]
                signals = cx.analyse_request(
                    path=path, body=body_text, headers=dict(request.headers), ip=ip
                )
                if any(s.severity.value == "critical" for s in signals):
                    return _JSONResponse(
                        {"error": "Request blocked by Cryptex"},
                        status_code=403,
                        headers={"X-Request-ID": request_id},
                    )

                # Re-attach body so FastAPI can read it normally
                async def _body_override():
                    return body_bytes

                request._body = body_bytes
            except Exception:
                pass  # Never block on Cryptex failure

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
