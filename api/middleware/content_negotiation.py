"""Content negotiation middleware — JSON (default) or MessagePack."""

from __future__ import annotations

import json

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

try:
    import msgpack

    _MSGPACK = True
except ImportError:
    _MSGPACK = False


class ContentNegotiationMiddleware(BaseHTTPMiddleware):
    """Serve MessagePack when client sends Accept: application/msgpack.

    Only converts application/json responses — streaming responses and
    non-JSON content types are passed through unchanged to avoid OOM on
    SSE streams or large file downloads.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        if not _MSGPACK:
            return response
        accept = request.headers.get("Accept", "")
        content_type = response.headers.get("content-type", "")
        if "application/msgpack" not in accept or "application/json" not in content_type:
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])
        try:
            data = json.loads(body)
            packed = msgpack.packb(data, use_bin_type=True)
            # Preserve original headers; override content-type and add encoding hint
            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() not in ("content-length", "content-type")
            }
            headers["X-Content-Encoding"] = "msgpack"
            return Response(
                content=packed,
                status_code=response.status_code,
                media_type="application/msgpack",
                headers=headers,
            )
        except Exception:
            return Response(
                content=body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )
