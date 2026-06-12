# src/database/vector_store.py
# VectorStore — unified zero-cost vector storage abstraction
#
# Backend priority (all zero-cost, self-hosted):
#   1. Qdrant  — self-hosted (docker-compose qdrant service, port 6333)
#                persistent, high-performance, Apache 2.0
#   2. FAISS   — in-process persistent store (src/knowledge/vector_store.py)
#                no network dependency, file-backed
#   3. In-memory — ephemeral fallback, dev/test only
#
# Pinecone has been removed — it was the only paid dependency in this module.

import logging
import os
import uuid
from typing import Dict, List, Optional, Tuple

import numpy as np

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)

# UUID5 namespace for deterministic, collision-free Qdrant point IDs.
# Matches the same formula in scripts/migrate_pinecone_to_qdrant.py.
_UUID_NS = uuid.UUID("6ba7b811-9dad-11d1-80b4-00c04fd430c8")  # uuid.NAMESPACE_URL


def _point_id(vector_id: str) -> str:
    """Return a deterministic UUID5 string ID for a given vector_id."""
    return str(uuid.uuid5(_UUID_NS, vector_id))


_EMBED_DIM = int(os.environ.get("EMBED_DIM", "384"))
_COLLECTION = os.environ.get("QDRANT_COLLECTION", "tranc3-memory")
_QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
_QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", None)  # only for Qdrant Cloud


class VectorStore:
    """
    Unified vector storage abstraction — zero-cost, self-hosted.

    Backend selection (auto, in priority order):
      1. Qdrant (self-hosted docker service) — persistent, scalable
      2. FAISS knowledge store             — in-process, file-backed
      3. InMemoryVectorStore               — ephemeral, dev/test only

    All callers use the same upsert/query/delete/delete_user interface
    regardless of which backend is active.
    """

    def __init__(self):
        self._backend = self._init_backend()
        logger.info("VectorStore initialised: backend=%s", sanitize_for_log(self._backend_name))

    def _init_backend(self):
        # ── 1. Try self-hosted Qdrant ─────────────────────────────────────────
        try:
            from qdrant_client import QdrantClient
            from qdrant_client.models import Distance, VectorParams

            client = QdrantClient(url=_QDRANT_URL, api_key=_QDRANT_API_KEY, timeout=3)
            existing = [c.name for c in client.get_collections().collections]
            if _COLLECTION not in existing:
                client.create_collection(
                    collection_name=_COLLECTION,
                    vectors_config=VectorParams(size=_EMBED_DIM, distance=Distance.COSINE),
                )
            # Smoke-test connectivity
            client.get_collection(_COLLECTION)
            self._backend_name = "qdrant"
            logger.info("VectorStore: Qdrant backend active at %s", sanitize_for_log(_QDRANT_URL))
            return _QdrantBackend(client)
        except Exception as e:
            logger.info("Qdrant unavailable (%s) — trying FAISS", sanitize_for_log(e))

        # ── 2. Try FAISS (in-process persistent store) ────────────────────────
        try:
            # src/knowledge/vector_store.py exposes `VectorStore` (not FAISSVectorStore)
            from src.knowledge.vector_store import (
                VectorStore as _KnowledgeVS,  # type: ignore[import]
            )

            store = _KnowledgeVS()
            self._backend_name = "faiss"
            logger.info("VectorStore: FAISS backend active (file-backed, in-process)")
            return _FAISSBackend(store)
        except Exception as e:
            logger.info("FAISS unavailable (%s) — falling back to in-memory", sanitize_for_log(e))

        # ── 3. In-memory fallback (dev/test only) ─────────────────────────────
        self._backend_name = "in_memory"
        logger.warning("VectorStore: using ephemeral in-memory backend — data will not persist")
        return InMemoryVectorStore()

    # ── Public interface ──────────────────────────────────────────────────────

    def upsert(self, vector_id: str, embedding: List[float], metadata: Dict) -> bool:
        try:
            if self._backend_name == "pinecone":
                self._backend.upsert(
                    vectors=[
                        {
                            "id": vector_id,
                            "values": embedding,
                            "metadata": metadata,
                        },
                    ],
                )
            else:
                self._backend.upsert(vector_id, embedding, metadata)
            return True
        except Exception as e:
            logger.error("VectorStore upsert failed: %s", sanitize_for_log(e))
            return False

    def query(
        self,
        embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict] = None,
    ) -> List[Dict]:
        try:
            if self._backend_name == "pinecone":
                results = self._backend.query(
                    vector=embedding,
                    top_k=top_k,
                    include_metadata=True,
                    filter=filter or {},
                )
                return [
                    {"id": m.id, "score": m.score, "metadata": m.metadata} for m in results.matches
                ]
            else:
                return self._backend.query(embedding, top_k)
        except Exception as e:
            logger.error("VectorStore query failed: %s", sanitize_for_log(e))
            return []

    def delete(self, vector_ids: List[str]) -> bool:
        """GDPR right-to-erasure — delete specific vectors by ID."""
        try:
            self._backend.delete(vector_ids)
            return True
        except Exception as e:
            logger.error("VectorStore delete failed: %s", sanitize_for_log(e))
            return False

    def delete_user(self, user_id: str) -> bool:
        """Delete all vectors for a user — GDPR Art. 17 compliance."""
        try:
            self._backend.delete_by_metadata("user_id", user_id)
            logger.info("VectorStore: deleted all vectors for user %s", sanitize_for_log(user_id))
            return True
        except Exception as e:
            logger.error("VectorStore user delete failed: %s", sanitize_for_log(e))
            return False

    @property
    def backend_name(self) -> str:
        return self._backend_name


# ── Backend adapters ──────────────────────────────────────────────────────────


class _QdrantBackend:
    """Thin adapter wrapping QdrantClient to the VectorStore protocol."""

    def __init__(self, client):
        self._client = client

    def upsert(self, vector_id: str, embedding: List[float], metadata: Dict) -> None:
        from qdrant_client.models import PointStruct

        self._client.upsert(
            collection_name=_COLLECTION,
            points=[
                PointStruct(
                    id=_point_id(vector_id),
                    vector=embedding,
                    payload={**metadata, "_vector_id": vector_id},
                )
            ],
        )

    def query(
        self,
        embedding: List[float],
        top_k: int,
        filter: Optional[Dict] = None,  # noqa: A002
    ) -> List[Dict]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        qdrant_filter = None
        if filter:
            conditions = [
                FieldCondition(key=k, match=MatchValue(value=v)) for k, v in filter.items()
            ]
            qdrant_filter = Filter(must=conditions)

        results = self._client.search(
            collection_name=_COLLECTION,
            query_vector=embedding,
            limit=top_k,
            query_filter=qdrant_filter,
            with_payload=True,
        )
        return [
            {"id": r.payload.get("_vector_id", str(r.id)), "score": r.score, "metadata": r.payload}
            for r in results
        ]

    def delete(self, vector_ids: List[str]) -> None:
        from qdrant_client.models import PointIdsList

        point_ids = [_point_id(vid) for vid in vector_ids]
        self._client.delete(
            collection_name=_COLLECTION,
            points_selector=PointIdsList(points=point_ids),
        )

    def delete_by_metadata(self, key: str, value: str) -> None:
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        self._client.delete(
            collection_name=_COLLECTION,
            points_selector=Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))]),
        )


class _FAISSBackend:
    """Thin adapter wrapping the FAISS knowledge store to the VectorStore protocol."""

    def __init__(self, store):
        self._store = store

    def upsert(self, vector_id: str, embedding: List[float], metadata: Dict) -> None:
        self._store.add(vector_id, embedding, metadata)

    def query(
        self,
        embedding: List[float],
        top_k: int,
        filter: Optional[Dict] = None,  # noqa: A002
    ) -> List[Dict]:
        results = self._store.search(embedding, top_k)
        if filter:
            results = [
                r
                for r in results
                if all(r.get("metadata", {}).get(k) == v for k, v in filter.items())
            ]
        return results

    def delete(self, vector_ids: List[str]) -> None:
        for vid in vector_ids:
            self._store.delete(vid)

    def delete_by_metadata(self, key: str, value: str) -> None:
        self._store.delete_by_metadata(key, value)


class InMemoryVectorStore:
    """Ephemeral in-memory vector store — dev/test only, no persistence."""

    def __init__(self):
        self._store: Dict[str, Tuple[List[float], Dict]] = {}

    def upsert(self, vector_id: str, embedding: List[float], metadata: Dict) -> None:
        self._store[vector_id] = (embedding, metadata)

    def query(
        self,
        embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict] = None,  # noqa: A002
    ) -> List[Dict]:
        if not self._store:
            return []
        query_vec = np.array(embedding)
        scores = []
        for vid, (vec, meta) in self._store.items():
            if filter and not all(meta.get(k) == v for k, v in filter.items()):
                continue
            v = np.array(vec)
            score = float(
                np.dot(query_vec, v) / (np.linalg.norm(query_vec) * np.linalg.norm(v) + 1e-8),
            )
            scores.append({"id": vid, "score": score, "metadata": meta})
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]

    def delete(self, vector_ids: List[str]) -> None:
        for vid in vector_ids:
            self._store.pop(vid, None)

    def delete_by_metadata(self, key: str, value: str) -> None:
        to_delete = [vid for vid, (_, meta) in self._store.items() if meta.get(key) == value]
        for vid in to_delete:
            del self._store[vid]


# Singleton
vector_store = VectorStore()
