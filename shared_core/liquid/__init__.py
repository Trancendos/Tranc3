"""
shared_core.liquid — Liquid Neural Network routing layer.

Provides ODE-governed adaptive routing where route weights shift
continuously based on input signals and elapsed time deltas.

Uses ncps (Neural Circuit Policies) when available for LTC cells
with proper ODE solvers. Falls back to the hand-coded LTC analogue
from src/fluidic/fluid_router.py otherwise.
"""

from .ltc_router import LiquidRouter, RouteCell, LiquidRoutingResult
from .wiring import AutoWiring, build_ncp_wiring

__all__ = [
    "LiquidRouter",
    "RouteCell",
    "LiquidRoutingResult",
    "AutoWiring",
    "build_ncp_wiring",
]
