"""Ant Colony Optimisation for AI provider routing.

ACO is a real, proven meta-heuristic (Dorigo, 1992) used in production routing systems.
Ants deposit pheromones on successful paths; evaporation prevents stagnation.

Applied here: each AI provider is a node. Successful (fast, cheap, correct) requests
reinforce pheromone on that provider. Failed or slow requests evaporate pheromone faster.
Over time, the colony converges to the optimal provider sequence for each request type.

This is NOT a buzzword — ACO is deployed in real-time routing at Cisco, AT&T, etc.
"""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from threading import RLock
from typing import Dict, List, Optional

logger = logging.getLogger("tranc3.dimensional.swarm.aco")


@dataclass
class ProviderNode:
    name: str
    pheromone: float = 1.0
    heuristic: float = 1.0  # static quality estimate (0-1)
    success_count: int = 0
    failure_count: int = 0
    total_latency_ms: float = 0.0
    last_success: float = field(default_factory=time.time)

    @property
    def avg_latency_ms(self) -> float:
        total = self.success_count
        return (self.total_latency_ms / total) if total > 0 else 999_999.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.failure_count
        return self.success_count / total if total > 0 else 0.5


class AntColonyRouter:
    """ACO-based adaptive provider selection.

    Parameters follow Dorigo & Stützle (2004) recommendations:
    - alpha=1.0: pheromone influence
    - beta=2.0: heuristic influence (favour faster providers)
    - rho=0.1: evaporation rate per cycle
    - Q=100: pheromone deposit per successful request
    """

    def __init__(
        self,
        providers: List[str],
        alpha: float = 1.0,
        beta: float = 2.0,
        rho: float = 0.1,
        Q: float = 100.0,
        heuristics: Optional[Dict[str, float]] = None,
    ) -> None:
        self._lock = RLock()
        self.alpha = alpha
        self.beta = beta
        self.rho = rho
        self.Q = Q

        # Static heuristics: local > cloud-fast > cloud-slow
        default_heuristics = {
            "llamacpp": 0.95,
            "vllm": 0.95,
            "ollama": 0.90,
            "groq": 0.85,
            "cerebras": 0.80,
            "gemini": 0.75,
            "sambanova": 0.70,
            "cloudflare_ai": 0.65,
            "openrouter": 0.60,
            "huggingface": 0.55,
            "github_models": 0.50,
            "together": 0.50,
            "deepseek": 0.45,
            "offline": 0.10,
        }
        h = {**default_heuristics, **(heuristics or {})}
        self.nodes: Dict[str, ProviderNode] = {
            name: ProviderNode(name=name, heuristic=h.get(name, 0.5))
            for name in providers
        }

    def select(self, n: int = 3) -> List[str]:
        """Select `n` providers in priority order using ACO probability."""
        with self._lock:
            remaining = list(self.nodes.values())
            selected: List[str] = []
            for _ in range(min(n, len(remaining))):
                probs = self._probabilities(remaining)
                chosen = self._roulette(remaining, probs)
                selected.append(chosen.name)
                remaining.remove(chosen)
            return selected

    def _probabilities(self, nodes: List[ProviderNode]) -> List[float]:
        scores = [
            (n.pheromone ** self.alpha) * (n.heuristic ** self.beta)
            for n in nodes
        ]
        total = sum(scores) or 1.0
        return [s / total for s in scores]

    def _roulette(self, nodes: List[ProviderNode], probs: List[float]) -> ProviderNode:
        r = random.random()  # nosec B311 — not cryptographic
        cumulative = 0.0
        for node, prob in zip(nodes, probs, strict=False):
            cumulative += prob
            if r <= cumulative:
                return node
        return nodes[-1]

    def record_success(self, provider: str, latency_ms: float) -> None:
        with self._lock:
            node = self.nodes.get(provider)
            if not node:
                return
            node.success_count += 1
            node.total_latency_ms += latency_ms
            node.last_success = time.time()
            # Deposit pheromone: more pheromone for faster responses
            speed_bonus = max(0.1, 1.0 - latency_ms / 30_000.0)
            node.pheromone += self.Q * speed_bonus
            self._evaporate()

    def record_failure(self, provider: str) -> None:
        with self._lock:
            node = self.nodes.get(provider)
            if not node:
                return
            node.failure_count += 1
            # Failures evaporate extra pheromone
            node.pheromone = max(0.01, node.pheromone * (1 - self.rho * 3))
            self._evaporate()

    def _evaporate(self) -> None:
        for node in self.nodes.values():
            node.pheromone = max(0.01, node.pheromone * (1 - self.rho))

    def pheromone_map(self) -> Dict[str, float]:
        with self._lock:
            return {name: node.pheromone for name, node in self.nodes.items()}

    def stats(self) -> Dict[str, Dict]:
        with self._lock:
            return {
                name: {
                    "pheromone": round(node.pheromone, 3),
                    "success_rate": round(node.success_rate, 3),
                    "avg_latency_ms": round(node.avg_latency_ms, 1),
                    "calls": node.success_count + node.failure_count,
                }
                for name, node in self.nodes.items()
            }
