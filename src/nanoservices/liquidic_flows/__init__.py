"""Liquidic/Gas Flow Engine — Phase 8.5

Fluid computing paradigm where services flow like liquids and gases
through the nanoservice mesh, adapting their shape and behavior
to container constraints and environmental conditions.
"""

from .liquidic_flows import (
    ContainerShape,
    FlowContainer,
    FlowState,
    FluidProperties,
    GasService,
    LiquidicFlowEngine,
    LiquidicService,
    PressureValve,
)

__all__ = [
    "FlowState",
    "ContainerShape",
    "FluidProperties",
    "LiquidicService",
    "GasService",
    "FlowContainer",
    "PressureValve",
    "LiquidicFlowEngine",
]
