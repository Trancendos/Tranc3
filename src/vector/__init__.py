"""
src/vector — Unified vector store adapter.

Single entry point replacing:
  - src/database/vector_store.py  (Pinecone/pgvector shim)
  - src/knowledge/vector_store.py (FAISS in-process)

Uses Qdrant when available (docker-compose service on port 6333).
Falls back to FAISS (no server required) when Qdrant is unreachable.
Falls back to in-memory numpy when FAISS is not installed.

Usage:
    from src.vector import get_vector_store
    vs = get_vector_store("my-collection")
    vs.upsert("doc-1", [0.1, 0.2, ...], {"title": "My Doc"})
    results = vs.search([0.1, 0.2, ...], top_k=5)
"""

from .adapter import SearchResult, VectorStore, get_vector_store

__all__ = ["VectorStore", "get_vector_store", "SearchResult"]
