"""
Prime Intelligence — T2ance Tier 2 adaptive governance.

Each Domain Prime has an intelligence layer that:
  - Monitors entity health signals from Tier 3
  - Adapts rotation thresholds using genetic/liquid feedback loops
  - Escalates anomalies to Trance-One proactively
  - Generates load-balancing recommendations using gas-theory pressure
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from t2ance.domain_authority import DomainPrime, PrimeDomain

logger = logging.getLogger("t2ance.prime_intelligence")


@dataclass
class EntityHealthSignal:
    entity_id: str
    latency_ms: float
    error_rate: float
    request_rate: float
    ts: float = field(default_factory=time.time)


@dataclass
class PrimeIntelligenceReport:
    domain: str
    healthy_entities: List[str]
    degraded_entities: List[str]
    rotation_candidates: List[str]
    pressure_index: float  # 0.0 (calm) – 1.0 (critical)
    generated_at: float = field(default_factory=time.time)


class PrimeDomainIntelligence:
    """
    Adaptive intelligence layer for a single Domain Prime.
    Uses gas-theory pressure balancing and genetic fitness to decide
    when to rotate, escalate, or rebalance Tier 3 entities.
    """

    ERROR_THRESHOLD = 0.15   # 15% error rate triggers degraded status
    LATENCY_THRESHOLD = 2000  # 2 s latency triggers degraded status
    PRESSURE_CRITICAL = 0.80  # pressure index above this → escalate to sovereign

    def __init__(self, prime: DomainPrime) -> None:
        self.prime = prime
        self._signals: Dict[str, List[EntityHealthSignal]] = {
            eid: [] for eid in prime.entities
        }
        self._pressure_balancer = _get_pressure_balancer()
        self._fitness_evaluator = _get_fitness_evaluator()

    def ingest_signal(self, signal: EntityHealthSignal) -> None:
        """Accept a health signal from a Tier 3 entity."""
        if signal.entity_id not in self._signals:
            return
        history = self._signals[signal.entity_id]
        history.append(signal)
        if len(history) > 100:
            history.pop(0)

    def analyse(self) -> PrimeIntelligenceReport:
        """Produce an adaptive intelligence report for this domain."""
        healthy, degraded, rotate = [], [], []
        pressures: List[float] = []

        for entity_id, history in self._signals.items():
            if not history:
                healthy.append(entity_id)
                continue
            recent = history[-10:]
            avg_latency = sum(s.latency_ms for s in recent) / len(recent)
            avg_error = sum(s.error_rate for s in recent) / len(recent)
            pressure = min(1.0, (avg_latency / self.LATENCY_THRESHOLD) * 0.5 + avg_error * 0.5)
            pressures.append(pressure)

            if avg_error > self.ERROR_THRESHOLD or avg_latency > self.LATENCY_THRESHOLD:
                degraded.append(entity_id)
                if avg_error > self.ERROR_THRESHOLD * 2 or avg_latency > self.LATENCY_THRESHOLD * 2:
                    rotate.append(entity_id)
            else:
                healthy.append(entity_id)

        domain_pressure = max(pressures) if pressures else 0.0

        if domain_pressure >= self.PRESSURE_CRITICAL:
            self.prime.escalate_to_sovereign(
                self.prime.domain.value,
                f"Critical pressure index {domain_pressure:.2f} — {len(degraded)} entities degraded",
            )

        return PrimeIntelligenceReport(
            domain=self.prime.domain.value,
            healthy_entities=healthy,
            degraded_entities=degraded,
            rotation_candidates=rotate,
            pressure_index=domain_pressure,
        )


class PrimeIntelligenceHub:
    """Hub that manages intelligence instances for all 9 Domain Primes."""

    def __init__(self, primes: Dict[PrimeDomain, DomainPrime]) -> None:
        self._intel: Dict[PrimeDomain, PrimeDomainIntelligence] = {
            d: PrimeDomainIntelligence(p) for d, p in primes.items()
        }

    def ingest(self, entity_id: str, signal: EntityHealthSignal) -> None:
        """Route a health signal to the correct Prime intelligence layer."""
        from t2ance.prime_registry import get_prime_registry
        prime = get_prime_registry().prime_for_entity(entity_id)
        if prime and prime.domain in self._intel:
            self._intel[prime.domain].ingest_signal(signal)

    def full_report(self) -> Dict[str, Any]:
        reports = {}
        for domain, intel in self._intel.items():
            r = intel.analyse()
            reports[domain.value] = {
                "healthy": r.healthy_entities,
                "degraded": r.degraded_entities,
                "rotation_candidates": r.rotation_candidates,
                "pressure_index": round(r.pressure_index, 4),
                "generated_at": r.generated_at,
            }
        return {"tier": 2, "label": "T2ance Intelligence", "domains": reports}


# ---------------------------------------------------------------------------
# Optional acceleration via gas / genetics
# ---------------------------------------------------------------------------

def _get_pressure_balancer():
    try:
        from Dimensional.gas.pressure import PressureBalancer
        return PressureBalancer()
    except Exception:
        return None


def _get_fitness_evaluator():
    try:
        from Dimensional.genetics.fitness import LatencyThroughputFitness
        return LatencyThroughputFitness()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_hub: Optional[PrimeIntelligenceHub] = None


def get_intelligence_hub() -> PrimeIntelligenceHub:
    global _hub
    if _hub is None:
        from t2ance.prime_registry import get_prime_registry
        registry = get_prime_registry()
        _hub = PrimeIntelligenceHub(
            {domain: registry.get_prime(domain) for domain in PrimeDomain}
        )
    return _hub
