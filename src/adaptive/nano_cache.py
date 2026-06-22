"""
src/adaptive/nano_cache.py
==========================
Nano-scale distributed cache with gossip protocol.

Each NanoNode holds a TTL-keyed store. Nodes gossip updates to peers
(HTTP POST). Eviction uses LRU policy.
"""

from __future__ import annotations

import logging
import os
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

NANO_CACHE_PEERS = [
    p.strip() for p in os.getenv("NANO_CACHE_PEERS", "").split(",") if p.strip()
]
DEFAULT_TTL = 300  # seconds
MAX_CACHE_SIZE = 1000


@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    accessed_at: float = field(default_factory=time.time)

    @property
    def expired(self) -> bool:
        return time.time() > self.expires_at


class NanoNode:
    """Single cache node with TTL-based eviction."""

    def __init__(self, node_id: str = "local", max_size: int = MAX_CACHE_SIZE) -> None:
        self.node_id = node_id
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._max_size = max_size

    def set(self, key: str, value: Any, ttl: float = DEFAULT_TTL) -> None:
        self._store[key] = CacheEntry(value=value, expires_at=time.time() + ttl)
        self._store.move_to_end(key)
        if len(self._store) > self._max_size:
            self.evict_lru()

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            return None
        if entry.expired:
            del self._store[key]
            return None
        entry.accessed_at = time.time()
        self._store.move_to_end(key)
        return entry.value

    def delete(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def evict_lru(self) -> Optional[str]:
        """Remove least recently used entry. Returns evicted key."""
        while self._store:
            key, entry = next(iter(self._store.items()))
            if entry.expired or len(self._store) > self._max_size:
                del self._store[key]
                return key
            break
        return None

    def purge_expired(self) -> int:
        """Remove all expired entries. Returns count removed."""
        expired_keys = [k for k, e in self._store.items() if e.expired]
        for k in expired_keys:
            del self._store[k]
        return len(expired_keys)

    def stats(self) -> dict[str, Any]:
        active = sum(1 for e in self._store.values() if not e.expired)
        return {"node_id": self.node_id, "total": len(self._store), "active": active}


class NanoCache:
    """Distributed nano-scale cache with gossip propagation."""

    def __init__(
        self,
        node_id: str = "local",
        peers: list[str] | None = None,
        max_size: int = MAX_CACHE_SIZE,
    ) -> None:
        self._node = NanoNode(node_id=node_id, max_size=max_size)
        self._peers: list[str] = peers if peers is not None else NANO_CACHE_PEERS
        self._gossip_queue: list[dict[str, Any]] = []

    def set(self, key: str, value: Any, ttl: float = DEFAULT_TTL) -> None:
        self._node.set(key, value, ttl)
        self._gossip_queue.append({"op": "set", "key": key, "value": value, "ttl": ttl})

    def get(self, key: str) -> Optional[Any]:
        local = self._node.get(key)
        if local is not None:
            return local
        return None  # peer query is async — caller should use async_get

    async def async_get(self, key: str) -> Optional[Any]:
        local = self._node.get(key)
        if local is not None:
            return local

        # Query peers
        for peer in self._peers:
            try:
                import httpx

                async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                    resp = await client.get(f"{peer}/cache/{key}")
                    if resp.status_code == 200:
                        data = resp.json()
                        value = data.get("value")
                        ttl = data.get("ttl", DEFAULT_TTL)
                        if value is not None:
                            self._node.set(key, value, ttl)
                            return value
            except Exception as exc:
                logger.debug("Peer %s unreachable: %s", peer, exc)

        return None

    async def gossip(self) -> int:
        """Broadcast pending cache updates to peers. Returns count sent."""
        if not self._peers or not self._gossip_queue:
            return 0

        pending = list(self._gossip_queue)
        self._gossip_queue.clear()
        sent = 0

        try:
            import httpx

            for peer in self._peers:
                try:
                    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
                        resp = await client.post(f"{peer}/cache/gossip", json={"updates": pending})
                        if resp.status_code in (200, 204):
                            sent += len(pending)
                except Exception as exc:
                    logger.debug("Gossip to %s failed: %s", peer, exc)
        except ImportError:
            pass

        return sent

    def apply_gossip(self, updates: list[dict[str, Any]]) -> int:
        """Apply gossip updates received from a peer."""
        applied = 0
        for update in updates:
            if update.get("op") == "set":
                self._node.set(update["key"], update["value"], update.get("ttl", DEFAULT_TTL))
                applied += 1
            elif update.get("op") == "delete":
                self._node.delete(update["key"])
                applied += 1
        return applied

    def evict_lru(self) -> Optional[str]:
        return self._node.evict_lru()

    def stats(self) -> dict[str, Any]:
        s = self._node.stats()
        s["peers"] = len(self._peers)
        s["gossip_queue_size"] = len(self._gossip_queue)
        return s
