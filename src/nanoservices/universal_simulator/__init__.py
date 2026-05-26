"""Universal Simulator — Phase 10.5"""

from .universal_simulator import (
    PhysicsDomain,
    SimulationState,
    SolverType,
    BoundaryCondition,
    Vector3D,
    PhysicalBody,
    SimulationConfig,
    SimulationResult,
    ClassicalMechanicsSolver,
    FluidDynamicsSolver,
    ThermodynamicsSolver,
    UniversalSimulator,
    UniversalSimulatorService,
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
