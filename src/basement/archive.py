# src/basement/archive.py
# The Basement — archived intelligence layer for Trancendos.
#
# Responsibilities:
#   - Archive overflow events from The Observatory (events beyond ring buffer)
#   - Provide semantic vector search over archived content (FAISS)
#   - Supply The Spark's RAG pipeline with embedded knowledge chunks
#   - House retired Library articles moved from active KB
#
# The Basement receives all SECURITY and CRITICAL events from The Observatory
# regardless of TTL — these are never dropped.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ArchiveSource(str, Enum):
    OBSERVATORY = "observatory"  # Overflow audit events
    LIBRARY = "library"  # Retired KB articles
    WORKFLOW = "workflow"  # Completed workflow runs
    INFERENCE = "inference"  # AI conversation logs
    SECURITY = "security"  # Always-retained security events


@dataclass
class ArchiveRecord:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    source: ArchiveSource = ArchiveSource.OBSERVATORY
    event_type: str = ""
    content: str = ""  # Serialised/text representation
    metadata: Dict[str, Any] = field(default_factory=dict)
    embedding: Optional[List[float]] = field(default=None, repr=False)
    retained: bool = False  # True = never auto-purge (security events)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp,
            "source": self.source.value,
            "event_type": self.event_type,
            "content_preview": self.content[:200],
            "metadata": self.metadata,
            "retained": self.retained,
        }


class Basement:
    """
    The Basement — persistent archive and semantic search layer.

    Stores records that have aged out of The Observatory's ring buffer,
    plus any content flagged for long-term retention.

    Vector search is powered by FAISS when available, with a brute-force
    fallback that uses token overlap scoring.
    """

    MAX_RECORDS = 100_000

    def __init__(self):
        self._records: Dict[str, ArchiveRecord] = {}
        self._source_index: Dict[str, List[str]] = {}  # source → [record_id]
        self._faiss_index = None
        self._faiss_ids: List[str] = []
        self._embedder = None
        self._try_init_faiss()

    # ── Ingest ────────────────────────────────────────────────────────────────

    def ingest(
        self,
        content: str,
        source: ArchiveSource = ArchiveSource.OBSERVATORY,
        event_type: str = "",
        metadata: Optional[Dict[str, Any]] = None,
        retained: bool = False,
    ) -> ArchiveRecord:
        record = ArchiveRecord(
            source=source,
            event_type=event_type,
            content=content,
            metadata=metadata or {},
            retained=retained,
        )

        # Auto-retain security events
        if source == ArchiveSource.SECURITY or "security" in event_type:
            record.retained = True

        # Embed for vector search
        if self._embedder is not None:
            try:
                vec = self._embedder.encode([content], normalize_embeddings=True)[0]
                record.embedding = vec.tolist()
                self._add_to_faiss(record.id, vec)
            except Exception as exc:
                logger.debug("basement: embedding failed: %s", exc)

        self._records[record.id] = record
        self._source_index.setdefault(source.value, []).append(record.id)

        # Evict oldest non-retained records if over limit
        if len(self._records) > self.MAX_RECORDS:
            self._evict()

        return record

    def ingest_observatory_event(self, event: Any) -> ArchiveRecord:
        """Accept an AuditEvent from The Observatory."""
        content = f"{event.event_type} | actor={event.actor} | target={event.target} | outcome={event.outcome}"
        retained = getattr(event, "severity", None) in ("critical", "security")
        return self.ingest(
            content=content,
            source=ArchiveSource.SECURITY if retained else ArchiveSource.OBSERVATORY,
            event_type=getattr(event, "event_type", ""),
            metadata={
                "actor": event.actor,
                "target": event.target,
                "service": event.service,
            },
            retained=retained,
        )

    # ── Search ────────────────────────────────────────────────────────────────

    def search(self, query: str, top_k: int = 10) -> List[Tuple[ArchiveRecord, float]]:
        """
        Semantic search over archived records.
        Returns [(record, score)] sorted by descending score.
        """
        if self._embedder is not None and self._faiss_index is not None:
            return self._faiss_search(query, top_k)
        return self._keyword_search(query, top_k)

    def by_source(self, source: ArchiveSource, limit: int = 100) -> List[ArchiveRecord]:
        ids = self._source_index.get(source.value, [])
        return [self._records[i] for i in ids[-limit:] if i in self._records]

    def recent(
        self, limit: int = 50, source: Optional[ArchiveSource] = None
    ) -> List[ArchiveRecord]:
        records = list(self._records.values())
        if source:
            records = [r for r in records if r.source == source]
        return sorted(records, key=lambda r: r.timestamp, reverse=True)[:limit]

    def get(self, record_id: str) -> Optional[ArchiveRecord]:
        return self._records.get(record_id)

    def stats(self) -> Dict[str, Any]:
        total = len(self._records)
        retained = sum(1 for r in self._records.values() if r.retained)
        by_source: Dict[str, int] = {}
        for r in self._records.values():
            by_source[r.source.value] = by_source.get(r.source.value, 0) + 1
        return {
            "total_records": total,
            "retained_records": retained,
            "by_source": by_source,
            "faiss_indexed": len(self._faiss_ids),
            "vector_search": self._embedder is not None,
        }

    # ── FAISS internals ───────────────────────────────────────────────────────

    def _try_init_faiss(self) -> None:
        try:
            import faiss  # type: ignore
            from sentence_transformers import SentenceTransformer  # type: ignore

            model_name = "all-MiniLM-L6-v2"
            self._embedder = SentenceTransformer(model_name)
            dim = self._embedder.get_sentence_embedding_dimension()
            self._faiss_index = faiss.IndexFlatIP(dim)
            logger.info("basement: FAISS vector search active (dim=%d)", dim)
        except ImportError:
            logger.debug(
                "basement: faiss/sentence-transformers not installed — keyword search only"
            )
        except Exception as exc:
            logger.warning("basement: FAISS init failed: %s", exc)

    def _add_to_faiss(self, record_id: str, vec) -> None:
        try:
            import numpy as np

            self._faiss_index.add(np.array([vec], dtype="float32"))
            self._faiss_ids.append(record_id)
        except Exception as exc:
            logger.debug("basement: faiss add failed: %s", exc)

    def _faiss_search(
        self, query: str, top_k: int
    ) -> List[Tuple[ArchiveRecord, float]]:
        try:
            vec = self._embedder.encode([query], normalize_embeddings=True)
            scores, indices = self._faiss_index.search(
                vec.astype("float32"), min(top_k, len(self._faiss_ids))
            )
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._faiss_ids):
                    continue
                rid = self._faiss_ids[idx]
                if rid in self._records:
                    results.append((self._records[rid], float(score)))
            return results
        except Exception as exc:
            logger.debug("basement: faiss search failed: %s", exc)
            return self._keyword_search(query, top_k)

    def _keyword_search(
        self, query: str, top_k: int
    ) -> List[Tuple[ArchiveRecord, float]]:
        terms = set(query.lower().split())
        scored = []
        for record in self._records.values():
            text = (record.content + " " + record.event_type).lower()
            hits = sum(1 for t in terms if t in text)
            if hits:
                scored.append((record, hits / len(terms)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def _evict(self) -> None:
        evictable = sorted(
            [r for r in self._records.values() if not r.retained],
            key=lambda r: r.timestamp,
        )
        to_remove = len(self._records) - int(self.MAX_RECORDS * 0.9)
        for r in evictable[:to_remove]:
            del self._records[r.id]
            src_ids = self._source_index.get(r.source.value, [])
            if r.id in src_ids:
                src_ids.remove(r.id)


# ── Module-level singleton ────────────────────────────────────────────────────
_basement: Optional[Basement] = None


def get_basement() -> Basement:
    global _basement
    if _basement is None:
        _basement = Basement()
    return _basement
