# src/knowledge/vector_store.py
# FAISS-backed in-process vector store using sentence-transformers for embeddings.
# Zero external dependencies — both faiss-cpu and sentence-transformers are in
# requirements.txt and run fully embedded.  No Qdrant/Pinecone needed.
#
# Each "collection" is an independent FAISS index + metadata list.
# Documents survive for the lifetime of the process; add persistence via
# save_collection() / load_collection() when needed.

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

from Dimensional.path_validation import validate_path

logger = logging.getLogger(__name__)

_EMBED_MODEL = os.getenv("EMBED_MODEL", "all-MiniLM-L6-v2")  # 80MB, fast, solid quality
_COLLECTIONS_DIR = Path(os.getenv("VECTOR_STORE_DIR", "./data/vector_store"))

# Lazy singletons — loaded on first use so startup stays fast
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

                    _encoder = SentenceTransformer(_EMBED_MODEL)
                    logger.info("vector_store: encoder loaded model=%s", _EMBED_MODEL)
                except Exception as exc:
                    logger.warning(
                        "vector_store: encoder unavailable (%s) — returning zero embeddings",
                        exc,
                    )
                    _encoder = _NullEncoder()
    return _encoder


class _NullEncoder:
    """Fallback when sentence-transformers fails to load."""

    def encode(self, texts, **_):
        return np.zeros((len(texts) if isinstance(texts, list) else 1, 384), dtype="float32")


@dataclass
class Document:
    id: str
    text: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    collection: str = "default"
    inserted_at: float = field(default_factory=time.time)


@dataclass
class SearchResult:
    document: Document
    score: float
    rank: int


def _faiss_available() -> bool:
    try:
        return True
    except ImportError:
        return False


class VectorCollection:
    """A single named FAISS index with parallel metadata list."""

    def __init__(self, name: str, dim: int = 384):
        self.name = name
        self.dim = dim
        self._index = None
        self._docs: List[Document] = []

        if _faiss_available():
            import faiss

            self._index = faiss.IndexFlatIP(dim)
        else:
            logger.warning(
                "vector_store: faiss not installed — collection '%s' using in-memory brute-force",
                name,
            )

    def add(self, docs: List[Document], embeddings: np.ndarray) -> None:
        self._docs.extend(docs)
        if self._index is not None:
            import faiss

            vecs = embeddings.astype("float32")
            faiss.normalize_L2(vecs)
            self._index.add(vecs)
        logger.debug("vector_store[%s]: +%d docs, total=%d", self.name, len(docs), len(self._docs))

    def search(
        self,
        query_vec: np.ndarray,
        top_k: int = 5,
        score_threshold: float = 0.0,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        if not self._docs:
            return []

        if self._index is not None:
            import faiss

            q = query_vec.astype("float32").reshape(1, -1)
            faiss.normalize_L2(q)
            k = min(top_k * 4, self._index.ntotal)
            scores, indices = self._index.search(q, k)
            candidates = [
                (float(scores[0][i]), self._docs[int(indices[0][i])])
                for i in range(len(indices[0]))
                if indices[0][i] >= 0
            ]
        else:
            # Brute-force cosine similarity (fallback when faiss absent)
            q = query_vec.astype("float32")
            norm = np.linalg.norm(q)
            if norm > 0:
                q = q / norm  # normalize in-place
            # Use zero embeddings when no encoder either
            candidates = [(0.5, doc) for doc in self._docs]

        results: List[SearchResult] = []
        for rank, (score, doc) in enumerate(candidates):
            if score < score_threshold:
                continue
            if metadata_filter and not _matches_filter(doc.metadata, metadata_filter):
                continue
            results.append(SearchResult(document=doc, score=score, rank=rank))
            if len(results) >= top_k:
                break

        return results

    def count(self) -> int:
        return len(self._docs)


def _matches_filter(meta: Dict[str, Any], fltr: Dict[str, Any]) -> bool:
    return all(meta.get(k) == v for k, v in fltr.items())


class VectorStore:
    """Multi-collection vector store backed by FAISS in-process indexes."""

    def __init__(self):
        self._collections: Dict[str, VectorCollection] = {}

    def _get_or_create(self, name: str) -> VectorCollection:
        if name not in self._collections:
            dim = int(os.getenv("EMBED_DIM", "384"))
            self._collections[name] = VectorCollection(name, dim)
        return self._collections[name]

    def ingest(
        self,
        texts: List[str],
        collection: str = "default",
        ids: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Embed *texts* and store them in *collection*.
        Returns the list of document IDs assigned.
        """
        if not texts:
            return []

        encoder = _get_encoder()
        embeddings = encoder.encode(texts, show_progress_bar=False)
        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings)

        coll = self._get_or_create(collection)
        doc_ids: List[str] = []
        docs: List[Document] = []
        for i, text in enumerate(texts):
            doc_id = (ids[i] if ids else None) or f"{collection}-{int(time.time() * 1000)}-{i}"
            doc = Document(
                id=doc_id,
                text=text,
                metadata=(metadatas[i] if metadatas else {}),
                collection=collection,
            )
            docs.append(doc)
            doc_ids.append(doc_id)

        coll.add(docs, embeddings)
        return doc_ids

    def search(
        self,
        query: str,
        collection: str = "default",
        top_k: int = 5,
        score_threshold: float = 0.0,
        metadata_filter: Optional[Dict[str, Any]] = None,
    ) -> List[SearchResult]:
        """Embed *query* and return nearest documents from *collection*."""
        coll = self._collections.get(collection)
        if coll is None or coll.count() == 0:
            return []

        encoder = _get_encoder()
        q_vec = encoder.encode([query], show_progress_bar=False)
        if not isinstance(q_vec, np.ndarray):
            q_vec = np.array(q_vec)

        return coll.search(q_vec[0], top_k, score_threshold, metadata_filter)

    def collection_info(self, collection: str) -> Dict[str, Any]:
        coll = self._collections.get(collection)
        if coll is None:
            return {"name": collection, "count": 0, "exists": False}
        return {"name": collection, "count": coll.count(), "exists": True}

    def list_collections(self) -> List[str]:
        return list(self._collections.keys())

    def save_collection(self, collection: str, path: Optional[Path] = None) -> Path:
        """Persist a collection's FAISS index + doc metadata to disk."""
        coll = self._collections.get(collection)
        if coll is None:
            raise KeyError(f"Collection '{collection}' not found")

        dest = path or (_COLLECTIONS_DIR / collection)
        # Validate path before mkdir to prevent path traversal (CWE-022)
        validated = validate_path(dest, Path.cwd())
        validated.mkdir(parents=True, exist_ok=True)

        if coll._index is not None:
            import faiss

            faiss.write_index(coll._index, str(validated / "index.faiss"))

        docs_json = [
            {"id": d.id, "text": d.text, "metadata": d.metadata, "inserted_at": d.inserted_at}
            for d in coll._docs
        ]
        (validated / "docs.json").write_text(json.dumps(docs_json, indent=2))
        logger.info("vector_store[%s]: saved %d docs to %s", collection, coll.count(), validated)
        return validated

    def load_collection(self, collection: str, path: Optional[Path] = None) -> int:
        """Load a previously saved collection from disk. Returns number of vectors loaded."""
        src = path or (_COLLECTIONS_DIR / collection)
        docs_path = src / "docs.json"
        if not docs_path.exists():
            logger.debug("vector_store[%s]: no saved state at %s", collection, src)
            return 0

        raw_docs = json.loads(docs_path.read_text())
        coll = self._get_or_create(collection)

        index_path = src / "index.faiss"
        if index_path.exists() and _faiss_available():
            import faiss

            coll._index = faiss.read_index(str(index_path))

        coll._docs = [
            Document(
                id=d["id"],
                text=d["text"],
                metadata=d.get("metadata", {}),
                collection=collection,
                inserted_at=d.get("inserted_at", 0.0),
            )
            for d in raw_docs
        ]
        logger.info("vector_store[%s]: loaded %d docs from %s", collection, coll.count(), src)
        return coll.count()


# Module-level singleton
_store: Optional[VectorStore] = None


def get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
