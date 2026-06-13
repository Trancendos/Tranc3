"""Aerial Drone Adapter — TranceX Phase 8

ROS2 + WasmEdge integration for real-time nested sensor queries on
aerial drones. Supports multi-drone swarm coordination, sensor fusion,
and edge-based NRC query processing for aerial data streams.

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DroneState(Enum):
    """Drone operational states."""

    IDLE = "idle"
    TAKEOFF = "takeoff"
    HOVERING = "hovering"
    FLYING = "flying"
    LANDING = "landing"
    EMERGENCY = "emergency"
    CHARGING = "charging"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"


class SensorType(Enum):
    """Types of drone sensors."""

    CAMERA_RGB = "camera_rgb"
    CAMERA_THERMAL = "camera_thermal"
    LIDAR = "lidar"
    RADAR = "radar"
    GPS = "gps"
    IMU = "imu"
    BAROMETER = "barometer"
    GAS_SENSOR = "gas_sensor"
    RADIATION = "radiation"
    MULTISPECTRAL = "multispectral"
    ACOUSTIC = "acoustic"


class SwarmFormation(Enum):
    """Drone swarm formation patterns."""

    LINE = "line"
    V_SHAPE = "v_shape"
    CIRCLE = "circle"
    GRID = "grid"
    SCATTER = "scatter"
    FOLLOW_LEADER = "follow_leader"
    ADAPTIVE = "adaptive"


@dataclass
class GeoCoordinate:
    """Geographic coordinate with altitude."""

    latitude: float = 0.0
    longitude: float = 0.0
    altitude_m: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class DroneSensorReading:
    """A single sensor reading from a drone."""

    reading_id: str = ""
    drone_id: str = ""
    sensor_type: SensorType = SensorType.CAMERA_RGB
    value: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    coordinate: Optional[GeoCoordinate] = None
    timestamp: float = field(default_factory=time.time)
    quality_score: float = 1.0

    def __post_init__(self):
        if not self.reading_id:
            self.reading_id = f"read-{uuid.uuid4().hex[:8]}"


@dataclass
class DroneCapabilities:
    """Capabilities of a drone."""

    max_altitude_m: float = 120.0
    max_speed_ms: float = 15.0
    max_flight_time_min: float = 30.0
    max_payload_kg: float = 2.0
    sensors: List[SensorType] = field(
        default_factory=lambda: [SensorType.CAMERA_RGB, SensorType.GPS]
    )
    wasm_runtime: bool = True
    edge_compute_tflops: float = 0.5
    battery_capacity_mah: float = 5000.0
    communication_range_m: float = 5000.0


@dataclass
class DroneNode:
    """Represents a single drone in the swarm."""

    drone_id: str = ""
    name: str = ""
    state: DroneState = DroneState.IDLE
    position: GeoCoordinate = field(default_factory=GeoCoordinate)
    capabilities: DroneCapabilities = field(default_factory=DroneCapabilities)
    battery_level: float = 100.0
    active_sensors: List[SensorType] = field(default_factory=list)
    current_mission: Optional[str] = None
    last_heartbeat: float = field(default_factory=time.time)
    wasm_module_id: Optional[str] = None
    sensor_buffer: List[DroneSensorReading] = field(default_factory=list)

    def __post_init__(self):
        if not self.drone_id:
            self.drone_id = f"drone-{uuid.uuid4().hex[:8]}"
        if not self.name:
            self.name = f"TranceX-{self.drone_id[-4:]}"

    @property
    def is_available(self) -> bool:
        """Check if drone is available for new missions."""
        return self.state in (DroneState.IDLE, DroneState.HOVERING) and self.battery_level > 20

    @property
    def can_execute_wasm(self) -> bool:
        """Check if drone can execute WASM modules."""
        return self.capabilities.wasm_runtime and self.state not in (
            DroneState.OFFLINE,
            DroneState.EMERGENCY,
        )


@dataclass
class DroneMission:
    """A mission assigned to one or more drones."""

    mission_id: str = ""
    name: str = ""
    waypoints: List[GeoCoordinate] = field(default_factory=list)
    sensors_to_activate: List[SensorType] = field(default_factory=list)
    nrc_query: str = ""
    formation: SwarmFormation = SwarmFormation.ADAPTIVE
    assigned_drones: List[str] = field(default_factory=list)
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    priority: int = 5
    results: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.mission_id:
            self.mission_id = f"miss-{uuid.uuid4().hex[:8]}"


class ROS2Bridge:
    """ROS2 communication bridge for drone coordination.

    Simulates ROS2 topics, services, and actions for drone control
    when real ROS2 is not available. In production, connects to
    actual ROS2 nodes via rclpy.
    """

    def __init__(self, namespace: str = "/trancex"):
        self.namespace = namespace
        self._publishers: Dict[str, List[Callable]] = {}
        self._subscribers: Dict[str, Callable] = {}
        self._services: Dict[str, Callable] = {}
        self._message_log: List[Dict[str, Any]] = []

    def create_publisher(self, topic: str, callback: Callable) -> None:
        """Register a publisher for a ROS2 topic."""
        self._publishers.setdefault(topic, []).append(callback)

    def create_subscriber(self, topic: str, callback: Callable) -> None:
        """Subscribe to a ROS2 topic."""
        self._subscribers[topic] = callback

    async def publish(self, topic: str, message: Dict[str, Any]) -> None:
        """Publish a message to a ROS2 topic."""
        full_topic = f"{self.namespace}{topic}"
        msg = {
            "topic": full_topic,
            "timestamp": time.time(),
            "data": message,
        }
        self._message_log.append(msg)

        if topic in self._subscribers:
            self._subscribers[topic](msg)

    async def call_service(self, service_name: str, request: Dict[str, Any]) -> Dict[str, Any]:
        """Call a ROS2 service."""
        if service_name in self._services:
            return self._services[service_name](request)
        return {"success": False, "error": f"Service {service_name} not found"}

    def register_service(self, service_name: str, handler: Callable) -> None:
        """Register a ROS2 service handler."""
        self._services[service_name] = handler

    def get_message_log(self) -> List[Dict[str, Any]]:
        """Get the message log."""
        return self._message_log.copy()


class WasmEdgeDroneExecutor:
    """WasmEdge executor for NRC queries on drone edge nodes.

    Deploys WASM-compiled NRC queries to drones for real-time
    sensor data processing without cloud round-trips.
    """

    def __init__(self, wasm_manager=None):
        self.wasm_manager = wasm_manager
        self._deployed_modules: Dict[str, str] = {}  # drone_id -> module_id

    async def deploy_query_to_drone(self, drone: DroneNode, nrc_query: str) -> Optional[str]:
        """Deploy an NRC query as a WASM module to a drone."""
        if not drone.can_execute_wasm:
            logger.warning(f"Drone {drone.drone_id} cannot execute WASM")
            return None

        if self.wasm_manager:
            try:
                from ..wasm_edge import NRCQueryWasm, EdgeTier

                query = NRCQueryWasm(
                    query_id=f"drone-{drone.drone_id}",
                    nrc_dsl=nrc_query,
                    target_tier=EdgeTier.AERIAL,
                )
                module = await self.wasm_manager.compile_and_deploy(query)
                drone.wasm_module_id = module.module_id
                self._deployed_modules[drone.drone_id] = module.module_id
                logger.info(f"Deployed WASM query to drone {drone.drone_id}")
                return module.module_id
            except Exception as e:
                logger.warning(f"WASM deployment to drone failed: {e}")

        # Fallback: mark as locally deployed
        module_id = f"wasm-drone-{drone.drone_id}"
        drone.wasm_module_id = module_id
        self._deployed_modules[drone.drone_id] = module_id
        return module_id

    async def execute_on_drone(self, drone: DroneNode, sensor_data: bytes) -> Optional[bytes]:
        """Execute the deployed WASM module on a drone with sensor data."""
        if not drone.wasm_module_id:
            return None

        if self.wasm_manager and drone.wasm_module_id in self.wasm_manager._module_registry:
            try:
                from ..wasm_edge import EdgeTier

                runtime = self.wasm_manager.runtimes[EdgeTier.AERIAL]
                result = await runtime.execute(drone.wasm_module_id, sensor_data)
                return result.output if result.success else None
            except Exception as e:
                logger.warning(f"WASM execution on drone failed: {e}")

        # Simulated execution
        try:
            data = json.loads(sensor_data) if sensor_data else {}
            result = {"processed": True, "drone_id": drone.drone_id, "data": data}
            return json.dumps(result).encode()
        except (json.JSONDecodeError, UnicodeDecodeError):
            return sensor_data


class SwarmCoordinator:
    """Multi-drone swarm coordination for distributed NRC queries.

    Manages drone fleet, assigns missions, coordinates formations,
    and aggregates results from multiple drones.
    """

    def __init__(
        self,
        ros2_bridge: Optional[ROS2Bridge] = None,
        wasm_executor: Optional[WasmEdgeDroneExecutor] = None,
    ):
        self.ros2 = ros2_bridge or ROS2Bridge()
        self.wasm_executor = wasm_executor or WasmEdgeDroneExecutor()
        self.drones: Dict[str, DroneNode] = {}
        self.missions: Dict[str, DroneMission] = {}

    def register_drone(self, drone: DroneNode) -> str:
        """Register a drone in the swarm."""
        self.drones[drone.drone_id] = drone
        logger.info(f"Registered drone {drone.name} ({drone.drone_id})")
        return drone.drone_id

    def deregister_drone(self, drone_id: str) -> None:
        """Remove a drone from the swarm."""
        self.drones.pop(drone_id, None)

    async def create_mission(
        self,
        name: str,
        waypoints: List[GeoCoordinate],
        nrc_query: str,
        sensors: Optional[List[SensorType]] = None,
        formation: SwarmFormation = SwarmFormation.ADAPTIVE,
        priority: int = 5,
    ) -> DroneMission:
        """Create a new drone mission with NRC query processing."""
        mission = DroneMission(
            name=name,
            waypoints=waypoints,
            sensors_to_activate=sensors or [SensorType.CAMERA_RGB],
            nrc_query=nrc_query,
            formation=formation,
            priority=priority,
        )

        # Assign available drones
        available = [d for d in self.drones.values() if d.is_available]
        n_drones = max(1, min(len(available), len(waypoints)))

        assigned = available[:n_drones]
        mission.assigned_drones = [d.drone_id for d in assigned]

        # Deploy WASM query to assigned drones
        for drone in assigned:
            await self.wasm_executor.deploy_query_to_drone(drone, nrc_query)
            drone.current_mission = mission.mission_id
            drone.state = DroneState.TAKEOFF

        self.missions[mission.mission_id] = mission
        logger.info(f"Created mission {mission.name} with {len(assigned)} drones")
        return mission

    async def execute_mission(self, mission_id: str) -> List[Dict[str, Any]]:
        """Execute a drone mission and collect results."""
        mission = self.missions.get(mission_id)
        if not mission:
            return []

        mission.status = "executing"
        results = []

        for drone_id in mission.assigned_drones:
            drone = self.drones.get(drone_id)
            if not drone:
                continue

            # Simulate sensor data collection
            sensor_readings = self._simulate_sensor_collection(drone, mission)

            # Process through WASM NRC query on drone
            sensor_data = json.dumps([r.__dict__ for r in sensor_readings]).encode()
            processed = await self.wasm_executor.execute_on_drone(drone, sensor_data)

            result = {
                "drone_id": drone_id,
                "readings": len(sensor_readings),
                "processed": processed is not None,
                "data": json.loads(processed) if processed else None,
            }
            results.append(result)

            # Update drone state
            drone.state = DroneState.HOVERING
            drone.battery_level = max(0, drone.battery_level - 5)

        mission.results = results
        mission.status = "completed"
        return results

    def _simulate_sensor_collection(
        self, drone: DroneNode, mission: DroneMission
    ) -> List[DroneSensorReading]:
        """Simulate sensor data collection from a drone."""
        readings = []
        for sensor in mission.sensors_to_activate:
            reading = DroneSensorReading(
                drone_id=drone.drone_id,
                sensor_type=sensor,
                value=self._generate_sensor_value(sensor),
                coordinate=drone.position,
                quality_score=max(0.5, 1.0 - (100 - drone.battery_level) * 0.005),
            )
            readings.append(reading)
        return readings

    def _generate_sensor_value(self, sensor: SensorType) -> Any:
        """Generate a simulated sensor value."""
        if sensor == SensorType.GPS:
            return {
                "lat": 37.7749 + (uuid.uuid4().int % 1000) * 0.0001,
                "lon": -122.4194 + (uuid.uuid4().int % 1000) * 0.0001,
            }
        elif sensor == SensorType.IMU:
            return {
                "accel_x": 0.1,
                "accel_y": 0.2,
                "accel_z": -9.8,
                "gyro_x": 0.0,
                "gyro_y": 0.0,
                "gyro_z": 0.0,
            }
        elif sensor == SensorType.BAROMETER:
            return {"pressure_hpa": 1013.25, "altitude_m": 50.0}
        elif sensor == SensorType.GAS_SENSOR:
            return {"co2_ppm": 400 + uuid.uuid4().int % 100, "voc_ppb": 50}
        elif sensor == SensorType.RADIATION:
            return {"dose_rate_usv_h": 0.1}
        else:
            return {"type": sensor.value, "simulated": True}

    def get_available_drones(self) -> List[DroneNode]:
        """Get all available drones in the swarm."""
        return [d for d in self.drones.values() if d.is_available]

    def get_swarm_status(self) -> Dict[str, Any]:
        """Get overall swarm status."""
        states = {}
        for d in self.drones.values():
            states[d.state.value] = states.get(d.state.value, 0) + 1

        return {
            "total_drones": len(self.drones),
            "available_drones": len(self.get_available_drones()),
            "state_distribution": states,
            "active_missions": sum(1 for m in self.missions.values() if m.status == "executing"),
            "total_missions": len(self.missions),
        }


class AerialDroneAdapter:
    """High-level aerial drone adapter for the TranceX ecosystem.

    Integrates ROS2 bridge, WasmEdge executor, and swarm coordination
    for seamless NRC query processing on aerial platforms.
    """

    def __init__(
        self,
        wasm_manager=None,
        namespace: str = "/trancex/aerial",
    ):
        self.ros2 = ROS2Bridge(namespace=namespace)
        self.wasm_executor = WasmEdgeDroneExecutor(wasm_manager=wasm_manager)
        self.swarm = SwarmCoordinator(
            ros2_bridge=self.ros2,
            wasm_executor=self.wasm_executor,
        )

    async def deploy_nrc_query(
        self, nrc_query: str, n_drones: int = 1, sensors: Optional[List[SensorType]] = None
    ) -> DroneMission:
        """Deploy an NRC query to the aerial drone swarm."""
        # Create waypoints based on available drones
        drones = self.swarm.get_available_drones()[:n_drones]
        waypoints = [d.position for d in drones] if drones else [GeoCoordinate()]

        mission = await self.swarm.create_mission(
            name=f"NRC-Query-{uuid.uuid4().hex[:6]}",
            waypoints=waypoints,
            nrc_query=nrc_query,
            sensors=sensors,
        )
        return mission

    async def execute_and_collect(self, mission_id: str) -> List[Dict[str, Any]]:
        """Execute a mission and collect NRC-processed results."""
        return await self.swarm.execute_mission(mission_id)

    def get_adapter_status(self) -> Dict[str, Any]:
        """Get the full adapter status."""
        return {
            "ros2_messages": len(self.ros2.get_message_log()),
            "swarm": self.swarm.get_swarm_status(),
            "wasm_deployments": len(self.wasm_executor._deployed_modules),
        }
