"""Re-export shim — canonical implementation lives in src/vector/adapter.py."""

from src.vector.adapter import (  # noqa: F401
    Document,
    SearchResult,
    VectorStore,
    embedding_stats,
    get_store,
    get_vector_store,
)

__all__ = [
    "Document",
    "SearchResult",
    "VectorStore",
    "embedding_stats",
    "get_store",
    "get_vector_store",
]
