"""Semantic similarity cache for search/RAG results.

Avoids redundant retrieval by storing recent (query, results) pairs and
returning cached results when a new query is semantically similar above a
configurable threshold.

Embedding backend: sentence-transformers (local, free).
Fallback: exact-string cache (no-dependency mode).

Zero-cost: in-memory; TTL eviction; no external services.
"""

from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger("tranc3.search.semantic_cache")

_DEFAULT_EMBED_MODEL = "all-MiniLM-L6-v2"
_DEFAULT_THRESHOLD = 0.92  # cosine similarity to count as a cache hit
_DEFAULT_TTL = 300  # seconds


@dataclass
class _CacheEntry:
    query: str
    embedding: Optional[List[float]]
    results: Any
    ts: float = field(default_factory=time.time)


class SemanticCache:
    """In-memory semantic cache with TTL and cosine-similarity matching."""

    def __init__(
        self,
        model_name: str = _DEFAULT_EMBED_MODEL,
        threshold: float = _DEFAULT_THRESHOLD,
        ttl: float = _DEFAULT_TTL,
        max_size: int = 256,
    ) -> None:
        self._model_name = model_name
        self._threshold = threshold
        self._ttl = ttl
        self._max_size = max_size
        self._store: Dict[str, _CacheEntry] = {}
        self._embedder = None
        self._embed_ok: Optional[bool] = None

    # ── embedding ────────────────────────────────────────────────────────────

    def _load_embedder(self) -> bool:
        if self._embed_ok is not None:
            return bool(self._embed_ok)
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._embedder = SentenceTransformer(self._model_name)
            self._embed_ok = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("SemanticCache embedding unavailable (%s) — exact-match mode", exc)
            self._embed_ok = False
        return bool(self._embed_ok)

    def _embed(self, text: str) -> Optional[List[float]]:
        if not self._load_embedder() or self._embedder is None:
            return None
        try:
            vec = self._embedder.encode(text, normalize_embeddings=True)
            return vec.tolist()  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _cosine(a: List[float], b: List[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        # vectors are already L2-normalised when using SentenceTransformer with normalize=True
        return dot

    # ── cache key (fallback for exact-match mode) ────────────────────────────

    @staticmethod
    def _key(query: str) -> str:
        return hashlib.sha256(query.strip().lower().encode()).hexdigest()[:16]

    # ── public API ────────────────────────────────────────────────────────────

    def get(self, query: str) -> Optional[Any]:
        """Return cached results if a semantically similar query exists."""
        now = time.time()
        self._evict(now)

        emb = self._embed(query)

        if emb is not None:
            best_sim = 0.0
            best_entry: Optional[_CacheEntry] = None
            for entry in self._store.values():
                if entry.embedding is None:
                    continue
                sim = self._cosine(emb, entry.embedding)
                if sim > best_sim:
                    best_sim = sim
                    best_entry = entry
            if best_entry is not None and best_sim >= self._threshold:
                _q = query[:60].replace("\n", " ").replace("\r", " ")
                logger.debug("SemanticCache HIT (sim=%.3f) for '%s'", best_sim, _q)
                return best_entry.results
        else:
            # exact-match fallback
            entry = self._store.get(self._key(query))
            if entry is not None:
                _q = query[:60].replace("\n", " ").replace("\r", " ")
                logger.debug("SemanticCache exact HIT for '%s'", _q)
                return entry.results

        return None

    def set(self, query: str, results: Any) -> None:
        """Store results for *query* in the cache."""
        if len(self._store) >= self._max_size:
            # evict oldest entry
            oldest = min(self._store, key=lambda k: self._store[k].ts)
            del self._store[oldest]

        key = self._key(query)
        emb = self._embed(query)
        self._store[key] = _CacheEntry(query=query, embedding=emb, results=results)

    def invalidate(self, query: Optional[str] = None) -> None:
        if query is None:
            self._store.clear()
        else:
            self._store.pop(self._key(query), None)

    def stats(self) -> Dict[str, Any]:
        return {
            "size": len(self._store),
            "max_size": self._max_size,
            "ttl": self._ttl,
            "embed_mode": "semantic" if self._embed_ok else "exact",
            "threshold": self._threshold,
        }

    # ── internal ──────────────────────────────────────────────────────────────

    def _evict(self, now: float) -> None:
        expired = [k for k, e in self._store.items() if now - e.ts > self._ttl]
        for k in expired:
            del self._store[k]


# Module-level singleton
_cache: Optional[SemanticCache] = None


def get_cache(
    threshold: float = _DEFAULT_THRESHOLD,
    ttl: float = _DEFAULT_TTL,
) -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache(threshold=threshold, ttl=ttl)
    return _cache


def get_or_search(
    query: str,
    search_fn,
    *args: Any,
    **kwargs: Any,
) -> Tuple[Any, bool]:
    """Return (results, cache_hit).

    Calls *search_fn(query, *args, **kwargs)* on a miss and caches the result.
    """
    cache = get_cache()
    cached = cache.get(query)
    if cached is not None:
        return cached, True
    results = search_fn(query, *args, **kwargs)
    cache.set(query, results)
    return results, False
