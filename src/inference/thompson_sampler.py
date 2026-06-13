"""
Thompson Sampler — intelligent provider/model selection for Luminous.

Uses Beta-distribution Thompson sampling (multi-armed bandit) to balance
exploration (trying underused providers) vs exploitation (using the best
known provider). Each provider has a Beta(α, β) belief:
  α = success count + 1
  β = failure count + 1

On each request, sample θ ~ Beta(α, β) for each provider and pick the
highest. This naturally routes toward reliable providers while still
occasionally probing degraded ones to detect recovery.

Zero-cost: pure Python stdlib — no external dependencies.
"""
from __future__ import annotations

import random
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class ProviderBelief:
    name: str
    successes: int = 0
    failures: int = 0
    total_latency_ms: float = 0.0
    last_updated: float = field(default_factory=time.time)

    @property
    def alpha(self) -> float:
        return float(self.successes + 1)

    @property
    def beta(self) -> float:
        return float(self.failures + 1)

    @property
    def mean(self) -> float:
        return self.alpha / (self.alpha + self.beta)

    @property
    def avg_latency_ms(self) -> float:
        total = self.successes + self.failures
        return self.total_latency_ms / total if total > 0 else 0.0

    def sample(self) -> float:
        """Sample θ from Beta(α, β) using Johnk's method (stdlib only)."""
        return _beta_sample(self.alpha, self.beta)


def _beta_sample(alpha: float, beta: float) -> float:
    """Beta distribution sampler using Johnk's method (no scipy needed)."""
    if alpha <= 0 or beta <= 0:
        return 0.5
    # Use Python's random.betavariate which IS in stdlib
    try:
        return random.betavariate(alpha, beta)
    except Exception:
        # Degenerate case: return mean
        return alpha / (alpha + beta)


class ThompsonSampler:
    """
    Multi-armed bandit provider selector for the Luminous AI gateway.

    Providers are registered by name. After each request, record success
    or failure. The sampler will naturally route toward reliable providers.

    Persistence: optional SQLite backend so beliefs survive restarts.
    """

    def __init__(
        self,
        providers: List[str],
        db_path: Optional[str] = None,
        latency_weight: float = 0.3,
    ) -> None:
        self._beliefs: Dict[str, ProviderBelief] = {
            name: ProviderBelief(name=name) for name in providers
        }
        self._latency_weight = latency_weight
        self._db_path = db_path
        if db_path:
            self._init_db(db_path)
            self._load_from_db()

    # ── Selection ────────────────────────────────────────────────────────────

    def select(self, exclude: Optional[List[str]] = None) -> str:
        """
        Select the best provider by Thompson sampling.

        Scores = θ_success × (1 - latency_weight) + latency_penalty × latency_weight
        """
        exclude = set(exclude or [])
        candidates = [b for n, b in self._beliefs.items() if n not in exclude]

        if not candidates:
            # All excluded — fall back to any
            candidates = list(self._beliefs.values())

        if len(candidates) == 1:
            return candidates[0].name

        # Score each provider
        scored: List[tuple[float, str]] = []
        max_latency = max(b.avg_latency_ms for b in candidates) or 1.0

        for belief in candidates:
            theta = belief.sample()
            # Latency penalty: 0 = fast, 1 = slowest
            latency_penalty = 1.0 - (belief.avg_latency_ms / max_latency)
            score = (
                theta * (1.0 - self._latency_weight)
                + latency_penalty * self._latency_weight
            )
            scored.append((score, belief.name))

        scored.sort(reverse=True)
        return scored[0][1]

    def rank_all(self) -> List[str]:
        """Return all providers ranked by current mean belief (exploitation only)."""
        ranked = sorted(
            self._beliefs.values(),
            key=lambda b: b.mean,
            reverse=True,
        )
        return [b.name for b in ranked]

    # ── Feedback ─────────────────────────────────────────────────────────────

    def record_success(self, provider: str, latency_ms: float = 0.0) -> None:
        belief = self._beliefs.get(provider)
        if belief is None:
            return
        belief.successes += 1
        belief.total_latency_ms += latency_ms
        belief.last_updated = time.time()
        self._persist(provider)

    def record_failure(self, provider: str, latency_ms: float = 0.0) -> None:
        belief = self._beliefs.get(provider)
        if belief is None:
            return
        belief.failures += 1
        belief.total_latency_ms += latency_ms
        belief.last_updated = time.time()
        self._persist(provider)

    def add_provider(self, name: str) -> None:
        if name not in self._beliefs:
            self._beliefs[name] = ProviderBelief(name=name)

    # ── Stats ────────────────────────────────────────────────────────────────

    def stats(self) -> List[Dict]:
        return [
            {
                "name": b.name,
                "successes": b.successes,
                "failures": b.failures,
                "mean": round(b.mean, 4),
                "avg_latency_ms": round(b.avg_latency_ms, 1),
                "last_updated": b.last_updated,
            }
            for b in sorted(self._beliefs.values(), key=lambda x: x.mean, reverse=True)
        ]

    # ── Persistence ───────────────────────────────────────────────────────────

    def _init_db(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS provider_beliefs (
                    name TEXT PRIMARY KEY,
                    successes INTEGER NOT NULL DEFAULT 0,
                    failures INTEGER NOT NULL DEFAULT 0,
                    total_latency_ms REAL NOT NULL DEFAULT 0.0,
                    last_updated REAL NOT NULL DEFAULT 0.0
                )"""
            )
            conn.commit()

    def _load_from_db(self) -> None:
        if not self._db_path:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                for row in conn.execute(
                    "SELECT name, successes, failures, total_latency_ms, last_updated FROM provider_beliefs"
                ):
                    name, s, f, tl, lu = row
                    if name in self._beliefs:
                        b = self._beliefs[name]
                        b.successes = s
                        b.failures = f
                        b.total_latency_ms = tl
                        b.last_updated = lu
        except Exception:
            pass

    def _persist(self, provider: str) -> None:
        if not self._db_path:
            return
        belief = self._beliefs.get(provider)
        if belief is None:
            return
        try:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    """INSERT INTO provider_beliefs (name, successes, failures, total_latency_ms, last_updated)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(name) DO UPDATE SET
                           successes=excluded.successes,
                           failures=excluded.failures,
                           total_latency_ms=excluded.total_latency_ms,
                           last_updated=excluded.last_updated""",
                    (
                        belief.name,
                        belief.successes,
                        belief.failures,
                        belief.total_latency_ms,
                        belief.last_updated,
                    ),
                )
                conn.commit()
        except Exception:
            pass


# Module-level singleton wired to all known free providers
_DEFAULT_PROVIDERS = [
    "ollama",
    "groq",
    "cerebras",
    "sambanova",
    "openrouter",
    "gemini",
    "huggingface",
    "github_models",
    "offline",
]

_sampler: Optional[ThompsonSampler] = None


def get_sampler(db_path: str = "data/thompson_sampler.db") -> ThompsonSampler:
    global _sampler
    if _sampler is None:
        _sampler = ThompsonSampler(
            providers=_DEFAULT_PROVIDERS,
            db_path=db_path,
        )
    return _sampler
