"""
shared_core.gas — Gas/kinetic-theory-inspired pressure-based load balancing.

Models worker pool as a gas system:
  - Workers are "molecules" with kinetic energy (throughput capacity)
  - Request queue is "pressure" (P = nRT, where n=pending, T=avg_latency)
  - Load balancing follows Maxwell-Boltzmann distribution
  - Pressure differential drives automatic worker scaling

All pure Python — zero external dependencies.
"""

from .kinetic import KineticEnergyTracker, MaxwellBoltzmannSelector
from .pressure import GasPressureResult, PressureBalancer, WorkerMolecule

__all__ = [
    "PressureBalancer",
    "WorkerMolecule",
    "GasPressureResult",
    "MaxwellBoltzmannSelector",
    "KineticEnergyTracker",
]
