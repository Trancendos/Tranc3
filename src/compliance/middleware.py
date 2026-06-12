# src/compliance/middleware.py
# Magna Carta ASGI middleware — evaluates MC-RULE-001 through MC-RULE-009 per request

from __future__ import annotations

import logging

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = logging.getLogger("tranc3.compliance.middleware")

# Paths that never run through Magna Carta (health + metrics + SSE streams)
_MC_SKIP_PATHS = frozenset(
    {
        "/health",
        "/ready",
        "/metrics",
        "/openapi.json",
        "/docs",
        "/redoc",
        "/favicon.ico",
        "/mcp/sse",
        "/observatory/sse",
    }
)


class MagnaCartaMiddleware(BaseHTTPMiddleware):
    """
    Evaluates Magna Carta runtime rules on every request.

    In advisory mode (the default) violations are logged but never block requests.
    Set enforcement.fail_closed_on_violation=true in magna_carta_config.json AND
    MAGNA_CARTA_ENABLED=true to switch to enforcement mode.

    Adds response headers:
      X-MC-Compliant: true | false
      X-MC-Violations: <count>   (only when violations > 0)
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)
        from src.compliance.magna_carta import MAGNA_CARTA_ENABLED, compliance

        self._compliance = compliance
        self._enabled = MAGNA_CARTA_ENABLED
        if self._enabled:
            logger.info("MagnaCartaMiddleware ACTIVE — rules enforcement wired")
        else:
            logger.debug("MagnaCartaMiddleware loaded but MAGNA_CARTA_ENABLED=false")

    async def dispatch(self, request: Request, call_next) -> Response:
        if not self._enabled:
            return await call_next(request)

        path = request.url.path
        if path in _MC_SKIP_PATHS:
            return await call_next(request)

        # Build request_data from available context.
        # ZeroTrustASGIMiddleware (outer) has already decoded JWT and set request.state.
        headers = dict(request.headers)
        jwt_claims: dict = {}
        try:
            # Reuse already-decoded claims placed on request.state by ZeroTrustASGIMiddleware
            jwt_claims = getattr(request.state, "jwt_claims", {}) or {}
        except Exception:  # noqa: BLE001 — request.state access can raise on uninitialized state
            pass

        zero_trust_ok = getattr(request.state, "zero_trust_ok", None)
        tenant_tier = getattr(request.state, "tenant_tier", "free")
        request_count = getattr(request.state, "request_count", None)

        request_data = {
            "path": path,
            "method": request.method,
            "headers": headers,
            "query_params": dict(request.query_params),
            "content_type": request.headers.get("content-type", ""),
            "user_agent": request.headers.get("user-agent", ""),
            "user_id": getattr(request.state, "user_id", None),
            "jwt_claims": jwt_claims,
            "zero_trust_ok": zero_trust_ok,
            "tenant_tier": tenant_tier,
            "request_count": request_count,
            "ip": request.client.host if request.client else None,
            # AI / governance fields populated from request.state when set by route handlers
            "model_id": getattr(request.state, "model_id", None),
            "use_case": getattr(request.state, "use_case", None),
            "change_type": getattr(request.state, "change_type", None),
            "cab_approved": getattr(request.state, "cab_approved", None),
        }

        result = self._compliance.check_request(request_data)
        violations = result.get("violations", [])
        is_compliant = result.get("compliant", True)
        # Use fail_closed_on_violation from the config result (set by the rule engine)
        fail_closed = result.get("fail_closed", False) and not is_compliant

        if not is_compliant:
            logger.warning(
                "Magna Carta violations on %s %s: %s",
                request.method,
                path,
                [v.get("rule_id") for v in violations],
            )

        if fail_closed and any(v.get("severity") == "high" for v in violations):
            return JSONResponse(
                {
                    "error": "Request blocked by compliance policy",
                    "violations": [
                        {"rule_id": v["rule_id"], "message": v.get("message", "")}
                        for v in violations
                        if v.get("severity") == "high"
                    ],
                    "framework": "magna_carta_v1",
                },
                status_code=403,
                headers={
                    "X-MC-Compliant": "false",
                    "X-MC-Violations": str(len(violations)),
                },
            )

        response = await call_next(request)

        # Run response-side checks (MC-RULE-002 PII leakage, MC-RULE-008 transparency)
        if hasattr(self._compliance, "check_response"):
            try:
                resp_result = self._compliance.check_response(
                    {**request_data, "status_code": response.status_code}
                )
                resp_violations = resp_result.get("violations", [])
                if resp_violations:
                    violations = violations + resp_violations
                    is_compliant = False
                    logger.warning(
                        "Magna Carta response violations on %s %s: %s",
                        request.method,
                        path,
                        [v.get("rule_id") for v in resp_violations],
                    )
            except Exception:  # noqa: BLE001 — response checks must never crash the response
                pass

        response.headers["X-MC-Compliant"] = "true" if is_compliant else "false"
        if violations:
            response.headers["X-MC-Violations"] = str(len(violations))
        return response
