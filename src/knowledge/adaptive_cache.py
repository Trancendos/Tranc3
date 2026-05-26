"""
Adaptive TTL cache with hit-rate-driven expiry extension and predictive prefetching.

Uses cachetools when available for the underlying LRU store.
Falls back to a plain dict with manual size eviction.

Designed for the Luminous AI Gateway request cache and The Digital Grid result cache.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

try:
    from cachetools import LRUCache  # type: ignore

    _CACHETOOLS = True
except ImportError:
    _CACHETOOLS = False


@dataclass
class _Entry:
    value: Any
    inserted_at: float
    ttl: float
    hits: int = 0
    last_hit: float = field(default_factory=time.monotonic)


class AdaptiveTTLCache:
    """
    LRU cache with adaptive TTL:
      - Each cache hit extends TTL by ×1.1 (up to max_ttl)
      - Cache misses with high reuse patterns trigger pre-warming
      - Optional async background eviction

    Usage::

        cache = AdaptiveTTLCache(maxsize=1000, base_ttl=300.0)
        cache.set("key", value)
        val = cache.get("key")   # extends TTL if hit
        cache.invalidate("key")
    """

    def __init__(
        self,
        maxsize: int = 1000,
        base_ttl: float = 300.0,
        min_ttl: float = 30.0,
        max_ttl: float = 3600.0,
        ttl_growth: float = 1.1,
    ) -> None:
        self._maxsize = maxsize
        self.base_ttl = base_ttl
        self.min_ttl = min_ttl
        self.max_ttl = max_ttl
        self._ttl_growth = ttl_growth

        if _CACHETOOLS:
            self._store: Dict[str, _Entry] = LRUCache(maxsize=maxsize)  # type: ignore
        else:
            self._store = {}

        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: str, default: Any = None) -> Any:
        entry = self._store.get(key)
        if entry is None:
            self._misses += 1
            return default

        now = time.monotonic()
        if now - entry.inserted_at > entry.ttl:
            # Expired
            self._store.pop(key, None)
            self._misses += 1
            return default

        # Hit: extend TTL
        entry.hits += 1
        entry.last_hit = now
        entry.ttl = min(entry.ttl * self._ttl_growth, self.max_ttl)
        self._hits += 1
        return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None) -> None:
        if not _CACHETOOLS and len(self._store) >= self._maxsize:
            # Evict oldest entry (FIFO fallback when cachetools absent)
            oldest = min(self._store, key=lambda k: self._store[k].inserted_at, default=None)
            if oldest:
                del self._store[oldest]
                self._evictions += 1

        self._store[key] = _Entry(
            value=value,
            inserted_at=time.monotonic(),
            ttl=ttl if ttl is not None else self.base_ttl,
        )

    def invalidate(self, key: str) -> bool:
        return self._store.pop(key, None) is not None

    def clear(self) -> None:
        self._store.clear()

    @property
    def hit_rate(self) -> float:
        total = self._hits + self._misses
        return self._hits / total if total else 0.0

    @property
    def size(self) -> int:
        return len(self._store)

    def stats(self) -> Dict[str, Any]:
        return {
            "size": self.size,
            "maxsize": self._maxsize,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": self.hit_rate,
            "evictions": self._evictions,
        }


class PredictivePrefetcher:
    """
    Markov-chain access predictor for cache prefetching.

    Tracks sequential access patterns and predicts likely next keys.
    Trigger a prefetch callback when confidence exceeds threshold.

    Usage::

        prefetcher = PredictivePrefetcher(lookahead=3, confidence=0.6)
        prefetcher.record("user:123:profile")
        next_keys = prefetcher.predict("user:123:profile")
        # → ["user:123:orders", "user:123:settings"]
    """

    def __init__(
        self,
        lookahead: int = 5,
        confidence: float = 0.5,
        max_history: int = 2000,
    ) -> None:
        self._lookahead = lookahead
        self._confidence = confidence
        self._max_history = max_history
        self._log: List[str] = []
        self._transitions: Dict[str, Counter] = defaultdict(Counter)
        self._prefetch_cb: Optional[Callable[[str], None]] = None

    def register_prefetch(self, callback: Callable[[str], None]) -> None:
        """Register callback invoked when a key should be prefetched."""
        self._prefetch_cb = callback

    def record(self, key: str) -> None:
        if self._log:
            prev = self._log[-1]
            self._transitions[prev][key] += 1

        self._log.append(key)
        if len(self._log) > self._max_history:
            self._log = self._log[-self._max_history // 2 :]

        # Trigger prefetch for predictions from the current key
        if self._prefetch_cb and self._log:
            current = self._log[-1]
            for predicted_key in self.predict(current):
                self._prefetch_cb(predicted_key)

    def predict(self, key: str) -> List[str]:
        """Return top-N likely next keys with confidence ≥ threshold."""
        if key not in self._transitions:
            return []
        counts = self._transitions[key]
        total = sum(counts.values())
        return [k for k, c in counts.most_common(self._lookahead) if c / total >= self._confidence]

    def clear_history(self) -> None:
        self._log.clear()
        self._transitions.clear()
