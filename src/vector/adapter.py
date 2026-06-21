"""
src/vector/adapter.py — Unified vector store with graceful backend fallback.

Backend priority:
  1. Qdrant   (docker-compose :6333) — persistent, scalable, free OSS
  2. FAISS    (in-process)           — zero network, fast, no persistence
  3. Numpy    (in-memory dict)       — always available, no deps needed

All backends expose the identical VectorStore interface so callers never
need to know which backend is running.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger("tranc3.vector")

_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
_EMBED_DIM = int(os.getenv("VECTOR_DIM", "384"))  # all-MiniLM-L6-v2 default

_backend_cache: Dict[str, "VectorStore"] = {}


@dataclass
class SearchResult:
    id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)


# ─── Backend implementations ──────────────────────────────────────────────────


class _QdrantBackend:
    """Qdrant client backend — requires qdrant-client package."""

    def __init__(self, collection: str, dim: int) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.models import Distance, VectorParams  # type: ignore

        self._collection = collection
        self._client = QdrantClient(url=_QDRANT_URL, timeout=5)
        existing = [c.name for c in self._client.get_collections().collections]
        if collection not in existing:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        log.info("VectorStore[qdrant] collection=%s dim=%d", collection, dim)

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct  # type: ignore

        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=_str_to_uuid(doc_id), vector=vector, payload=payload)],
        )

    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            limit=top_k,
        )
        return [SearchResult(id=str(h.id), score=h.score, payload=h.payload or {}) for h in hits]

    def delete(self, doc_id: str) -> None:
        from qdrant_client.models import PointIdsList  # type: ignore

        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[_str_to_uuid(doc_id)]),
        )

    def count(self) -> int:
        return self._client.count(collection_name=self._collection).count


class _FaissBackend:
    """FAISS in-process backend — no server required."""

    def __init__(self, collection: str, dim: int) -> None:
        import faiss  # type: ignore

        self._collection = collection
        self._dim = dim
        self._index = faiss.IndexFlatIP(dim)  # inner product (cosine after L2-norm)
        self._ids: List[str] = []
        self._vectors: List[List[float]] = []
        self._payloads: List[Dict[str, Any]] = []
        log.info("VectorStore[faiss] collection=%s dim=%d", collection, dim)

    def _rebuild_index(self) -> None:
        import faiss  # type: ignore
        import numpy as np  # type: ignore

        self._index = faiss.IndexFlatIP(self._dim)
        if self._vectors:
            v = np.array(self._vectors, dtype="float32")
            faiss.normalize_L2(v)
            self._index.add(v)

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        if doc_id in self._ids:
            idx = self._ids.index(doc_id)
            self._vectors[idx] = vector
            self._payloads[idx] = payload
            self._rebuild_index()
        else:
            import faiss  # type: ignore
            import numpy as np  # type: ignore

            v = np.array([vector], dtype="float32")
            faiss.normalize_L2(v)
            self._index.add(v)
            self._ids.append(doc_id)
            self._vectors.append(vector)
            self._payloads.append(payload)

    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        import faiss  # type: ignore
        import numpy as np  # type: ignore

        if self._index.ntotal == 0:
            return []
        v = np.array([vector], dtype="float32")
        faiss.normalize_L2(v)
        k = min(top_k, self._index.ntotal)
        scores, indices = self._index.search(v, k)
        results = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if 0 <= idx < len(self._ids):
                results.append(
                    SearchResult(id=self._ids[idx], score=float(score), payload=self._payloads[idx])
                )
        return results

    def delete(self, doc_id: str) -> None:
        if doc_id in self._ids:
            i = self._ids.index(doc_id)
            self._ids.pop(i)
            self._vectors.pop(i)
            self._payloads.pop(i)
            self._rebuild_index()

    def count(self) -> int:
        return len(self._ids)


class _NumpyBackend:
    """Pure-numpy in-memory fallback — zero dependencies."""

    def __init__(self, collection: str, dim: int) -> None:
        import numpy as np  # type: ignore

        self._collection = collection
        self._dim = dim
        self._ids: List[str] = []
        self._vectors: List[List[float]] = []
        self._payloads: List[Dict[str, Any]] = []
        self._np = np
        log.info("VectorStore[numpy] collection=%s dim=%d", collection, dim)

    def _cosine(self, a: Any, b: Any) -> float:
        np = self._np
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        if doc_id in self._ids:
            idx = self._ids.index(doc_id)
            self._vectors[idx] = vector
            self._payloads[idx] = payload
        else:
            self._ids.append(doc_id)
            self._vectors.append(vector)
            self._payloads.append(payload)

    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        np = self._np
        if not self._vectors:
            return []
        v = np.array(vector)
        scores = [self._cosine(v, np.array(sv)) for sv in self._vectors]
        top = sorted(zip(scores, range(len(scores)), strict=False), reverse=True)[:top_k]
        return [SearchResult(id=self._ids[i], score=s, payload=self._payloads[i]) for s, i in top]

    def delete(self, doc_id: str) -> None:
        if doc_id in self._ids:
            i = self._ids.index(doc_id)
            self._ids.pop(i)
            self._vectors.pop(i)
            self._payloads.pop(i)

    def count(self) -> int:
        return len(self._ids)


# ─── Public VectorStore facade ────────────────────────────────────────────────


class VectorStore:
    """
    Unified vector store. Use get_vector_store() to obtain an instance.
    """

    def __init__(self, collection: str, dim: int = _EMBED_DIM) -> None:
        self._backend = _make_backend(collection, dim)

    def upsert(
        self, doc_id: str, vector: List[float], payload: Optional[Dict[str, Any]] = None
    ) -> None:
        self._backend.upsert(doc_id, vector, payload or {})

    def search(self, vector: List[float], top_k: int = 5) -> List[SearchResult]:
        return self._backend.search(vector, top_k)

    def delete(self, doc_id: str) -> None:
        self._backend.delete(doc_id)

    def count(self) -> int:
        return self._backend.count()

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__.lstrip("_").replace("Backend", "").lower()


def get_vector_store(collection: str, dim: int = _EMBED_DIM) -> VectorStore:
    """Return a cached VectorStore for the given collection name."""
    key = f"{collection}:{dim}"
    if key not in _backend_cache:
        _backend_cache[key] = VectorStore(collection, dim)
    return _backend_cache[key]


# ─── Backend selection ────────────────────────────────────────────────────────


def _make_backend(collection: str, dim: int) -> Any:
    # 1. Try Qdrant
    try:
        backend = _QdrantBackend(collection, dim)
        return backend
    except Exception as exc:
        log.debug("Qdrant unavailable (%s) — trying FAISS", exc)

    # 2. Try FAISS
    try:
        return _FaissBackend(collection, dim)
    except Exception as exc:
        log.debug("FAISS unavailable (%s) — falling back to numpy", exc)

    # 3. Numpy (always works)
    return _NumpyBackend(collection, dim)


def _str_to_uuid(s: str) -> str:
    try:
        uuid.UUID(s)
        return s
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, s))
