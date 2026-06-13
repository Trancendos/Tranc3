"""Multi-Drone Swarm Simulation — Phase 9

Simulates and coordinates drone swarms using decentralized
consensus, formation control, and task allocation algorithms.
Integrates with the aerial_drone_adapter for ROS2 bridge support.
"""

from __future__ import annotations  # noqa: I001

import logging
import math
import random
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class DroneState(Enum):
    IDLE = "idle"
    FLYING = "flying"
    HOVERING = "hovering"
    RETURNING = "returning"
    CHARGING = "charging"
    EMERGENCY = "emergency"
    OFFLINE = "offline"


class FormationType(Enum):
    LINE = "line"
    V_SHAPE = "v_shape"
    CIRCLE = "circle"
    GRID = "grid"
    SWARM = "swarm"
    DIAMOND = "diamond"


class SwarmTaskType(Enum):
    SURVEY = "survey"
    DELIVERY = "delivery"
    SEARCH_RESCUE = "search_rescue"
    MAPPING = "mapping"
    SURVEILLANCE = "surveillance"
    FORMATION_FLY = "formation_fly"
    PERIMETER_SCAN = "perimeter_scan"


@dataclass
class GeoPosition:
    """3D geographic position."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    latitude: float = 0.0
    longitude: float = 0.0
    altitude: float = 0.0

    def distance_to(self, other: GeoPosition) -> float:
        return math.sqrt(
            (self.x - other.x) ** 2 + (self.y - other.y) ** 2 + (self.z - other.z) ** 2
        )

    def to_dict(self) -> Dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "lat": self.latitude,
            "lon": self.longitude,
            "alt": self.altitude,
        }


@dataclass
class DroneSpec:
    """Physical specification of a drone."""

    max_speed: float = 15.0
    max_altitude: float = 120.0
    battery_capacity: float = 100.0
    payload_capacity: float = 2.0
    flight_time_minutes: float = 30.0
    sensor_range: float = 100.0
    communication_range: float = 500.0


@dataclass
class SimDrone:
    """Simulated drone entity."""

    drone_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    state: DroneState = DroneState.IDLE
    position: GeoPosition = field(default_factory=GeoPosition)
    target_position: GeoPosition = field(default_factory=GeoPosition)
    velocity: GeoPosition = field(default_factory=GeoPosition)
    spec: DroneSpec = field(default_factory=DroneSpec)
    battery_level: float = 100.0
    current_task: Optional[str] = None
    swarm_id: Optional[str] = None
    neighbors: List[str] = field(default_factory=list)
    sensor_readings: Dict[str, float] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_position(self, dt: float = 0.1):
        if self.state in (DroneState.FLYING, DroneState.RETURNING):
            dx = self.target_position.x - self.position.x
            dy = self.target_position.y - self.position.y
            dz = self.target_position.z - self.position.z
            dist = math.sqrt(dx * dx + dy * dy + dz * dz)
            if dist < 0.5:
                self.position.x = self.target_position.x
                self.position.y = self.target_position.y
                self.position.z = self.target_position.z
                self.state = DroneState.HOVERING
            else:
                speed = min(self.spec.max_speed, dist / dt)
                self.position.x += (dx / dist) * speed * dt
                self.position.y += (dy / dist) * speed * dt
                self.position.z += (dz / dist) * speed * dt
                self.battery_level = max(0, self.battery_level - 0.05 * dt)

    def can_reach(self, target: GeoPosition) -> bool:
        dist = self.position.distance_to(target)
        battery_needed = dist * 0.01
        return self.battery_level >= battery_needed and dist <= self.spec.communication_range

    def to_dict(self) -> Dict[str, Any]:
        return {
            "drone_id": self.drone_id,
            "name": self.name,
            "state": self.state.value,
            "position": self.position.to_dict(),
            "target": self.target_position.to_dict(),
            "battery_level": self.battery_level,
            "current_task": self.current_task,
            "swarm_id": self.swarm_id,
            "neighbors": self.neighbors,
            "sensor_readings": self.sensor_readings,
        }


@dataclass
class SwarmTask:
    """A task assigned to the swarm."""

    task_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    task_type: SwarmTaskType = SwarmTaskType.SURVEY
    target_area: GeoPosition = field(default_factory=GeoPosition)
    radius: float = 100.0
    assigned_drones: List[str] = field(default_factory=list)
    status: str = "pending"
    priority: int = 0
    result: Optional[Dict[str, Any]] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "task_type": self.task_type.value,
            "target_area": self.target_area.to_dict(),
            "radius": self.radius,
            "assigned_drones": self.assigned_drones,
            "status": self.status,
            "priority": self.priority,
            "result": self.result,
            "created_at": self.created_at,
        }


class FormationController:
    """Controls drone formation patterns."""

    def compute_formation(
        self, center: GeoPosition, formation: FormationType, num_drones: int, spacing: float = 10.0
    ) -> List[GeoPosition]:
        positions = []
        if formation == FormationType.LINE:
            for i in range(num_drones):
                offset = (i - num_drones / 2) * spacing
                positions.append(GeoPosition(x=center.x + offset, y=center.y, z=center.z))
        elif formation == FormationType.V_SHAPE:
            for i in range(num_drones):
                row = i // 2 + 1
                side = 1 if i % 2 == 0 else -1
                positions.append(
                    GeoPosition(
                        x=center.x - row * spacing * 0.7,
                        y=center.y + side * row * spacing * 0.5,
                        z=center.z,
                    )
                )
        elif formation == FormationType.CIRCLE:
            for i in range(num_drones):
                angle = 2 * math.pi * i / num_drones
                positions.append(
                    GeoPosition(
                        x=center.x + spacing * math.cos(angle),
                        y=center.y + spacing * math.sin(angle),
                        z=center.z,
                    )
                )
        elif formation == FormationType.GRID:
            cols = int(math.ceil(math.sqrt(num_drones)))
            for i in range(num_drones):
                row, col = divmod(i, cols)
                positions.append(
                    GeoPosition(
                        x=center.x + col * spacing - (cols - 1) * spacing / 2,
                        y=center.y + row * spacing,
                        z=center.z,
                    )
                )
        elif formation == FormationType.DIAMOND:
            half = num_drones // 2
            for i in range(num_drones):
                if i < half:
                    row = i
                    spread = i + 1
                else:
                    row = num_drones - 1 - i
                    spread = num_drones - i
                positions.append(
                    GeoPosition(
                        x=center.x + row * spacing * 0.7,
                        y=center.y + (i % 2 * 2 - 1) * spread * spacing * 0.3,
                        z=center.z,
                    )
                )
        else:
            for i in range(num_drones):
                angle = random.uniform(0, 2 * math.pi)
                r = random.uniform(0, spacing * 2)
                positions.append(
                    GeoPosition(
                        x=center.x + r * math.cos(angle),
                        y=center.y + r * math.sin(angle),
                        z=center.z + random.uniform(-2, 2),
                    )
                )
        return positions


class TaskAllocator:
    """Allocates swarm tasks to individual drones using auction-based allocation."""

    def allocate(self, task: SwarmTask, drones: Dict[str, SimDrone]) -> List[str]:
        available = {
            did: d
            for did, d in drones.items()
            if d.state == DroneState.IDLE and d.battery_level > 20
        }
        if not available:
            return []

        bids: List[Tuple[float, str]] = []
        for did, drone in available.items():
            dist = drone.position.distance_to(task.target_area)
            battery_factor = drone.battery_level / 100.0
            bid = battery_factor / (1 + dist)
            bids.append((bid, did))

        bids.sort(key=lambda x: x[0], reverse=True)
        needed = max(1, min(len(bids), 3))
        assigned = [did for _, did in bids[:needed]]
        return assigned


class SwarmCoordinator:
    """Decentralized swarm coordination using consensus."""

    def __init__(self, swarm_id: str, drones: Optional[List[SimDrone]] = None):
        self.swarm_id = swarm_id
        self.drones: Dict[str, SimDrone] = {}
        self.formation_controller = FormationController()
        self.task_allocator = TaskAllocator()
        self.current_formation = FormationType.SWARM
        self.tasks: Dict[str, SwarmTask] = {}
        self._consensus_state: Dict[str, Any] = {}

        if drones:
            for d in drones:
                self.drones[d.drone_id] = d

    def add_drone(self, drone: SimDrone) -> bool:
        drone.swarm_id = self.swarm_id
        self.drones[drone.drone_id] = drone
        self._update_neighbors()
        return True

    def remove_drone(self, drone_id: str) -> bool:
        if drone_id in self.drones:
            self.drones[drone_id].state = DroneState.OFFLINE
            del self.drones[drone_id]
            self._update_neighbors()
            return True
        return False

    def _update_neighbors(self):
        drone_list = list(self.drones.values())
        for drone in drone_list:
            neighbors = []
            for other in drone_list:
                if other.drone_id != drone.drone_id:
                    dist = drone.position.distance_to(other.position)
                    if dist <= drone.spec.communication_range:
                        neighbors.append(other.drone_id)
            drone.neighbors = neighbors

    def set_formation(
        self, formation: FormationType, center: Optional[GeoPosition] = None, spacing: float = 10.0
    ):
        self.current_formation = formation
        if center is None:
            positions = [d.position for d in self.drones.values()]
            if positions:
                center = GeoPosition(
                    x=sum(p.x for p in positions) / len(positions),
                    y=sum(p.y for p in positions) / len(positions),
                    z=sum(p.z for p in positions) / len(positions),
                )
            else:
                center = GeoPosition()

        target_positions = self.formation_controller.compute_formation(
            center, formation, len(self.drones), spacing
        )
        for i, drone in enumerate(self.drones.values()):
            if i < len(target_positions):
                drone.target_position = target_positions[i]
                drone.state = DroneState.FLYING

    def assign_task(self, task: SwarmTask) -> SwarmTask:
        assigned = self.task_allocator.allocate(task, self.drones)
        for did in assigned:
            self.drones[did].current_task = task.task_id
            self.drones[did].target_position = task.target_area
            self.drones[did].state = DroneState.FLYING
        task.assigned_drones = assigned
        task.status = "in_progress"
        self.tasks[task.task_id] = task
        return task

    def simulate_step(self, dt: float = 0.1):
        for drone in self.drones.values():
            drone.update_position(dt)
            for sensor in ["temperature", "humidity", "pressure", "wind_speed"]:
                drone.sensor_readings[sensor] = round(random.uniform(0, 100), 2)
        self._update_neighbors()

    def get_swarm_status(self) -> Dict[str, Any]:
        active = sum(1 for d in self.drones.values() if d.state != DroneState.OFFLINE)
        avg_battery = (
            (sum(d.battery_level for d in self.drones.values()) / len(self.drones))
            if self.drones
            else 0
        )
        return {
            "swarm_id": self.swarm_id,
            "total_drones": len(self.drones),
            "active_drones": active,
            "average_battery": round(avg_battery, 2),
            "current_formation": self.current_formation.value,
            "tasks": {tid: t.to_dict() for tid, t in self.tasks.items()},
            "drone_states": {did: d.state.value for did, d in self.drones.items()},
        }


class MultiDroneSwarmSimulation:
    """Multi-drone swarm simulation environment.

    Features:
    - Multiple independent swarms with inter-swarm coordination
    - Formation control (line, V-shape, circle, grid, diamond, swarm)
    - Auction-based task allocation
    - Decentralized consensus for swarm decisions
    - Battery management and range constraints
    - Sensor simulation and neighbor detection
    - Integration with aerial_drone_adapter for real drone bridge
    """

    def __init__(self):
        self.swarms: Dict[str, SwarmCoordinator] = {}
        self.all_drones: Dict[str, SimDrone] = {}
        self.global_tasks: Dict[str, SwarmTask] = {}
        self.simulation_time: float = 0.0
        self._id = str(uuid.uuid4())[:8]

    def create_swarm(
        self, swarm_id: Optional[str] = None, num_drones: int = 5, spec: Optional[DroneSpec] = None
    ) -> SwarmCoordinator:
        sid = swarm_id or f"swarm-{str(uuid.uuid4())[:6]}"
        drones = []
        drone_spec = spec or DroneSpec()
        for i in range(num_drones):
            drone = SimDrone(
                name=f"{sid}-drone-{i}",
                spec=drone_spec,
                position=GeoPosition(
                    x=random.uniform(-50, 50),
                    y=random.uniform(-50, 50),
                    z=random.uniform(10, 50),
                ),
            )
            drones.append(drone)
            self.all_drones[drone.drone_id] = drone

        coordinator = SwarmCoordinator(sid, drones)
        self.swarms[sid] = coordinator
        logger.info("Created swarm %s with %d drones", sid, num_drones)
        return coordinator

    def remove_swarm(self, swarm_id: str) -> bool:
        if swarm_id in self.swarms:
            for did in list(self.swarms[swarm_id].drones.keys()):
                self.all_drones.pop(did, None)
            del self.swarms[swarm_id]
            return True
        return False

    def create_task(
        self, task_type: SwarmTaskType, target: GeoPosition, priority: int = 0
    ) -> SwarmTask:
        task = SwarmTask(
            task_type=task_type,
            target_area=target,
            priority=priority,
        )
        self.global_tasks[task.task_id] = task
        return task

    def distribute_task(self, task: SwarmTask) -> Dict[str, Any]:
        best_swarm = None
        best_score = -1
        for sid, swarm in self.swarms.items():
            active = sum(1 for d in swarm.drones.values() if d.state == DroneState.IDLE)
            if active > 0:
                center_x = sum(d.position.x for d in swarm.drones.values()) / len(swarm.drones)
                center_y = sum(d.position.y for d in swarm.drones.values()) / len(swarm.drones)
                dist = math.sqrt(
                    (center_x - task.target_area.x) ** 2 + (center_y - task.target_area.y) ** 2
                )
                score = active / (1 + dist)
                if score > best_score:
                    best_score = score
                    best_swarm = swarm

        if best_swarm:
            result = best_swarm.assign_task(task)
            return {"assigned_to": best_swarm.swarm_id, "task": result.to_dict()}

        return {"assigned_to": None, "task": task.to_dict(), "error": "No available swarm"}

    def simulate(self, steps: int = 10, dt: float = 0.1) -> Dict[str, Any]:
        for _ in range(steps):
            for swarm in self.swarms.values():
                swarm.simulate_step(dt)
            self.simulation_time += dt

        return {
            "simulation_id": self._id,
            "simulation_time": round(self.simulation_time, 2),
            "total_drones": len(self.all_drones),
            "total_swarms": len(self.swarms),
            "swarm_statuses": {sid: s.get_swarm_status() for sid, s in self.swarms.items()},
        }

    def get_simulation_status(self) -> Dict[str, Any]:
        return {
            "simulation_id": self._id,
            "simulation_time": round(self.simulation_time, 2),
            "total_drones": len(self.all_drones),
            "total_swarms": len(self.swarms),
            "total_tasks": len(self.global_tasks),
            "drone_summary": {
                did: {
                    "state": d.state.value,
                    "battery": round(d.battery_level, 2),
                    "position": d.position.to_dict(),
                }
                for did, d in self.all_drones.items()
            },
        }
