"""
src/vector/adapter.py — Unified vector store with adaptive backend + embedding rotation
========================================================================================
Canonical vector store for the Trancendos platform. Consolidates:
  • src/database/vector_store.py   (Pinecone/in-memory)
  • src/knowledge/vector_store.py  (FAISS/sentence-transformers, text-level API)
  • src/database/pgvector.py       (PostgreSQL pgvector backend)

Backend priority (all zero-cost, self-hosted or free tier):
  1. Qdrant      (self-hosted :6333)         — persistent, scalable, production-grade
  2. pgvector    (Supabase/Neon free tier)   — SQL-native, no extra infra
  3. ChromaDB    (in-process)                — persistent, SQL-backed
  4. LanceDB     (in-process)                — columnar, fast, zero-copy
  5. FAISS       (in-process)                — GPU-optional, battle-tested
  6. Numpy       (always available)          — zero dependencies

Embedding provider rotation (all zero-cost):
  1. Ollama          (local, zero network)
  2. sentence-transformers (local, 80MB model)
  3. HuggingFace Inference API (free tier, 30k req/day)
  4. Jina AI         (free tier, 1M tokens/month)
  5. Cohere          (free tier, 1k req/month)
  6. Together AI     (free tier credits)
  7. Nomic Embed     (local via Ollama or API free tier)
  8. Zero fallback   (null embeddings — store still works, search degrades)

Hard stops: each free-tier provider tracks daily usage and disables itself
when within 10% of its limit, rotating to the next healthy provider.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("tranc3.vector")

# ─── Configuration ────────────────────────────────────────────────────────────

_QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
_DATABASE_URL = os.getenv("DATABASE_URL", "")
_PGVECTOR_TABLE = os.getenv("PGVECTOR_TABLE", "tranc3_embeddings")
_EMBED_DIM = int(os.getenv("VECTOR_DIM", "384"))
_EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")
_COLLECTIONS_DIR = Path(os.getenv("VECTOR_STORE_DIR", "./data/vector_store"))

_OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
_OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")
_HF_TOKEN = os.getenv("HF_TOKEN", os.getenv("HUGGINGFACE_API_KEY", ""))
_JINA_API_KEY = os.getenv("JINA_API_KEY", "")
_COHERE_API_KEY = os.getenv("COHERE_API_KEY", "")
_TOGETHER_API_KEY = os.getenv("TOGETHER_AI_API_KEY", "")

# ─── Shared types ─────────────────────────────────────────────────────────────


@dataclass
class SearchResult:
    id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)
    # text-level alias (populated when text is stored in payload)
    text: str = ""

    def __post_init__(self) -> None:
        if not self.text:
            self.text = self.payload.get("text", "")


@dataclass
class Document:
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    collection: str = "default"
    inserted_at: float = field(default_factory=time.time)


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive Embedding Rotation — 8 free providers
# ─────────────────────────────────────────────────────────────────────────────

# Daily usage caps (conservative — triggers rotation before hitting real limit)
_EMBED_PROVIDER_LIMITS: Dict[str, int] = {
    "ollama": 10_000_000,  # local, effectively unlimited
    "sentence_transformers": 10_000_000,  # local
    "huggingface": 27_000,  # free tier ~30k/day, hard stop at 90%
    "jina": 900_000,  # free 1M/month ≈ 30k/day, hard stop at 90%
    "cohere": 900,  # free 1k/month ≈ 33/day, hard stop at 90%
    "together": 900,  # free credits estimate
    "nomic": 900_000,  # nomic API free tier
    "zero": 10_000_000,  # always available
}

_embed_counters: Dict[str, int] = dict.fromkeys(_EMBED_PROVIDER_LIMITS, 0)
_embed_counter_lock = threading.Lock()
_embed_last_reset: Dict[str, float] = {k: time.time() for k in _EMBED_PROVIDER_LIMITS}
_encoder_cache: Dict[str, Any] = {}
_encoder_lock = threading.Lock()


def _reset_embed_counters_if_needed() -> None:
    now = time.time()
    with _embed_counter_lock:
        for provider in list(_embed_last_reset):
            if now - _embed_last_reset[provider] >= 86400:  # 24h reset
                _embed_counters[provider] = 0
                _embed_last_reset[provider] = now


def _embed_provider_healthy(provider: str) -> bool:
    _reset_embed_counters_if_needed()
    with _embed_counter_lock:
        used = _embed_counters.get(provider, 0)
        limit = _EMBED_PROVIDER_LIMITS.get(provider, 0)
        return used < limit


def _record_embed_usage(provider: str, count: int = 1) -> None:
    with _embed_counter_lock:
        _embed_counters[provider] = _embed_counters.get(provider, 0) + count


def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed *texts* using the first healthy free provider.
    Rotates automatically when a provider's daily limit is approaching.
    """
    if not texts:
        return []

    providers = [
        ("ollama", _embed_ollama),
        ("sentence_transformers", _embed_sentence_transformers),
        ("huggingface", _embed_huggingface),
        ("jina", _embed_jina),
        ("cohere", _embed_cohere),
        ("together", _embed_together),
        ("nomic", _embed_nomic),
        ("zero", _embed_zero),
    ]

    for name, fn in providers:
        if not _embed_provider_healthy(name):
            log.debug("embed: provider %s at limit — skipping", name)
            continue
        try:
            vecs = fn(texts)
            if vecs and len(vecs) == len(texts):
                _record_embed_usage(name, len(texts))
                log.debug("embed: used %s for %d texts", name, len(texts))
                return vecs
        except Exception as exc:
            log.debug("embed: %s failed (%s)", name, exc)

    return _embed_zero(texts)


def embed_text(text: str) -> List[float]:
    vecs = embed_texts([text])
    return vecs[0] if vecs else [0.0] * _EMBED_DIM


def embedding_stats() -> Dict[str, Any]:
    """Return current daily usage and limits per provider."""
    _reset_embed_counters_if_needed()
    with _embed_counter_lock:
        return {
            provider: {
                "used": _embed_counters.get(provider, 0),
                "limit": _EMBED_PROVIDER_LIMITS[provider],
                "healthy": _embed_provider_healthy(provider),
                "pct": round(
                    100
                    * _embed_counters.get(provider, 0)
                    / max(1, _EMBED_PROVIDER_LIMITS[provider]),
                    1,
                ),
            }
            for provider in _EMBED_PROVIDER_LIMITS
        }


# ── Embedding provider implementations ───────────────────────────────────────


def _embed_ollama(texts: List[str]) -> List[List[float]]:
    import httpx

    results = []
    for text in texts:
        resp = httpx.post(
            f"{_OLLAMA_URL}/api/embeddings",
            json={"model": _OLLAMA_EMBED_MODEL, "prompt": text},
            timeout=10.0,
        )
        resp.raise_for_status()
        results.append(resp.json()["embedding"])
    return results


def _embed_sentence_transformers(texts: List[str]) -> List[List[float]]:
    key = "st"
    if key not in _encoder_cache:
        with _encoder_lock:
            if key not in _encoder_cache:
                from sentence_transformers import SentenceTransformer  # type: ignore

                _encoder_cache[key] = SentenceTransformer(_EMBED_MODEL)
    enc = _encoder_cache[key]
    vecs = enc.encode(texts, show_progress_bar=False)
    return [v.tolist() for v in vecs]


def _embed_huggingface(texts: List[str]) -> List[List[float]]:
    if not _HF_TOKEN:
        raise RuntimeError("HF_TOKEN not set")
    import httpx

    resp = httpx.post(
        f"https://api-inference.huggingface.co/pipeline/feature-extraction/sentence-transformers/{_EMBED_MODEL}",
        headers={"Authorization": f"Bearer {_HF_TOKEN}"},
        json={"inputs": texts, "options": {"wait_for_model": True}},
        timeout=30.0,
    )
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data[0][0], list):
        # Mean-pool sentence embeddings
        import statistics

        return [[statistics.mean(row) for row in doc] for doc in data]
    return data


def _embed_jina(texts: List[str]) -> List[List[float]]:
    if not _JINA_API_KEY:
        raise RuntimeError("JINA_API_KEY not set")
    import httpx

    resp = httpx.post(
        "https://api.jina.ai/v1/embeddings",
        headers={"Authorization": f"Bearer {_JINA_API_KEY}", "Content-Type": "application/json"},
        json={"input": texts, "model": "jina-embeddings-v3"},
        timeout=30.0,
    )
    resp.raise_for_status()
    return [item["embedding"] for item in resp.json()["data"]]


def _embed_cohere(texts: List[str]) -> List[List[float]]:
    if not _COHERE_API_KEY:
        raise RuntimeError("COHERE_API_KEY not set")
    import httpx

    resp = httpx.post(
        "https://api.cohere.ai/v1/embed",
        headers={"Authorization": f"Bearer {_COHERE_API_KEY}", "Content-Type": "application/json"},
        json={
            "texts": texts,
            "model": "embed-multilingual-light-v3.0",
            "input_type": "search_document",
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"]


def _embed_together(texts: List[str]) -> List[List[float]]:
    if not _TOGETHER_API_KEY:
        raise RuntimeError("TOGETHER_AI_API_KEY not set")
    import httpx

    results = []
    for text in texts:
        resp = httpx.post(
            "https://api.together.xyz/v1/embeddings",
            headers={"Authorization": f"Bearer {_TOGETHER_API_KEY}"},
            json={"model": "togethercomputer/m2-bert-80M-8k-retrieval", "input": text},
            timeout=30.0,
        )
        resp.raise_for_status()
        results.append(resp.json()["data"][0]["embedding"])
    return results


def _embed_nomic(texts: List[str]) -> List[List[float]]:
    """Nomic via Ollama (nomic-embed-text model) or Nomic API free tier."""
    try:
        import httpx

        results = []
        for text in texts:
            resp = httpx.post(
                f"{_OLLAMA_URL}/api/embeddings",
                json={"model": "nomic-embed-text", "prompt": text},
                timeout=10.0,
            )
            resp.raise_for_status()
            results.append(resp.json()["embedding"])
        return results
    except Exception as err:
        raise RuntimeError("nomic via ollama unavailable") from err


def _embed_zero(texts: List[str]) -> List[List[float]]:
    """Null embeddings — store works, semantic search degrades to random."""
    return [[0.0] * _EMBED_DIM for _ in texts]


# ─────────────────────────────────────────────────────────────────────────────
# Backend implementations
# ─────────────────────────────────────────────────────────────────────────────


class _QdrantBackend:
    """Qdrant (self-hosted, free OSS). Persistent, scalable."""

    def __init__(self, collection: str, dim: int) -> None:
        from qdrant_client import QdrantClient  # type: ignore
        from qdrant_client.models import Distance, VectorParams  # type: ignore

        self._collection = collection
        self._client = QdrantClient(url=_QDRANT_URL, timeout=5)
        existing = [c.name for c in self._client.get_collections().collections]
        if collection not in existing:
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
        log.info("VectorStore[qdrant] collection=%s dim=%d", collection, dim)

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct  # type: ignore

        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(id=_str_to_uuid(doc_id), vector=vector, payload=payload)],
        )

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore

        qfilter = None
        if metadata_filter:
            qfilter = Filter(
                must=[
                    FieldCondition(key=k, match=MatchValue(value=v))
                    for k, v in metadata_filter.items()
                ]
            )
        hits = self._client.search(
            collection_name=self._collection,
            query_vector=vector,
            query_filter=qfilter,
            limit=top_k,
        )
        return [SearchResult(id=str(h.id), score=h.score, payload=h.payload or {}) for h in hits]

    def delete(self, doc_id: str) -> None:
        from qdrant_client.models import PointIdsList  # type: ignore

        self._client.delete(
            collection_name=self._collection,
            points_selector=PointIdsList(points=[_str_to_uuid(doc_id)]),
        )

    def delete_by_metadata(self, key: str, value: str) -> int:
        from qdrant_client.models import FieldCondition, Filter, MatchValue  # type: ignore

        result = self._client.delete(
            collection_name=self._collection,
            points_selector=Filter(must=[FieldCondition(key=key, match=MatchValue(value=value))]),
        )
        return getattr(result, "operation_id", 0)

    def count(self) -> int:
        return self._client.count(collection_name=self._collection).count

    def save(self, path: Path) -> None:
        pass  # Qdrant persists automatically

    def load(self, path: Path) -> int:
        return self.count()


class _PgvectorBackend:
    """PostgreSQL pgvector backend. Free on Supabase/Neon free tiers.

    Uses SQLAlchemy text() with named bound parameters throughout — no raw
    string concatenation into SQL, satisfying static-analysis requirements.
    Table name is validated against a strict identifier whitelist at init time.
    """

    # Strict allowlist: only alphanumeric + underscore, max 63 chars (PostgreSQL limit)
    _SAFE_IDENT = __import__("re").compile(r"^[a-z][a-z0-9_]{0,62}$")

    def __init__(self, collection: str, dim: int) -> None:
        from sqlalchemy import create_engine  # type: ignore

        raw_table = f"vec_{collection.replace('-', '_').lower()}"
        if not self._SAFE_IDENT.match(raw_table):
            raise ValueError(f"Unsafe pgvector table name derived from collection '{collection}'")
        self._table = raw_table
        self._dim = dim
        self._engine = create_engine(_DATABASE_URL, pool_pre_ping=True)
        self._bootstrap()
        log.info("VectorStore[pgvector] table=%s dim=%d", self._table, dim)

    def _bootstrap(self) -> None:
        from sqlalchemy import text  # type: ignore

        # Table and index names are validated identifiers — safe to embed as
        # format strings here; all *values* travel via bound parameters below.
        tbl = self._table
        idx = f"{tbl}_idx"
        with self._engine.connect() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(
                text(
                    f"CREATE TABLE IF NOT EXISTS {tbl} ("  # noqa: S608 — identifier validated
                    "  id TEXT PRIMARY KEY,"
                    f"  embedding vector({self._dim}),"
                    "  payload JSONB NOT NULL DEFAULT '{}',"
                    "  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()"
                    ")"
                )
            )
            conn.execute(
                text(
                    f"CREATE INDEX IF NOT EXISTS {idx} "  # noqa: S608
                    f"ON {tbl} USING ivfflat (embedding vector_cosine_ops) "
                    "WITH (lists = 100)"
                )
            )
            conn.commit()

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        from sqlalchemy import text  # type: ignore

        tbl = self._table
        with self._engine.connect() as conn:
            conn.execute(
                text(
                    f"INSERT INTO {tbl} (id, embedding, payload) "  # noqa: S608
                    "VALUES (:id, :vec::vector, :payload::jsonb) "
                    "ON CONFLICT (id) DO UPDATE SET "
                    "  embedding = EXCLUDED.embedding,"
                    "  payload   = EXCLUDED.payload,"
                    "  updated_at = NOW()"
                ),
                {"id": doc_id, "vec": str(vector), "payload": json.dumps(payload)},
            )
            conn.commit()

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        from sqlalchemy import text  # type: ignore

        tbl = self._table
        if metadata_filter:
            rows = (
                self._engine.connect()
                .execute(
                    text(
                        f"SELECT id, payload, 1 - (embedding <=> :vec::vector) AS score "  # noqa: S608
                        f"FROM {tbl} WHERE payload @> :filter::jsonb "
                        "ORDER BY score DESC LIMIT :k"
                    ),
                    {"vec": str(vector), "filter": json.dumps(metadata_filter), "k": top_k},
                )
                .fetchall()
            )
        else:
            rows = (
                self._engine.connect()
                .execute(
                    text(
                        f"SELECT id, payload, 1 - (embedding <=> :vec::vector) AS score "  # noqa: S608
                        f"FROM {tbl} ORDER BY score DESC LIMIT :k"
                    ),
                    {"vec": str(vector), "k": top_k},
                )
                .fetchall()
            )
        return [SearchResult(id=r[0], score=float(r[2]), payload=r[1] or {}) for r in rows]

    def delete(self, doc_id: str) -> None:
        from sqlalchemy import text  # type: ignore

        with self._engine.connect() as conn:
            conn.execute(
                text(f"DELETE FROM {self._table} WHERE id = :id"),  # noqa: S608
                {"id": doc_id},
            )
            conn.commit()

    def delete_by_metadata(self, key: str, value: str) -> int:
        from sqlalchemy import text  # type: ignore

        with self._engine.connect() as conn:
            result = conn.execute(
                text(
                    f"DELETE FROM {self._table} WHERE payload->>:key = :val"  # noqa: S608
                ),
                {"key": key, "val": value},
            )
            conn.commit()
            return result.rowcount

    def count(self) -> int:
        from sqlalchemy import text  # type: ignore

        with self._engine.connect() as conn:
            return (
                conn.execute(
                    text(f"SELECT COUNT(*) FROM {self._table}")  # noqa: S608
                ).scalar()
                or 0
            )

    def save(self, path: Path) -> None:
        pass  # pgvector persists automatically

    def load(self, path: Path) -> int:
        return self.count()


class _ChromaBackend:
    """ChromaDB — in-process persistent backend. SQLite-backed, zero network."""

    def __init__(self, collection: str, dim: int) -> None:
        import chromadb  # type: ignore

        persist_dir = str(_COLLECTIONS_DIR / "chroma")
        self._client = chromadb.PersistentClient(path=persist_dir)
        self._coll = self._client.get_or_create_collection(name=collection)
        log.info("VectorStore[chroma] collection=%s", collection)

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        self._coll.upsert(ids=[doc_id], embeddings=[vector], metadatas=[payload])

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        kwargs: Dict[str, Any] = {"query_embeddings": [vector], "n_results": top_k}
        if metadata_filter:
            kwargs["where"] = {k: {"$eq": v} for k, v in metadata_filter.items()}
        res = self._coll.query(**kwargs)
        results = []
        for doc_id, distance, meta in zip(
            res["ids"][0], res["distances"][0], res["metadatas"][0], strict=False
        ):
            results.append(SearchResult(id=doc_id, score=1.0 - distance, payload=meta or {}))
        return results

    def delete(self, doc_id: str) -> None:
        self._coll.delete(ids=[doc_id])

    def delete_by_metadata(self, key: str, value: str) -> int:
        existing = self._coll.get(where={key: {"$eq": value}})
        ids = existing.get("ids", [])
        if ids:
            self._coll.delete(ids=ids)
        return len(ids)

    def count(self) -> int:
        return self._coll.count()

    def save(self, path: Path) -> None:
        pass  # ChromaDB persists automatically

    def load(self, path: Path) -> int:
        return self.count()


class _LanceBackend:
    """LanceDB — columnar in-process backend. Lance format, zero network."""

    def __init__(self, collection: str, dim: int) -> None:
        import lancedb  # type: ignore

        db_path = str(_COLLECTIONS_DIR / "lance")
        self._db = lancedb.connect(db_path)
        self._name = collection
        self._dim = dim
        if collection not in self._db.table_names():
            import pyarrow as pa  # type: ignore

            schema = pa.schema(
                [
                    pa.field("id", pa.string()),
                    pa.field("vector", pa.list_(pa.float32(), dim)),
                    pa.field("payload", pa.string()),
                ]
            )
            self._table = self._db.create_table(collection, schema=schema)
        else:
            self._table = self._db.open_table(collection)
        log.info("VectorStore[lancedb] collection=%s dim=%d", collection, dim)

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        self._table.delete(f"id = '{doc_id}'")
        self._table.add([{"id": doc_id, "vector": vector, "payload": json.dumps(payload)}])

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        q = self._table.search(vector).limit(top_k)
        rows = q.to_list()
        results = []
        for row in rows:
            payload = json.loads(row.get("payload", "{}"))
            if metadata_filter and not all(payload.get(k) == v for k, v in metadata_filter.items()):
                continue
            results.append(
                SearchResult(id=row["id"], score=1.0 - row.get("_distance", 0.0), payload=payload)
            )
        return results

    def delete(self, doc_id: str) -> None:
        self._table.delete(f"id = '{doc_id}'")

    def delete_by_metadata(self, key: str, value: str) -> int:
        rows = self._table.to_pandas()
        count = 0
        for _, row in rows.iterrows():
            payload = json.loads(row.get("payload", "{}"))
            if payload.get(key) == value:
                self._table.delete(f"id = '{row['id']}'")
                count += 1
        return count

    def count(self) -> int:
        return self._table.count_rows()

    def save(self, path: Path) -> None:
        pass  # LanceDB persists automatically

    def load(self, path: Path) -> int:
        return self.count()


class _FaissBackend:
    """FAISS in-process backend with disk persistence."""

    def __init__(self, collection: str, dim: int) -> None:
        import faiss  # type: ignore

        self._collection = collection
        self._dim = dim
        self._index = faiss.IndexFlatIP(dim)
        self._ids: List[str] = []
        self._vectors: List[List[float]] = []
        self._payloads: List[Dict[str, Any]] = []
        log.info("VectorStore[faiss] collection=%s dim=%d", collection, dim)

    def _rebuild_index(self) -> None:
        import faiss  # type: ignore
        import numpy as np  # type: ignore

        self._index = faiss.IndexFlatIP(self._dim)
        if self._vectors:
            v = np.array(self._vectors, dtype="float32")
            faiss.normalize_L2(v)
            self._index.add(v)

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        if doc_id in self._ids:
            idx = self._ids.index(doc_id)
            self._vectors[idx] = vector
            self._payloads[idx] = payload
            self._rebuild_index()
        else:
            import faiss  # type: ignore
            import numpy as np  # type: ignore

            v = np.array([vector], dtype="float32")
            faiss.normalize_L2(v)
            self._index.add(v)
            self._ids.append(doc_id)
            self._vectors.append(vector)
            self._payloads.append(payload)

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        import faiss  # type: ignore
        import numpy as np  # type: ignore

        if self._index.ntotal == 0:
            return []
        v = np.array([vector], dtype="float32")
        faiss.normalize_L2(v)
        k = min(top_k * (4 if metadata_filter else 1), self._index.ntotal)
        scores, indices = self._index.search(v, k)
        results = []
        for score, idx in zip(scores[0], indices[0], strict=False):
            if 0 <= idx < len(self._ids):
                payload = self._payloads[idx]
                if metadata_filter and not all(
                    payload.get(k) == val for k, val in metadata_filter.items()
                ):
                    continue
                results.append(SearchResult(id=self._ids[idx], score=float(score), payload=payload))
                if len(results) >= top_k:
                    break
        return results

    def delete(self, doc_id: str) -> None:
        if doc_id in self._ids:
            i = self._ids.index(doc_id)
            self._ids.pop(i)
            self._vectors.pop(i)
            self._payloads.pop(i)
            self._rebuild_index()

    def delete_by_metadata(self, key: str, value: str) -> int:
        to_del = [i for i, p in enumerate(self._payloads) if p.get(key) == value]
        for i in reversed(to_del):
            self._ids.pop(i)
            self._vectors.pop(i)
            self._payloads.pop(i)
        if to_del:
            self._rebuild_index()
        return len(to_del)

    def count(self) -> int:
        return len(self._ids)

    def save(self, path: Path) -> None:
        import faiss  # type: ignore

        path.mkdir(parents=True, exist_ok=True)
        faiss.write_index(self._index, str(path / "index.faiss"))
        (path / "docs.json").write_text(
            json.dumps(
                [
                    {"id": self._ids[i], "vector": self._vectors[i], "payload": self._payloads[i]}
                    for i in range(len(self._ids))
                ]
            )
        )

    def load(self, path: Path) -> int:
        import faiss  # type: ignore

        idx_path = path / "index.faiss"
        docs_path = path / "docs.json"
        if not docs_path.exists():
            return 0
        docs = json.loads(docs_path.read_text())
        self._ids = [d["id"] for d in docs]
        self._vectors = [d["vector"] for d in docs]
        self._payloads = [d["payload"] for d in docs]
        if idx_path.exists():
            self._index = faiss.read_index(str(idx_path))
        else:
            self._rebuild_index()
        return len(self._ids)


class _NumpyBackend:
    """Pure-numpy fallback — zero dependencies beyond numpy."""

    def __init__(self, collection: str, dim: int) -> None:
        self._collection = collection
        self._dim = dim
        self._ids: List[str] = []
        self._vectors: List[List[float]] = []
        self._payloads: List[Dict[str, Any]] = []
        log.info("VectorStore[numpy] collection=%s dim=%d", collection, dim)

    def _cosine(self, a: Any, b: Any) -> float:
        import numpy as np  # type: ignore

        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na == 0 or nb == 0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    def upsert(self, doc_id: str, vector: List[float], payload: Dict[str, Any]) -> None:
        if doc_id in self._ids:
            idx = self._ids.index(doc_id)
            self._vectors[idx] = vector
            self._payloads[idx] = payload
        else:
            self._ids.append(doc_id)
            self._vectors.append(vector)
            self._payloads.append(payload)

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        import numpy as np  # type: ignore

        if not self._vectors:
            return []
        v = np.array(vector)
        candidates = [
            (self._cosine(v, np.array(sv)), i)
            for i, sv in enumerate(self._vectors)
            if not metadata_filter
            or all(self._payloads[i].get(k) == val for k, val in metadata_filter.items())
        ]
        top = sorted(candidates, reverse=True)[:top_k]
        return [SearchResult(id=self._ids[i], score=s, payload=self._payloads[i]) for s, i in top]

    def delete(self, doc_id: str) -> None:
        if doc_id in self._ids:
            i = self._ids.index(doc_id)
            self._ids.pop(i)
            self._vectors.pop(i)
            self._payloads.pop(i)

    def delete_by_metadata(self, key: str, value: str) -> int:
        to_del = [i for i, p in enumerate(self._payloads) if p.get(key) == value]
        for i in reversed(to_del):
            self._ids.pop(i)
            self._vectors.pop(i)
            self._payloads.pop(i)
        return len(to_del)

    def count(self) -> int:
        return len(self._ids)

    def save(self, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        (path / "docs.json").write_text(
            json.dumps(
                [
                    {"id": self._ids[i], "vector": self._vectors[i], "payload": self._payloads[i]}
                    for i in range(len(self._ids))
                ]
            )
        )

    def load(self, path: Path) -> int:
        docs_path = path / "docs.json"
        if not docs_path.exists():
            return 0
        docs = json.loads(docs_path.read_text())
        self._ids = [d["id"] for d in docs]
        self._vectors = [d["vector"] for d in docs]
        self._payloads = [d["payload"] for d in docs]
        return len(self._ids)


# ─────────────────────────────────────────────────────────────────────────────
# Backend selection — 6-tier adaptive fallback
# ─────────────────────────────────────────────────────────────────────────────


def _make_backend(collection: str, dim: int) -> Any:
    # 1. Qdrant (self-hosted)
    try:
        return _QdrantBackend(collection, dim)
    except Exception as exc:
        log.debug("Qdrant unavailable (%s)", exc)

    # 2. pgvector (Supabase/Neon free tier)
    if _DATABASE_URL:
        try:
            return _PgvectorBackend(collection, dim)
        except Exception as exc:
            log.debug("pgvector unavailable (%s)", exc)

    # 3. ChromaDB (in-process persistent)
    try:
        return _ChromaBackend(collection, dim)
    except Exception as exc:
        log.debug("ChromaDB unavailable (%s)", exc)

    # 4. LanceDB (in-process columnar)
    try:
        return _LanceBackend(collection, dim)
    except Exception as exc:
        log.debug("LanceDB unavailable (%s)", exc)

    # 5. FAISS (in-process)
    try:
        return _FaissBackend(collection, dim)
    except Exception as exc:
        log.debug("FAISS unavailable (%s)", exc)

    # 6. Numpy (always available)
    return _NumpyBackend(collection, dim)


# ─────────────────────────────────────────────────────────────────────────────
# Public VectorStore facade
# ─────────────────────────────────────────────────────────────────────────────

_backend_cache: Dict[str, "VectorStore"] = {}


class VectorStore:
    """
    Unified vector store facade. Use ``get_vector_store()`` to obtain a
    cached instance per collection.

    Provides both:
    - Vector-level API: ``upsert(id, vector, payload)``, ``search(vector)``
    - Text-level API:   ``ingest(texts)``, ``search_text(query)``

    The text-level API auto-embeds using the adaptive embedding rotation
    (8 free providers with daily limit monitoring and hard stops).
    """

    def __init__(self, collection: str, dim: int = _EMBED_DIM) -> None:
        self._collection = collection
        self._dim = dim
        self._backend = _make_backend(collection, dim)

    # ── Vector-level API ──────────────────────────────────────────────────────

    def upsert(
        self,
        doc_id: str,
        vector: List[float],
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._backend.upsert(doc_id, vector, payload or {})

    def search(
        self,
        vector: List[float],
        top_k: int = 5,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        return self._backend.search(vector, top_k, metadata_filter)

    def delete(self, doc_id: str) -> None:
        self._backend.delete(doc_id)

    def count(self) -> int:
        return self._backend.count()

    # ── Text-level API (auto-embeds) ──────────────────────────────────────────

    def ingest(
        self,
        texts: List[str],
        ids: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Embed *texts* and upsert into the collection.
        Returns the list of assigned document IDs.
        """
        if not texts:
            return []
        vectors = embed_texts(texts)
        doc_ids: List[str] = []
        for i, (text, vec) in enumerate(zip(texts, vectors, strict=False)):
            doc_id = (ids[i] if ids else None) or _make_id(text, i)
            meta = (metadatas[i] if metadatas else {}).copy()
            meta["text"] = text
            self._backend.upsert(doc_id, vec, meta)
            doc_ids.append(doc_id)
        return doc_ids

    def search_text(
        self,
        query: str,
        top_k: int = 5,
        score_threshold: float = 0.0,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Embed *query* and return nearest documents."""
        vec = embed_text(query)
        results = self._backend.search(
            vec, top_k * 4 if metadata_filter else top_k, metadata_filter
        )
        if score_threshold > 0:
            results = [r for r in results if r.score >= score_threshold]
        return results[:top_k]

    # ── GDPR / erasure ────────────────────────────────────────────────────────

    def delete_user(self, user_id: str) -> int:
        """Delete all vectors associated with a user_id. GDPR right-to-erasure."""
        return self._backend.delete_by_metadata("user_id", user_id)

    def delete_by_metadata(self, key: str, value: str) -> int:
        return self._backend.delete_by_metadata(key, value)

    # ── Compatibility (src/database/vector_store.py callers) ─────────────────

    def query(
        self,
        embedding: List[float],
        top_k: int = 5,
        filter: Optional[Dict[str, Any]] = None,  # noqa: A002
    ) -> List[Dict[str, Any]]:
        """Alias for search() returning dicts matching the old Pinecone-style API."""
        results = self._backend.search(embedding, top_k, filter)
        return [{"id": r.id, "score": r.score, "metadata": r.payload} for r in results]

    # ── Persistence ───────────────────────────────────────────────────────────

    def save_collection(self, path: Optional[Path] = None) -> Path:
        """Persist to disk (backends that support it: FAISS, numpy)."""
        dest = path or (_COLLECTIONS_DIR / self._collection)
        dest.mkdir(parents=True, exist_ok=True)
        self._backend.save(dest)
        log.info("VectorStore[%s]: saved to %s", self._collection, dest)
        return dest

    def load_collection(self, path: Optional[Path] = None) -> int:
        """Restore from disk. Returns number of vectors loaded."""
        src = path or (_COLLECTIONS_DIR / self._collection)
        n = self._backend.load(src)
        log.info("VectorStore[%s]: loaded %d vectors from %s", self._collection, n, src)
        return n

    # ── Introspection ─────────────────────────────────────────────────────────

    @property
    def backend_name(self) -> str:
        return type(self._backend).__name__.lstrip("_").replace("Backend", "").lower()

    def collection_info(self) -> Dict[str, Any]:
        return {
            "collection": self._collection,
            "backend": self.backend_name,
            "count": self.count(),
            "dim": self._dim,
        }


# ─── Public factories ─────────────────────────────────────────────────────────


def get_vector_store(collection: str, dim: int = _EMBED_DIM) -> VectorStore:
    """Return a cached VectorStore for the given collection name."""
    key = f"{collection}:{dim}"
    if key not in _backend_cache:
        _backend_cache[key] = VectorStore(collection, dim)
    return _backend_cache[key]


def get_store() -> VectorStore:
    """Convenience alias for the default 'knowledge' collection."""
    return get_vector_store("knowledge")


# ─── Helpers ─────────────────────────────────────────────────────────────────


def _str_to_uuid(s: str) -> str:
    try:
        uuid.UUID(s)
        return s
    except ValueError:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, s))


def _make_id(text: str, idx: int) -> str:
    h = hashlib.sha256(f"{text}:{idx}:{time.time()}".encode()).hexdigest()[:16]
    return h


# ─── Public API ───────────────────────────────────────────────────────────────

__all__ = [
    "Document",
    "SearchResult",
    "VectorStore",
    "embed_text",
    "embed_texts",
    "embedding_stats",
    "get_store",
    "get_vector_store",
]
