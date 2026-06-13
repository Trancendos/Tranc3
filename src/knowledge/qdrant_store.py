"""
Qdrant Vector Store — Zero-cost self-hosted vector search
===========================================================
Replaces Pinecone/paid vector services with self-hosted Qdrant (Apache 2.0).
Falls back gracefully to no-op if Qdrant is unavailable or not installed.

Free tier: unlimited vectors on self-hosted Qdrant.
Docker: qdrant/qdrant:latest on port 6333.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("tranc3.knowledge.qdrant")

QDRANT_URL = os.environ.get("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.environ.get("QDRANT_API_KEY", None)  # Only for Qdrant Cloud
_COLLECTION = "tranc3_knowledge"
_VECTOR_SIZE = int(os.environ.get("EMBED_DIM", "384"))  # all-MiniLM-L6-v2 default


def _client():
    """Lazy Qdrant client — returns None if not installed or unreachable."""
    try:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY, timeout=5)
        existing = [c.name for c in client.get_collections().collections]
        if _COLLECTION not in existing:
            client.create_collection(
                collection_name=_COLLECTION,
                vectors_config=VectorParams(size=_VECTOR_SIZE, distance=Distance.COSINE),
            )
        return client
    except Exception as e:
        logger.debug("Qdrant unavailable (%s) — vector ops will no-op", e)
        return None


def upsert(doc_id: str, vector: list[float], payload: dict[str, Any]) -> bool:
    """Store or update a document vector. Returns True on success."""
    try:
        from qdrant_client.models import PointStruct
    except ImportError:
        return False

    client = _client()
    if client is None:
        return False
    try:
        client.upsert(
            collection_name=_COLLECTION,
            points=[
                PointStruct(
                    id=abs(hash(doc_id)) % (2**63),
                    vector=vector,
                    payload={**payload, "doc_id": doc_id},
                )
            ],
        )
        return True
    except Exception as e:
        logger.warning("Qdrant upsert failed: %s", e)
        return False


def search(
    query_vector: list[float],
    top_k: int = 5,
    score_threshold: float = 0.6,
) -> list[dict[str, Any]]:
    """Cosine similarity search. Returns {doc_id, score, ...payload} dicts."""
    client = _client()
    if client is None:
        return []
    try:
        results = client.search(
            collection_name=_COLLECTION,
            query_vector=query_vector,
            limit=top_k,
            score_threshold=score_threshold,
        )
        return [
            {"doc_id": r.payload.get("doc_id", str(r.id)), "score": r.score, **r.payload}
            for r in results
        ]
    except Exception as e:
        logger.warning("Qdrant search failed: %s", e)
        return []


def delete(doc_id: str) -> bool:
    """Remove a document. Returns True on success."""
    try:
        from qdrant_client.models import PointIdsList
    except ImportError:
        return False

    client = _client()
    if client is None:
        return False
    try:
        client.delete(
            collection_name=_COLLECTION,
            points_selector=PointIdsList(points=[abs(hash(doc_id)) % (2**63)]),
        )
        return True
    except Exception as e:
        logger.warning("Qdrant delete failed: %s", e)
        return False


def collection_info() -> dict[str, Any]:
    """Return collection metadata (vectors_count, status)."""
    client = _client()
    if client is None:
        return {"available": False, "url": QDRANT_URL}
    try:
        info = client.get_collection(_COLLECTION)
        return {
            "available": True,
            "url": QDRANT_URL,
            "collection": _COLLECTION,
            "vectors_count": info.vectors_count,
            "status": str(info.status),
        }
    except Exception as e:
        return {"available": False, "url": QDRANT_URL, "error": str(e)}
