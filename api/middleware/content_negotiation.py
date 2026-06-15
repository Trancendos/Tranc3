"""Content negotiation middleware — JSON (default) or MessagePack."""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:
    import msgpack
    _MSGPACK = True
except ImportError:
    _MSGPACK = False


class ContentNegotiationMiddleware(BaseHTTPMiddleware):
    """Serve MessagePack when client sends Accept: application/msgpack."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        accept = request.headers.get("Accept", "")
        if _MSGPACK and "application/msgpack" in accept:
            import json
            body = b"".join([chunk async for chunk in response.body_iterator])
            try:
                data = json.loads(body)
                packed = msgpack.packb(data, use_bin_type=True)
                return Response(
                    content=packed,
                    status_code=response.status_code,
                    media_type="application/msgpack",
                    headers={"X-Content-Encoding": "msgpack"},
                )
            except Exception:
                return Response(content=body, status_code=response.status_code,
                                headers=dict(response.headers))
        return response
