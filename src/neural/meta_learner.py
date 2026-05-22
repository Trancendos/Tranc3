# src/neural/meta_learner.py
"""
Meta-Learning & Few-Shot Adaptation for Tranc3 Nanoservices.

Provides a lightweight meta-learning framework that enables nanoservices
to rapidly adapt to new tasks with minimal examples.  Unlike
self_improving_core.py (which uses genetic/evolutionary optimization),
MetaLearner uses gradient-free task-prototype matching and rapid
parameter adaptation inspired by MAML (Model-Agnostic Meta-Learning)
but without requiring PyTorch autograd.

Key concepts
------------
- **TaskPrototype**: A reusable task template capturing input/output
  patterns and the parameter adjustments that worked well.
- **MetaLearner**: A task library that matches new tasks to existing
  prototypes and adapts parameters accordingly.
- **Experience replay**: Successful adaptations are stored as
  prototypes for future few-shot learning.

Zero-cost guarantees
--------------------
- No external APIs; all computation is local.
- No PyTorch autograd required; uses lightweight numerical optimization.
- Gracefully degrades when numpy is unavailable.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Optional numpy for vector operations
try:
    import numpy as np
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False
    np = None  # type: ignore[assignment]


# ── Data structures ────────────────────────────────────────────────

@dataclass
class TaskPrototype:
    """A reusable task template for few-shot learning.

    A prototype captures the signature of a task type (input shape,
    output shape, domain tags) along with the parameter adjustments
    that previously succeeded for similar tasks.

    Attributes
    ----------
    prototype_id : str
        Unique identifier.
    domain : str
        Broad domain (e.g., "nlp", "vision", "reasoning").
    task_type : str
        Specific task type (e.g., "summarization", "classification").
    input_signature : Dict[str, Any]
        Expected input shape/schema.
    output_signature : Dict[str, Any]
        Expected output shape/schema.
    parameter_deltas : Dict[str, float]
        Parameter adjustments that worked for this task type.
    success_count : int
        Number of times this prototype led to a successful adaptation.
    failure_count : int
        Number of times this prototype failed.
    created_at : float
        Creation timestamp.
    last_used : float
        Last usage timestamp.
    tags : List[str]
        Additional categorization tags.
    embedding : Optional[List[float]]
        Optional vector embedding for similarity matching.
    """
    prototype_id: str = ""
    domain: str = ""
    task_type: str = ""
    input_signature: Dict[str, Any] = field(default_factory=dict)
    output_signature: Dict[str, Any] = field(default_factory=dict)
    parameter_deltas: Dict[str, float] = field(default_factory=dict)
    success_count: int = 0
    failure_count: int = 0
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)
    tags: List[str] = field(default_factory=list)
    embedding: Optional[List[float]] = None

    def __post_init__(self) -> None:
        if not self.prototype_id:
            content = f"{self.domain}:{self.task_type}:{self.tags}"
            self.prototype_id = hashlib.sha256(content.encode()).hexdigest()[:12]

    @property
    def success_rate(self) -> float:
        """Fraction of uses that succeeded."""
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.0

    @property
    def confidence(self) -> float:
        """Confidence score combining success rate and usage count.

        Uses a Bayesian-inspired prior: a prototype with few uses
        has lower confidence than one with many successful uses.
        """
        prior_strength = 5.0  # Virtual prior observations
        prior_success = 0.5   # Prior success rate
        total = self.success_count + self.failure_count + prior_strength
        successes = self.success_count + prior_strength * prior_success
        return successes / total


@dataclass
class AdaptationResult:
    """Result of a meta-learning adaptation attempt."""
    prototype_id: str
    adapted_parameters: Dict[str, float]
    confidence: float
    adaptation_time: float
    matched_score: float


# ── Similarity functions ───────────────────────────────────────────

def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    if _HAS_NUMPY:
        va = np.array(a, dtype=np.float64)
        vb = np.array(b, dtype=np.float64)
        dot = float(np.dot(va, vb))
        norm_a = float(np.linalg.norm(va))
        norm_b = float(np.linalg.norm(vb))
    else:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _signature_similarity(
    sig_a: Dict[str, Any],
    sig_b: Dict[str, Any],
) -> float:
    """Compute structural similarity between two signatures.

    Returns a value in [0, 1] based on key overlap and value equality.
    """
    if not sig_a or not sig_b:
        return 0.0
    keys_a = set(sig_a.keys())
    keys_b = set(sig_b.keys())
    overlap = keys_a & keys_b
    if not overlap:
        return 0.0
    key_score = len(overlap) / len(keys_a | keys_b)
    value_matches = sum(1 for k in overlap if sig_a[k] == sig_b[k])
    value_score = value_matches / len(overlap) if overlap else 0.0
    return 0.4 * key_score + 0.6 * value_score


# ── Meta Learner ───────────────────────────────────────────────────

class MetaLearner:
    """Few-shot task adaptation through prototype matching.

    The MetaLearner maintains a library of TaskPrototypes and, when
    presented with a new task, finds the most similar prototype and
    adapts its parameters for the new context.

    Parameters
    ----------
    max_prototypes : int
        Maximum number of prototypes to retain.
    similarity_threshold : float
        Minimum similarity score for a prototype match.
    adaptation_rate : float
        Learning rate for parameter adaptation.
    exploration_rate : float
        Probability of trying a random prototype (exploration vs exploitation).
    """

    def __init__(
        self,
        max_prototypes: int = 500,
        similarity_threshold: float = 0.3,
        adaptation_rate: float = 0.1,
        exploration_rate: float = 0.1,
    ) -> None:
        self._prototypes: Dict[str, TaskPrototype] = {}
        self._max_prototypes = max_prototypes
        self._similarity_threshold = similarity_threshold
        self._adaptation_rate = adaptation_rate
        self._exploration_rate = exploration_rate
        self._lock = asyncio.Lock()
        self._adaptation_history: List[AdaptationResult] = []

    # ── Prototype management ───────────────────────────────────────

    async def register_prototype(self, prototype: TaskPrototype) -> str:
        """Register a new task prototype.

        Returns the prototype ID.
        """
        async with self._lock:
            # Evict lowest-confidence prototypes if at capacity
            while len(self._prototypes) >= self._max_prototypes:
                worst_id = min(
                    self._prototypes,
                    key=lambda pid: self._prototypes[pid].confidence,
                )
                del self._prototypes[worst_id]

            self._prototypes[prototype.prototype_id] = prototype
            logger.info(
                "meta_learner: registered prototype %s domain=%s type=%s",
                prototype.prototype_id, prototype.domain, prototype.task_type,
            )
        return prototype.prototype_id

    async def record_outcome(
        self,
        prototype_id: str,
        success: bool,
        parameter_feedback: Optional[Dict[str, float]] = None,
    ) -> None:
        """Record the outcome of using a prototype.

        If the adaptation succeeded, the prototype's success count is
        incremented and its parameter deltas may be reinforced.  If it
        failed, the failure count is incremented and the deltas may be
        adjusted using the provided feedback.

        Parameters
        ----------
        prototype_id : str
            The prototype that was used.
        success : bool
            Whether the adaptation succeeded.
        parameter_feedback : dict, optional
            If provided, used to adjust parameter deltas.
        """
        async with self._lock:
            proto = self._prototypes.get(prototype_id)
            if proto is None:
                logger.warning("meta_learner: unknown prototype %s", prototype_id)
                return
            if success:
                proto.success_count += 1
                if parameter_feedback:
                    for key, value in parameter_feedback.items():
                        old = proto.parameter_deltas.get(key, 0.0)
                        # Exponential moving average toward successful values
                        proto.parameter_deltas[key] = (
                            (1 - self._adaptation_rate) * old
                            + self._adaptation_rate * value
                        )
            else:
                proto.failure_count += 1
                if parameter_feedback:
                    for key, value in parameter_feedback.items():
                        old = proto.parameter_deltas.get(key, 0.0)
                        # Move away from failing values
                        proto.parameter_deltas[key] = (
                            (1 - self._adaptation_rate) * old
                            - self._adaptation_rate * value
                        )
            proto.last_used = time.monotonic()

    # ── Adaptation ─────────────────────────────────────────────────

    async def adapt(
        self,
        domain: str = "",
        task_type: str = "",
        input_signature: Optional[Dict[str, Any]] = None,
        output_signature: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None,
        embedding: Optional[List[float]] = None,
        current_parameters: Optional[Dict[str, float]] = None,
    ) -> AdaptationResult:
        """Find the best-matching prototype and adapt parameters.

        Uses a weighted combination of:
        1. Domain/task_type exact match
        2. Tag overlap (Jaccard similarity)
        3. Signature similarity
        4. Embedding cosine similarity (if available)

        Returns an AdaptationResult with the adjusted parameters.
        """
        start_time = time.monotonic()

        async with self._lock:
            if not self._prototypes:
                return AdaptationResult(
                    prototype_id="",
                    adapted_parameters=current_parameters or {},
                    confidence=0.0,
                    adaptation_time=time.monotonic() - start_time,
                    matched_score=0.0,
                )

            # Compute similarity scores for all prototypes
            scores: List[Tuple[str, float]] = []
            for pid, proto in self._prototypes.items():
                score = self._compute_match_score(
                    proto, domain, task_type, input_signature,
                    output_signature, tags, embedding,
                )
                scores.append((pid, score))

            # Sort by score descending
            scores.sort(key=lambda x: -x[1])

            # Exploration: occasionally pick a random top-5 prototype
            import random
            if random.random() < self._exploration_rate and len(scores) > 1:  # nosec B311 — non-cryptographic random usage

                top_n = min(5, len(scores))
                choice_idx = random.randint(0, top_n - 1)  # nosec B311 — non-cryptographic exploration sampling
                best_pid, best_score = scores[choice_idx]
            else:
                best_pid, best_score = scores[0]

            # No good match found
            if best_score < self._similarity_threshold:
                return AdaptationResult(
                    prototype_id="",
                    adapted_parameters=current_parameters or {},
                    confidence=0.0,
                    adaptation_time=time.monotonic() - start_time,
                    matched_score=best_score,
                )

            # Apply parameter deltas from best prototype
            proto = self._prototypes[best_pid]
            adapted = dict(current_parameters or {})
            for key, delta in proto.parameter_deltas.items():
                base = adapted.get(key, 0.0)
                adapted[key] = base + delta * proto.confidence

        result = AdaptationResult(
            prototype_id=best_pid,
            adapted_parameters=adapted,
            confidence=proto.confidence,
            adaptation_time=time.monotonic() - start_time,
            matched_score=best_score,
        )
        self._adaptation_history.append(result)
        return result

    def _compute_match_score(
        self,
        proto: TaskPrototype,
        domain: str,
        task_type: str,
        input_signature: Optional[Dict[str, Any]],
        output_signature: Optional[Dict[str, Any]],
        tags: Optional[List[str]],
        embedding: Optional[List[float]],
    ) -> float:
        """Compute a composite match score between a prototype and a query."""
        score = 0.0

        # Domain match (weight: 0.25)
        if domain and proto.domain == domain:
            score += 0.25

        # Task type match (weight: 0.25)
        if task_type and proto.task_type == task_type:
            score += 0.25

        # Tag overlap (Jaccard, weight: 0.15)
        if tags and proto.tags:
            query_tags = set(tags)
            proto_tags = set(proto.tags)
            jaccard = len(query_tags & proto_tags) / len(query_tags | proto_tags)
            score += 0.15 * jaccard

        # Signature similarity (weight: 0.15)
        if input_signature and proto.input_signature:
            score += 0.15 * _signature_similarity(input_signature, proto.input_signature)
        if output_signature and proto.output_signature:
            score += 0.05 * _signature_similarity(output_signature, proto.output_signature)

        # Embedding similarity (weight: 0.15)
        if embedding and proto.embedding:
            score += 0.15 * _cosine_similarity(embedding, proto.embedding)

        return score

    # ── Batch operations ───────────────────────────────────────────

    async def batch_adapt(
        self,
        tasks: List[Dict[str, Any]],
    ) -> List[AdaptationResult]:
        """Adapt parameters for multiple tasks in sequence."""
        results = []
        for task in tasks:
            result = await self.adapt(**task)
            results.append(result)
        return results

    # ── Introspection ──────────────────────────────────────────────

    def list_prototypes(
        self,
        domain: Optional[str] = None,
        min_confidence: float = 0.0,
    ) -> List[TaskPrototype]:
        """List prototypes, optionally filtered by domain and confidence."""
        protos = list(self._prototypes.values())
        if domain:
            protos = [p for p in protos if p.domain == domain]
        if min_confidence > 0:
            protos = [p for p in protos if p.confidence >= min_confidence]
        return sorted(protos, key=lambda p: -p.confidence)

    def stats(self) -> Dict[str, Any]:
        """Return statistics about the meta-learner."""
        domains = defaultdict(int)
        for p in self._prototypes.values():
            domains[p.domain] += 1
        return {
            "total_prototypes": len(self._prototypes),
            "total_adaptations": len(self._adaptation_history),
            "domains": dict(domains),
            "max_prototypes": self._max_prototypes,
        }

    def adaptation_history(self, limit: int = 50) -> List[AdaptationResult]:
        """Return recent adaptation results."""
        return self._adaptation_history[-limit:]
