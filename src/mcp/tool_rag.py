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
# No new dependencies — sentence-transformers + faiss-cpu are already in
# requirements.txt.

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List, Optional

import numpy as np

if TYPE_CHECKING:
    from src.mcp.tools import SparkTool  # codeql[py/cyclic-import]

logger = logging.getLogger(__name__)

_encoder = None
_encoder_lock = None


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


class ToolRAG:
    """
    Semantic tool retriever for The Spark's MCP registry.

    Usage:
        rag = ToolRAG()
        rag.index(registry.list_all_tools())   # called once after tool registration
        relevant = rag.select_tools("retrieve similar documents", top_k=5)
    """

    def __init__(self) -> None:
        self._tools: List["SparkTool"] = []
        self._index = None  # faiss.IndexFlatIP
        self._embeddings: Optional[np.ndarray] = None
        self._indexed = False

    def index(self, tools: List["SparkTool"]) -> None:
        """Embed all tool descriptions and build the FAISS index."""
        if not tools:
            return
        encoder = _get_encoder()
        if encoder is None:
            logger.warning("tool_rag: skipping index — encoder not available")
            return

        try:
            import faiss
        except ImportError:
            logger.warning("tool_rag: faiss not available — semantic search disabled")
            return

        self._tools = list(tools)
        texts = [f"{t.name}: {t.description}" for t in self._tools]
        embeddings = encoder.encode(texts, show_progress_bar=False)
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings)
        embeddings = embeddings.astype("float32")
        faiss.normalize_L2(embeddings)
        self._embeddings = embeddings

        dim = embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dim)
        self._index.add(embeddings)
        self._indexed = True
        logger.info("tool_rag: indexed %d tools (dim=%d)", len(self._tools), dim)

    def select_tools(self, query: str, top_k: int = 5) -> List["SparkTool"]:
        """Return the top-k most semantically relevant tools for *query*."""
        if not self._indexed or self._index is None:
            return self._tools[:top_k] if self._tools else []

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
