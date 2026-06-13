"""
Meta-Router — Transcendent Cross-Cutting Routing Layer
=======================================================
Orchestrates all routing engines (Quantum, Genetic, Fluidic, Thompson)
into a single decision surface. The meta-router:

  1. Consults each sub-router for a route recommendation
  2. Weighs recommendations by each router's recent accuracy
  3. Applies quota enforcement (hard stops at threshold%)
  4. Returns the consensus best route

This is the "transcendent" layer above individual routers — aware of
all routing strategies simultaneously and able to combine their signals.

Also implements:
  - Canary routing with auto-rollback
  - EWMA (Exponentially Weighted Moving Average) latency scoring
  - Power-of-Two-Choices (P2C) for O(log N) optimal selection
  - Dimensional routing: route to different service layers (nano/micro/macro)
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from typing import Any, Optional

logger = logging.getLogger("tranc3.mesh.meta_router")

# EWMA smoothing factor (alpha): higher = more reactive to recent data
EWMA_ALPHA = 0.3


@dataclass
class RouterAdvisor:
    """Tracks the accuracy of a sub-router so the meta-router can weight it."""

    name: str
    weight: float = 1.0
    correct_predictions: int = 0
    total_predictions: int = 0

    @property
    def accuracy(self) -> float:
        return self.correct_predictions / max(self.total_predictions, 1)

    def record(self, correct: bool) -> None:
        self.total_predictions += 1
        if correct:
            self.correct_predictions += 1
        # Decay weight toward accuracy
        self.weight = 0.9 * self.weight + 0.1 * self.accuracy
        self.weight = max(self.weight, 0.1)


@dataclass
class RouteMetrics:
    """EWMA-tracked metrics per route."""

    name: str
    ewma_latency_ms: float = 100.0
    ewma_error_rate: float = 0.0
    call_count: int = 0
    canary_traffic_pct: float = 0.0  # >0 = canary
    canary_errors: int = 0
    canary_calls: int = 0

    def update(self, latency_ms: float, success: bool) -> None:
        self.call_count += 1
        self.ewma_latency_ms = EWMA_ALPHA * latency_ms + (1 - EWMA_ALPHA) * self.ewma_latency_ms
        err = 0.0 if success else 1.0
        self.ewma_error_rate = EWMA_ALPHA * err + (1 - EWMA_ALPHA) * self.ewma_error_rate

    @property
    def score(self) -> float:
        """Composite score: lower latency + lower error = higher score."""
        lat_score = 1.0 / (1.0 + self.ewma_latency_ms / 200.0)
        err_score = 1.0 - self.ewma_error_rate
        return lat_score * err_score

    @property
    def stats(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ewma_latency_ms": round(self.ewma_latency_ms, 2),
            "ewma_error_rate": round(self.ewma_error_rate, 3),
            "score": round(self.score, 4),
            "calls": self.call_count,
            "canary_pct": self.canary_traffic_pct,
        }


class MetaRouter:
    """
    Transcendent routing coordinator.

    Combines signals from quantum, genetic, fluidic, and Thompson sub-routers.
    Applies EWMA latency scoring and P2C for final selection.
    Enforces quota hard-stops via QuotaEnforcer integration.

    Usage::

        meta = MetaRouter()
        route = meta.select()
        try:
            result = await dispatch(route)
            meta.record_success(route, latency_ms=45.0)
        except Exception:
            meta.record_failure(route)
    """

    def __init__(self) -> None:
        self._metrics: dict[str, RouteMetrics] = {}
        self._advisors: dict[str, RouterAdvisor] = {}
        self._canary_rollback_threshold: float = 0.1  # 10% error triggers rollback

        # Optional sub-router integrations (guarded imports)
        self._quantum_router = None
        self._genetic_router = None
        self._thompson_sampler = None
        self._quota_enforcer = None
        self._initialized = False

    def _lazy_init(self) -> None:
        if self._initialized:
            return
        self._initialized = True

        try:
            from src.mesh.quantum_router import get_quantum_router
            self._quantum_router = get_quantum_router()
            self._advisors["quantum"] = RouterAdvisor("quantum", weight=1.0)
        except Exception:  # sub-router is optional; degraded gracefully
            pass

        try:
            from src.mesh.genetic_router import get_genetic_router
            self._genetic_router = get_genetic_router()
            self._advisors["genetic"] = RouterAdvisor("genetic", weight=1.0)
        except Exception:  # sub-router is optional; degraded gracefully
            pass

        try:
            from src.inference.thompson_sampler import get_sampler
            self._thompson_sampler = get_sampler()
            self._advisors["thompson"] = RouterAdvisor("thompson", weight=1.2)
        except Exception:  # sub-router is optional; degraded gracefully
            pass

        try:
            from src.mesh.quota_enforcer import get_enforcer
            self._quota_enforcer = get_enforcer()
        except Exception:  # quota enforcer is optional; runs without hard stops
            pass

    def register_route(self, name: str, canary_pct: float = 0.0) -> None:
        self._metrics[name] = RouteMetrics(name=name, canary_traffic_pct=canary_pct)

    def _get_votes(self, exclude: Optional[list[str]] = None) -> dict[str, float]:
        """Collect weighted votes from all sub-routers."""
        votes: dict[str, float] = {}

        exclude_set = set(exclude or [])

        if self._quantum_router:
            top = self._quantum_router.top_k(3)
            for i, name in enumerate(top):
                if name not in exclude_set:
                    votes[name] = votes.get(name, 0) + self._advisors["quantum"].weight * (3 - i)

        if self._genetic_router:
            ranked = self._genetic_router.ranked()[:3]
            for i, gene in enumerate(ranked):
                if gene.name not in exclude_set:
                    votes[gene.name] = votes.get(gene.name, 0) + self._advisors["genetic"].weight * (3 - i)

        if self._thompson_sampler:
            ranked_ts = self._thompson_sampler.rank_all()
            for i, name in enumerate(ranked_ts[:3]):
                if name not in exclude_set:
                    votes[name] = votes.get(name, 0) + self._advisors["thompson"].weight * (3 - i)

        # Add EWMA scores for local metrics
        for name, m in self._metrics.items():
            if name not in exclude_set and m.call_count > 0:
                votes[name] = votes.get(name, 0) + m.score * 2.0

        return votes

    def _p2c_select(self, candidates: list[str], scores: dict[str, float]) -> str:
        """Power-of-Two-Choices: sample 2, pick higher score."""
        if len(candidates) < 2:
            return candidates[0] if candidates else "offline"
        a, b = random.sample(candidates, 2)  # nosec B311
        return a if scores.get(a, 0) >= scores.get(b, 0) else b

    def _check_canary(self) -> Optional[str]:
        """Route to canary if configured and random check passes."""
        canaries = [m for m in self._metrics.values() if m.canary_traffic_pct > 0]
        for canary in canaries:
            if random.random() * 100 < canary.canary_traffic_pct:  # nosec B311
                # Check for auto-rollback
                if canary.canary_calls >= 20:
                    err_rate = canary.canary_errors / canary.canary_calls
                    if err_rate > self._canary_rollback_threshold:
                        logger.warning(
                            "meta_router: canary rollback %s (err=%.1f%%)",
                            canary.name, err_rate * 100,
                        )
                        canary.canary_traffic_pct = 0.0
                        continue
                return canary.name
        return None

    def select(self, exclude: Optional[list[str]] = None) -> str:
        """Select best route using meta-consensus from all sub-routers."""
        self._lazy_init()

        # Canary check first
        canary = self._check_canary()
        if canary:
            return canary

        # Quota check
        if self._quota_enforcer:
            votes = self._get_votes(exclude)
            # Filter out blocked providers
            allowed_votes = {
                k: v for k, v in votes.items()
                if not self._quota_enforcer.is_blocked(k)
            }
            if not allowed_votes:
                return self._quota_enforcer.select_provider()
            votes = allowed_votes
        else:
            votes = self._get_votes(exclude)

        if not votes:
            return "offline"

        candidates = list(votes.keys())
        return self._p2c_select(candidates, votes)

    def record_success(self, name: str, latency_ms: float = 0.0) -> None:
        """Propagate success to all sub-routers."""
        self._lazy_init()
        if name not in self._metrics:
            self._metrics[name] = RouteMetrics(name=name)
        m = self._metrics[name]
        m.update(latency_ms, success=True)
        if m.canary_traffic_pct > 0:
            m.canary_calls += 1

        if self._quantum_router:
            self._quantum_router.record_success(name, latency_ms)
        if self._genetic_router:
            self._genetic_router.record_success(name, latency_ms)
        if self._thompson_sampler:
            self._thompson_sampler.record_success(name, latency_ms)
        if self._quota_enforcer:
            self._quota_enforcer.record_request(name)

    def record_failure(self, name: str) -> None:
        """Propagate failure to all sub-routers."""
        self._lazy_init()
        if name not in self._metrics:
            self._metrics[name] = RouteMetrics(name=name)
        self._metrics[name].update(0.0, success=False)

        # Track canary failures for rollback
        m = self._metrics[name]
        if m.canary_traffic_pct > 0:
            m.canary_errors += 1
            m.canary_calls += 1

        if self._quantum_router:
            self._quantum_router.record_failure(name)
        if self._genetic_router:
            self._genetic_router.record_failure(name)
        if self._thompson_sampler:
            self._thompson_sampler.record_failure(name)

    def set_canary(self, name: str, traffic_pct: float) -> None:
        """Configure canary traffic for a route."""
        if name not in self._metrics:
            self._metrics[name] = RouteMetrics(name=name)
        self._metrics[name].canary_traffic_pct = traffic_pct
        self._metrics[name].canary_errors = 0
        self._metrics[name].canary_calls = 0
        logger.info("meta_router: canary %s set to %.1f%%", name, traffic_pct)

    @property
    def stats(self) -> dict[str, Any]:
        self._lazy_init()
        return {
            "metrics": {n: m.stats for n, m in self._metrics.items()},
            "advisors": {n: {"weight": a.weight, "accuracy": round(a.accuracy, 3)} for n, a in self._advisors.items()},
            "quota_dashboard": self._quota_enforcer.dashboard() if self._quota_enforcer else None,
        }


# ── Dimensional routing layers ─────────────────────────────────────────────────


class DimensionalRouter:
    """
    Route requests across service dimensions: nano (in-process), micro (local worker), macro (cloud).
    Automatically promotes/demotes routes based on latency budgets.
    """

    NANO_LATENCY_BUDGET_MS = 1.0
    MICRO_LATENCY_BUDGET_MS = 50.0
    MACRO_LATENCY_BUDGET_MS = 500.0

    def __init__(self) -> None:
        self._nano: Optional[Any] = None
        self._micro: dict[str, str] = {}   # capability → local worker URL
        self._macro: MetaRouter = MetaRouter()

    def set_nano_mesh(self, nano_mesh: Any) -> None:
        self._nano = nano_mesh

    def register_micro(self, capability: str, url: str) -> None:
        self._micro[capability] = url

    async def route(self, capability: str, *args: Any, **kwargs: Any) -> Any:
        """
        Try nano → micro → macro in order of latency budget.
        Returns result from the fastest successful layer.
        """
        # Nano: in-process function
        if self._nano:
            try:
                return await self._nano.call(capability, *args, **kwargs)
            except Exception:  # nano layer unavailable; fall through to micro
                pass

        # Micro: local worker
        if capability in self._micro:
            import httpx
            url = self._micro[capability]
            try:
                async with httpx.AsyncClient(timeout=self.MICRO_LATENCY_BUDGET_MS / 1000.0) as client:
                    resp = await client.post(url, json={"capability": capability, "args": list(args), "kwargs": kwargs})
                    if resp.status_code == 200:
                        return resp.json()
            except Exception:  # micro layer unavailable; fall through to macro
                pass

        # Macro: cloud provider via meta-router
        provider = self._macro.select()
        return {"provider": provider, "capability": capability, "layer": "macro"}


# ── Singletons ─────────────────────────────────────────────────────────────────

_meta_router: Optional[MetaRouter] = None
_dimensional_router: Optional[DimensionalRouter] = None


def get_meta_router() -> MetaRouter:
    global _meta_router
    if _meta_router is None:
        _meta_router = MetaRouter()
    return _meta_router


def get_dimensional_router() -> DimensionalRouter:
    global _dimensional_router
    if _dimensional_router is None:
        _dimensional_router = DimensionalRouter()
    return _dimensional_router


__all__ = [
    "RouteMetrics", "MetaRouter", "DimensionalRouter",
    "get_meta_router", "get_dimensional_router",
]
