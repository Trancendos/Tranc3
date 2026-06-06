# src/security/middleware.py
# Security headers middleware — 5 Whys #5 root cause fix
# Wires SecurityHeaders into every FastAPI response

import logging
import os

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

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
                    path=path,
                    body=body_text,
                    headers=dict(request.headers),
                    ip=ip,
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
            except Exception:  # noqa: S110
                pass  # nosec B110 - never block on Cryptex failure

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


class RBACMiddleware(BaseHTTPMiddleware):
    """
    Populates ``request.state.user`` from a Bearer JWT so that
    ``require_permission()`` can enforce RBAC without a separate dependency.

    Runs before route handlers; silently skips unauthenticated requests so
    public endpoints are unaffected.  The existing ``get_current_user``
    dependency still works independently — this middleware is additive.
    """

    _PUBLIC_PREFIXES = frozenset(
        {
            "/health",
            "/ready",
            "/docs",
            "/openapi",
            "/redoc",
            "/auth/register",
            "/auth/token",
            "/mcp/health",
        },
    )

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path.startswith(pfx) for pfx in self._PUBLIC_PREFIXES):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            try:
                from auth import token_manager as _tm  # lazy, avoids circular import

                payload = _tm.decode_token(token)
                username = payload.get("sub")
                if username:
                    user: dict | None = None
                    try:
                        import api as _api  # lazy import

                        mgr = getattr(_api, "db_user_manager", None)
                        if mgr:
                            user = mgr.get_user(username)
                    except Exception as _exc:
                        logger.debug("db_user_manager lookup failed: %s", _exc)
                    if user is None:
                        from auth import user_manager as _um

                        user = _um.get_user(username)
                    if user:
                        request.state.user = user
            except Exception:
                pass  # invalid token → leave request.state.user unset

        return await call_next(request)


class ZeroTrustASGIMiddleware(BaseHTTPMiddleware):
    """
    ASGI wrapper around ZeroTrustMiddleware.

    Skips enforcement when ZERO_TRUST_ENABLED=false (e.g. local dev).
    Reads MFA routes from ZERO_TRUST_MFA_ROUTES (comma-separated paths).
    """

    _SKIP_PREFIXES = frozenset({"/health", "/ready", "/docs", "/openapi", "/mcp/health"})

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        self._enabled = os.getenv("ZERO_TRUST_ENABLED", "true").lower() not in ("false", "0", "no")
        if self._enabled:
            try:
                from src.auth.zero_trust import ZeroTrustMiddleware, ZeroTrustOptions

                mfa_routes = [
                    p.strip()
                    for p in os.getenv("ZERO_TRUST_MFA_ROUTES", "/admin,/api/secrets").split(",")
                    if p.strip()
                ]
                blocked_countries = [
                    c.strip()
                    for c in os.getenv("ZERO_TRUST_BLOCKED_COUNTRIES", "").split(",")
                    if c.strip()
                ]
                self._zt = ZeroTrustMiddleware(
                    ZeroTrustOptions(
                        mfa_routes=mfa_routes,
                        blocked_countries=blocked_countries,
                    ),
                )
                logger.info("ZeroTrustASGIMiddleware active (MFA routes: %s)", mfa_routes)
            except Exception:
                self._enabled = False
                logger.warning("ZeroTrustMiddleware unavailable — skipping zero-trust enforcement")

    async def dispatch(self, request: Request, call_next) -> Response:
        from fastapi.responses import JSONResponse as _JSONResponse

        if not self._enabled:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(pfx) for pfx in self._SKIP_PREFIXES):
            return await call_next(request)

        headers = dict(request.headers)
        context = self._zt.extract_context(headers)
        decision = self._zt.evaluate(context, path)

        if decision.access_policy.value == "deny":
            reason = getattr(decision, "block_reason", "Zero Trust policy violation")
            logger.warning("ZeroTrust blocked request: path=%s reason=%s", path, reason)
            return _JSONResponse({"error": "Access denied", "reason": reason}, status_code=403)

        return await call_next(request)
