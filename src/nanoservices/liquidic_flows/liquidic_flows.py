"""Liquidic/Gas Flow Engine — Fluid Computing Paradigm for TranceX Phase 8.5

Implements a fluid computing paradigm where nanoservices behave like
liquids and gases, adapting their shape to container constraints,
flowing through pressure gradients, and expanding/compressing based
on environmental conditions.

Key concepts:
- Liquidic Services: Services that flow like liquids, filling available
  container capacity and adapting to constraints
- Gas Services: Services that expand to fill all available space,
  scaling horizontally without explicit configuration
- Flow Containers: Execution environments that constrain and shape
  service behavior (like physical containers shape fluids)
- Pressure Valves: Backpressure mechanisms that control flow rates
  and prevent resource exhaustion
- Viscosity: Resistance to flow — higher viscosity means slower
  adaptation but more predictable behavior
- Surface Tension: Services that cluster together and resist separation

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class FlowState(Enum):
    """States of a fluid service."""

    SOLID = "solid"  # Frozen, not flowing
    LIQUID = "liquid"  # Flowing, adapting to container
    GAS = "gas"  # Expanding to fill space
    PLASMA = "plasma"  # Supercharged, ionized state
    SUPERFLUID = "superfluid"  # Zero viscosity, perfect flow


class ContainerShape(Enum):
    """Shapes of flow containers."""

    PIPELINE = "pipeline"  # Linear flow
    RESERVOIR = "reservoir"  # Accumulation buffer
    VORTEX = "vortex"  # Circular/spiral processing
    DELTA = "delta"  # Fan-out distribution
    CONVERGENT = "convergent"  # Fan-in aggregation
    POROUS = "porous"  # Filter/mesh processing
    SPHERICAL = "spherical"  # All-to-all communication
    FRACTAL = "fractal"  # Self-similar recursive processing


class FluidProperty(Enum):
    """Physical properties mapped to service behavior."""

    VISCOSITY = "viscosity"  # Resistance to flow/changes
    DENSITY = "density"  # Resource consumption per unit
    SURFACE_TENSION = "surface_tension"  # Clustering/cohesion strength
    COMPRESSIBILITY = "compressibility"  # How much load it can absorb
    VOLATILITY = "volatility"  # Tendency to scale up rapidly
    CONDUCTIVITY = "conductivity"  # Communication throughput
    ELASTICITY = "elasticity"  # Ability to recover from strain
    TURBIDITY = "turbidity"  # Processing complexity/opacity


class PressureType(Enum):
    """Types of pressure in the fluid system."""

    THROUGHPUT = "throughput"  # Requests per second
    MEMORY = "memory"  # Memory utilization
    CPU = "cpu"  # CPU utilization
    NETWORK = "network"  # Bandwidth pressure
    LATENCY = "latency"  # Response time pressure
    BACKPRESSURE = "backpressure"  # Downstream resistance


@dataclass
class FluidProperties:
    """Physical-like properties of a fluid service."""

    viscosity: float = 0.5  # 0.0 (instant) to 1.0 (very slow adaptation)
    density: float = 0.5  # Resource usage per unit
    surface_tension: float = 0.3  # Clustering strength
    compressibility: float = 0.7  # Load absorption capacity
    volatility: float = 0.3  # Tendency to scale up
    conductivity: float = 0.8  # Communication throughput
    elasticity: float = 0.6  # Recovery from strain
    turbidity: float = 0.2  # Processing complexity

    def effective_flow_rate(self, pressure: float) -> float:
        """Calculate effective flow rate given pressure (Poiseuille-like)."""
        # Simplified: flow_rate = pressure / viscosity
        if self.viscosity <= 0:
            return float("inf")
        return pressure / self.viscosity

    def expansion_factor(self, available_space: float) -> float:
        """Calculate how much the service expands given available space."""
        # Gas-like: expands proportionally to available space and compressibility
        return 1.0 + (available_space * self.compressibility * self.volatility)

    def cohesion_force(self, other: FluidProperties) -> float:
        """Calculate cohesion between two services (surface tension)."""
        similarity = 1.0 - abs(self.density - other.density)
        return similarity * (self.surface_tension + other.surface_tension) / 2


@dataclass
class LiquidicService:
    """A service that behaves like a liquid.

    Liquidic services flow to fill containers, adapt their shape
    to constraints, and merge/split based on pressure gradients.
    """

    service_id: str = ""
    name: str = ""
    flow_state: FlowState = FlowState.LIQUID
    properties: FluidProperties = field(default_factory=FluidProperties)
    current_pressure: Dict[PressureType, float] = field(default_factory=dict)
    capacity: float = 100.0  # Max throughput units
    current_load: float = 0.0  # Current throughput usage
    container_id: Optional[str] = None
    temperature: float = 20.0  # System "temperature" (load indicator)
    flow_rate: float = 0.0  # Current flow rate
    connected_services: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.service_id:
            self.service_id = f"liq-{uuid.uuid4().hex[:8]}"

    @property
    def utilization(self) -> float:
        """Current utilization ratio."""
        return self.current_load / self.capacity if self.capacity > 0 else 0.0

    @property
    def state_transition_temperature(self) -> float:
        """Temperature at which state transitions occur."""
        if self.flow_state == FlowState.SOLID:
            return 0.0  # Melting point
        elif self.flow_state == FlowState.LIQUID:
            return 100.0  # Boiling point
        elif self.flow_state == FlowState.GAS:
            return 10000.0  # Ionization point
        return float("inf")

    def apply_pressure(self, pressure_type: PressureType, magnitude: float) -> float:
        """Apply pressure to the service and return resulting flow."""
        self.current_pressure[pressure_type] = magnitude

        # Update temperature based on pressure
        total_pressure = sum(self.current_pressure.values())
        self.temperature = 20.0 + total_pressure * 0.5

        # State transitions based on temperature
        if self.temperature > self.state_transition_temperature:
            if self.flow_state == FlowState.LIQUID:
                self.flow_state = FlowState.GAS
                logger.info("Service %s transitioned: LIQUID -> GAS", self.service_id)
            elif self.flow_state == FlowState.GAS:
                self.flow_state = FlowState.PLASMA
                logger.info("Service %s transitioned: GAS -> PLASMA", self.service_id)

        # Calculate flow rate
        self.flow_rate = self.properties.effective_flow_rate(magnitude)
        return self.flow_rate

    def can_absorb(self, additional_load: float) -> bool:
        """Check if service can absorb additional load."""
        return (self.current_load + additional_load) <= (
            self.capacity * self.properties.compressibility
        )

    def absorb(self, additional_load: float) -> bool:
        """Try to absorb additional load (like a sponge)."""
        if self.can_absorb(additional_load):
            self.current_load += additional_load
            return True
        return False


@dataclass
class GasService:
    """A service that behaves like a gas.

    Gas services expand to fill all available space, scaling
    horizontally without explicit configuration.
    """

    service_id: str = ""
    name: str = ""
    properties: FluidProperties = field(
        default_factory=lambda: FluidProperties(
            viscosity=0.1, density=0.2, compressibility=0.95, volatility=0.8, conductivity=0.9
        )
    )
    instances: int = 1
    max_instances: int = 100
    min_instances: int = 1
    volume: float = 1.0  # Current service volume
    max_volume: float = 100.0  # Maximum expandable volume
    pressure: float = 1.0  # Current internal pressure
    temperature: float = 20.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.service_id:
            self.service_id = f"gas-{uuid.uuid4().hex[:8]}"

    @property
    def density(self) -> float:
        """Gas density = instances / volume."""
        return self.instances / self.volume if self.volume > 0 else 0

    def expand(self, available_space: float) -> int:
        """Expand gas service to fill available space.

        Returns number of new instances spawned.
        """
        if self.instances >= self.max_instances:
            return 0

        expansion = self.properties.expansion_factor(available_space)
        new_instances = min(
            int(self.instances * (expansion - 1.0)),
            self.max_instances - self.instances,
        )
        self.instances += new_instances
        self.volume = min(self.volume * expansion, self.max_volume)

        # Expansion reduces pressure (Boyle's law analog)
        if self.volume > 0:
            self.pressure = self.instances / self.volume

        return new_instances

    def compress(self, required_density: float) -> int:
        """Compress gas service by reducing instances.

        Returns number of instances removed.
        """
        if self.instances <= self.min_instances:
            return 0

        current_density = self.density
        if current_density >= required_density:
            return 0

        # Need to reduce instances to increase density
        target_instances = max(
            int(required_density * self.volume),
            self.min_instances,
        )
        removed = self.instances - target_instances
        if removed > 0:
            self.instances = target_instances
            self.volume = max(self.volume * 0.9, 1.0)
            if self.volume > 0:
                self.pressure = self.instances / self.volume

        return removed


@dataclass
class FlowContainer:
    """Container that constrains and shapes fluid services.

    Like physical containers shape liquids and gases, flow containers
    define the execution environment and constraints for services.
    """

    container_id: str = ""
    name: str = ""
    shape: ContainerShape = ContainerShape.PIPELINE
    capacity: float = 1000.0  # Total capacity units
    current_fill: float = 0.0  # Current fill level
    inlet_pressure: float = 1.0  # Pressure at inlet
    outlet_pressure: float = 0.5  # Pressure at outlet
    max_temperature: float = 1000.0  # Overheat threshold
    contained_services: List[str] = field(default_factory=list)
    properties: Dict[str, Any] = field(default_factory=dict)
    flow_direction: str = "forward"  # forward, reverse, bidirectional

    def __post_init__(self):
        if not self.container_id:
            self.container_id = f"cont-{uuid.uuid4().hex[:8]}"

    @property
    def pressure_gradient(self) -> float:
        """Pressure difference driving flow through container."""
        return self.inlet_pressure - self.outlet_pressure

    @property
    def fill_ratio(self) -> float:
        """How full the container is (0.0 to 1.0+)."""
        return self.current_fill / self.capacity if self.capacity > 0 else 0.0

    @property
    def is_overflowing(self) -> bool:
        """Whether the container is overflowing."""
        return self.current_fill > self.capacity

    def add_service(self, service_id: str, volume: float = 1.0) -> bool:
        """Add a service to the container."""
        if self.current_fill + volume > self.capacity * 1.2:  # 20% overflow margin
            return False
        self.contained_services.append(service_id)
        self.current_fill += volume
        return True

    def remove_service(self, service_id: str, volume: float = 1.0) -> bool:
        """Remove a service from the container."""
        if service_id in self.contained_services:
            self.contained_services.remove(service_id)
            self.current_fill = max(0, self.current_fill - volume)
            return True
        return False


@dataclass
class PressureValve:
    """Backpressure valve for flow control.

    Regulates flow rates between containers to prevent
    resource exhaustion and ensure smooth operation.
    """

    valve_id: str = ""
    name: str = ""
    source_container: str = ""  # container_id
    target_container: str = ""  # container_id
    max_flow_rate: float = 100.0  # Max throughput units/sec
    current_flow_rate: float = 0.0
    opening_ratio: float = 1.0  # 0.0 (closed) to 1.0 (fully open)
    trigger_pressure: float = 0.8  # Open when source pressure > this
    release_pressure: float = 0.3  # Close when source pressure < this
    valve_type: str = "safety"  # safety, regulator, check
    is_open: bool = True
    total_flow_through: float = 0.0

    def __post_init__(self):
        if not self.valve_id:
            self.valve_id = f"valve-{uuid.uuid4().hex[:8]}"

    def regulate(self, source_pressure: float) -> float:
        """Regulate flow based on source pressure."""
        if source_pressure >= self.trigger_pressure:
            self.is_open = True
            # Flow proportional to opening ratio and pressure
            self.current_flow_rate = self.max_flow_rate * self.opening_ratio * source_pressure
        elif source_pressure <= self.release_pressure:
            self.is_open = False
            self.current_flow_rate = 0.0
        else:
            # Partially open — linear interpolation
            ratio = (source_pressure - self.release_pressure) / (
                self.trigger_pressure - self.release_pressure
            )
            self.current_flow_rate = self.max_flow_rate * ratio * self.opening_ratio

        self.total_flow_through += self.current_flow_rate
        return self.current_flow_rate

    def emergency_close(self) -> None:
        """Emergency close the valve."""
        self.is_open = False
        self.opening_ratio = 0.0
        self.current_flow_rate = 0.0
        logger.warning("Emergency close on valve %s", self.valve_id)


class LiquidicFlowEngine:
    """Main engine for the liquidic/gas flow paradigm.

    Manages the lifecycle of liquidic and gas services, flow containers,
    and pressure valves. Provides unified orchestration of the fluid
    computing mesh.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self._liquidic_services: Dict[str, LiquidicService] = {}
        self._gas_services: Dict[str, GasService] = {}
        self._containers: Dict[str, FlowContainer] = {}
        self._valves: Dict[str, PressureValve] = {}
        self._flow_log: List[Dict[str, Any]] = []
        logger.info("LiquidicFlowEngine initialized")

    def register_liquidic_service(self, service: LiquidicService) -> str:
        """Register a liquidic service."""
        self._liquidic_services[service.service_id] = service
        logger.info("Registered liquidic service: %s", service.name)
        return service.service_id

    def register_gas_service(self, service: GasService) -> str:
        """Register a gas service."""
        self._gas_services[service.service_id] = service
        logger.info("Registered gas service: %s", service.name)
        return service.service_id

    def create_container(
        self,
        name: str,
        shape: ContainerShape = ContainerShape.PIPELINE,
        capacity: float = 1000.0,
    ) -> FlowContainer:
        """Create a flow container."""
        container = FlowContainer(name=name, shape=shape, capacity=capacity)
        self._containers[container.container_id] = container
        logger.info("Created container: %s (shape=%s, capacity=%.0f)", name, shape.value, capacity)
        return container

    def create_valve(
        self,
        name: str,
        source: str,
        target: str,
        max_flow_rate: float = 100.0,
    ) -> PressureValve:
        """Create a pressure valve between containers."""
        valve = PressureValve(
            name=name,
            source_container=source,
            target_container=target,
            max_flow_rate=max_flow_rate,
        )
        self._valves[valve.valve_id] = valve
        return valve

    def flow_through(
        self,
        service_id: str,
        container_id: str,
        volume: float = 1.0,
    ) -> bool:
        """Flow a service into a container."""
        container = self._containers.get(container_id)
        if not container:
            logger.error("Container %s not found", container_id)
            return False

        service = self._liquidic_services.get(service_id) or self._gas_services.get(service_id)
        if not service:
            logger.error("Service %s not found", service_id)
            return False

        if container.add_service(service_id, volume):
            if hasattr(service, "container_id"):
                service.container_id = container_id
            self._log_flow("flow_in", service_id, container_id, volume)
            return True

        self._log_flow("overflow", service_id, container_id, volume)
        return False

    def regulate_valves(self) -> Dict[str, float]:
        """Regulate all pressure valves based on current conditions."""
        results = {}
        for valve_id, valve in self._valves.items():
            source = self._containers.get(valve.source_container)
            if source:
                pressure = source.fill_ratio
                flow_rate = valve.regulate(pressure)
                results[valve_id] = flow_rate
        return results

    def auto_scale_gas_services(self) -> Dict[str, int]:
        """Auto-scale gas services based on container pressure."""
        scaling = {}
        for sid, gas in self._gas_services.items():
            container = self._containers.get(getattr(gas, "container_id", ""))
            if container and container.fill_ratio > 0.7:
                new_instances = gas.expand(container.capacity - container.current_fill)
                if new_instances > 0:
                    scaling[sid] = new_instances
                    logger.info("Gas service %s expanded by %d instances", sid, new_instances)
            elif container and container.fill_ratio < 0.2:
                removed = gas.compress(0.5)
                if removed > 0:
                    scaling[sid] = -removed
                    logger.info("Gas service %s compressed by %d instances", sid, removed)
        return scaling

    def calculate_flow_distribution(self) -> Dict[str, Dict[str, float]]:
        """Calculate optimal flow distribution across the mesh."""
        distribution = {}
        for container_id, container in self._containers.items():
            if not container.contained_services:
                continue

            n_services = len(container.contained_services)
            available_capacity = container.capacity - container.current_fill

            if n_services == 0:
                continue

            per_service = available_capacity / n_services
            distribution[container_id] = {sid: per_service for sid in container.contained_services}

        return distribution

    def find_flow_path(
        self,
        source_container: str,
        target_container: str,
    ) -> List[str]:
        """Find a flow path between two containers through valves."""
        # Build adjacency from valves
        adjacency: Dict[str, List[Tuple[str, str]]] = {}  # container -> [(valve_id, target)]
        for valve_id, valve in self._valves.items():
            if valve.source_container not in adjacency:
                adjacency[valve.source_container] = []
            adjacency[valve.source_container].append((valve_id, valve.target_container))

        # BFS
        visited = {source_container}
        queue = [(source_container, [])]

        while queue:
            current, path = queue.pop(0)
            if current == target_container:
                return path

            for valve_id, next_container in adjacency.get(current, []):
                if next_container not in visited:
                    visited.add(next_container)
                    queue.append((next_container, path + [valve_id]))

        return []  # No path found

    def get_mesh_topology(self) -> Dict[str, Any]:
        """Get the full mesh topology."""
        return {
            "liquidic_services": len(self._liquidic_services),
            "gas_services": len(self._gas_services),
            "containers": [
                {
                    "id": c.container_id,
                    "name": c.name,
                    "shape": c.shape.value,
                    "fill_ratio": c.fill_ratio,
                    "services": len(c.contained_services),
                }
                for c in self._containers.values()
            ],
            "valves": [
                {
                    "id": v.valve_id,
                    "name": v.name,
                    "source": v.source_container,
                    "target": v.target_container,
                    "is_open": v.is_open,
                    "flow_rate": v.current_flow_rate,
                }
                for v in self._valves.values()
            ],
            "total_flow_events": len(self._flow_log),
        }

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get comprehensive engine statistics."""
        total_liquidic_load = sum(s.current_load for s in self._liquidic_services.values())
        total_gas_instances = sum(g.instances for g in self._gas_services.values())

        return {
            "liquidic_services": {
                "count": len(self._liquidic_services),
                "total_load": total_liquidic_load,
                "states": {
                    state.value: sum(
                        1 for s in self._liquidic_services.values() if s.flow_state == state
                    )
                    for state in FlowState
                },
            },
            "gas_services": {
                "count": len(self._gas_services),
                "total_instances": total_gas_instances,
            },
            "containers": {
                "count": len(self._containers),
                "overflowing": sum(1 for c in self._containers.values() if c.is_overflowing),
            },
            "valves": {
                "count": len(self._valves),
                "open": sum(1 for v in self._valves.values() if v.is_open),
            },
            "flow_events": len(self._flow_log),
        }

    def _log_flow(self, event_type: str, service_id: str, container_id: str, volume: float):
        """Log a flow event."""
        self._flow_log.append(
            {
                "timestamp": time.time(),
                "event": event_type,
                "service_id": service_id,
                "container_id": container_id,
                "volume": volume,
            }
        )
