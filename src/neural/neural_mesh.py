# src/neural/neural_mesh.py
"""
Distributed Neural Computation Mesh for Tranc3.

A lightweight, zero-cost coordination layer that enables nanoservices to
operate as nodes in a computational mesh.  Unlike bio_neural's spiking
networks (which model individual neurons), the NeuralMesh models
*service-level* coordination: message passing, topology adaptation, and
collective signal propagation across the nanoservice fleet.

Key concepts
------------
- **MeshNode**: A nanoservice endpoint with signal I/O channels.
- **NeuralMesh**: The topology manager that routes signals, adapts
  connection strengths, and detects partitioned sub-meshes.
- **Signal propagation**: Messages flow along weighted edges; weights
  are reinforced by successful deliveries and decay over time (Hebbian-
  inspired plasticity).

Zero-cost guarantees
--------------------
- No external broker (Redis, Kafka, etc.); uses in-process asyncio queues.
- No paid APIs; all computation is local.
- Gracefully degrades when optional dependencies are unavailable.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ── Data structures ────────────────────────────────────────────────


class NodeState(str, Enum):
    """Lifecycle states for a mesh node."""

    INITIALIZING = "initializing"
    ACTIVE = "active"
    DRAINING = "draining"
    OFFLINE = "offline"


@dataclass
class MeshNode:
    """A single nanoservice endpoint in the neural mesh.

    Attributes
    ----------
    node_id : str
        Unique identifier (typically the service name).
    channels : Dict[str, asyncio.Queue]
        Named signal channels for receiving messages.
    state : NodeState
        Current lifecycle state.
    metadata : Dict[str, Any]
        Arbitrary metadata (version, capabilities, etc.).
    last_heartbeat : float
        Monotonic timestamp of the last heartbeat.
    signal_count : int
        Number of signals processed (for adaptive weighting).
    error_count : int
        Number of errors encountered.
    """

    node_id: str
    channels: Dict[str, asyncio.Queue] = field(default_factory=dict)
    state: NodeState = NodeState.INITIALIZING
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat: float = field(default_factory=time.monotonic)
    signal_count: int = 0
    error_count: int = 0

    def health_score(self) -> float:
        """Return a 0-1 health score based on signal/error ratio."""
        total = self.signal_count + self.error_count
        if total == 0:
            return 1.0
        return self.signal_count / total


@dataclass
class MeshEdge:
    """A weighted, directed connection between two mesh nodes.

    The weight is adapted using a Hebbian-inspired rule: successful
    signal deliveries strengthen the edge, while failures or timeouts
    weaken it.
    """

    source: str
    target: str
    weight: float = 1.0
    success_count: int = 0
    failure_count: int = 0
    last_used: float = 0.0

    def decay(self, rate: float = 0.01, minimum: float = 0.1) -> None:
        """Apply exponential decay to the edge weight."""
        self.weight = max(minimum, self.weight * (1.0 - rate))

    def reinforce(self, amount: float = 0.05, maximum: float = 2.0) -> None:
        """Strengthen the edge after a successful delivery."""
        self.weight = min(maximum, self.weight + amount)
        self.success_count += 1
        self.last_used = time.monotonic()

    def penalize(self, amount: float = 0.1, minimum: float = 0.1) -> None:
        """Weaken the edge after a failure or timeout."""
        self.weight = max(minimum, self.weight - amount)
        self.failure_count += 1


@dataclass
class Signal:
    """A message propagated through the neural mesh."""

    signal_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    source: str = ""
    channel: str = "default"
    payload: Any = None
    timestamp: float = field(default_factory=time.monotonic)
    ttl: int = 64  # hop limit to prevent infinite propagation


# ── Neural Mesh ────────────────────────────────────────────────────


class NeuralMesh:
    """Distributed neural computation mesh.

    Manages a dynamic topology of MeshNodes connected by weighted
    MeshEdges.  Signals are propagated along edges using weighted
    fan-out, with Hebbian-inspired plasticity adapting edge strengths
    over time.

    Parameters
    ----------
    decay_interval : float
        Seconds between periodic edge-weight decay sweeps.
    heartbeat_timeout : float
        Seconds before a node without a heartbeat is marked OFFLINE.
    max_channel_size : int
        Maximum items per asyncio.Queue channel (back-pressure).
    """

    def __init__(
        self,
        decay_interval: float = 60.0,
        heartbeat_timeout: float = 120.0,
        max_channel_size: int = 1000,
    ) -> None:
        self._nodes: Dict[str, MeshNode] = {}
        self._edges: Dict[str, MeshEdge] = {}  # key = "source->target"
        self._handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._decay_interval = decay_interval
        self._heartbeat_timeout = heartbeat_timeout
        self._max_channel_size = max_channel_size
        self._lock = asyncio.Lock()
        self._running = False
        self._decay_task: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None

    # ── Node management ────────────────────────────────────────────

    async def register_node(
        self,
        node_id: str,
        channels: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MeshNode:
        """Register a new nanoservice as a mesh node.

        Parameters
        ----------
        node_id : str
            Unique node identifier.
        channels : list[str], optional
            Named channels this node listens on.
        metadata : dict, optional
            Arbitrary metadata.

        Returns
        -------
        MeshNode
            The newly created node.

        Raises
        ------
        ValueError
            If a node with the same ID already exists.
        """
        async with self._lock:
            if node_id in self._nodes:
                raise ValueError(f"Node '{node_id}' already registered")
            ch_map: Dict[str, asyncio.Queue] = {}
            for ch in channels or ["default"]:
                ch_map[ch] = asyncio.Queue(maxsize=self._max_channel_size)
            node = MeshNode(
                node_id=node_id,
                channels=ch_map,
                metadata=metadata or {},
                state=NodeState.ACTIVE,
            )
            self._nodes[node_id] = node
            logger.info("neural_mesh: registered node=%s channels=%s", node_id, list(ch_map))
            return node

    async def deregister_node(self, node_id: str) -> None:
        """Gracefully remove a node from the mesh.

        Sets the node to DRAINING first, allowing in-flight signals to
        complete, then removes it after a brief delay.
        """
        async with self._lock:
            node = self._nodes.get(node_id)
            if node is None:
                return
            node.state = NodeState.DRAINING
        # Allow in-flight signals to drain
        await asyncio.sleep(0.1)
        async with self._lock:
            node.state = NodeState.OFFLINE
            # Remove edges involving this node
            keys_to_remove = [
                k for k in self._edges if k.startswith(f"{node_id}->") or k.endswith(f"->{node_id}")
            ]
            for k in keys_to_remove:
                del self._edges[k]
            del self._nodes[node_id]
            logger.info("neural_mesh: deregistered node=%s", node_id)

    async def heartbeat(self, node_id: str) -> None:
        """Record a heartbeat for the given node."""
        node = self._nodes.get(node_id)
        if node:
            node.last_heartbeat = time.monotonic()

    def get_node(self, node_id: str) -> Optional[MeshNode]:
        """Return a node by ID, or None."""
        return self._nodes.get(node_id)

    @property
    def nodes(self) -> Dict[str, MeshNode]:
        """Read-only view of all nodes."""
        return dict(self._nodes)

    # ── Edge management ────────────────────────────────────────────

    async def connect(
        self,
        source: str,
        target: str,
        weight: float = 1.0,
    ) -> MeshEdge:
        """Create or update a directed edge between two nodes.

        Both nodes must already be registered.
        """
        async with self._lock:
            if source not in self._nodes:
                raise ValueError(f"Source node '{source}' not registered")
            if target not in self._nodes:
                raise ValueError(f"Target node '{target}' not registered")
            key = f"{source}->{target}"
            if key in self._edges:
                self._edges[key].weight = weight
                return self._edges[key]
            edge = MeshEdge(source=source, target=target, weight=weight)
            self._edges[key] = edge
            logger.info("neural_mesh: connected %s -> %s (w=%.2f)", source, target, weight)
            return edge

    async def disconnect(self, source: str, target: str) -> None:
        """Remove a directed edge."""
        async with self._lock:
            key = f"{source}->{target}"
            self._edges.pop(key, None)

    def get_neighbors(self, node_id: str) -> List[Tuple[str, float]]:
        """Return [(neighbor_id, weight), ...] for outgoing edges."""
        result = []
        prefix = f"{node_id}->"
        for key, edge in self._edges.items():
            if key.startswith(prefix) and edge.weight > 0:
                result.append((edge.target, edge.weight))
        return sorted(result, key=lambda x: -x[1])

    # ── Signal propagation ─────────────────────────────────────────

    async def emit(self, signal: Signal) -> int:
        """Propagate a signal from its source to all connected neighbors.

        Uses weighted fan-out: the signal is placed on each neighbor's
        channel queue with a probability proportional to the edge weight.

        Returns
        -------
        int
            Number of neighbors that received the signal.
        """
        if signal.ttl <= 0:
            logger.debug("neural_mesh: signal %s expired (ttl=0)", signal.signal_id)
            return 0

        source_id = signal.source
        neighbors = self.get_neighbors(source_id)
        delivered = 0

        for target_id, weight in neighbors:
            # Skip very weak edges
            if weight < 0.2:
                continue
            target_node = self._nodes.get(target_id)
            if target_node is None or target_node.state != NodeState.ACTIVE:
                continue

            # Find matching channel
            channel = signal.channel
            queue = target_node.channels.get(channel) or target_node.channels.get("default")
            if queue is None:
                continue

            try:
                # Decrement TTL before forwarding so the hop limit is enforced.
                # We put a copy with ttl-1 to avoid mutating the original signal
                # (which may be forwarded to multiple neighbors in the same call).
                import dataclasses

                forwarded = dataclasses.replace(signal, ttl=signal.ttl - 1)
                queue.put_nowait(forwarded)
                delivered += 1
                # Reinforce successful edge
                edge_key = f"{source_id}->{target_id}"
                edge = self._edges.get(edge_key)
                if edge:
                    edge.reinforce()
            except asyncio.QueueFull:
                # Back-pressure: penalize edge
                edge_key = f"{source_id}->{target_id}"
                edge = self._edges.get(edge_key)
                if edge:
                    edge.penalize()
                logger.warning(
                    "neural_mesh: back-pressure on %s->%s/%s",
                    source_id,
                    target_id,
                    channel,
                )

        # Notify registered handlers
        for handler in self._handlers.get(signal.channel, []):
            try:
                result = handler(signal)
                if asyncio.iscoroutine(result):
                    await result
            except Exception as exc:
                logger.error("neural_mesh: handler error: %s", exc)

        return delivered

    async def receive(
        self,
        node_id: str,
        channel: str = "default",
        timeout: float = 5.0,
    ) -> Optional[Signal]:
        """Wait for a signal on a node's channel.

        Returns None if the timeout expires.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return None
        queue = node.channels.get(channel)
        if queue is None:
            return None
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    # ── Handler registration ───────────────────────────────────────

    def on_signal(self, channel: str, handler: Callable) -> None:
        """Register a signal handler for a given channel."""
        self._handlers[channel].append(handler)

    # ── Topology analysis ──────────────────────────────────────────

    def topology_snapshot(self) -> Dict[str, Any]:
        """Return a serializable snapshot of the mesh topology."""
        return {
            "nodes": {
                nid: {
                    "state": n.state.value,
                    "health": n.health_score(),
                    "signals": n.signal_count,
                    "errors": n.error_count,
                    "channels": list(n.channels.keys()),
                }
                for nid, n in self._nodes.items()
            },
            "edges": {
                key: {
                    "weight": e.weight,
                    "successes": e.success_count,
                    "failures": e.failure_count,
                }
                for key, e in self._edges.items()
            },
        }

    def find_partitions(self) -> List[Set[str]]:
        """Detect disconnected sub-meshes using BFS.

        Returns a list of sets, each containing the node IDs of one
        connected component (ignoring edge direction).
        """
        if not self._nodes:
            return []

        # Build undirected adjacency
        adj: Dict[str, Set[str]] = defaultdict(set)
        for _key, edge in self._edges.items():
            adj[edge.source].add(edge.target)
            adj[edge.target].add(edge.source)

        visited: Set[str] = set()
        partitions: List[Set[str]] = []

        for node_id in self._nodes:
            if node_id in visited:
                continue
            component: Set[str] = set()
            queue = [node_id]
            while queue:
                current = queue.pop(0)
                if current in visited:
                    continue
                visited.add(current)
                component.add(current)
                queue.extend(adj[current] - visited)
            partitions.append(component)

        return partitions

    # ── Background tasks ───────────────────────────────────────────

    async def start(self) -> None:
        """Start background decay and heartbeat monitoring."""
        if self._running:
            return
        self._running = True
        self._decay_task = asyncio.create_task(self._decay_loop())
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info("neural_mesh: started")

    async def stop(self) -> None:
        """Stop background tasks."""
        self._running = False
        for task in (self._decay_task, self._heartbeat_task):
            if task and not task.done():
                task.cancel()
        logger.info("neural_mesh: stopped")

    async def _decay_loop(self) -> None:
        """Periodically decay edge weights and remove dead edges."""
        while self._running:
            await asyncio.sleep(self._decay_interval)
            async with self._lock:
                dead_keys = []
                for key, edge in self._edges.items():
                    edge.decay()
                    if edge.weight <= 0.1 and edge.success_count == 0:
                        dead_keys.append(key)
                for key in dead_keys:
                    del self._edges[key]
                if dead_keys:
                    logger.debug("neural_mesh: pruned %d dead edges", len(dead_keys))

    async def _heartbeat_loop(self) -> None:
        """Mark nodes as OFFLINE if they miss heartbeats."""
        while self._running:
            await asyncio.sleep(self._heartbeat_timeout / 2)
            now = time.monotonic()
            for node in self._nodes.values():
                if node.state == NodeState.ACTIVE:
                    if now - node.last_heartbeat > self._heartbeat_timeout:
                        node.state = NodeState.OFFLINE
                        logger.warning("neural_mesh: node %s heartbeat timeout", node.node_id)
