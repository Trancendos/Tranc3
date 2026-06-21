"""Cross-encoder re-ranking for precision after first-pass retrieval.

Uses sentence-transformers cross-encoder models (local, free, no API).
Falls back gracefully to the original hybrid score if unavailable.

Zero-cost: models run locally via sentence-transformers / transformers.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from src.search.hybrid import SearchHit

logger = logging.getLogger("tranc3.search.reranker")

_DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"


class CrossEncoderReranker:
    """Re-rank a list of SearchHits using a cross-encoder model.

    Falls back to passthrough (original order preserved) if the model
    cannot be loaded — ensuring zero hard dependencies.
    """

    def __init__(self, model_name: str = _DEFAULT_MODEL) -> None:
        self.model_name = model_name
        self._model = None
        self._available: Optional[bool] = None

    def _load(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from sentence_transformers import CrossEncoder  # type: ignore

            self._model = CrossEncoder(self.model_name)
            self._available = True
            logger.info("CrossEncoder loaded: %s", self.model_name)
        except Exception as exc:  # noqa: BLE001
            logger.warning("CrossEncoder unavailable (%s) — passthrough mode", exc)
            self._available = False
        return bool(self._available)

    def rerank(
        self,
        query: str,
        hits: List[SearchHit],
        top_k: Optional[int] = None,
    ) -> List[SearchHit]:
        """Re-score *hits* using the cross-encoder; return sorted by new score."""
        if not hits:
            return hits

        if not self._load() or self._model is None:
            return hits[:top_k] if top_k else hits

        try:
            texts = [hit.payload.get("content") or hit.payload.get("text") or "" for hit in hits]
            pairs = [(query, t) for t in texts]
            scores = self._model.predict(pairs)
            for hit, score in zip(hits, scores, strict=False):
                hit.score = float(score)
            hits.sort(key=lambda h: h.score, reverse=True)
            if top_k:
                hits = hits[:top_k]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Reranking failed: %s — returning original order", exc)

        return hits
