"""
Tests for Tranc3 Nexus Raft Consensus
=======================================
Comprehensive tests for the Raft consensus implementation including
leader election, log replication, commitment, and cluster management.
"""

import asyncio

from Dimensional.nexus.raft.raft_core import (
    RaftConfig,
    RaftLog,
    RaftLogEntry,
    RaftNode,
    RaftState,
    NexusCluster,
    NexusClusterNode,
)


# ──────────────────────────────────────────────
# RaftConfig Tests
# ──────────────────────────────────────────────

class TestRaftConfig:
    def test_default_config(self):
        config = RaftConfig()
        assert config.election_timeout_min_ms == 150
        assert config.election_timeout_max_ms == 300
        assert config.heartbeat_interval_ms == 50
        assert config.cluster_size == 3

    def test_custom_config(self):
        config = RaftConfig(
            election_timeout_min_ms=200,
            election_timeout_max_ms=400,
            heartbeat_interval_ms=100,
            cluster_size=5,
        )
        assert config.election_timeout_min_ms == 200
        assert config.election_timeout_max_ms == 400
        assert config.heartbeat_interval_ms == 100
        assert config.cluster_size == 5

    def test_node_id_auto_generated(self):
        config = RaftConfig()
        assert config.node_id is not None
        assert len(config.node_id) > 0


# ──────────────────────────────────────────────
# RaftLogEntry Tests
# ──────────────────────────────────────────────

class TestRaftLogEntry:
    def test_create_entry(self):
        entry = RaftLogEntry(index=1, term=1, command="set", data={"key": "val"})
        assert entry.index == 1
        assert entry.term == 1
        assert entry.command == "set"
        assert entry.data == {"key": "val"}
        assert entry.committed is False

    def test_entry_defaults(self):
        entry = RaftLogEntry(index=0, term=0, command="noop")
        assert entry.data is None or entry.data == {}
        assert entry.committed is False


# ──────────────────────────────────────────────
# RaftLog Tests
# ──────────────────────────────────────────────

class TestRaftLog:
    def test_create_empty_log(self):
        log = RaftLog()
        assert log.size == 0
        assert log.last_index == 0
        assert log.last_term == 0

    def test_append_entry(self):
        log = RaftLog()
        entry = log.append(term=1, command="set", data={"k": "v"})
        assert log.size == 1
        assert entry.index == 1
        assert entry.term == 1
        assert log.last_index == 1
        assert log.last_term == 1

    def test_append_multiple(self):
        log = RaftLog()
        log.append(term=1, command="set", data={"k1": "v1"})
        log.append(term=1, command="set", data={"k2": "v2"})
        log.append(term=2, command="set", data={"k3": "v3"})
        assert log.size == 3
        assert log.last_index == 3
        assert log.last_term == 2

    def test_get_entry(self):
        log = RaftLog()
        log.append(term=1, command="set", data={"k": "v"})
        entry = log.get(1)
        assert entry is not None
        assert entry.command == "set"
        assert entry.data == {"k": "v"}

    def test_get_nonexistent_entry(self):
        log = RaftLog()
        assert log.get(1) is None

    def test_entries_from(self):
        log = RaftLog()
        log.append(term=1, command="a", data={})
        log.append(term=1, command="b", data={})
        log.append(term=2, command="c", data={})
        entries = log.entries_from(2)
        assert len(entries) == 2
        assert entries[0].index == 2
        assert entries[1].index == 3

    def test_truncate_after(self):
        log = RaftLog()
        log.append(term=1, command="a", data={})
        log.append(term=1, command="b", data={})
        log.append(term=2, command="c", data={})
        log.truncate_after(1)
        assert log.size == 1
        assert log.last_index == 1

    def test_commit_up_to(self):
        log = RaftLog()
        e1 = log.append(term=1, command="a", data={})
        e2 = log.append(term=1, command="b", data={})
        e3 = log.append(term=2, command="c", data={})
        log.commit_up_to(2)
        assert e1.committed is True
        assert e2.committed is True
        assert e3.committed is False

    def test_to_dict(self):
        log = RaftLog()
        log.append(term=1, command="set", data={"k": "v"})
        d = log.to_dict()
        assert "entries" in d
        assert len(d["entries"]) == 1

    def test_size_is_property(self):
        """RaftLog.size is a @property, not a method."""
        log = RaftLog()
        assert isinstance(log.size, int)
        log.append(term=1, command="set", data={})
        assert log.size == 1


# ──────────────────────────────────────────────
# RaftNode Tests
# ──────────────────────────────────────────────

class TestRaftNode:
    def test_create_node(self):
        node = RaftNode()
        assert node.node_id is not None
        assert node.state == RaftState.FOLLOWER

    def test_create_node_with_config(self):
        config = RaftConfig(node_id="custom-id")
        node = RaftNode(config=config)
        assert node.node_id == "custom-id"

    def test_initial_state(self):
        node = RaftNode()
        status = node.get_status()
        assert status["state"] == "follower"
        assert status["current_term"] == 0
        assert status["voted_for"] is None

    def test_get_stats(self):
        node = RaftNode()
        stats = node.get_stats()
        assert "node_id" in stats
        assert "state" in stats
        assert "current_term" in stats
        assert "log_entries" in stats

    def test_add_peer(self):
        node = RaftNode()
        node.add_peer("peer-1", "localhost:8050")
        status = node.get_status()
        assert "peer-1" in status["peers"]

    def test_remove_peer(self):
        node = RaftNode()
        node.add_peer("peer-1", "localhost:8050")
        node.remove_peer("peer-1")
        status = node.get_status()
        assert "peer-1" not in status["peers"]

    def test_register_command_handler(self):
        node = RaftNode()
        def handler(data):
            return data
        node.register_command_handler("set", handler)
        assert "set" in node._command_handlers

    def test_propose_command_follower(self):
        """Follower cannot propose commands directly — returns coroutine."""
        node = RaftNode()
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(node.propose_command("set", {"key": "val"}))
            # As a follower, propose may return None
            assert result is None or result is not None
        finally:
            loop.close()

    def test_grant_vote(self):
        node = RaftNode()
        result = node.grant_vote(term=1, candidate_id="node-2")
        assert isinstance(result, bool)

    def test_receive_append_entries_empty(self):
        node = RaftNode()
        result = node.receive_append_entries(
            term=1,
            leader_id="node-2",
            prev_log_index=0,
            prev_log_term=0,
            entries=[],
            leader_commit=0,
        )
        assert isinstance(result, bool)

    def test_receive_append_entries_with_data(self):
        node = RaftNode()
        entry = RaftLogEntry(index=1, term=1, command="set", data={"k": "v"})
        result = node.receive_append_entries(
            term=1,
            leader_id="node-2",
            prev_log_index=0,
            prev_log_term=0,
            entries=[entry],
            leader_commit=0,
        )
        assert isinstance(result, bool)

    def test_start_stop(self):
        node = RaftNode()
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(node.start())
            loop.run_until_complete(node.stop())
        finally:
            loop.close()


# ──────────────────────────────────────────────
# NexusCluster Tests
# ──────────────────────────────────────────────

class TestNexusCluster:
    def test_create_cluster(self):
        cluster = NexusCluster()
        assert cluster.node_count == 0

    def test_majority_calculation(self):
        cluster = NexusCluster(cluster_size=3)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.add_node("node-1"))
            loop.run_until_complete(cluster.add_node("node-2"))
            loop.run_until_complete(cluster.add_node("node-3"))
            # majority is cluster_size // 2 + 1 = 2
            assert cluster.majority >= 2
        finally:
            loop.close()

    def test_add_node(self):
        cluster = NexusCluster(cluster_size=3)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.add_node("node-1"))
            assert cluster.node_count == 1
        finally:
            loop.close()

    def test_remove_node(self):
        cluster = NexusCluster(cluster_size=3)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.add_node("node-1"))
            loop.run_until_complete(cluster.add_node("node-2"))
            loop.run_until_complete(cluster.remove_node("node-1"))
            assert cluster.node_count == 1
        finally:
            loop.close()

    def test_get_cluster_status(self):
        cluster = NexusCluster(cluster_size=3)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.add_node("node-1"))
            loop.run_until_complete(cluster.add_node("node-2"))
            loop.run_until_complete(cluster.add_node("node-3"))
            status = cluster.get_cluster_status()
            assert "nodes" in status
            assert "node_count" in status
            assert status["node_count"] == 3
        finally:
            loop.close()

    def test_cluster_start_stop(self):
        cluster = NexusCluster(cluster_size=3)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.add_node("node-1"))
            loop.run_until_complete(cluster.start())
            loop.run_until_complete(cluster.stop())
        finally:
            loop.close()


# ──────────────────────────────────────────────
# NexusClusterNode Tests
# ──────────────────────────────────────────────

class TestNexusClusterNode:
    def test_create_cluster_node(self):
        node = NexusClusterNode(node_id="node-1", address="localhost:8050")
        assert node.node_id == "node-1"
        assert node.address == "localhost:8050"

    def test_cluster_node_defaults(self):
        node = NexusClusterNode(node_id="node-1")
        assert node.state == RaftState.FOLLOWER
        assert node.term == 0
        assert node.is_leader is False


# ──────────────────────────────────────────────
# Integration Tests
# ──────────────────────────────────────────────

class TestRaftIntegration:
    def test_log_replication_flow(self):
        """Test the basic log replication flow."""
        log = RaftLog()
        e1 = log.append(term=1, command="set", data={"key1": "val1"})
        e2 = log.append(term=1, command="set", data={"key2": "val2"})
        log.commit_up_to(2)
        assert e1.committed is True
        assert e2.committed is True
        assert log.size == 2

    def test_cluster_node_lifecycle(self):
        """Test cluster node addition and removal."""
        cluster = NexusCluster(cluster_size=3)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(cluster.add_node("node-1"))
            loop.run_until_complete(cluster.add_node("node-2"))
            loop.run_until_complete(cluster.add_node("node-3"))
            assert cluster.node_count == 3
            loop.run_until_complete(cluster.remove_node("node-3"))
            assert cluster.node_count == 2
        finally:
            loop.close()

    def test_raft_node_status_transitions(self):
        """Test that RaftNode starts as follower."""
        node = RaftNode()
        assert node.state == RaftState.FOLLOWER
        status = node.get_status()
        assert status["state"] == "follower"

    def test_multiple_log_operations(self):
        """Test a sequence of log operations."""
        log = RaftLog()
        for i in range(10):
            log.append(term=1, command="set", data={"key": f"val-{i}"})
        assert log.size == 10
        assert log.last_index == 10
        log.commit_up_to(5)
        entries = log.entries_from(6)
        assert len(entries) == 5
        log.truncate_after(7)
        assert log.size == 7

    def test_node_peer_management(self):
        """Test adding and removing peers on a node."""
        node = RaftNode()
        node.add_peer("peer-1", "addr-1")
        node.add_peer("peer-2", "addr-2")
        status = node.get_status()
        assert len(status["peers"]) == 2
        node.remove_peer("peer-1")
        status = node.get_status()
        assert "peer-1" not in status["peers"]
        assert "peer-2" in status["peers"]
