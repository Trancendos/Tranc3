"""Hybrid search — BM25 (Meilisearch) + dense vector (Qdrant/FAISS) fusion.

Uses Reciprocal Rank Fusion (RRF) to merge two ranked lists without needing
score normalisation. RRF is proven in TREC benchmarks to outperform either
ranker alone; no training required.

    score(d) = Σ 1 / (k + rank_i(d))

where k=60 (Cormack et al., 2009). The fused ranked list is then optionally
re-ranked by a cross-encoder for precision.

Zero-cost: all components are self-hosted or pure-Python.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger("tranc3.search.hybrid")

_RRF_K = 60  # Cormack et al. constant


@dataclass
class SearchHit:
    doc_id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "hybrid"  # "bm25" | "vector" | "hybrid"
    rank_bm25: Optional[int] = None
    rank_vector: Optional[int] = None
    highlight: Optional[str] = None


def reciprocal_rank_fusion(
    bm25_hits: List[SearchHit],
    vector_hits: List[SearchHit],
    k: int = _RRF_K,
    bm25_weight: float = 0.5,
    vector_weight: float = 0.5,
) -> List[SearchHit]:
    """Merge two ranked lists via weighted RRF."""
    scores: Dict[str, float] = {}
    meta: Dict[str, SearchHit] = {}

    for rank, hit in enumerate(bm25_hits, start=1):
        scores[hit.doc_id] = scores.get(hit.doc_id, 0.0) + bm25_weight / (k + rank)
        hit.rank_bm25 = rank
        meta[hit.doc_id] = hit

    for rank, hit in enumerate(vector_hits, start=1):
        scores[hit.doc_id] = scores.get(hit.doc_id, 0.0) + vector_weight / (k + rank)
        if hit.doc_id not in meta:
            meta[hit.doc_id] = hit
        meta[hit.doc_id].rank_vector = rank

    fused = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    results: List[SearchHit] = []
    for doc_id, score in fused:
        hit = meta[doc_id]
        hit.score = score
        hit.source = "hybrid"
        results.append(hit)
    return results


class HybridSearch:
    """Orchestrates BM25 + vector search with RRF fusion.

    Adaptive: falls back gracefully if either backend is unavailable.
    """

    def __init__(
        self,
        index_uid: str = "tranc3_docs",
        vector_collection: str = "tranc3_docs",
        bm25_weight: float = 0.5,
        vector_weight: float = 0.5,
    ) -> None:
        self.index_uid = index_uid
        self.vector_collection = vector_collection
        self.bm25_weight = bm25_weight
        self.vector_weight = vector_weight
        self._meili_ok: Optional[bool] = None
        self._vector_ok: Optional[bool] = None

    def _check_backends(self) -> None:
        from src.search import meilisearch_client as ms

        self._meili_ok = ms.is_available()

        try:
            from src.vector.adapter import get_vector_store

            vs = get_vector_store(self.vector_collection)
            self._vector_ok = vs is not None
        except Exception:
            self._vector_ok = False

        logger.info(
            "HybridSearch backends — Meilisearch: %s, Vector: %s",
            self._meili_ok,
            self._vector_ok,
        )

    def search(
        self,
        query: str,
        top_k: int = 10,
        filter_expr: Optional[str] = None,
        score_threshold: float = 0.0,
    ) -> List[SearchHit]:
        """Run hybrid search: BM25 + vector → RRF → ranked results."""
        t0 = time.time()

        if self._meili_ok is None or self._vector_ok is None:
            self._check_backends()

        bm25_hits: List[SearchHit] = []
        vector_hits: List[SearchHit] = []

        # ── BM25 via Meilisearch ──────────────────────────────────────────────
        if self._meili_ok:
            try:
                from src.search import meilisearch_client as ms

                result = ms.search(
                    self.index_uid,
                    query,
                    limit=top_k * 2,
                    filter_expr=filter_expr,
                    attributes_to_highlight=["content", "text"],
                )
                for hit in result.get("hits", []):
                    highlight = None
                    if "_formatted" in hit:
                        highlight = hit["_formatted"].get("content") or hit["_formatted"].get(
                            "text"
                        )
                    bm25_hits.append(
                        SearchHit(
                            doc_id=str(hit.get("id", hit.get("_id", ""))),
                            score=hit.get("_rankingScore", 0.0),
                            payload={k: v for k, v in hit.items() if not k.startswith("_")},
                            source="bm25",
                            highlight=highlight,
                        )
                    )
            except Exception as exc:
                logger.warning("BM25 search failed: %s", exc)
                self._meili_ok = False

        # ── Dense vector search ───────────────────────────────────────────────
        if self._vector_ok:
            try:
                from src.vector.adapter import get_vector_store

                vs = get_vector_store(self.vector_collection)
                raw = vs.search_text(query, top_k=top_k * 2, score_threshold=score_threshold)
                for item in raw:
                    vector_hits.append(
                        SearchHit(
                            doc_id=str(item.get("id", item.get("doc_id", ""))),
                            score=float(item.get("score", 0.0)),
                            payload=item.get("payload", item),
                            source="vector",
                        )
                    )
            except Exception as exc:
                logger.warning("Vector search failed: %s", exc)
                self._vector_ok = False

        # ── Fusion ────────────────────────────────────────────────────────────
        if bm25_hits and vector_hits:
            results = reciprocal_rank_fusion(
                bm25_hits,
                vector_hits,
                bm25_weight=self.bm25_weight,
                vector_weight=self.vector_weight,
            )
        elif bm25_hits:
            results = bm25_hits
        elif vector_hits:
            results = vector_hits
        else:
            results = []

        latency_ms = (time.time() - t0) * 1000
        _q = query[:80].replace("\n", " ").replace("\r", " ")
        logger.debug("HybridSearch '%s' → %d hits in %.1fms", _q, len(results), latency_ms)
        return results[:top_k]

    def ingest(self, documents: List[Dict[str, Any]]) -> None:
        """Ingest documents into both BM25 and vector backends."""
        if self._meili_ok is None:
            self._check_backends()

        if self._meili_ok:
            try:
                from src.search import meilisearch_client as ms

                ms.ensure_index(self.index_uid)
                ms.upsert_documents(self.index_uid, documents)
            except Exception as exc:
                logger.warning("Meilisearch ingest failed: %s", exc)

        texts = [d.get("content") or d.get("text") or "" for d in documents]
        ids = [str(d.get("id", i)) for i, d in enumerate(documents)]
        metadatas = [
            {k: v for k, v in d.items() if k not in ("content", "text")} for d in documents
        ]

        if self._vector_ok:
            try:
                from src.vector.adapter import get_vector_store

                vs = get_vector_store(self.vector_collection)
                vs.ingest(texts=texts, ids=ids, metadatas=metadatas)
            except Exception as exc:
                logger.warning("Vector ingest failed: %s", exc)
