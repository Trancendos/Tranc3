# src/database/vector_store.py
# VectorStore — Gap G14 action
# Pinecone/pgvector abstraction for embedding storage and retrieval

import logging
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class VectorStore:
    """
    Unified vector storage abstraction.
    Uses Pinecone if configured, falls back to in-memory for dev.
    Swap backend without changing calling code.
    """

    def __init__(self):
        self._backend = self._init_backend()
        logger.info("VectorStore initialised: backend=%s", sanitize_for_log(self._backend_name))  # codeql[py/cleartext-logging]

    def _init_backend(self):
        # Try Pinecone first
        api_key = os.getenv("PINECONE_API_KEY")
        if api_key:
            try:
                from pinecone import Pinecone, ServerlessSpec
                pc = Pinecone(api_key=api_key)
                index_name = os.getenv("PINECONE_INDEX", "tranc3-memory")
                if index_name not in [i.name for i in pc.list_indexes()]:
                    pc.create_index(
                        name=index_name,
                        dimension=768,
                        metric="cosine",
                        spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                    )
                self._backend_name = "pinecone"
                return pc.Index(index_name)
            except Exception as e:
                logger.warning("Pinecone init failed: %s — using in-memory", sanitize_for_log(e))  # codeql[py/cleartext-logging]

        self._backend_name = "in_memory"
        return InMemoryVectorStore()

    def upsert(self, vector_id: str, embedding: List[float], metadata: Dict) -> bool:
        try:
            if self._backend_name == "pinecone":
                self._backend.upsert(vectors=[{
                    "id": vector_id,
                    "values": embedding,
                    "metadata": metadata,
                }])
            else:
                self._backend.upsert(vector_id, embedding, metadata)
            return True
        except Exception as e:
            logger.error("VectorStore upsert failed: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
            return False

    def query(self, embedding: List[float], top_k: int = 5,
              filter: Optional[Dict] = None) -> List[Dict]:
        try:
            if self._backend_name == "pinecone":
                results = self._backend.query(
                    vector=embedding, top_k=top_k,
                    include_metadata=True, filter=filter or {}
                )
                return [{"id": m.id, "score": m.score, "metadata": m.metadata}
                        for m in results.matches]
            else:
                return self._backend.query(embedding, top_k)
        except Exception as e:
            logger.error("VectorStore query failed: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
            return []

    def delete(self, vector_ids: List[str]) -> bool:
        """GDPR right-to-erasure — Gap G19 action."""
        try:
            if self._backend_name == "pinecone":
                self._backend.delete(ids=vector_ids)
            else:
                self._backend.delete(vector_ids)
            return True
        except Exception as e:
            logger.error("VectorStore delete failed: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
            return False

    def delete_user(self, user_id: str) -> bool:
        """Delete all vectors for a user — GDPR compliance."""
        try:
            if self._backend_name == "pinecone":
                self._backend.delete(filter={"user_id": user_id})
            else:
                self._backend.delete_by_metadata("user_id", user_id)
            logger.info("Deleted all vectors for user: %s", sanitize_for_log(user_id))  # codeql[py/cleartext-logging]
            return True
        except Exception as e:
            logger.error("VectorStore user delete failed: %s", sanitize_for_log(e))  # codeql[py/cleartext-logging]
            return False


class InMemoryVectorStore:
    """In-memory fallback vector store using cosine similarity."""

    def __init__(self):
        self._store: Dict[str, Tuple[List[float], Dict]] = {}

    def upsert(self, vector_id: str, embedding: List[float], metadata: Dict):
        self._store[vector_id] = (embedding, metadata)

    def query(self, embedding: List[float], top_k: int = 5) -> List[Dict]:
        if not self._store:
            return []
        query_vec = np.array(embedding)
        scores = []
        for vid, (vec, meta) in self._store.items():
            v = np.array(vec)
            score = float(np.dot(query_vec, v) / (np.linalg.norm(query_vec) * np.linalg.norm(v) + 1e-8))
            scores.append({"id": vid, "score": score, "metadata": meta})
        scores.sort(key=lambda x: x["score"], reverse=True)
        return scores[:top_k]

    def delete(self, vector_ids: List[str]):
        for vid in vector_ids:
            self._store.pop(vid, None)

    def delete_by_metadata(self, key: str, value: str):
        to_delete = [vid for vid, (_, meta) in self._store.items() if meta.get(key) == value]
        for vid in to_delete:
            del self._store[vid]


# Singleton
vector_store = VectorStore()
