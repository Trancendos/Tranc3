"""Re-export shim — canonical implementation lives in src/vector/adapter.py."""

from src.vector.adapter import (  # noqa: F401
    Document,
    SearchResult,
    VectorStore,
    embedding_stats,
    get_vector_store,
)

# Backward-compatible default instance (matches previous "database" usage)
vector_store: VectorStore = get_vector_store("database")

__all__ = [
    "Document",
    "SearchResult",
    "VectorStore",
    "embedding_stats",
    "get_vector_store",
    "vector_store",
]
