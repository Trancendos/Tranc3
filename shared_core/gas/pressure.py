"""
Gas-pressure-based load balancer.

Analogues:
  - Pressure P = nRT  →  queue_depth × avg_latency_ms
  - Temperature T     →  avg_latency (thermal agitation)
  - Volume V          →  worker capacity (concurrent slots)
  - Kinetic energy KE →  throughput (requests/sec)

Selection: workers with highest KE (throughput) receive highest routing weight.
Overflow: when pressure exceeds threshold, emit scale-up signal.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass
class WorkerMolecule:
    """
    Represents a single worker as a gas molecule.

    velocity  = requests_per_second (kinetic energy = 0.5 * mass * v²)
    mass      = worker weight / capacity scaling factor
    pressure  = queue_depth * avg_latency_ms (ideal gas analogue)
    """

    name: str
    mass: float = 1.0               # capacity weight
    velocity: float = 10.0          # current RPS
    queue_depth: int = 0            # pending requests
    avg_latency_ms: float = 50.0    # thermal temperature
    capacity: int = 100             # max concurrent slots
    active_slots: int = 0           # currently occupied slots

    @property
    def kinetic_energy(self) -> float:
        """½mv² — higher energy = more routing preference."""
        return 0.5 * self.mass * self.velocity ** 2

    @property
    def pressure(self) -> float:
        """P = n × R × T analogue: queue × latency."""
        n = max(1, self.queue_depth)
        T = max(1.0, self.avg_latency_ms)
        return n * T  # dimensionless pressure units

    @property
    def free_capacity(self) -> int:
        return max(0, self.capacity - self.active_slots)

    @property
    def utilisation(self) -> float:
        return self.active_slots / max(1, self.capacity)

    def observe(self, rps: float, latency_ms: float, queue_depth: int, active_slots: int) -> None:
        """Update molecule state from observed metrics."""
        # EWMA smoothing (α=0.3)
        alpha = 0.3
        self.velocity = alpha * rps + (1 - alpha) * self.velocity
        self.avg_latency_ms = alpha * latency_ms + (1 - alpha) * self.avg_latency_ms
        self.queue_depth = queue_depth
        self.active_slots = active_slots


@dataclass
class GasPressureResult:
    selected: str
    weight: float
    all_weights: Dict[str, float]
    system_pressure: float
    scale_up_signal: bool
    scale_down_signal: bool
    elapsed_ms: float = 0.0


class PressureBalancer:
    """
    Routes requests based on kinetic energy differential.

    Workers with higher throughput (kinetic energy) receive proportionally
    more traffic. When system pressure exceeds threshold, emits scale_up_signal.

    Usage::

        balancer = PressureBalancer(["w1", "w2", "w3"])
        balancer.observe("w1", rps=120, latency_ms=30, queue=2, slots=20)
        balancer.observe("w2", rps=45,  latency_ms=80, queue=10, slots=45)
        result = balancer.select()
        print(result.selected, result.all_weights)
    """

    # Pressure thresholds (dimensionless)
    SCALE_UP_PRESSURE = 5000.0    # queue_depth × latency_ms
    SCALE_DOWN_PRESSURE = 500.0

    def __init__(
        self,
        workers: List[str],
        scale_up_threshold: float = SCALE_UP_PRESSURE,
        scale_down_threshold: float = SCALE_DOWN_PRESSURE,
    ) -> None:
        self._molecules: Dict[str, WorkerMolecule] = {
            w: WorkerMolecule(name=w) for w in workers
        }
        self._scale_up_thresh = scale_up_threshold
        self._scale_down_thresh = scale_down_threshold

    def observe(
        self,
        worker: str,
        rps: float,
        latency_ms: float,
        queue: int = 0,
        slots: int = 0,
    ) -> None:
        """Update worker molecule state from live metrics."""
        if worker not in self._molecules:
            self._molecules[worker] = WorkerMolecule(name=worker)
        self._molecules[worker].observe(rps, latency_ms, queue, slots)

    def select(self, exclude: Optional[List[str]] = None) -> GasPressureResult:
        """Select best worker via kinetic energy weighted routing."""
        t0 = time.perf_counter()
        excl = set(exclude or [])

        candidates = {
            name: mol
            for name, mol in self._molecules.items()
            if name not in excl and mol.free_capacity > 0
        }

        if not candidates:
            # Fallback: use all workers
            candidates = {n: m for n, m in self._molecules.items() if n not in excl}

        if not candidates:
            # Absolute fallback
            name = next(iter(self._molecules))
            return GasPressureResult(
                selected=name, weight=1.0,
                all_weights={name: 1.0},
                system_pressure=0.0,
                scale_up_signal=False,
                scale_down_signal=False,
                elapsed_ms=(time.perf_counter() - t0) * 1000,
            )

        # Energy-proportional weights
        energies = {n: max(0.001, m.kinetic_energy) for n, m in candidates.items()}
        total_energy = sum(energies.values())
        weights = {n: e / total_energy for n, e in energies.items()}

        selected = max(weights, key=weights.get)
        system_pressure = sum(m.pressure for m in self._molecules.values())

        elapsed = (time.perf_counter() - t0) * 1000
        return GasPressureResult(
            selected=selected,
            weight=weights[selected],
            all_weights=weights,
            system_pressure=system_pressure,
            scale_up_signal=system_pressure > self._scale_up_thresh,
            scale_down_signal=system_pressure < self._scale_down_thresh and len(self._molecules) > 1,
            elapsed_ms=elapsed,
        )

    def system_temperature(self) -> float:
        """Average latency across all workers — gas temperature analogue."""
        if not self._molecules:
            return 0.0
        return sum(m.avg_latency_ms for m in self._molecules.values()) / len(self._molecules)

    def add_worker(self, name: str, initial_rps: float = 10.0) -> None:
        """Scale-out: add a new molecule to the gas system."""
        if name not in self._molecules:
            mol = WorkerMolecule(name=name)
            mol.velocity = initial_rps
            self._molecules[name] = mol

    def remove_worker(self, name: str) -> None:
        """Scale-in: remove a molecule from the gas system."""
        self._molecules.pop(name, None)

    @property
    def workers(self) -> List[str]:
        return list(self._molecules.keys())
