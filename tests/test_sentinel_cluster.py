"""
Tests for Tranc3 Sentinel Station Clustering
===============================================
Comprehensive tests for Redis Cluster HA with node management,
failover, partition handling, and cluster lifecycle.
"""

import asyncio
import pytest

from Dimensional.infinity.sentinel_cluster import (
    NodeRole,
    NodeState,
    ClusterHealth,
    FailoverPolicy,
    SentinelClusterNode,
    ClusterPartition,
    ClusterConfig,
    SentinelCluster,
    SentinelClusterManager,
    get_sentinel_cluster_manager,
)


# ──────────────────────────────────────────────
# SentinelClusterNode Tests
# ──────────────────────────────────────────────

class TestSentinelClusterNode:
    def test_create_node(self):
        node = SentinelClusterNode(
            node_id="node-1",
            host="10.0.0.1",
            port=6379,
            role=NodeRole.PRIMARY,
        )
        assert node.node_id == "node-1"
        assert node.host == "10.0.0.1"
        assert node.port == 6379
        assert node.role == NodeRole.PRIMARY
        assert node.state == NodeState.ONLINE

    def test_default_role_is_replica(self):
        node = SentinelClusterNode(node_id="node-1")
        assert node.role == NodeRole.REPLICA

    def test_mark_online(self):
        node = SentinelClusterNode(node_id="node-1")
        node.state = NodeState.OFFLINE
        node.mark_online()
        assert node.state == NodeState.ONLINE
        assert node.last_heartbeat is not None

    def test_mark_offline(self):
        node = SentinelClusterNode(node_id="node-1")
        node.mark_offline()
        assert node.state == NodeState.OFFLINE

    def test_mark_partitioned(self):
        node = SentinelClusterNode(node_id="node-1")
        node.mark_partitioned()
        assert node.state == NodeState.PARTITIONED

    def test_promote_to_primary(self):
        node = SentinelClusterNode(node_id="node-1", role=NodeRole.REPLICA)
        node.promote_to_primary()
        assert node.role == NodeRole.PRIMARY
        assert node.state == NodeState.ONLINE

    def test_demote_to_replica(self):
        node = SentinelClusterNode(node_id="node-1", role=NodeRole.PRIMARY)
        node.demote_to_replica()
        assert node.role == NodeRole.REPLICA
        assert node.state == NodeState.SYNCING


# ──────────────────────────────────────────────
# ClusterPartition Tests
# ──────────────────────────────────────────────

class TestClusterPartition:
    def test_create_partition(self):
        partition = ClusterPartition(
            isolated_nodes=["node-2", "node-3"],
            majority_nodes=["node-1"],
        )
        assert len(partition.isolated_nodes) == 2
        assert len(partition.majority_nodes) == 1
        assert partition.resolved is False

    def test_partition_defaults(self):
        partition = ClusterPartition()
        assert partition.isolated_nodes == []
        assert partition.resolved is False
        assert partition.resolved_at is None


# ──────────────────────────────────────────────
# ClusterConfig Tests
# ──────────────────────────────────────────────

class TestClusterConfig:
    def test_default_config(self):
        config = ClusterConfig()
        assert config.cluster_name == "sentinel-cluster"
        assert config.min_replicas == 2
        assert config.failover_policy == FailoverPolicy.AUTOMATIC
        assert config.slot_count == 16384

    def test_custom_config(self):
        config = ClusterConfig(
            cluster_name="my-cluster",
            min_replicas=3,
            failover_policy=FailoverPolicy.MANUAL,
            heartbeat_interval_seconds=2.0,
        )
        assert config.cluster_name == "my-cluster"
        assert config.min_replicas == 3
        assert config.failover_policy == FailoverPolicy.MANUAL


# ──────────────────────────────────────────────
# SentinelCluster Tests
# ──────────────────────────────────────────────

class TestSentinelCluster:
    def test_create_cluster(self):
        cluster = SentinelCluster()
        assert cluster.node_count == 0
        assert cluster.primary is None

    def test_add_primary_node(self):
        cluster = SentinelCluster()
        node = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        cluster.add_node(node)
        assert cluster.node_count == 1
        assert cluster.primary is not None
        assert cluster.primary.node_id == "node-1"

    def test_add_replica_node(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        cluster.add_node(primary)
        replica = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(replica)
        assert cluster.node_count == 2
        assert len(cluster.replicas) == 1

    def test_remove_node(self):
        cluster = SentinelCluster()
        node = SentinelClusterNode(node_id="node-1", role=NodeRole.REPLICA)
        cluster.add_node(node)
        removed = cluster.remove_node("node-1")
        assert removed is not None
        assert cluster.node_count == 0

    def test_remove_primary_triggers_failover(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(primary)
        cluster.add_node(replica)
        cluster.remove_node("node-1")
        # Failover should promote node-2
        assert cluster.primary is not None
        assert cluster.primary.node_id == "node-2"

    def test_get_node(self):
        cluster = SentinelCluster()
        node = SentinelClusterNode(node_id="node-1")
        cluster.add_node(node)
        found = cluster.get_node("node-1")
        assert found is not None
        assert found.node_id == "node-1"

    def test_get_nonexistent_node(self):
        cluster = SentinelCluster()
        assert cluster.get_node("nope") is None

    def test_perform_failover(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica1 = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=50
        )
        replica2 = SentinelClusterNode(
            node_id="node-3", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(primary)
        cluster.add_node(replica1)
        cluster.add_node(replica2)
        new_primary = cluster.perform_failover()
        assert new_primary is not None
        # Should promote highest priority (lowest number)
        assert new_primary.node_id == "node-2"

    def test_perform_failover_specific_target(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica1 = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        replica2 = SentinelClusterNode(
            node_id="node-3", role=NodeRole.REPLICA, priority=50
        )
        cluster.add_node(primary)
        cluster.add_node(replica1)
        cluster.add_node(replica2)
        result = cluster.perform_failover(target_node_id="node-3")
        assert result is not None
        assert result.node_id == "node-3"

    def test_detect_partition(self):
        cluster = SentinelCluster()
        for i in range(1, 6):
            role = NodeRole.PRIMARY if i == 1 else NodeRole.REPLICA
            cluster.add_node(SentinelClusterNode(
                node_id=f"node-{i}", role=role, priority=i * 10
            ))
        partition = cluster.detect_partition(["node-4", "node-5"])
        assert partition is not None
        assert len(partition.isolated_nodes) == 2
        # Nodes should be marked partitioned
        for nid in ["node-4", "node-5"]:
            node = cluster.get_node(nid)
            assert node.state == NodeState.PARTITIONED

    def test_resolve_partition(self):
        cluster = SentinelCluster()
        for i in range(1, 5):
            role = NodeRole.PRIMARY if i == 1 else NodeRole.REPLICA
            cluster.add_node(SentinelClusterNode(
                node_id=f"node-{i}", role=role, priority=i * 10
            ))
        partition = cluster.detect_partition(["node-3"])
        result = cluster.resolve_partition(partition.partition_id)
        assert result is True
        # Node should be back online
        node = cluster.get_node("node-3")
        assert node.state == NodeState.ONLINE

    def test_resolve_nonexistent_partition(self):
        cluster = SentinelCluster()
        result = cluster.resolve_partition("nonexistent")
        assert result is False

    def test_get_health_empty(self):
        cluster = SentinelCluster()
        assert cluster.get_health() == ClusterHealth.DOWN

    def test_get_health_healthy(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        for i in range(2, 5):
            cluster.add_node(SentinelClusterNode(
                node_id=f"node-{i}", role=NodeRole.REPLICA, priority=i * 10
            ))
        cluster.add_node(primary)
        health = cluster.get_health()
        assert health in (ClusterHealth.HEALTHY, ClusterHealth.DEGRADED)

    def test_get_health_no_primary(self):
        cluster = SentinelCluster()
        cluster.add_node(SentinelClusterNode(
            node_id="node-1", role=NodeRole.REPLICA, priority=100
        ))
        health = cluster.get_health()
        assert health == ClusterHealth.CRITICAL

    def test_get_cluster_status(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(primary)
        cluster.add_node(replica)
        status = cluster.get_cluster_status()
        assert status["node_count"] == 2
        assert status["primary_id"] == "node-1"
        assert "health" in status

    def test_start_stop(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(primary)
        cluster.add_node(replica)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.start())
            assert cluster._started is True
            loop.run_until_complete(cluster.stop())
            assert cluster._started is False
        finally:
            loop.close()

    def test_allocate_slots(self):
        cluster = SentinelCluster()
        node = SentinelClusterNode(node_id="node-1", role=NodeRole.PRIMARY)
        cluster.add_node(node)
        result = cluster.allocate_slots("node-1", [0, 1, 2, 3, 4])
        assert result is True
        assert cluster.get_node("node-1").slots == [0, 1, 2, 3, 4]

    def test_get_slot_owner(self):
        cluster = SentinelCluster()
        node1 = SentinelClusterNode(node_id="node-1", role=NodeRole.PRIMARY)
        node2 = SentinelClusterNode(node_id="node-2", role=NodeRole.REPLICA)
        cluster.add_node(node1)
        cluster.add_node(node2)
        cluster.allocate_slots("node-1", [0, 1, 2])
        cluster.allocate_slots("node-2", [3, 4, 5])
        owner = cluster.get_slot_owner(1)
        assert owner is not None
        assert owner.node_id == "node-1"

    def test_get_slot_owner_unallocated(self):
        cluster = SentinelCluster()
        owner = cluster.get_slot_owner(0)
        assert owner is None

    def test_manual_failover_policy(self):
        config = ClusterConfig(failover_policy=FailoverPolicy.MANUAL)
        cluster = SentinelCluster(config)
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(primary)
        cluster.add_node(replica)
        cluster.remove_node("node-1")
        # Manual policy should not auto-promote
        assert cluster.primary is None

    def test_online_nodes(self):
        cluster = SentinelCluster()
        primary = SentinelClusterNode(
            node_id="node-1", role=NodeRole.PRIMARY, priority=1
        )
        replica = SentinelClusterNode(
            node_id="node-2", role=NodeRole.REPLICA, priority=100
        )
        cluster.add_node(primary)
        cluster.add_node(replica)
        assert len(cluster.online_nodes) == 2
        cluster.get_node("node-2").mark_offline()
        assert len(cluster.online_nodes) == 1


# ──────────────────────────────────────────────
# SentinelClusterManager Tests
# ──────────────────────────────────────────────

class TestSentinelClusterManager:
    def test_create_manager(self):
        manager = SentinelClusterManager()
        assert len(manager.list_clusters()) == 0

    def test_create_cluster(self):
        manager = SentinelClusterManager()
        cluster = manager.create_cluster()
        assert cluster is not None
        assert len(manager.list_clusters()) == 1

    def test_get_cluster(self):
        manager = SentinelClusterManager()
        cluster = manager.create_cluster()
        found = manager.get_cluster(cluster.config.cluster_name)
        assert found is not None

    def test_remove_cluster(self):
        manager = SentinelClusterManager()
        cluster = manager.create_cluster()
        result = manager.remove_cluster(cluster.config.cluster_name)
        assert result is True
        assert len(manager.list_clusters()) == 0

    def test_remove_nonexistent_cluster(self):
        manager = SentinelClusterManager()
        result = manager.remove_cluster("nonexistent")
        assert result is False

    def test_get_status(self):
        manager = SentinelClusterManager()
        manager.create_cluster()
        status = manager.get_status()
        assert "cluster_count" in status
        assert status["cluster_count"] == 1


# ──────────────────────────────────────────────
# Singleton Tests
# ──────────────────────────────────────────────

class TestSentinelClusterSingleton:
    def test_get_manager(self):
        manager = get_sentinel_cluster_manager()
        assert manager is not None
        assert isinstance(manager, SentinelClusterManager)

    def test_singleton_identity(self):
        m1 = get_sentinel_cluster_manager()
        m2 = get_sentinel_cluster_manager()
        assert m1 is m2
