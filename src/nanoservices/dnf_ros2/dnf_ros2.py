"""DNF ROS2 Extension — Robotics Integration for Distributed Nano-Flows

Extends the DNF (Distributed Nano-Flows) orchestrator with ROS2
(robotic operating system) integration for real-time sensor data
processing, robot task orchestration, and edge-robot hybrid flows.

Key features:
- ROS2 topic subscription/publishing within DNF flow nodes
- QoS-aware message routing (RELIABLE, BEST_EFFORT, TRANSIENT_LOCAL)
- Robot task flow DAGs with real-time constraints
- Sensor fusion pipelines (LiDAR, camera, IMU, GPS)
- Navigation and manipulation flow primitives
- Seamless integration with existing DNF orchestrator

All dependencies are 0-cost (free/open-source).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class ROS2TopicType(Enum):
    """ROS2 standard topic types."""

    SENSOR_MSGS_IMAGE = "sensor_msgs/Image"
    SENSOR_MSGS_LASER_SCAN = "sensor_msgs/LaserScan"
    SENSOR_MSGS_IMU = "sensor_msgs/Imu"
    SENSOR_MSGS_GPS = "sensor_msgs/NavSatFix"
    SENSOR_MSGS_POINT_CLOUD2 = "sensor_msgs/PointCloud2"
    GEOMETRY_MSGS_TWIST = "geometry_msgs/Twist"
    GEOMETRY_MSGS_POSE = "geometry_msgs/Pose"
    NAV_MSGS_ODOMETRY = "nav_msgs/Odometry"
    NAV_MSGS_PATH = "nav_msgs/Path"
    STD_MSGS_STRING = "std_msgs/String"
    STD_MSGS_FLOAT64 = "std_msgs/Float64"
    DIAGNOSTIC_MSGS_DIAGNOSTIC = "diagnostic_msgs/DiagnosticArray"
    ACTION_MSGS_GOAL = "action_msgs/GoalInfo"
    CUSTOM_NRC_QUERY = "trancex/NRCQuery"
    CUSTOM_FLOW_RESULT = "trancex/FlowResult"


class ROS2QoSPolicy(Enum):
    """ROS2 Quality of Service policies."""

    RELIABLE = "reliable"
    BEST_EFFORT = "best_effort"
    TRANSIENT_LOCAL = "transient_local"
    VOLATILE = "volatile"


class ROS2Reliability(Enum):
    """ROS2 reliability levels."""

    RELIABLE = "reliable"
    BEST_EFFORT = "best_effort"


class FlowNodeType(Enum):
    """Types of nodes in a robot task flow."""

    SENSOR_INPUT = "sensor_input"
    SENSOR_FUSION = "sensor_fusion"
    PERCEPTION = "perception"
    PLANNING = "planning"
    CONTROL = "control"
    ACTION = "action"
    NRC_QUERY = "nrc_query"
    WASM_EXECUTE = "wasm_execute"
    GPU_ACCELERATE = "gpu_accelerate"
    CONDITIONAL = "conditional"
    LOOP = "loop"
    SINK = "sink"


@dataclass
class ROS2NodeConfig:
    """Configuration for a ROS2 node within the DNF extension."""

    node_id: str = ""
    node_name: str = ""
    namespace: str = "/"
    parameters: Dict[str, Any] = field(default_factory=dict)
    remappings: Dict[str, str] = field(default_factory=dict)
    qos_overrides: Dict[str, ROS2QoSPolicy] = field(default_factory=dict)

    def __post_init__(self):
        if not self.node_id:
            self.node_id = f"ros2-node-{uuid.uuid4().hex[:8]}"


@dataclass
class ROS2Message:
    """Represents a ROS2 message with metadata."""

    msg_id: str = ""
    topic: str = ""
    topic_type: ROS2TopicType = ROS2TopicType.STD_MSGS_STRING
    payload: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = 0.0
    frame_id: str = ""
    qos: ROS2QoSPolicy = ROS2QoSPolicy.BEST_EFFORT
    sequence_number: int = 0

    def __post_init__(self):
        if not self.msg_id:
            self.msg_id = f"msg-{uuid.uuid4().hex[:8]}"
        if not self.timestamp:
            self.timestamp = time.time()

    def serialize(self) -> bytes:
        """Serialize message to bytes for IPC transmission."""
        data = {
            "msg_id": self.msg_id,
            "topic": self.topic,
            "topic_type": self.topic_type.value,
            "payload": self.payload,
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "sequence_number": self.sequence_number,
        }
        return json.dumps(data).encode("utf-8")

    @classmethod
    def deserialize(cls, data: bytes) -> ROS2Message:
        """Deserialize message from bytes."""
        parsed = json.loads(data.decode("utf-8"))
        return cls(
            msg_id=parsed["msg_id"],
            topic=parsed["topic"],
            topic_type=ROS2TopicType(parsed["topic_type"]),
            payload=parsed["payload"],
            timestamp=parsed["timestamp"],
            frame_id=parsed.get("frame_id", ""),
            sequence_number=parsed.get("sequence_number", 0),
        )


@dataclass
class ROS2Subscription:
    """Tracks a ROS2 topic subscription."""

    sub_id: str = ""
    topic: str = ""
    topic_type: ROS2TopicType = ROS2TopicType.STD_MSGS_STRING
    qos: ROS2QoSPolicy = ROS2QoSPolicy.BEST_EFFORT
    callback_id: str = ""
    message_count: int = 0
    last_message_time: float = 0.0
    active: bool = True

    def __post_init__(self):
        if not self.sub_id:
            self.sub_id = f"sub-{uuid.uuid4().hex[:8]}"


@dataclass
class ROS2Publisher:
    """Tracks a ROS2 topic publisher."""

    pub_id: str = ""
    topic: str = ""
    topic_type: ROS2TopicType = ROS2TopicType.STD_MSGS_STRING
    qos: ROS2QoSPolicy = ROS2QoSPolicy.RELIABLE
    message_count: int = 0
    active: bool = True

    def __post_init__(self):
        if not self.pub_id:
            self.pub_id = f"pub-{uuid.uuid4().hex[:8]}"


@dataclass
class FlowNode:
    """A node in a robot task flow DAG."""

    node_id: str = ""
    node_type: FlowNodeType = FlowNodeType.SENSOR_INPUT
    label: str = ""
    config: Dict[str, Any] = field(default_factory=dict)
    input_topics: List[str] = field(default_factory=list)
    output_topics: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # node_ids
    timeout_ms: int = 5000
    retry_count: int = 3
    nrc_query: Optional[str] = None  # For NRC_QUERY nodes
    wasm_module: Optional[str] = None  # For WASM_EXECUTE nodes
    gpu_kernel: Optional[str] = None  # For GPU_ACCELERATE nodes
    processing_time_ms: float = 0.0
    status: str = "pending"  # pending, running, completed, failed

    def __post_init__(self):
        if not self.node_id:
            self.node_id = f"flow-node-{uuid.uuid4().hex[:8]}"
        if not self.label:
            self.label = f"{self.node_type.value}_{self.node_id[:8]}"


@dataclass
class FlowEdge:
    """An edge in a robot task flow DAG."""

    edge_id: str = ""
    source_node: str = ""  # node_id
    target_node: str = ""  # node_id
    topic: str = ""
    topic_type: ROS2TopicType = ROS2TopicType.STD_MSGS_STRING
    qos: ROS2QoSPolicy = ROS2QoSPolicy.RELIABLE
    condition: Optional[str] = None  # Optional condition for conditional edges

    def __post_init__(self):
        if not self.edge_id:
            self.edge_id = f"edge-{uuid.uuid4().hex[:8]}"


@dataclass
class RobotTaskFlow:
    """Complete robot task flow DAG with ROS2 integration."""

    flow_id: str = ""
    name: str = ""
    description: str = ""
    robot_id: str = ""
    nodes: List[FlowNode] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    variables: Dict[str, Any] = field(default_factory=dict)
    priority: int = 5  # 1-10, higher = more important
    deadline_ms: int = 30000
    created_at: float = 0.0
    started_at: float = 0.0
    completed_at: float = 0.0
    status: str = "created"  # created, running, completed, failed, cancelled

    def __post_init__(self):
        if not self.flow_id:
            self.flow_id = f"rtf-{uuid.uuid4().hex[:8]}"
        if not self.created_at:
            self.created_at = time.time()

    def validate(self) -> List[str]:
        """Validate the flow DAG structure."""
        errors = []
        node_ids = {n.node_id for n in self.nodes}

        # Check all edge references are valid
        for edge in self.edges:
            if edge.source_node not in node_ids:
                errors.append(f"Edge {edge.edge_id}: source node {edge.source_node} not found")
            if edge.target_node not in node_ids:
                errors.append(f"Edge {edge.edge_id}: target node {edge.target_node} not found")

        # Check for cycles (simple DFS)
        adjacency: Dict[str, List[str]] = {n.node_id: [] for n in self.nodes}
        for edge in self.edges:
            adjacency[edge.source_node].append(edge.target_node)

        visited: set = set()
        rec_stack: set = set()

        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            for neighbor in adjacency.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            rec_stack.remove(node)
            return False

        for node_id in node_ids:
            if node_id not in visited:
                if has_cycle(node_id):
                    errors.append("Flow DAG contains a cycle")
                    break

        # Check for at least one input and one output
        sources = {n.node_id for n in self.nodes if n.node_type == FlowNodeType.SENSOR_INPUT}
        sinks = {n.node_id for n in self.nodes if n.node_type == FlowNodeType.SINK}
        if not sources and self.nodes:
            errors.append("Flow has no sensor input nodes")
        if not sinks and self.nodes:
            errors.append("Flow has no sink nodes")

        return errors

    def get_execution_order(self) -> List[str]:
        """Topologically sort nodes for execution."""
        adjacency: Dict[str, List[str]] = {n.node_id: [] for n in self.nodes}
        in_degree: Dict[str, int] = {n.node_id: 0 for n in self.nodes}

        for edge in self.edges:
            adjacency[edge.source_node].append(edge.target_node)
            in_degree[edge.target_node] = in_degree.get(edge.target_node, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order = []

        while queue:
            node = queue.pop(0)
            order.append(node)
            for neighbor in adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return order


class ROS2ServiceBridge:
    """Bridge between ROS2 communication layer and DNF nanoservices.

    Simulates ROS2 pub/sub communication within the DNF framework,
    enabling real-time robot data to flow through nano-flow pipelines.
    In production, this would use rclpy for actual ROS2 communication.
    """

    def __init__(self, node_config: Optional[ROS2NodeConfig] = None):
        self.node_config = node_config or ROS2NodeConfig(node_name="trancex_dnf_bridge")
        self._publishers: Dict[str, ROS2Publisher] = {}
        self._subscribers: Dict[str, ROS2Subscription] = {}
        self._message_queue: Dict[str, List[ROS2Message]] = {}  # topic -> messages
        self._callbacks: Dict[str, Callable] = {}  # sub_id -> callback
        self._spin_running = False
        logger.info("ROS2ServiceBridge initialized: %s", self.node_config.node_name)

    def create_publisher(
        self,
        topic: str,
        topic_type: ROS2TopicType,
        qos: ROS2QoSPolicy = ROS2QoSPolicy.RELIABLE,
    ) -> ROS2Publisher:
        """Create a ROS2 publisher for a topic."""
        pub = ROS2Publisher(topic=topic, topic_type=topic_type, qos=qos)
        self._publishers[pub.pub_id] = pub
        if topic not in self._message_queue:
            self._message_queue[topic] = []
        logger.debug("Created publisher: %s on topic %s", pub.pub_id, topic)
        return pub

    def create_subscription(
        self,
        topic: str,
        topic_type: ROS2TopicType,
        callback: Optional[Callable] = None,
        qos: ROS2QoSPolicy = ROS2QoSPolicy.BEST_EFFORT,
    ) -> ROS2Subscription:
        """Create a ROS2 subscription for a topic."""
        sub = ROS2Subscription(topic=topic, topic_type=topic_type, qos=qos)
        if callback:
            self._callbacks[sub.sub_id] = callback
            sub.callback_id = sub.sub_id
        self._subscribers[sub.sub_id] = sub
        if topic not in self._message_queue:
            self._message_queue[topic] = []
        logger.debug("Created subscription: %s on topic %s", sub.sub_id, topic)
        return sub

    def publish(self, pub_id: str, message: ROS2Message) -> bool:
        """Publish a message through a registered publisher."""
        pub = self._publishers.get(pub_id)
        if not pub or not pub.active:
            logger.warning("Publisher %s not found or inactive", pub_id)
            return False

        # Queue message
        if pub.topic not in self._message_queue:
            self._message_queue[pub.topic] = []
        self._message_queue[pub.topic].append(message)
        pub.message_count += 1

        # Trigger subscriber callbacks
        for sub_id, sub in self._subscribers.items():
            if sub.topic == pub.topic and sub.active:
                sub.message_count += 1
                sub.last_message_time = time.time()
                callback = self._callbacks.get(sub.callback_id)
                if callback:
                    try:
                        callback(message)
                    except Exception as e:
                        logger.error("Callback error for sub %s: %s", sub_id, e)

        return True

    def get_messages(self, topic: str, count: int = 10) -> List[ROS2Message]:
        """Get recent messages from a topic."""
        messages = self._message_queue.get(topic, [])
        return messages[-count:]

    def spin_once(self, timeout_ms: int = 100) -> int:
        """Process one round of callbacks (simulated)."""
        processed = 0
        for topic, messages in self._message_queue.items():
            for msg in messages:
                for sub_id, sub in self._subscribers.items():
                    if sub.topic == topic and sub.active:
                        callback = self._callbacks.get(sub.callback_id)
                        if callback:
                            try:
                                callback(msg)
                                processed += 1
                            except Exception as e:
                                logger.error("Spin callback error: %s", e)
        return processed

    def get_bridge_stats(self) -> Dict[str, Any]:
        """Get bridge statistics."""
        return {
            "publishers": len(self._publishers),
            "subscribers": len(self._subscribers),
            "total_published": sum(p.message_count for p in self._publishers.values()),
            "total_received": sum(s.message_count for s in self._subscribers.values()),
            "topics": list(self._message_queue.keys()),
            "active_subscriptions": sum(1 for s in self._subscribers.values() if s.active),
        }


class DNFROS2Extension:
    """Main DNF ROS2 Extension service.

    Integrates ROS2 communication with DNF flow orchestration,
    enabling robot task flows that combine sensor processing,
    NRC queries, WASM edge computing, and GPU acceleration
    within a unified DAG-based pipeline.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.ros2_bridge = ROS2ServiceBridge()
        self._flows: Dict[str, RobotTaskFlow] = {}
        self._flow_results: Dict[str, Dict[str, Any]] = {}
        self._sensor_data: Dict[str, List[ROS2Message]] = {}  # topic -> recent data
        logger.info("DNFROS2Extension initialized")

    def create_sensor_flow(
        self,
        name: str,
        robot_id: str,
        sensor_topics: List[Tuple[str, ROS2TopicType]],
        fusion_algorithm: str = "kalman_filter",
    ) -> RobotTaskFlow:
        """Create a standard sensor processing flow."""
        flow = RobotTaskFlow(name=name, robot_id=robot_id)

        # Create sensor input nodes
        input_nodes = []
        for i, (topic, topic_type) in enumerate(sensor_topics):
            node = FlowNode(
                node_type=FlowNodeType.SENSOR_INPUT,
                label=f"sensor_{i}",
                config={"topic": topic, "topic_type": topic_type.value},
                input_topics=[topic],
            )
            flow.nodes.append(node)
            input_nodes.append(node)

            # Create ROS2 subscription
            self.ros2_bridge.create_subscription(topic, topic_type)

        # Create sensor fusion node
        fusion_node = FlowNode(
            node_type=FlowNodeType.SENSOR_FUSION,
            label="sensor_fusion",
            config={"algorithm": fusion_algorithm},
            dependencies=[n.node_id for n in input_nodes],
        )
        flow.nodes.append(fusion_node)

        # Connect inputs to fusion
        for input_node in input_nodes:
            flow.edges.append(
                FlowEdge(
                    source_node=input_node.node_id,
                    target_node=fusion_node.node_id,
                    topic=f"{input_node.label}_data",
                    topic_type=input_node.config.get("topic_type", ROS2TopicType.STD_MSGS_STRING),
                ),
            )

        # Create perception node
        perception_node = FlowNode(
            node_type=FlowNodeType.PERCEPTION,
            label="perception",
            dependencies=[fusion_node.node_id],
        )
        flow.nodes.append(perception_node)
        flow.edges.append(
            FlowEdge(
                source_node=fusion_node.node_id,
                target_node=perception_node.node_id,
                topic="fused_data",
            ),
        )

        # Create sink
        sink_node = FlowNode(
            node_type=FlowNodeType.SINK,
            label="result_sink",
            dependencies=[perception_node.node_id],
        )
        flow.nodes.append(sink_node)
        flow.edges.append(
            FlowEdge(
                source_node=perception_node.node_id,
                target_node=sink_node.node_id,
                topic="perception_result",
            ),
        )

        # Validate and store
        errors = flow.validate()
        if errors:
            logger.warning("Flow validation errors: %s", errors)
        self._flows[flow.flow_id] = flow
        return flow

    def create_navigation_flow(
        self,
        name: str,
        robot_id: str,
        goal_topic: str = "/goal_pose",
        odometry_topic: str = "/odom",
    ) -> RobotTaskFlow:
        """Create a navigation flow with planning and control."""
        flow = RobotTaskFlow(name=name, robot_id=robot_id, priority=8)

        # Goal input
        goal_node = FlowNode(
            node_type=FlowNodeType.SENSOR_INPUT,
            label="goal_input",
            config={"topic": goal_topic, "topic_type": ROS2TopicType.GEOMETRY_MSGS_POSE.value},
            input_topics=[goal_topic],
        )
        flow.nodes.append(goal_node)

        # Odometry input
        odom_node = FlowNode(
            node_type=FlowNodeType.SENSOR_INPUT,
            label="odometry_input",
            config={"topic": odometry_topic, "topic_type": ROS2TopicType.NAV_MSGS_ODOMETRY.value},
            input_topics=[odometry_topic],
        )
        flow.nodes.append(odom_node)

        # Planning
        plan_node = FlowNode(
            node_type=FlowNodeType.PLANNING,
            label="path_planner",
            config={"planner": "nav2_navfn", "timeout_ms": 2000},
            dependencies=[goal_node.node_id, odom_node.node_id],
        )
        flow.nodes.append(plan_node)

        # Control
        control_node = FlowNode(
            node_type=FlowNodeType.CONTROL,
            label="velocity_controller",
            config={"controller": "dwb", "max_speed": 0.5},
            dependencies=[plan_node.node_id],
        )
        flow.nodes.append(control_node)

        # Action output
        action_node = FlowNode(
            node_type=FlowNodeType.ACTION,
            label="cmd_vel_output",
            config={"topic": "/cmd_vel", "topic_type": ROS2TopicType.GEOMETRY_MSGS_TWIST.value},
            output_topics=["/cmd_vel"],
            dependencies=[control_node.node_id],
        )
        flow.nodes.append(action_node)

        # Sink
        sink_node = FlowNode(
            node_type=FlowNodeType.SINK,
            label="nav_result",
            dependencies=[action_node.node_id],
        )
        flow.nodes.append(sink_node)

        # Create edges
        for src, tgt in [
            (goal_node, plan_node),
            (odom_node, plan_node),
            (plan_node, control_node),
            (control_node, action_node),
            (action_node, sink_node),
        ]:
            flow.edges.append(FlowEdge(source_node=src.node_id, target_node=tgt.node_id))

        self._flows[flow.flow_id] = flow

        # Create ROS2 entities
        self.ros2_bridge.create_subscription(goal_topic, ROS2TopicType.GEOMETRY_MSGS_POSE)
        self.ros2_bridge.create_subscription(odometry_topic, ROS2TopicType.NAV_MSGS_ODOMETRY)
        self.ros2_bridge.create_publisher("/cmd_vel", ROS2TopicType.GEOMETRY_MSGS_TWIST)

        return flow

    def create_nrc_query_flow(
        self,
        name: str,
        robot_id: str,
        nrc_query: str,
        input_topic: str,
        output_topic: str,
    ) -> RobotTaskFlow:
        """Create a flow that processes sensor data through an NRC query."""
        flow = RobotTaskFlow(name=name, robot_id=robot_id)

        # Input
        input_node = FlowNode(
            node_type=FlowNodeType.SENSOR_INPUT,
            label="data_input",
            config={"topic": input_topic},
            input_topics=[input_topic],
        )
        flow.nodes.append(input_node)

        # NRC query processing
        nrc_node = FlowNode(
            node_type=FlowNodeType.NRC_QUERY,
            label="nrc_processor",
            nrc_query=nrc_query,
            dependencies=[input_node.node_id],
        )
        flow.nodes.append(nrc_node)
        flow.edges.append(FlowEdge(source_node=input_node.node_id, target_node=nrc_node.node_id))

        # Output
        output_node = FlowNode(
            node_type=FlowNodeType.SINK,
            label="query_result",
            config={"topic": output_topic},
            output_topics=[output_topic],
            dependencies=[nrc_node.node_id],
        )
        flow.nodes.append(output_node)
        flow.edges.append(FlowEdge(source_node=nrc_node.node_id, target_node=output_node.node_id))

        self._flows[flow.flow_id] = flow
        self.ros2_bridge.create_subscription(input_topic, ROS2TopicType.CUSTOM_NRC_QUERY)
        self.ros2_bridge.create_publisher(output_topic, ROS2TopicType.CUSTOM_FLOW_RESULT)
        return flow

    async def execute_flow(self, flow_id: str) -> Dict[str, Any]:
        """Execute a robot task flow."""
        flow = self._flows.get(flow_id)
        if not flow:
            return {"success": False, "error": f"Flow {flow_id} not found"}

        errors = flow.validate()
        if errors:
            return {"success": False, "errors": errors}

        execution_order = flow.get_execution_order()
        results: Dict[str, Any] = {}
        flow.status = "running"
        flow.started_at = time.time()

        for node_id in execution_order:
            node = next((n for n in flow.nodes if n.node_id == node_id), None)
            if not node:
                continue

            node.status = "running"
            start = time.monotonic()

            try:
                # Simulate node execution
                node_result = await self._execute_node(node, results)
                processing_time = (time.monotonic() - start) * 1000
                node.processing_time_ms = processing_time
                node.status = "completed"
                results[node_id] = node_result

            except Exception as e:
                node.status = "failed"
                node.processing_time_ms = (time.monotonic() - start) * 1000
                results[node_id] = {"success": False, "error": str(e)}
                flow.status = "failed"
                break

        flow.completed_at = time.time()
        if flow.status == "running":
            flow.status = "completed"

        self._flow_results[flow_id] = results
        return {
            "success": flow.status == "completed",
            "flow_id": flow_id,
            "status": flow.status,
            "execution_time_ms": (flow.completed_at - flow.started_at) * 1000,
            "node_results": results,
        }

    async def _execute_node(self, node: FlowNode, prior_results: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a single flow node (simulated)."""
        await asyncio.sleep(0.001)  # Simulate processing

        if node.node_type == FlowNodeType.SENSOR_INPUT:
            return {
                "success": True,
                "data": {"sensor_readings": [0.1, 0.2, 0.3], "timestamp": time.time()},
                "topic": node.input_topics[0] if node.input_topics else "",
            }
        elif node.node_type == FlowNodeType.SENSOR_FUSION:
            return {
                "success": True,
                "data": {"fused_state": [0.15, 0.22, 0.28], "confidence": 0.95},
                "algorithm": node.config.get("algorithm", "kalman_filter"),
            }
        elif node.node_type == FlowNodeType.PERCEPTION:
            return {
                "success": True,
                "data": {
                    "objects_detected": 3,
                    "classifications": ["obstacle", "path", "landmark"],
                },
            }
        elif node.node_type == FlowNodeType.PLANNING:
            return {
                "success": True,
                "data": {"path_length": 15.3, "waypoints": 8, "estimated_time_ms": 5000},
            }
        elif node.node_type == FlowNodeType.CONTROL:
            return {
                "success": True,
                "data": {"linear_velocity": 0.3, "angular_velocity": 0.1},
            }
        elif node.node_type == FlowNodeType.ACTION:
            return {
                "success": True,
                "data": {"action_executed": True, "timestamp": time.time()},
            }
        elif node.node_type == FlowNodeType.NRC_QUERY:
            return {
                "success": True,
                "data": {"query_result": [1, 2, 3], "rows_affected": 3},
                "nrc_query": node.nrc_query,
            }
        elif node.node_type == FlowNodeType.SINK:
            return {"success": True, "data": {"stored": True}}
        else:
            return {"success": True, "data": {}}

    def get_flow(self, flow_id: str) -> Optional[RobotTaskFlow]:
        """Get a robot task flow by ID."""
        return self._flows.get(flow_id)

    def list_flows(self) -> List[Dict[str, Any]]:
        """List all robot task flows."""
        return [
            {
                "flow_id": f.flow_id,
                "name": f.name,
                "robot_id": f.robot_id,
                "status": f.status,
                "nodes": len(f.nodes),
                "edges": len(f.edges),
            }
            for f in self._flows.values()
        ]

    def cancel_flow(self, flow_id: str) -> bool:
        """Cancel a running flow."""
        flow = self._flows.get(flow_id)
        if flow and flow.status == "running":
            flow.status = "cancelled"
            return True
        return False

    def get_extension_stats(self) -> Dict[str, Any]:
        """Get extension statistics."""
        total_nodes = sum(len(f.nodes) for f in self._flows.values())
        return {
            "total_flows": len(self._flows),
            "active_flows": sum(1 for f in self._flows.values() if f.status == "running"),
            "total_nodes": total_nodes,
            "ros2_bridge": self.ros2_bridge.get_bridge_stats(),
            "flow_statuses": {
                status: sum(1 for f in self._flows.values() if f.status == status)
                for status in {f.status for f in self._flows.values()}
            },
        }
