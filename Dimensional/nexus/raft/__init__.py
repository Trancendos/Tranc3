"""
Tranc3 Nexus Raft Consensus
============================
Multi-node Nexus with Raft consensus for high availability.

Provides:
    - RaftNode: Individual node with state machine (Follower, Candidate, Leader)
    - RaftLog: Replicated log with append, commit, truncate operations
    - NexusCluster: Multi-node cluster manager with leader election
    - NexusClusterNode: Cluster member representation
"""

from Dimensional.nexus.raft.raft_core import (  # noqa: I001
    NexusCluster,
    NexusClusterNode,
    RaftConfig,
    RaftLog,
    RaftLogEntry,
    RaftNode,
    RaftNodeStatus,
    RaftState,
)

__all__ = [
    "RaftConfig",
    "RaftLog",
    "RaftLogEntry",
    "RaftNode",
    "RaftNodeStatus",
    "RaftState",
    "NexusCluster",
    "NexusClusterNode",
]
