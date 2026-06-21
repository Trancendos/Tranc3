"""Re-export shim — canonical implementation lives in src/vector/adapter.py.

The pgvector backend is now embedded as _PgvectorBackend inside the unified
VectorStore facade. Use get_vector_store() with a pgvector-compatible DATABASE_URL
to activate it automatically.
"""

from src.vector.adapter import (  # noqa: F401
    SearchResult,
    VectorStore,
    get_vector_store,
)

__all__ = ["SearchResult", "VectorStore", "get_vector_store"]
