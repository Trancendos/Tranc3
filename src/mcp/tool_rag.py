# src/mcp/tool_rag.py
# RAG-MCP: semantic tool selection for The Spark.
#
# Inspired by arxiv:2505.03275 — embeds tool descriptions once at registry
# time, then retrieves the top-k most relevant tools for each query using
# cosine similarity (FAISS IndexFlatIP after L2 normalisation).
#
# Benefits vs keyword search (SparkToolRegistry.search):
#   • Works on paraphrases and synonyms ("find document" → "search_skills")
#   • Cuts prompt context: expose only the 5 most relevant tools, not all of them
#   • Composable: call select_tools() before constructing any LLM prompt
#
# Persistence backends (tried in order, first available wins):
#   1. Qdrant self-hosted (src/knowledge/qdrant_store) — durable across restarts
#   2. FAISS IndexFlatIP in-process — fast, ephemeral
#
# No mandatory new dependencies — sentence-transformers + faiss-cpu already in
# requirements.txt; qdrant-client is optional.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import numpy as np

if TYPE_CHECKING:
    from src.mcp.tools import SparkTool  # codeql[py/cyclic-import]

logger = logging.getLogger(__name__)

_encoder = None
_encoder_lock = None

# Qdrant collection name for tool embeddings
_QDRANT_COLLECTION = "tranc3_tool_rag"


def _get_encoder():
    global _encoder, _encoder_lock
    if _encoder_lock is None:
        import threading

        _encoder_lock = threading.Lock()
    if _encoder is None:
        with _encoder_lock:
            if _encoder is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    _encoder = SentenceTransformer("all-MiniLM-L6-v2")
                    logger.info("tool_rag: encoder loaded")
                except Exception as exc:
                    logger.warning("tool_rag: encoder unavailable (%s)", exc)
                    _encoder = None
    return _encoder


def _qdrant_client():
    """Lazy Qdrant client for tool RAG persistence. Returns None if unavailable."""
    try:
        import os

        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        url = os.environ.get("QDRANT_URL", "http://localhost:6333")
        api_key = os.environ.get("QDRANT_API_KEY") or None
        client = QdrantClient(url=url, api_key=api_key, timeout=3)
        existing = [c.name for c in client.get_collections().collections]
        if _QDRANT_COLLECTION not in existing:
            client.create_collection(
                collection_name=_QDRANT_COLLECTION,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
        return client
    except Exception as exc:
        logger.debug("tool_rag: Qdrant unavailable (%s) — using FAISS only", exc)
        return None


class ToolRAG:
    """
    Semantic tool retriever for The Spark's MCP registry.

    Usage:
        rag = ToolRAG()
        rag.index(registry.list_all_tools())   # called once after tool registration
        relevant = rag.select_tools("retrieve similar documents", top_k=5)

    Persistence: if Qdrant is running, tool embeddings are stored there for
    durability across service restarts. Falls back to in-process FAISS if not.
    """

    def __init__(self) -> None:
        self._tools: List["SparkTool"] = []
        self._tool_map: dict[str, "SparkTool"] = {}
        self._index = None  # faiss.IndexFlatIP
        self._embeddings: Optional[np.ndarray] = None
        self._indexed = False
        self._qdrant_available = False

    def index(self, tools: List["SparkTool"]) -> None:
        """Embed all tool descriptions and build the search index."""
        if not tools:
            return
        encoder = _get_encoder()
        if encoder is None:
            logger.warning("tool_rag: skipping index — encoder not available")
            return

        self._tools = list(tools)
        self._tool_map = {t.name: t for t in self._tools}
        texts = [f"{t.name}: {t.description}" for t in self._tools]
        embeddings = encoder.encode(texts, show_progress_bar=False)
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings)
        embeddings = embeddings.astype("float32")

        # Try persisting to Qdrant first
        self._qdrant_available = self._persist_to_qdrant(embeddings)

        # Always build local FAISS index as fast-path fallback
        self._build_faiss_index(embeddings)
        self._indexed = True
        logger.info(
            "tool_rag: indexed %d tools (qdrant=%s)",
            len(self._tools),
            self._qdrant_available,
        )

    def _persist_to_qdrant(self, embeddings: np.ndarray) -> bool:
        """Upsert tool embeddings into Qdrant. Returns True on success."""
        client = _qdrant_client()
        if client is None:
            return False
        try:
            from qdrant_client.models import PointStruct

            points = [
                PointStruct(
                    id=abs(hash(tool.name)) % (2**63),
                    vector=embeddings[i].tolist(),
                    payload={"name": tool.name, "description": tool.description},
                )
                for i, tool in enumerate(self._tools)
            ]
            client.upsert(collection_name=_QDRANT_COLLECTION, points=points)
            return True
        except Exception as exc:
            logger.debug("tool_rag: Qdrant upsert failed (%s)", exc)
            return False

    def _build_faiss_index(self, embeddings: np.ndarray) -> None:
        """Build in-process FAISS index (L2-normalised cosine via inner product)."""
        try:
            import faiss

            normed = embeddings.copy()
            faiss.normalize_L2(normed)
            self._embeddings = normed
            dim = normed.shape[1]
            self._index = faiss.IndexFlatIP(dim)
            self._index.add(normed)
        except ImportError:
            logger.debug("tool_rag: faiss not available — Qdrant-only mode")
            self._index = None

    def _select_via_qdrant(self, query: str, top_k: int) -> Optional[List["SparkTool"]]:
        """Query Qdrant for top-k tools. Returns None if unavailable."""
        if not self._qdrant_available:
            return None
        encoder = _get_encoder()
        if encoder is None:
            return None
        client = _qdrant_client()
        if client is None:
            return None
        try:
            q_vec = encoder.encode([query], show_progress_bar=False)
            if not isinstance(q_vec, np.ndarray):
                q_vec = np.array(q_vec)
            results = client.search(
                collection_name=_QDRANT_COLLECTION,
                query_vector=q_vec[0].tolist(),
                limit=top_k,
                score_threshold=0.0,
            )
            tools = []
            for r in results:
                name = r.payload.get("name", "")
                if name in self._tool_map:
                    tools.append(self._tool_map[name])
            return tools if tools else None
        except Exception as exc:
            logger.debug("tool_rag: Qdrant query failed (%s)", exc)
            return None

    def select_tools(self, query: str, top_k: int = 5) -> List["SparkTool"]:
        """Return the top-k most semantically relevant tools for *query*."""
        if not self._indexed or not self._tools:
            return self._tools[:top_k]

        # Try Qdrant first (persistent, distributed-friendly)
        qdrant_result = self._select_via_qdrant(query, top_k)
        if qdrant_result is not None:
            return qdrant_result

        # Fall back to local FAISS
        if self._index is None:
            return self._tools[:top_k]

        encoder = _get_encoder()
        if encoder is None:
            return self._tools[:top_k]

        try:
            import faiss

            q_vec = encoder.encode([query], show_progress_bar=False)
            if not isinstance(q_vec, np.ndarray):
                q_vec = np.array(q_vec)
            q_vec = q_vec.astype("float32")
            faiss.normalize_L2(q_vec)

            k = min(top_k, self._index.ntotal)
            scores, indices = self._index.search(q_vec, k)
            results = []
            for score, idx in zip(scores[0], indices[0], strict=False):
                if idx < 0:
                    continue
                tool = self._tools[int(idx)]
                logger.debug("tool_rag: %s score=%.3f", tool.name, float(score))
                results.append(tool)
            return results
        except Exception as exc:
            logger.warning("tool_rag.select_tools error: %s", exc)
            return self._tools[:top_k]

    def select_tool_names(self, query: str, top_k: int = 5) -> List[str]:
        return [t.name for t in self.select_tools(query, top_k)]

    def tool_count(self) -> int:
        return len(self._tools)

    def is_ready(self) -> bool:
        return self._indexed


# Module-level singleton — created lazily; call index() after registry is populated
_rag: Optional[ToolRAG] = None


def get_rag() -> ToolRAG:
    global _rag
    if _rag is None:
        _rag = ToolRAG()
    return _rag


def rebuild_rag_index(tools: List["SparkTool"]) -> None:
    """Rebuild the global ToolRAG index. Call after any tool registration change."""
    get_rag().index(tools)
