# src/core/redis_store.py
# Shared async Redis persistence layer — backed by Upstash (REDIS_URL env var).
# Falls back to an in-memory dict when Redis is unavailable so dev/test never breaks.
#
# Usage:
#   from src.core.redis_store import get_store
#   store = await get_store()
#   await store.set("citadel:deploy:abc", deploy_dict, ttl=86400)
#   data = await store.get("citadel:deploy:abc")
#   keys = await store.keys("citadel:deploy:*")
#   await store.delete("citadel:deploy:abc")

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_REDIS_URL = os.environ.get("REDIS_URL", "")


class _InMemoryFallback:
    """Thread-safe in-memory dict that mirrors the Redis async interface."""

    def __init__(self) -> None:
        self._data: Dict[str, Any] = {}
        self._expiry: Dict[str, float] = {}

    def _evict(self, key: str) -> bool:
        exp = self._expiry.get(key)
        if exp and time.time() > exp:
            self._data.pop(key, None)
            self._expiry.pop(key, None)
            return True
        return False

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self._data[key] = value
        if ttl:
            self._expiry[key] = time.time() + ttl

    async def get(self, key: str) -> Optional[Any]:
        if self._evict(key):
            return None
        return self._data.get(key)

    async def delete(self, key: str) -> None:
        self._data.pop(key, None)
        self._expiry.pop(key, None)

    async def keys(self, pattern: str) -> List[str]:
        import fnmatch

        return [
            k for k in list(self._data.keys()) if fnmatch.fnmatch(k, pattern) and not self._evict(k)
        ]

    async def hset(self, name: str, mapping: Dict[str, Any]) -> None:
        existing = self._data.get(name, {})
        existing.update(mapping)
        self._data[name] = existing

    async def hget(self, name: str, field: str) -> Optional[Any]:
        return self._data.get(name, {}).get(field)

    async def hgetall(self, name: str) -> Dict[str, Any]:
        return dict(self._data.get(name, {}))

    async def hdel(self, name: str, *fields: str) -> None:
        h = self._data.get(name, {})
        for f in fields:
            h.pop(f, None)

    async def ping(self) -> bool:
        return True

    @property
    def backend(self) -> str:
        return "memory"


class _RedisStore:
    """Async Redis store backed by Upstash via redis-py asyncio client."""

    def __init__(self, client: Any) -> None:
        self._r = client

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        raw = json.dumps(value)
        if ttl:
            await self._r.setex(key, ttl, raw)
        else:
            await self._r.set(key, raw)

    async def get(self, key: str) -> Optional[Any]:
        raw = await self._r.get(key)
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        await self._r.delete(key)

    async def keys(self, pattern: str) -> List[str]:
        result = await self._r.keys(pattern)
        return [k.decode() if isinstance(k, bytes) else k for k in result]

    async def hset(self, name: str, mapping: Dict[str, Any]) -> None:
        encoded = {k: json.dumps(v) for k, v in mapping.items()}
        await self._r.hset(name, mapping=encoded)

    async def hget(self, name: str, field: str) -> Optional[Any]:
        raw = await self._r.hget(name, field)
        if raw is None:
            return None
        return json.loads(raw)

    async def hgetall(self, name: str) -> Dict[str, Any]:
        raw = await self._r.hgetall(name)
        return {(k.decode() if isinstance(k, bytes) else k): json.loads(v) for k, v in raw.items()}

    async def hdel(self, name: str, *fields: str) -> None:
        await self._r.hdel(name, *fields)

    async def ping(self) -> bool:
        result = await self._r.ping()
        return bool(result)

    @property
    def backend(self) -> str:
        return "redis"


_store: Optional[Any] = None


async def get_store() -> Any:
    """Return the singleton store (Redis or in-memory fallback)."""
    global _store
    if _store is not None:
        return _store

    if _REDIS_URL:
        try:
            import redis.asyncio as aioredis

            client = aioredis.from_url(
                _REDIS_URL,
                encoding="utf-8",
                decode_responses=False,
                socket_connect_timeout=3,
                socket_timeout=3,
            )
            await client.ping()
            _store = _RedisStore(client)
            logger.info("redis_store: connected to Redis (%s)", _REDIS_URL[:30])
        except Exception as exc:
            logger.warning("redis_store: Redis unavailable (%s) — using in-memory fallback", exc)
            _store = _InMemoryFallback()
    else:
        logger.info("redis_store: no REDIS_URL — using in-memory fallback")
        _store = _InMemoryFallback()

    return _store


def reset_store() -> None:
    """Reset singleton — used in tests."""
    global _store
    _store = None
