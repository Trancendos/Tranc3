# src/neural/attention_router.py
"""
Attention-Based Resource Allocation Router for Tranc3.

Implements a transformer-style attention mechanism for routing requests
to the most appropriate nanoservice.  Unlike fluid_router.py (which uses
weighted random selection based on health/performance metrics), the
AttentionRouter computes softmax attention scores over service
descriptions, enabling context-aware, multi-factor routing decisions.

Key concepts
------------
- **ServiceAttention**: A service's attention profile (description
  embedding, capability tags, load vector).
- **AttentionRouter**: Computes attention-weighted service selection
  based on query context, capability requirements, and current load.

The attention mechanism works as follows:
1. Encode the incoming request as a query vector.
2. Encode each available service as a key vector.
3. Compute scaled dot-product attention: softmax(Q·K^T / sqrt(d_k)).
4. Route the request to the service with the highest attention weight.

Zero-cost guarantees
--------------------
- No external APIs; embeddings are computed locally from tags and
  feature vectors (no paid embedding APIs).
- Gracefully degrades when numpy is unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# Optional numpy for vector operations
try:
    import numpy as np  # codeql[py/unused-import] – conditional import, used when available
except ImportError:
    np = None  # type: ignore[assignment]


# ── Data structures ────────────────────────────────────────────────

@dataclass
class ServiceAttention:
    """Attention profile for a nanoservice.

    Attributes
    ----------
    service_id : str
        Unique service identifier.
    capability_tags : Set[str]
        Tags describing what this service can handle (e.g., "nlp", "math").
    feature_vector : List[float]
        Dense feature vector representing the service's capabilities.
    max_capacity : int
        Maximum concurrent requests this service can handle.
    current_load : int
        Current number of active requests.
    latency_ema : float
        Exponential moving average of response latency (seconds).
    error_rate : float
        Recent error rate (0-1).
    priority : float
        Static priority multiplier (higher = preferred when scores are equal).
    metadata : Dict[str, Any]
        Additional metadata.
    """
    service_id: str
    capability_tags: Set[str] = field(default_factory=set)
    feature_vector: List[float] = field(default_factory=list)
    max_capacity: int = 100
    current_load: int = 0
    latency_ema: float = 0.1
    error_rate: float = 0.0
    priority: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def load_fraction(self) -> float:
        """Current load as a fraction of max capacity."""
        if self.max_capacity <= 0:
            return 1.0
        return self.current_load / self.max_capacity

    @property
    def availability_score(self) -> float:
        """0-1 score combining load, latency, and error rate."""
        load_score = 1.0 - self.load_fraction
        latency_score = 1.0 / (1.0 + self.latency_ema)
        error_score = 1.0 - self.error_rate
        return 0.4 * load_score + 0.3 * latency_score + 0.3 * error_score

    def update_latency(self, latency: float, alpha: float = 0.1) -> None:
        """Update the exponential moving average of latency."""
        self.latency_ema = alpha * latency + (1 - alpha) * self.latency_ema

    def update_error_rate(self, is_error: bool, alpha: float = 0.05) -> None:
        """Update the error rate EMA."""
        self.error_rate = alpha * float(is_error) + (1 - alpha) * self.error_rate


@dataclass
class RoutingRequest:
    """A request to be routed through the attention mechanism.

    Attributes
    ----------
    request_id : str
        Unique request identifier.
    required_tags : Set[str]
        Tags that the target service must support.
    context_vector : List[float]
        Dense vector representing the request context.
    priority : float
        Request priority (higher = more important).
    max_latency : float
        Maximum acceptable latency in seconds.
    metadata : Dict[str, Any]
        Additional request metadata.
    """
    request_id: str
    required_tags: Set[str] = field(default_factory=set)
    context_vector: List[float] = field(default_factory=list)
    priority: float = 1.0
    max_latency: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RoutingDecision:
    """Result of an attention-based routing decision."""
    request_id: str
    selected_service: str
    attention_weights: Dict[str, float]
    confidence: float
    decision_time: float


# ── Vector operations (numpy-free fallback) ────────────────────────

def _dot_product(a: List[float], b: List[float]) -> float:
    """Compute dot product of two vectors."""
    if len(a) != len(b):
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False))


def _vector_norm(v: List[float]) -> float:
    """Compute L2 norm of a vector."""
    return math.sqrt(sum(x * x for x in v))


def _softmax(scores: List[float], temperature: float = 1.0) -> List[float]:
    """Compute softmax with temperature scaling."""
    if not scores:
        return []
    max_score = max(scores)
    exp_scores = [math.exp((s - max_score) / temperature) for s in scores]
    total = sum(exp_scores)
    if total == 0:
        return [1.0 / len(scores)] * len(scores)
    return [e / total for e in exp_scores]


def _tag_to_vector(tags: Set[str], vocab: Dict[str, int], dim: int) -> List[float]:
    """Convert a set of tags to a sparse-like dense vector.

    Uses a simple hash-based embedding: each tag contributes to
    multiple dimensions via hash-to-index mapping.
    """
    vector = [0.0] * dim
    for tag in tags:
        # Deterministic hash-based indices
        h = hash(tag)
        idx1 = abs(h) % dim
        idx2 = abs(h >> 8) % dim
        idx3 = abs(h >> 16) % dim
        vector[idx1] += 1.0
        vector[idx2] += 0.5
        vector[idx3] += 0.25
    return vector


# ── Attention Router ───────────────────────────────────────────────

class AttentionRouter:
    """Attention-based service router for nanoservice coordination.

    Computes transformer-style attention scores to select the best
    service for each incoming request, factoring in capability
    matching, load balancing, and latency awareness.

    Parameters
    ----------
    embedding_dim : int
        Dimensionality of the attention space.
    temperature : float
        Softmax temperature (lower = more greedy, higher = more random).
    tag_vocabulary : Dict[str, int]
        Mapping from tag names to vocabulary indices.
    load_penalty_weight : float
        Weight of the load penalty in attention scoring.
    capability_bonus_weight : float
        Weight of the capability match bonus.
    """

    def __init__(
        self,
        embedding_dim: int = 64,
        temperature: float = 1.0,
        tag_vocabulary: Optional[Dict[str, int]] = None,
        load_penalty_weight: float = 2.0,
        capability_bonus_weight: float = 1.5,
    ) -> None:
        self._services: Dict[str, ServiceAttention] = {}
        self._embedding_dim = embedding_dim
        self._temperature = temperature
        self._tag_vocab = tag_vocabulary or {}
        self._load_penalty_weight = load_penalty_weight
        self._capability_bonus_weight = capability_bonus_weight
        self._lock = asyncio.Lock()
        self._routing_history: List[RoutingDecision] = []

    # ── Service registration ───────────────────────────────────────

    async def register_service(
        self,
        service_id: str,
        capability_tags: Optional[Set[str]] = None,
        feature_vector: Optional[List[float]] = None,
        max_capacity: int = 100,
        priority: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ServiceAttention:
        """Register a service with the attention router.

        If no feature_vector is provided, one is derived from the
        capability tags using hash-based embedding.
        """
        tags = capability_tags or set()
        if feature_vector is None:
            feature_vector = _tag_to_vector(tags, self._tag_vocab, self._embedding_dim)
        elif len(feature_vector) < self._embedding_dim:
            # Pad to embedding dimension
            feature_vector = feature_vector + [0.0] * (self._embedding_dim - len(feature_vector))

        service = ServiceAttention(
            service_id=service_id,
            capability_tags=tags,
            feature_vector=feature_vector[:self._embedding_dim],
            max_capacity=max_capacity,
            priority=priority,
            metadata=metadata or {},
        )

        async with self._lock:
            self._services[service_id] = service
            # Update tag vocabulary
            for tag in tags:
                if tag not in self._tag_vocab:
                    self._tag_vocab[tag] = len(self._tag_vocab)

        logger.info(
            "attention_router: registered service=%s tags=%s capacity=%d",
            service_id, tags, max_capacity,
        )
        return service

    async def deregister_service(self, service_id: str) -> None:
        """Remove a service from the router."""
        async with self._lock:
            self._services.pop(service_id, None)

    # ── Load tracking ──────────────────────────────────────────────

    async def report_load(self, service_id: str, current_load: int) -> None:
        """Update the current load for a service."""
        service = self._services.get(service_id)
        if service:
            service.current_load = current_load

    async def report_latency(self, service_id: str, latency: float) -> None:
        """Report a latency observation for a service."""
        service = self._services.get(service_id)
        if service:
            service.update_latency(latency)

    async def report_error(self, service_id: str, is_error: bool) -> None:
        """Report whether a request resulted in an error."""
        service = self._services.get(service_id)
        if service:
            service.update_error_rate(is_error)

    # ── Routing ────────────────────────────────────────────────────

    async def route(self, request: RoutingRequest) -> RoutingDecision:
        """Route a request using attention-based scoring.

        1. Encode the request as a query vector.
        2. Encode each service as a key vector.
        3. Compute attention scores with load and capability adjustments.
        4. Apply softmax to get probabilities.
        5. Select service (greedy by default, or sampled with temperature).

        Returns
        -------
        RoutingDecision
            The routing decision with attention weights.
        """
        start_time = time.monotonic()

        async with self._lock:
            if not self._services:
                return RoutingDecision(
                    request_id=request.request_id,
                    selected_service="",
                    attention_weights={},
                    confidence=0.0,
                    decision_time=time.monotonic() - start_time,
                )

            # Build query vector from request
            query_vector = request.context_vector or _tag_to_vector(
                request.required_tags, self._tag_vocab, self._embedding_dim,
            )
            if len(query_vector) < self._embedding_dim:
                query_vector = query_vector + [0.0] * (self._embedding_dim - len(query_vector))
            query_vector = query_vector[:self._embedding_dim]

            # Compute raw attention scores
            service_ids = list(self._services.keys())
            raw_scores: List[float] = []

            for sid in service_ids:
                service = self._services[sid]

                # Base attention: scaled dot-product
                key_vector = service.feature_vector
                attention_score = _dot_product(query_vector, key_vector)
                d_k = math.sqrt(self._embedding_dim)
                scaled_score = attention_score / d_k if d_k > 0 else 0.0

                # Capability bonus: Jaccard similarity of tags
                if request.required_tags and service.capability_tags:
                    overlap = request.required_tags & service.capability_tags
                    union = request.required_tags | service.capability_tags
                    jaccard = len(overlap) / len(union) if union else 0.0
                else:
                    jaccard = 0.0
                capability_bonus = self._capability_bonus_weight * jaccard

                # Hard filter: if required tags exist and the service doesn't
                # support ALL of them, penalize heavily.
                tag_penalty = 0.0
                if request.required_tags:
                    if not request.required_tags.issubset(service.capability_tags):
                        tag_penalty = -10.0  # Very low score for non-matching services

                # Load penalty: reduce score for heavily loaded services
                load_penalty = -self._load_penalty_weight * service.load_fraction

                # Availability bonus
                availability_bonus = service.availability_score

                # Priority multiplier
                priority_mult = service.priority * request.priority

                # Composite score
                composite = (
                    scaled_score
                    + capability_bonus
                    + tag_penalty
                    + load_penalty
                    + availability_bonus
                ) * priority_mult

                raw_scores.append(composite)

            # Apply softmax with temperature
            weights = _softmax(raw_scores, temperature=self._temperature)

            # Build attention weight map
            weight_map = dict(zip(service_ids, weights, strict=False))

            # Select service (highest weight)
            best_idx = weights.index(max(weights))
            selected = service_ids[best_idx]
            confidence = weights[best_idx]

        decision = RoutingDecision(
            request_id=request.request_id,
            selected_service=selected,
            attention_weights=weight_map,
            confidence=confidence,
            decision_time=time.monotonic() - start_time,
        )
        self._routing_history.append(decision)
        return decision

    # ── Introspection ──────────────────────────────────────────────

    def get_service(self, service_id: str) -> Optional[ServiceAttention]:
        """Return a service's attention profile."""
        return self._services.get(service_id)

    def list_services(self) -> List[str]:
        """List all registered service IDs."""
        return list(self._services.keys())

    def routing_history(self, limit: int = 50) -> List[RoutingDecision]:
        """Return recent routing decisions."""
        return self._routing_history[-limit:]

    def stats(self) -> Dict[str, Any]:
        """Return router statistics."""
        service_stats = {}
        for sid, svc in self._services.items():
            service_stats[sid] = {
                "load": f"{svc.current_load}/{svc.max_capacity}",
                "latency_ema": round(svc.latency_ema, 3),
                "error_rate": round(svc.error_rate, 3),
                "availability": round(svc.availability_score, 3),
                "tags": list(svc.capability_tags),
            }
        return {
            "total_services": len(self._services),
            "total_routes": len(self._routing_history),
            "embedding_dim": self._embedding_dim,
            "temperature": self._temperature,
            "tag_vocabulary_size": len(self._tag_vocab),
            "services": service_stats,
        }
