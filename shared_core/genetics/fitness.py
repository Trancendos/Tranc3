"""
Fitness evaluators for genetic optimisation of worker configurations.

Fitness functions are callables: (config: Dict) -> Tuple[float, ...]
Multi-objective fitness: lower latency, higher throughput, lower error_rate.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Tuple


class FitnessEvaluator(ABC):
    """Base class for fitness evaluation."""

    @abstractmethod
    def evaluate(self, config: Dict[str, Any]) -> Tuple[float, ...]:
        """
        Returns a tuple of fitness values.
        Convention: lower is better for all objectives (negate maximisation goals).
        """


class LatencyThroughputFitness(FitnessEvaluator):
    """
    Evaluates routing config fitness via simulated latency + throughput probe.

    Weights: (-1, 1) → minimise latency, maximise throughput (negated).
    In DEAP/NSGA-II terms: weights=(-1.0, -1.0) on (latency, -throughput).
    """

    def __init__(
        self,
        latency_fn: Callable[[Dict[str, Any]], float] | None = None,
        throughput_fn: Callable[[Dict[str, Any]], float] | None = None,
    ) -> None:
        self._latency_fn = latency_fn or self._default_latency
        self._throughput_fn = throughput_fn or self._default_throughput

    def evaluate(self, config: Dict[str, Any]) -> Tuple[float, float]:
        """Returns (latency_ms, neg_throughput_rps) — both lower-is-better."""
        latency = self._latency_fn(config)
        throughput = self._throughput_fn(config)
        return (latency, -throughput)  # negate throughput for minimisation

    @staticmethod
    def _default_latency(config: Dict[str, Any]) -> float:
        """Estimate latency from concurrency and batch_size heuristics."""
        concurrency = float(config.get("concurrency", 4))
        batch_size = float(config.get("batch_size", 16))
        # Higher concurrency generally reduces latency but increases overhead
        base = 10.0 / max(concurrency, 1)
        overhead = max(0.0, (concurrency - 8) * 0.5)
        batch_penalty = max(0.0, (batch_size - 32) * 0.1)
        return base + overhead + batch_penalty

    @staticmethod
    def _default_throughput(config: Dict[str, Any]) -> float:
        """Estimate throughput RPS from concurrency and batch_size."""
        concurrency = float(config.get("concurrency", 4))
        batch_size = float(config.get("batch_size", 16))
        return min(concurrency * batch_size * 5.0, 10000.0)


class MultiWorkerFitness(FitnessEvaluator):
    """
    Fitness for routing weight vectors across a worker pool.

    Each gene[i] = weight for worker[i].
    Fitness = weighted average latency across pool (lower is better).
    """

    def __init__(self, worker_latencies: List[float]) -> None:
        self._latencies = worker_latencies

    def evaluate(self, config: Dict[str, Any]) -> Tuple[float]:
        weights_raw: List[float] = config.get("weights", [1.0] * len(self._latencies))
        total = sum(abs(w) for w in weights_raw) or 1.0
        weights = [abs(w) / total for w in weights_raw]
        avg_latency = sum(w * l for w, l in zip(weights, self._latencies))
        return (avg_latency,)
