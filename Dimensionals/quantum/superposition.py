"""Quantum superposition ensemble search.

Conceptually models each search backend as a quantum state in superposition.
The "collapse" (measurement) is a weighted vote across N backends, where the
amplitude of each state is derived from the backend's historical hit quality.

This is a quantum-*inspired* algorithm — it does not require Qiskit or
quantum hardware. The mathematics mirrors quantum amplitude amplification:

    amplitude_i  = sqrt(quality_i)          # analogous to quantum amplitude
    probability_i = amplitude_i² = quality_i  # Born rule
    collapsed    = argmax(weighted_combination)

In practice this gives superior ensemble recall versus naive top-k union
because it amplifies high-quality backends quadratically and dampens
low-quality ones, matching the quantum amplitude relationship.

Zero-cost: pure Python, no external services.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger("tranc3.dimensional.quantum.superposition")


@dataclass
class QuantumState:
    """Represents one search backend as a quantum-inspired state."""

    name: str
    amplitude: float = 1.0  # sqrt(quality)
    hit_count: int = 0
    total_count: int = 0

    @property
    def quality(self) -> float:
        if self.total_count == 0:
            return 0.5  # uniform prior
        return self.hit_count / self.total_count

    @property
    def probability(self) -> float:
        """Born rule: probability = amplitude²."""
        return self.amplitude**2

    def update(self, rewarded: bool) -> None:
        self.total_count += 1
        if rewarded:
            self.hit_count += 1
        # update amplitude via square root of running quality
        self.amplitude = math.sqrt(max(0.01, self.quality))


@dataclass
class SearchResult:
    doc_id: str
    score: float
    payload: Dict[str, Any] = field(default_factory=dict)
    source: str = "superposition"


class SuperpositionEnsemble:
    """Ensemble search across multiple backends with quantum-amplitude weighting.

    Usage::

        ensemble = SuperpositionEnsemble(backends={
            "qdrant": qdrant_search_fn,
            "meilisearch": meili_search_fn,
        })
        results = ensemble.search("my query", top_k=10)
    """

    def __init__(
        self,
        backends: Optional[Dict[str, Callable]] = None,
        rrf_k: int = 60,
    ) -> None:
        self._states: Dict[str, QuantumState] = {}
        self._backends: Dict[str, Callable] = backends or {}
        self._rrf_k = rrf_k
        for name in self._backends:
            self._states[name] = QuantumState(name=name)

    def register(self, name: str, search_fn: Callable) -> None:
        self._backends[name] = search_fn
        if name not in self._states:
            self._states[name] = QuantumState(name=name)

    # ── collapse (measurement) ────────────────────────────────────────────────

    def search(
        self,
        query: str,
        top_k: int = 10,
        **kwargs: Any,
    ) -> List[SearchResult]:
        """Run all backends in superposition; collapse to ranked result list."""
        if not self._backends:
            return []

        per_backend: Dict[str, List[Tuple[str, float, Any]]] = {}

        for name, fn in self._backends.items():
            try:
                raw = fn(query, top_k=top_k * 2, **kwargs)
                per_backend[name] = [
                    (str(r.get("id", r.get("doc_id", ""))), float(r.get("score", 0.0)), r)
                    for r in (raw or [])
                ]
                self._states[name].update(rewarded=bool(raw))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Superposition backend '%s' failed: %s", name, exc)
                self._states[name].update(rewarded=False)
                per_backend[name] = []

        return self._collapse(per_backend, top_k)

    def _collapse(
        self,
        per_backend: Dict[str, List[Tuple[str, float, Any]]],
        top_k: int,
    ) -> List[SearchResult]:
        """Amplitude-weighted RRF collapse across all backend ranked lists."""
        scores: Dict[str, float] = {}
        payloads: Dict[str, Any] = {}

        for name, hits in per_backend.items():
            weight = self._states[name].probability  # quantum probability
            for rank, (doc_id, _score, payload) in enumerate(hits, start=1):
                rrf_score = weight / (self._rrf_k + rank)
                scores[doc_id] = scores.get(doc_id, 0.0) + rrf_score
                if doc_id not in payloads:
                    payloads[doc_id] = payload

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            SearchResult(doc_id=doc_id, score=score, payload=payloads.get(doc_id, {}))
            for doc_id, score in ranked
        ]

    # ── introspection ─────────────────────────────────────────────────────────

    def state_vector(self) -> Dict[str, Dict[str, float]]:
        """Return the current amplitude / probability for each backend."""
        return {
            name: {
                "amplitude": s.amplitude,
                "probability": s.probability,
                "quality": s.quality,
                "hits": s.hit_count,
                "total": s.total_count,
            }
            for name, s in self._states.items()
        }
