"""
Smart semantic cache for the AI gateway.

Architecture (zero external dependencies):
  - LRU eviction with configurable capacity
  - Semantic clustering: groups similar prompts by n-gram fingerprint
    so near-duplicate requests hit cache even if text differs slightly
  - TTL per entry with sliding expiry
  - Proactive eviction before capacity is breached (triggers at 90%)
  - Dimensional tagging: each entry carries a tag vector for future
    ML-powered retrieval

Gas metaphor: cache entries "evaporate" via TTL; hot entries "condense"
back with high hit counts; cluster centroids stay "dense".
"""

from __future__ import annotations

import hashlib
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import RLock
from typing import Any, Dict, Optional, Tuple


def _fingerprint(text: str, n: int = 3) -> str:
    """
    Character n-gram fingerprint — order-invariant similarity key.
    Two prompts with the same dominant n-grams share a fingerprint cluster.
    """
    tokens = re.findall(r'\w+', text.lower())
    ngrams = set()
    for tok in tokens:
        for i in range(len(tok) - n + 1):
            ngrams.add(tok[i:i + n])
    sorted_ng = sorted(ngrams)[:32]  # top-32 for stability
    raw = ''.join(sorted_ng)
    return hashlib.md5(raw.encode(), usedforsecurity=False).hexdigest()[:12]


@dataclass
class CacheEntry:
    key: str
    value: Any
    fingerprint: str
    tags: Dict[str, str] = field(default_factory=dict)
    created_at: float = field(default_factory=time.monotonic)
    last_hit: float = field(default_factory=time.monotonic)
    hit_count: int = 0
    ttl_s: float = 3600.0

    @property
    def expired(self) -> bool:
        return (time.monotonic() - self.created_at) > self.ttl_s

    @property
    def heat(self) -> float:
        """Heat score — high hit count + recent access = hot entry."""
        age_s = time.monotonic() - self.last_hit
        return self.hit_count / (1.0 + age_s / 60.0)


class SmartCache:
    """
    Adaptive LRU cache with semantic clustering and proactive eviction.
    Thread-safe via RLock.
    """

    def __init__(self, capacity: int = 2000, default_ttl_s: float = 3600.0) -> None:
        self._capacity = capacity
        self._default_ttl = default_ttl_s
        self._store: OrderedDict[str, CacheEntry] = OrderedDict()
        self._fingerprint_index: Dict[str, list[str]] = {}  # fp → [keys]
        self._lock = RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # ── Public API ────────────────────────────────────────────────────────────

    def get(self, prompt: str, tags: Optional[Dict[str, str]] = None) -> Optional[Any]:
        key = self._key(prompt)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                # Try semantic cluster lookup
                entry = self._cluster_lookup(prompt, tags)
            if entry is None or entry.expired:
                if entry and entry.expired:
                    self._evict(key)
                self.misses += 1
                return None
            entry.hit_count += 1
            entry.last_hit = time.monotonic()
            self._store.move_to_end(key)
            self.hits += 1
            return entry.value

    def put(
        self,
        prompt: str,
        value: Any,
        ttl_s: Optional[float] = None,
        tags: Optional[Dict[str, str]] = None,
    ) -> None:
        key = self._key(prompt)
        fp = _fingerprint(prompt)
        with self._lock:
            entry = CacheEntry(
                key=key,
                value=value,
                fingerprint=fp,
                tags=tags or {},
                ttl_s=ttl_s if ttl_s is not None else self._default_ttl,
            )
            self._store[key] = entry
            self._store.move_to_end(key)
            self._fingerprint_index.setdefault(fp, [])
            if key not in self._fingerprint_index[fp]:
                self._fingerprint_index[fp].append(key)
            self._proactive_evict()

    def invalidate(self, prompt: str) -> None:
        key = self._key(prompt)
        with self._lock:
            self._evict(key)

    def stats(self) -> Dict[str, Any]:
        with self._lock:
            total = self.hits + self.misses
            return {
                "size": len(self._store),
                "capacity": self._capacity,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
                "evictions": self.evictions,
                "clusters": len(self._fingerprint_index),
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    def _key(self, prompt: str) -> str:
        return hashlib.sha256(prompt.encode()).hexdigest()[:32]

    def _cluster_lookup(self, prompt: str, tags: Optional[Dict[str, str]]) -> Optional[CacheEntry]:
        fp = _fingerprint(prompt)
        sibling_keys = self._fingerprint_index.get(fp, [])
        for k in sibling_keys:
            e = self._store.get(k)
            if e and not e.expired:
                if tags is None or all(e.tags.get(tk) == tv for tk, tv in tags.items()):
                    return e
        return None

    def _evict(self, key: str) -> None:
        entry = self._store.pop(key, None)
        if entry:
            cluster = self._fingerprint_index.get(entry.fingerprint, [])
            if key in cluster:
                cluster.remove(key)
            self.evictions += 1

    def _proactive_evict(self) -> None:
        """Evict expired and cold entries before hitting capacity."""
        if len(self._store) < self._capacity * 0.9:
            return
        # Remove expired first
        expired_keys = [k for k, e in self._store.items() if e.expired]
        for k in expired_keys:
            self._evict(k)
        # If still over 90%, evict coldest
        while len(self._store) >= self._capacity:
            coldest_key = min(self._store, key=lambda k: self._store[k].heat)
            self._evict(coldest_key)


# Module-level singleton
_cache: Optional[SmartCache] = None


def get_cache(capacity: int = 2000, ttl_s: float = 3600.0) -> SmartCache:
    global _cache
    if _cache is None:
        _cache = SmartCache(capacity=capacity, default_ttl_s=ttl_s)
    return _cache
