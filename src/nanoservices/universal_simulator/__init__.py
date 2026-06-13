"""Universal Simulator — Phase 10.5"""

from .universal_simulator import (
    BoundaryCondition,
    ClassicalMechanicsSolver,
    FluidDynamicsSolver,
    PhysicalBody,
    PhysicsDomain,
    SimulationConfig,
    SimulationResult,
    SimulationState,
    SolverType,
    ThermodynamicsSolver,
    UniversalSimulator,
    UniversalSimulatorService,
    Vector3D,
)

__all__ = [
    "PhysicsDomain",
    "SimulationState",
    "SolverType",
    "BoundaryCondition",
    "Vector3D",
    "PhysicalBody",
    "SimulationConfig",
    "SimulationResult",
    "ClassicalMechanicsSolver",
    "FluidDynamicsSolver",
    "ThermodynamicsSolver",
    "UniversalSimulator",
    "UniversalSimulatorService",
]
