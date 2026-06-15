"""Idempotency key middleware — safe retries for POST/PUT/PATCH."""
from __future__ import annotations
import hashlib
import time
from collections import OrderedDict
from typing import Dict, Tuple
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_CACHE_TTL = 300  # 5 minutes
_MAX_CACHE = 10_000


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Cache responses for requests bearing an Idempotency-Key header."""

    def __init__(self, app, ttl: int = _CACHE_TTL, max_size: int = _MAX_CACHE) -> None:
        super().__init__(app)
        self._ttl = ttl
        self._store: OrderedDict[str, Tuple[float, int, bytes, Dict]] = OrderedDict()

    async def dispatch(self, request: Request, call_next):
        key = request.headers.get("Idempotency-Key")
        if not key or request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        cache_key = hashlib.sha256(
            f"{request.method}:{request.url.path}:{key}".encode()
        ).hexdigest()

        now = time.monotonic()
        # Evict expired
        expired = [k for k, (ts, *_) in self._store.items() if now - ts > self._ttl]
        for k in expired:
            self._store.pop(k, None)

        if cache_key in self._store:
            _, status, body, headers = self._store[cache_key]
            return Response(content=body, status_code=status, headers={**headers, "X-Idempotent-Replayed": "true"})

        response = await call_next(request)
        body = b"".join([chunk async for chunk in response.body_iterator])

        if len(self._store) >= _MAX_CACHE:
            self._store.popitem(last=False)
        self._store[cache_key] = (now, response.status_code, body, dict(response.headers))

        return Response(
            content=body,
            status_code=response.status_code,
            headers={**dict(response.headers), "X-Idempotency-Key": key},
        )
