"""
Tranc3 Sentinel Station Clustering
====================================
Redis Cluster support for Sentinel Station HA with automatic failover,
partition handling, and cluster node management.

Architecture:
    - SentinelClusterNode: Individual node in the sentinel cluster
    - SentinelCluster: Cluster manager with node coordination and failover
    - ClusterPartition: Represents a network partition scenario
    - SentinelClusterManager: Top-level manager for cluster lifecycle
"""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────


class NodeRole(str, Enum):
    """Role of a sentinel cluster node."""

    PRIMARY = "primary"
    REPLICA = "replica"


class NodeState(str, Enum):
    """State of a sentinel cluster node."""

    ONLINE = "online"
    OFFLINE = "offline"
    SYNCING = "syncing"
    FAILING_OVER = "failing_over"
    PARTITIONED = "partitioned"


class ClusterHealth(str, Enum):
    """Health status of the cluster."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    CRITICAL = "critical"
    DOWN = "down"


class FailoverPolicy(str, Enum):
    """Policy for failover behavior."""

    AUTOMATIC = "automatic"
    MANUAL = "manual"
    PRIORITY_BASED = "priority_based"


# ──────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────


class SentinelClusterNode(BaseModel):
    """A node in the sentinel cluster."""

    node_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    host: str = "localhost"
    port: int = 6379
    role: NodeRole = NodeRole.REPLICA
    state: NodeState = NodeState.ONLINE
    priority: int = 100
    slots: List[int] = Field(default_factory=list)
    last_heartbeat: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def mark_online(self) -> None:
        self.state = NodeState.ONLINE
        self.last_heartbeat = datetime.now(timezone.utc).isoformat()

    def mark_offline(self) -> None:
        self.state = NodeState.OFFLINE

    def mark_partitioned(self) -> None:
        self.state = NodeState.PARTITIONED

    def promote_to_primary(self) -> None:
        self.role = NodeRole.PRIMARY
        self.state = NodeState.ONLINE

    def demote_to_replica(self) -> None:
        self.role = NodeRole.REPLICA
        self.state = NodeState.SYNCING


class ClusterPartition(BaseModel):
    """Represents a network partition in the cluster."""

    partition_id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    isolated_nodes: List[str] = Field(default_factory=list)
    majority_nodes: List[str] = Field(default_factory=list)
    detected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    resolved_at: Optional[str] = None
    resolved: bool = False


class ClusterConfig(BaseModel):
    """Configuration for the sentinel cluster."""

    cluster_name: str = "sentinel-cluster"
    min_replicas: int = 2
    failover_policy: FailoverPolicy = FailoverPolicy.AUTOMATIC
    heartbeat_interval_seconds: float = 1.0
    failover_timeout_seconds: float = 30.0
    partition_threshold: int = 3  # Minimum majority nodes to stay healthy
    slot_count: int = 16384  # Redis-style slot count


# ──────────────────────────────────────────────
# Sentinel Cluster
# ──────────────────────────────────────────────


class SentinelCluster:
    """Manages a sentinel cluster with primary-replica topology and failover."""

    def __init__(self, config: Optional[ClusterConfig] = None) -> None:
        self.config = config or ClusterConfig()
        self._nodes: Dict[str, SentinelClusterNode] = {}
        self._primary_id: Optional[str] = None
        self._partitions: List[ClusterPartition] = []
        self._failover_count: int = 0
        self._started: bool = False
        self._started_at: Optional[str] = None

    @property
    def nodes(self) -> Dict[str, SentinelClusterNode]:
        return self._nodes

    @property
    def primary(self) -> Optional[SentinelClusterNode]:
        if self._primary_id:
            return self._nodes.get(self._primary_id)
        return None

    @property
    def replicas(self) -> List[SentinelClusterNode]:
        return [n for n in self._nodes.values() if n.role == NodeRole.REPLICA]

    @property
    def online_nodes(self) -> List[SentinelClusterNode]:
        return [n for n in self._nodes.values() if n.state == NodeState.ONLINE]

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    def add_node(self, node: SentinelClusterNode) -> SentinelClusterNode:
        """Add a node to the cluster."""
        self._nodes[node.node_id] = node
        if node.role == NodeRole.PRIMARY:
            if self._primary_id and self._primary_id != node.node_id:
                # Demote existing primary
                old_primary = self._nodes.get(self._primary_id)
                if old_primary:
                    old_primary.demote_to_replica()
            self._primary_id = node.node_id
        node.mark_online()
        return node

    def remove_node(self, node_id: str) -> Optional[SentinelClusterNode]:
        """Remove a node from the cluster."""
        node = self._nodes.pop(node_id, None)
        if node and node_id == self._primary_id:
            self._primary_id = None
            # Auto-promote highest priority replica
            self._auto_failover()
        return node

    def get_node(self, node_id: str) -> Optional[SentinelClusterNode]:
        """Get a node by ID."""
        return self._nodes.get(node_id)

    def _auto_failover(self) -> Optional[SentinelClusterNode]:
        """Perform automatic failover to the highest priority online replica."""
        if self.config.failover_policy == FailoverPolicy.MANUAL:
            logger.warning("Manual failover policy — not auto-promoting")
            return None

        candidates = [
            n
            for n in self._nodes.values()
            if n.role == NodeRole.REPLICA and n.state == NodeState.ONLINE
        ]

        if not candidates:
            logger.error("No eligible replicas for failover")
            return None

        # Sort by priority (lower number = higher priority)
        candidates.sort(key=lambda n: n.priority)
        new_primary = candidates[0]
        new_primary.promote_to_primary()
        self._primary_id = new_primary.node_id
        self._failover_count += 1
        logger.info(f"Failover: promoted node {new_primary.node_id} to primary")
        return new_primary

    def perform_failover(
        self, target_node_id: Optional[str] = None
    ) -> Optional[SentinelClusterNode]:
        """Manually trigger failover, optionally to a specific node."""
        if self._primary_id:
            old_primary = self._nodes.get(self._primary_id)
            if old_primary:
                old_primary.demote_to_replica()

        if target_node_id:
            target = self._nodes.get(target_node_id)
            if target and target.state == NodeState.ONLINE:
                target.promote_to_primary()
                self._primary_id = target.node_id
                self._failover_count += 1
                return target
            return None

        return self._auto_failover()

    def detect_partition(self, offline_node_ids: List[str]) -> Optional[ClusterPartition]:
        """Detect a network partition based on which nodes went offline."""
        online_ids = [
            nid
            for nid, n in self._nodes.items()
            if n.state == NodeState.ONLINE and nid not in offline_node_ids
        ]

        partition = ClusterPartition(
            isolated_nodes=offline_node_ids,
            majority_nodes=online_ids,
        )

        # Mark isolated nodes as partitioned
        for nid in offline_node_ids:
            node = self._nodes.get(nid)
            if node:
                node.mark_partitioned()

        self._partitions.append(partition)
        return partition

    def resolve_partition(self, partition_id: str) -> bool:
        """Resolve a network partition."""
        for partition in self._partitions:
            if partition.partition_id == partition_id and not partition.resolved:
                partition.resolved = True
                partition.resolved_at = datetime.now(timezone.utc).isoformat()
                # Bring partitioned nodes back online
                for nid in partition.isolated_nodes:
                    node = self._nodes.get(nid)
                    if node and node.state == NodeState.PARTITIONED:
                        node.mark_online()
                return True
        return False

    def get_health(self) -> ClusterHealth:
        """Get the current health of the cluster."""
        if not self._nodes:
            return ClusterHealth.DOWN

        online_count = len(self.online_nodes)
        total_count = self.node_count

        if online_count == 0:
            return ClusterHealth.DOWN

        if not self._primary_id or self.primary is None:
            return ClusterHealth.CRITICAL

        if online_count < self.config.min_replicas + 1:
            return ClusterHealth.DEGRADED

        if online_count == total_count:
            return ClusterHealth.HEALTHY

        # More than half online is degraded, otherwise critical
        if online_count > total_count / 2:
            return ClusterHealth.DEGRADED

        return ClusterHealth.CRITICAL

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get comprehensive cluster status."""
        return {
            "cluster_name": self.config.cluster_name,
            "started": self._started,
            "started_at": self._started_at,
            "health": self.get_health().value,
            "node_count": self.node_count,
            "online_count": len(self.online_nodes),
            "primary_id": self._primary_id,
            "failover_count": self._failover_count,
            "active_partitions": len([p for p in self._partitions if not p.resolved]),
            "nodes": {
                nid: {
                    "role": n.role.value,
                    "state": n.state.value,
                    "priority": n.priority,
                    "host": n.host,
                    "port": n.port,
                }
                for nid, n in self._nodes.items()
            },
        }

    async def start(self) -> None:
        """Start the sentinel cluster."""
        self._started = True
        self._started_at = datetime.now(timezone.utc).isoformat()
        # Heartbeat all nodes
        for node in self._nodes.values():
            node.mark_online()

    async def stop(self) -> None:
        """Stop the sentinel cluster."""
        self._started = False
        for node in self._nodes.values():
            node.mark_offline()

    def allocate_slots(self, node_id: str, slots: List[int]) -> bool:
        """Allocate hash slots to a node."""
        node = self._nodes.get(node_id)
        if not node:
            return False
        node.slots = slots
        return True

    def get_slot_owner(self, slot: int) -> Optional[SentinelClusterNode]:
        """Find which node owns a given hash slot."""
        for node in self._nodes.values():
            if slot in node.slots:
                return node
        return None


# ──────────────────────────────────────────────
# Sentinel Cluster Manager
# ──────────────────────────────────────────────


class SentinelClusterManager:
    """Top-level manager for multiple sentinel clusters."""

    def __init__(self) -> None:
        self._clusters: Dict[str, SentinelCluster] = {}

    def create_cluster(self, config: Optional[ClusterConfig] = None) -> SentinelCluster:
        """Create a new sentinel cluster."""
        cluster = SentinelCluster(config)
        self._clusters[cluster.config.cluster_name] = cluster
        return cluster

    def get_cluster(self, name: str) -> Optional[SentinelCluster]:
        """Get a cluster by name."""
        return self._clusters.get(name)

    def remove_cluster(self, name: str) -> bool:
        """Remove a cluster by name."""
        if name in self._clusters:
            del self._clusters[name]
            return True
        return False

    def list_clusters(self) -> List[str]:
        """List all cluster names."""
        return list(self._clusters.keys())

    def get_status(self) -> Dict[str, Any]:
        """Get manager status."""
        return {
            "cluster_count": len(self._clusters),
            "clusters": {
                name: cluster.get_cluster_status() for name, cluster in self._clusters.items()
            },
        }


# ──────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────

_manager: Optional[SentinelClusterManager] = None


def get_sentinel_cluster_manager() -> SentinelClusterManager:
    """Get or create the global SentinelClusterManager instance."""
    global _manager
    if _manager is None:
        _manager = SentinelClusterManager()
    return _manager


# ──────────────────────────────────────────────────────────────────────────────
# FastAPI Application — Sentinel Cluster Management
# ──────────────────────────────────────────────────────────────────────────────


def create_sentinel_cluster_app():
    """Create the Sentinel Cluster FastAPI application for cluster management."""
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(
        title="Tranc3 Sentinel Cluster",
        description="Sentinel Station Cluster Management — Redis Cluster HA with automatic failover",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
    )

    @app.get("/", tags=["sentinel-cluster"])
    async def root():
        """Sentinel Cluster root — system overview."""
        mgr = get_sentinel_cluster_manager()
        return {
            "service": "Tranc3 Sentinel Cluster",
            "version": "0.1.0",
            "description": "Redis Cluster HA with automatic failover and partition handling",
            "clusters": mgr.list_clusters(),
        }

    @app.get("/status", tags=["sentinel-cluster"])
    async def status():
        """Get overall cluster manager status."""
        mgr = get_sentinel_cluster_manager()
        return mgr.get_status()

    @app.post("/clusters/{cluster_name}", tags=["clusters"])
    async def create_cluster(cluster_name: str, request: Request):
        """Create a new sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        body = await request.json() if request.headers.get("content-type") else {}
        mgr.create_cluster(cluster_name, config=body.get("config"))
        return {"action": "create_cluster", "cluster_name": cluster_name, "status": "created"}

    @app.delete("/clusters/{cluster_name}", tags=["clusters"])
    async def delete_cluster(cluster_name: str):
        """Delete a sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        removed = mgr.remove_cluster(cluster_name)
        return {"action": "delete_cluster", "cluster_name": cluster_name, "removed": removed}

    @app.get("/clusters/{cluster_name}/status", tags=["clusters"])
    async def cluster_status(cluster_name: str):
        """Get status of a specific sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        cluster = mgr.get_cluster(cluster_name)
        if cluster is None:
            return {"error": "cluster not found", "cluster_name": cluster_name}
        return cluster.get_cluster_status()

    @app.get("/clusters/{cluster_name}/health", tags=["clusters"])
    async def cluster_health(cluster_name: str):
        """Get health of a specific sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        cluster = mgr.get_cluster(cluster_name)
        if cluster is None:
            return {"error": "cluster not found", "cluster_name": cluster_name}
        return cluster.get_health().value

    @app.post("/clusters/{cluster_name}/nodes/{node_id}", tags=["cluster-nodes"])
    async def add_cluster_node(cluster_name: str, node_id: str, request: Request):
        """Add a node to a sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        cluster = mgr.get_cluster(cluster_name)
        if cluster is None:
            return {"error": "cluster not found", "cluster_name": cluster_name}
        body = await request.json() if request.headers.get("content-type") else {}
        cluster.add_node(
            node_id=node_id,
            address=body.get("address", f"sentinel-{node_id}:6379"),
            role=body.get("role", "replica"),
        )
        return {
            "action": "add_node",
            "cluster_name": cluster_name,
            "node_id": node_id,
            "status": "added",
        }

    @app.delete("/clusters/{cluster_name}/nodes/{node_id}", tags=["cluster-nodes"])
    async def remove_cluster_node(cluster_name: str, node_id: str):
        """Remove a node from a sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        cluster = mgr.get_cluster(cluster_name)
        if cluster is None:
            return {"error": "cluster not found", "cluster_name": cluster_name}
        removed = cluster.remove_node(node_id)
        return {
            "action": "remove_node",
            "cluster_name": cluster_name,
            "node_id": node_id,
            "removed": removed,
        }

    @app.post("/clusters/{cluster_name}/failover", tags=["cluster-ops"])
    async def cluster_failover(cluster_name: str, request: Request):
        """Trigger a manual failover on a sentinel cluster."""
        mgr = get_sentinel_cluster_manager()
        cluster = mgr.get_cluster(cluster_name)
        if cluster is None:
            return {"error": "cluster not found", "cluster_name": cluster_name}
        body = await request.json() if request.headers.get("content-type") else {}
        result = await cluster.perform_failover(target_node_id=body.get("target_node_id"))
        return {"action": "failover", "cluster_name": cluster_name, "result": result}

    return app
