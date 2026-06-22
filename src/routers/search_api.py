"""Search & RAG REST API router.

Endpoints:
  POST /api/search           — Hybrid BM25 + vector search with optional re-ranking
  POST /api/rag              — Retrieve-and-generate: search + LLM answer synthesis
  POST /api/embed            — Embed a text payload via the adaptive embedding stack
  POST /api/ingest           — Ingest documents into both BM25 and vector backends
  GET  /api/search/status    — Health of all search backends
  GET  /api/search/cache     — Semantic cache statistics

All endpoints are zero-cost: local/self-hosted inference, no paid APIs.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger("tranc3.routers.search_api")

router = APIRouter(prefix="/api", tags=["search"])


# ── Request / response models ─────────────────────────────────────────────────


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(10, ge=1, le=100)
    filter_expr: Optional[str] = None
    score_threshold: float = Field(0.0, ge=0.0, le=1.0)
    rerank: bool = False
    expand_query: bool = False
    use_cache: bool = True


class SearchHitOut(BaseModel):
    doc_id: str
    score: float
    source: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    highlight: Optional[str] = None
    rank_bm25: Optional[int] = None
    rank_vector: Optional[int] = None


class SearchResponse(BaseModel):
    query: str
    hits: List[SearchHitOut]
    total: int
    latency_ms: float
    cache_hit: bool = False


class RAGRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(5, ge=1, le=20)
    max_tokens: int = Field(512, ge=64, le=4096)
    rerank: bool = True
    use_cache: bool = True


class RAGResponse(BaseModel):
    query: str
    answer: str
    sources: List[SearchHitOut]
    latency_ms: float
    cache_hit: bool = False


class EmbedRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=8000)


class EmbedResponse(BaseModel):
    embedding: List[float]
    dim: int
    model: str


class IngestRequest(BaseModel):
    documents: List[Dict[str, Any]] = Field(..., min_length=1, max_length=500)
    collection: str = "tranc3_docs"


class IngestResponse(BaseModel):
    ingested: int
    collection: str
    latency_ms: float


# ── Lazy singletons ───────────────────────────────────────────────────────────

_hybrid: Optional[Any] = None
_reranker: Optional[Any] = None
_expander: Optional[Any] = None


def _get_hybrid():
    global _hybrid
    if _hybrid is None:
        from src.search.hybrid import HybridSearch

        _hybrid = HybridSearch()
    return _hybrid


def _get_reranker():
    global _reranker
    if _reranker is None:
        from src.search.reranker import CrossEncoderReranker

        _reranker = CrossEncoderReranker()
    return _reranker


def _get_expander():
    global _expander
    if _expander is None:
        from src.search.query_expansion import QueryExpander

        _expander = QueryExpander()
    return _expander


# ── Helpers ───────────────────────────────────────────────────────────────────


def _hit_to_out(hit) -> SearchHitOut:
    return SearchHitOut(
        doc_id=hit.doc_id,
        score=hit.score,
        source=hit.source,
        payload=hit.payload,
        highlight=hit.highlight,
        rank_bm25=hit.rank_bm25,
        rank_vector=hit.rank_vector,
    )


def _run_search(query: str, req: SearchRequest):
    """Run hybrid search, optionally with query expansion + re-ranking."""
    from src.search.semantic_cache import get_or_search

    def _search(q: str, top_k: int, **kw):
        hs = _get_hybrid()
        results = hs.search(
            q, top_k=top_k, filter_expr=req.filter_expr, score_threshold=req.score_threshold
        )

        # expand and merge if requested
        if req.expand_query:
            expander = _get_expander()
            variants = expander.expand(q, n=2)
            for variant in variants[1:]:
                extra = hs.search(variant, top_k=top_k // 2 or 1)
                seen = {r.doc_id for r in results}
                for hit in extra:
                    if hit.doc_id not in seen:
                        results.append(hit)

        # re-rank if requested
        if req.rerank and results:
            results = _get_reranker().rerank(q, results, top_k=top_k)

        return results

    if req.use_cache:
        return get_or_search(query, _search, top_k=req.top_k)
    return _search(query, top_k=req.top_k), False


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest) -> SearchResponse:
    """Hybrid BM25 + vector search with optional query expansion and re-ranking."""
    t0 = time.time()
    try:
        hits, cache_hit = _run_search(req.query, req)
    except Exception as exc:
        logger.exception("Search error")
        raise HTTPException(status_code=500, detail="Search failed") from exc

    return SearchResponse(
        query=req.query,
        hits=[_hit_to_out(h) for h in hits],
        total=len(hits),
        latency_ms=(time.time() - t0) * 1000,
        cache_hit=cache_hit,
    )


@router.post("/rag", response_model=RAGResponse)
async def rag(req: RAGRequest) -> RAGResponse:
    """Retrieve context via hybrid search then synthesize an answer via LLM."""
    t0 = time.time()

    search_req = SearchRequest(
        query=req.query,
        top_k=req.top_k,
        rerank=req.rerank,
        use_cache=req.use_cache,
    )
    try:
        hits, cache_hit = _run_search(req.query, search_req)
    except Exception as exc:
        logger.exception("RAG retrieval error")
        raise HTTPException(status_code=500, detail="Retrieval failed") from exc

    context_parts: List[str] = []
    for hit in hits:
        text = hit.payload.get("content") or hit.payload.get("text") or ""
        if text:
            context_parts.append(f"[{hit.doc_id}] {text}")

    context = "\n\n".join(context_parts) or "No relevant context found."
    prompt = f"Context:\n{context}\n\nQuestion: {req.query}\n\nAnswer concisely based on the context above:"

    answer = ""
    try:
        from src.ai_gateway.provider_rotation import complete

        answer = complete(prompt, max_tokens=req.max_tokens)
    except Exception as exc:  # noqa: BLE001
        logger.warning("LLM synthesis failed: %s", exc)
        answer = "(LLM unavailable — context retrieved but synthesis failed)"

    return RAGResponse(
        query=req.query,
        answer=answer,
        sources=[_hit_to_out(h) for h in hits],
        latency_ms=(time.time() - t0) * 1000,
        cache_hit=cache_hit,
    )


@router.post("/embed", response_model=EmbedResponse)
async def embed(req: EmbedRequest) -> EmbedResponse:
    """Embed a text string using the adaptive embedding rotation stack."""
    try:
        from src.vector.adapter import _EMBED_MODEL as model_name
        from src.vector.adapter import embed_text

        vec = embed_text(req.text)
    except Exception as exc:
        logger.exception("Embedding error")
        raise HTTPException(status_code=500, detail="Embedding failed") from exc

    return EmbedResponse(embedding=vec, dim=len(vec), model=model_name)


@router.post("/ingest", response_model=IngestResponse)
async def ingest(req: IngestRequest) -> IngestResponse:
    """Ingest documents into BM25 (Meilisearch) and vector (adaptive) backends."""
    t0 = time.time()
    try:
        from src.search.hybrid import HybridSearch

        hs = HybridSearch(
            index_uid=req.collection,
            vector_collection=req.collection,
        )
        hs.ingest(req.documents)
    except Exception as exc:
        logger.exception("Ingest error")
        raise HTTPException(status_code=500, detail="Ingest failed") from exc

    return IngestResponse(
        ingested=len(req.documents),
        collection=req.collection,
        latency_ms=(time.time() - t0) * 1000,
    )


@router.get("/search/status")
async def search_status() -> Dict[str, Any]:
    """Health check for all search backends."""
    status: Dict[str, Any] = {}

    # Meilisearch
    try:
        from src.search import meilisearch_client as ms

        status["meilisearch"] = "ok" if ms.is_available() else "unavailable"
    except Exception:
        status["meilisearch"] = "error"

    # Vector adapter backend
    try:
        from src.vector.adapter import get_vector_store

        vs = get_vector_store("_health")
        status["vector"] = type(vs._backend).__name__
    except Exception:
        status["vector"] = "error"

    return {"backends": status, "timestamp": time.time()}


@router.get("/search/cache")
async def cache_stats() -> Dict[str, Any]:
    """Return semantic cache statistics."""
    try:
        from src.search.semantic_cache import get_cache

        return get_cache().stats()
    except Exception:
        return {"error": "cache stats unavailable"}
