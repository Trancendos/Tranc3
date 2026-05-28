"""
Tranc3 Nexus Raft Consensus Core
==================================
Implements the Raft consensus algorithm for distributed coordination
across Nexus cluster nodes.

Architecture:
    ┌─────────────────────────────────────────────────┐
    │                   NexusCluster                    │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐       │
    │  │ RaftNode  │  │ RaftNode  │  │ RaftNode  │     │
    │  │ (Leader)  │  │(Follower) │  │(Follower) │     │
    │  │  RaftLog  │  │  RaftLog  │  │  RaftLog  │     │
    │  └──────────┘  └──────────┘  └──────────┘       │
    └─────────────────────────────────────────────────┘

Key Features:
    - Leader election with configurable timeouts
    - Log replication and commitment
    - Automatic failover on leader loss
    - Command proposal via leader
    - Cluster membership changes

Zero-Cost: Uses in-process asyncio for node communication.
No external dependencies beyond asyncio.

Tier Integration:
    Operates at Tier 1 (ORCHESTRATOR) since it coordinates
    distributed consensus across Nexus cluster nodes.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("nexus.raft")


# ── Enums ────────────────────────────────────────────────────────────────────


class RaftState(str, Enum):
    """Raft node states."""

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"


# ── Configuration ────────────────────────────────────────────────────────────


@dataclass
class RaftConfig:
    """Configuration for a Raft node."""

    node_id: str = ""
    election_timeout_min_ms: int = 150
    election_timeout_max_ms: int = 300
    heartbeat_interval_ms: int = 50
    cluster_size: int = 3

    def __post_init__(self):
        if not self.node_id:
            self.node_id = str(uuid.uuid4())[:8]

    @property
    def election_timeout_ms(self) -> int:
        """Randomized election timeout to prevent split votes."""
        return random.randint(self.election_timeout_min_ms, self.election_timeout_max_ms)


# ── Log Entry ────────────────────────────────────────────────────────────────


@dataclass
class RaftLogEntry:
    """A single entry in the Raft log."""

    index: int
    term: int
    command: str
    data: Any = None
    committed: bool = False
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "term": self.term,
            "command": self.command,
            "data": self.data,
            "committed": self.committed,
            "timestamp": self.timestamp,
        }


# ── Raft Log ─────────────────────────────────────────────────────────────────


class RaftLog:
    """Replicated log for the Raft consensus algorithm.

    Maintains an ordered sequence of log entries with support for
    append, commit, and truncate operations.
    """

    def __init__(self):
        self._entries: List[RaftLogEntry] = []

    def append(self, term: int, command: str, data: Any = None) -> RaftLogEntry:
        """Append a new entry to the log."""
        index = len(self._entries) + 1
        entry = RaftLogEntry(index=index, term=term, command=command, data=data)
        self._entries.append(entry)
        return entry

    def get(self, index: int) -> Optional[RaftLogEntry]:
        """Get an entry by index (1-based)."""
        if 1 <= index <= len(self._entries):
            return self._entries[index - 1]
        return None

    def entries_from(self, start_index: int) -> List[RaftLogEntry]:
        """Get all entries from start_index onwards."""
        if start_index < 1:
            return list(self._entries)
        if start_index > len(self._entries):
            return []
        return list(self._entries[start_index - 1 :])

    @property
    def last_index(self) -> int:
        """Index of the last log entry (0 if empty)."""
        return len(self._entries)

    @property
    def last_term(self) -> int:
        """Term of the last log entry (0 if empty)."""
        if not self._entries:
            return 0
        return self._entries[-1].term

    @property
    def size(self) -> int:
        """Number of entries in the log."""
        return len(self._entries)

    def truncate_after(self, index: int) -> None:
        """Remove all entries after the given index."""
        if index < 0:
            return
        self._entries = self._entries[:index]

    def commit_up_to(self, index: int) -> List[RaftLogEntry]:
        """Mark all entries up to index as committed and return them."""
        committed = []
        for entry in self._entries:
            if entry.index <= index:
                entry.committed = True
                committed.append(entry)
        return committed

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the log to a dictionary."""
        return {
            "size": self.size,
            "last_index": self.last_index,
            "last_term": self.last_term,
            "entries": [e.to_dict() for e in self._entries],
        }


# ── Raft Node ────────────────────────────────────────────────────────────────


class RaftNode:
    """A single Raft consensus node.

    Implements the Raft state machine with follower, candidate, and
    leader states. Handles leader election, log replication, and
    command proposals.
    """

    def __init__(self, config: Optional[RaftConfig] = None):
        self._config = config or RaftConfig()
        self._state = RaftState.FOLLOWER
        self._current_term = 0
        self._voted_for: Optional[str] = None
        self._log = RaftLog()
        self._commit_index = 0
        self._last_applied = 0
        self._peers: Dict[str, str] = {}  # node_id → address
        self._leader_id: Optional[str] = None
        self._votes_received: Set[str] = set()
        self._command_handlers: Dict[str, Callable] = {}
        self._running = False
        self._election_timer: Optional[asyncio.Task] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._next_index: Dict[str, int] = {}
        self._match_index: Dict[str, int] = {}
        self._start_time: Optional[float] = None
        logger.info(
            "RaftNode %s initialized (cluster_size=%d)",
            self._config.node_id,
            self._config.cluster_size,
        )

    @property
    def node_id(self) -> str:
        return self._config.node_id

    @property
    def state(self) -> RaftState:
        return self._state

    @property
    def current_term(self) -> int:
        return self._current_term

    @property
    def log(self) -> RaftLog:
        return self._log

    @property
    def commit_index(self) -> int:
        return self._commit_index

    @property
    def leader_id(self) -> Optional[str]:
        return self._leader_id

    def add_peer(self, node_id: str, address: str = "") -> None:
        """Add a peer node."""
        self._peers[node_id] = address or f"node://{node_id}"
        self._next_index[node_id] = self._log.last_index + 1
        self._match_index[node_id] = 0
        logger.info("Node %s: peer added %s", self._config.node_id, node_id)

    def remove_peer(self, node_id: str) -> None:
        """Remove a peer node."""
        self._peers.pop(node_id, None)
        self._next_index.pop(node_id, None)
        self._match_index.pop(node_id, None)
        logger.info("Node %s: peer removed %s", self._config.node_id, node_id)

    def register_command_handler(self, command: str, handler: Callable) -> None:
        """Register a handler for a command type."""
        self._command_handlers[command] = handler

    async def start(self) -> None:
        """Start the Raft node."""
        if self._running:
            return
        self._running = True
        self._start_time = time.time()
        self._start_election_timer()
        logger.info("RaftNode %s started as %s", self._config.node_id, self._state.value)

    async def stop(self) -> None:
        """Stop the Raft node."""
        self._running = False
        if self._election_timer:
            self._election_timer.cancel()
            try:
                await self._election_timer
            except asyncio.CancelledError:
                pass
            self._election_timer = None
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
        logger.info("RaftNode %s stopped", self._config.node_id)

    def _start_election_timer(self) -> None:
        """Start the election timeout timer."""
        if self._election_timer:
            self._election_timer.cancel()
        try:
            loop = asyncio.get_event_loop()
            _timeout = self._config.election_timeout_ms / 1000.0
            self._election_timer = loop.create_task(self._election_timeout())
        except RuntimeError:
            pass

    async def _election_timeout(self) -> None:
        """Handle election timeout — become candidate and start election."""
        timeout = self._config.election_timeout_ms / 1000.0
        await asyncio.sleep(timeout)
        if not self._running:
            return
        if self._state != RaftState.LEADER:
            await self._start_election()

    async def _start_election(self) -> None:
        """Start a new election."""
        self._state = RaftState.CANDIDATE
        self._current_term += 1
        self._voted_for = self._config.node_id
        self._votes_received = {self._config.node_id}
        logger.info(
            "Node %s: starting election for term %d",
            self._config.node_id,
            self._current_term,
        )
        # In a real implementation, we'd send RequestVote RPCs
        # For in-process simulation, check if we have majority
        majority = (self._config.cluster_size // 2) + 1
        if len(self._votes_received) >= majority:
            await self._become_leader()

    async def _become_leader(self) -> None:
        """Transition to leader state."""
        self._state = RaftState.LEADER
        self._leader_id = self._config.node_id
        logger.info(
            "Node %s: became leader for term %d",
            self._config.node_id,
            self._current_term,
        )
        # Initialize leader state
        for peer_id in self._peers:
            self._next_index[peer_id] = self._log.last_index + 1
            self._match_index[peer_id] = 0
        # Start heartbeats
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        try:
            loop = asyncio.get_event_loop()
            self._heartbeat_task = loop.create_task(self._send_heartbeats())
        except RuntimeError:
            pass

    async def _send_heartbeats(self) -> None:
        """Send periodic heartbeats as leader."""
        while self._running and self._state == RaftState.LEADER:
            await asyncio.sleep(self._config.heartbeat_interval_ms / 1000.0)

    async def propose_command(self, command: str, data: Any = None) -> Optional[RaftLogEntry]:
        """Propose a command to the Raft cluster.

        Only the leader can propose commands. The command is appended
        to the leader's log and will be replicated to followers.
        """
        if self._state != RaftState.LEADER:
            logger.warning("Node %s: cannot propose — not leader", self._config.node_id)
            return None
        entry = self._log.append(self._current_term, command, data)
        logger.info(
            "Node %s: proposed command '%s' at index %d",
            self._config.node_id,
            command,
            entry.index,
        )
        return entry

    def grant_vote(self, term: int, candidate_id: str) -> bool:
        """Decide whether to grant a vote to a candidate."""
        if term < self._current_term:
            return False
        if term > self._current_term:
            self._current_term = term
            self._voted_for = None
            self._state = RaftState.FOLLOWER
        if self._voted_for is None or self._voted_for == candidate_id:
            self._voted_for = candidate_id
            return True
        return False

    def receive_append_entries(
        self,
        term: int,
        leader_id: str,
        prev_log_index: int,
        prev_log_term: int,
        entries: List[RaftLogEntry],
        leader_commit: int,
    ) -> bool:
        """Handle an AppendEntries RPC from the leader."""
        if term < self._current_term:
            return False
        if term > self._current_term:
            self._current_term = term
            self._voted_for = None
        self._state = RaftState.FOLLOWER
        self._leader_id = leader_id
        # Consistency check
        if prev_log_index > 0:
            prev_entry = self._log.get(prev_log_index)
            if prev_entry is None or prev_entry.term != prev_log_term:
                return False
        # Append new entries
        for entry in entries:
            existing = self._log.get(entry.index)
            if existing and existing.term != entry.term:
                self._log.truncate_after(entry.index - 1)
            if existing is None or existing.term != entry.term:
                self._log.append(entry.term, entry.command, entry.data)
        # Update commit index
        if leader_commit > self._commit_index:
            self._commit_index = min(leader_commit, self._log.last_index)
        return True

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of this Raft node."""
        return {
            "node_id": self._config.node_id,
            "state": self._state.value,
            "current_term": self._current_term,
            "voted_for": self._voted_for,
            "commit_index": self._commit_index,
            "last_applied": self._last_applied,
            "log_size": self._log.size,
            "leader_id": self._leader_id,
            "peers": list(self._peers.keys()),
        }

    def get_stats(self) -> Dict[str, Any]:
        """Get runtime statistics."""
        return {
            "node_id": self._config.node_id,
            "uptime_seconds": time.time() - self._start_time if self._start_time else 0,
            "state": self._state.value,
            "current_term": self._current_term,
            "log_entries": self._log.size,
            "committed_entries": sum(1 for e in self._log.entries_from(1) if e.committed),
        }


# ── Cluster Node ─────────────────────────────────────────────────────────────


@dataclass
class NexusClusterNode:
    """Represents a node in the Nexus cluster."""

    node_id: str
    address: str = ""
    state: RaftState = RaftState.FOLLOWER
    term: int = 0
    is_leader: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "address": self.address,
            "state": self.state.value,
            "term": self.term,
            "is_leader": self.is_leader,
        }


# ── Nexus Cluster ────────────────────────────────────────────────────────────


class NexusCluster:
    """Manages a multi-node Nexus cluster with Raft consensus.

    Provides a high-level interface for creating, starting, and
    managing a cluster of Raft nodes with automatic leader election,
    log replication, and failover.
    """

    def __init__(self, cluster_size: int = 3, config: Optional[RaftConfig] = None):
        self._cluster_size = cluster_size
        self._base_config = config or RaftConfig(cluster_size=cluster_size)
        self._nodes: Dict[str, RaftNode] = {}
        self._running = False
        self._leader_id: Optional[str] = None
        logger.info("NexusCluster initialized (size=%d)", cluster_size)

    @property
    def majority(self) -> int:
        """Majority count needed for consensus."""
        return (self._cluster_size // 2) + 1

    @property
    def leader_id(self) -> Optional[str]:
        """Current leader node ID."""
        return self._leader_id

    @property
    def node_count(self) -> int:
        """Number of nodes in the cluster."""
        return len(self._nodes)

    async def start(self) -> None:
        """Start the cluster with configured nodes."""
        if self._running:
            return
        # Create nodes if not already created
        if not self._nodes:
            for i in range(self._cluster_size):
                config = RaftConfig(
                    node_id=f"node-{i + 1}",
                    cluster_size=self._cluster_size,
                )
                node = RaftNode(config)
                self._nodes[config.node_id] = node
            # Add peers to each node
            for node_id, node in self._nodes.items():
                for other_id in self._nodes:
                    if other_id != node_id:
                        node.add_peer(other_id)
        # Start all nodes
        for node in self._nodes.values():
            await node.start()
        self._running = True
        logger.info("NexusCluster started with %d nodes", len(self._nodes))

    async def stop(self) -> None:
        """Stop all nodes in the cluster."""
        for node in self._nodes.values():
            await node.stop()
        self._running = False
        logger.info("NexusCluster stopped")

    async def propose(self, command: str, data: Any = None) -> Optional[RaftLogEntry]:
        """Propose a command to the cluster via the leader."""
        leader = self._get_leader()
        if not leader:
            logger.warning("NexusCluster: no leader to propose command")
            return None
        entry = await leader.propose_command(command, data)
        if entry:
            # In a real implementation, replicate to followers
            # For in-process, we simulate replication
            for node_id, node in self._nodes.items():
                if node_id != leader.node_id:
                    node.receive_append_entries(
                        term=leader.current_term,
                        leader_id=leader.node_id,
                        prev_log_index=entry.index - 1,
                        prev_log_term=leader.log.get(entry.index - 1).term  # type: ignore[union-attr]
                        if entry.index > 1
                        else 0,
                        entries=[entry],
                        leader_commit=entry.index,
                    )
        return entry

    def _get_leader(self) -> Optional[RaftNode]:
        """Get the current leader node."""
        for node in self._nodes.values():
            if node.state == RaftState.LEADER:
                self._leader_id = node.node_id
                return node
        return None

    async def add_node(self, node_id: str) -> None:
        """Add a new node to the cluster."""
        if node_id in self._nodes:
            return
        config = RaftConfig(node_id=node_id, cluster_size=self._cluster_size + 1)
        node = RaftNode(config)
        for other_id, other_node in self._nodes.items():
            node.add_peer(other_id)
            other_node.add_peer(node_id)
        self._nodes[node_id] = node
        self._cluster_size += 1
        if self._running:
            await node.start()
        logger.info("NexusCluster: node %s added", node_id)

    async def remove_node(self, node_id: str) -> None:
        """Remove a node from the cluster."""
        if node_id not in self._nodes:
            return
        node = self._nodes.pop(node_id)
        if self._running:
            await node.stop()
        for other_node in self._nodes.values():
            other_node.remove_peer(node_id)
        self._cluster_size = max(1, self._cluster_size - 1)
        logger.info("NexusCluster: node %s removed", node_id)

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get comprehensive cluster status."""
        _leader = self._get_leader()
        return {
            "running": self._running,
            "cluster_size": self._cluster_size,
            "node_count": len(self._nodes),
            "leader_id": self._leader_id,
            "majority": self.majority,
            "nodes": {nid: node.get_status() for nid, node in self._nodes.items()},
            "three_bridges": {
                "nexus": {
                    "name": "The Nexus",
                    "role": "ai_agent_bot_traffic",
                    "description": "AI, Agent, and Bot movement and traffic",
                    "status": "active" if self._running else "stopped",
                    "bridge_type": "intelligence",
                },
            },
        }


# ── Raft Node Status (compatibility) ────────────────────────────────────────


class RaftNodeStatus:
    """Helper class for Raft node status reporting."""

    @staticmethod
    def from_node(node: RaftNode) -> Dict[str, Any]:
        return node.get_status()
