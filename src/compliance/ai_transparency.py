"""AI Transparency Headers middleware — REQ-AI-003 / EU AI Act Art. 50.

Injects X-AI-Generated, X-AI-Model, and X-AI-Provider headers on all
responses from AI inference routes. Enables downstream consumers to identify
AI-generated content programmatically.
"""

import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Routes that serve AI-generated content
_AI_ROUTES = frozenset([
    "/v1/chat",
    "/v1/completions",
    "/v1/embed",
    "/mcp/rpc",
    "/generate",
    "/chat",
    "/inference",
    "/ai/",
])


class AITransparencyMiddleware(BaseHTTPMiddleware):
    """Attach EU AI Act transparency headers to AI inference responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        path = request.url.path
        is_ai_route = any(path.startswith(r) for r in _AI_ROUTES)

        if is_ai_route:
            response.headers["X-AI-Generated"] = "true"
            response.headers["X-AI-Provider"] = os.getenv("AI_PROVIDER_LABEL", "Tranc3-AI")
            response.headers["X-AI-Assistive-Only"] = "true"
            # X-AI-Model populated downstream by infinity-ai worker when known
            if not response.headers.get("X-AI-Model"):
                response.headers["X-AI-Model"] = os.getenv("DEFAULT_AI_MODEL", "unknown")

        return response
