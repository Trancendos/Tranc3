# src/fluidic/holographic_memory.py
# Holographic memory — Merkle-tree based event log for tamper-proof history
# Enables verifiable audit trails and efficient state proofs

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


@dataclass
class MemoryNode:
    """A node in the holographic memory tree"""

    hash: str
    data: Optional[Dict[str, Any]] = None
    left: Optional["MemoryNode"] = None
    right: Optional["MemoryNode"] = None
    timestamp: float = field(default_factory=time.time)

    @property
    def is_leaf(self) -> bool:
        return self.data is not None


class HolographicMemory:
    """
    Merkle-tree based memory system for tamper-proof event logging.
    Provides cryptographic proof that events haven't been modified.
    """

    def __init__(self, name: str = "default"):
        self.name = name
        self._leaves: List[MemoryNode] = []
        self._root: Optional[MemoryNode] = None
        self._max_leaves: int = 10000

    def append(self, event: Dict[str, Any]) -> str:
        """Add an event to the holographic memory. Returns the leaf hash."""
        event_data = {
            **event,
            "_timestamp": time.time(),
            "_index": len(self._leaves),
        }

        event_json = json.dumps(event_data, sort_keys=True, default=str)
        event_hash = hashlib.sha256(event_json.encode()).hexdigest()

        leaf = MemoryNode(hash=event_hash, data=event_data)
        self._leaves.append(leaf)
        self._rebuild_tree()

        if len(self._leaves) > self._max_leaves:
            self._leaves = self._leaves[-self._max_leaves :]
            self._rebuild_tree()

        logger.debug(
            "Holographic memory append: %s...", sanitize_for_log(event_hash[:12])
        )  # codeql[py/cleartext-logging]
        return event_hash

    def _rebuild_tree(self) -> None:
        """Rebuild the Merkle tree from leaves"""
        if not self._leaves:
            self._root = None
            return

        nodes = list(self._leaves)

        while len(nodes) > 1:
            new_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else None

                combined = left.hash + (right.hash if right else left.hash)
                parent_hash = hashlib.sha256(combined.encode()).hexdigest()

                parent = MemoryNode(hash=parent_hash, left=left, right=right)
                new_level.append(parent)

            nodes = new_level

        self._root = nodes[0]

    @property
    def root_hash(self) -> Optional[str]:
        """Current Merkle root hash"""
        return self._root.hash if self._root else None

    def verify(self, event_hash: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """Verify that an event exists in the tree"""
        for leaf in self._leaves:
            if leaf.hash == event_hash:
                return True, leaf.data
        return False, None

    def get_proof(self, event_hash: str) -> Optional[List[Dict[str, str]]]:
        """Generate a Merkle proof for an event"""
        leaf_index = None
        for i, leaf in enumerate(self._leaves):
            if leaf.hash == event_hash:
                leaf_index = i
                break

        if leaf_index is None:
            return None

        proof = []
        nodes = list(self._leaves)
        index = leaf_index

        while len(nodes) > 1:
            new_level = []
            for i in range(0, len(nodes), 2):
                left = nodes[i]
                right = nodes[i + 1] if i + 1 < len(nodes) else None

                if i == index:
                    if right and right != left:
                        proof.append({"hash": right.hash, "side": "right"})
                    elif i > 0:
                        proof.append({"hash": left.hash, "side": "left"})

                combined = left.hash + (right.hash if right else left.hash)
                parent_hash = hashlib.sha256(combined.encode()).hexdigest()
                parent = MemoryNode(hash=parent_hash, left=left, right=right)
                new_level.append(parent)

            index = index // 2
            nodes = new_level

        return proof

    def verify_proof(self, event_hash: str, proof: List[Dict[str, str]]) -> bool:
        """Verify a Merkle proof against the current root"""
        current_hash = event_hash

        for step in proof:
            if step["side"] == "right":
                combined = current_hash + step["hash"]
            else:
                combined = step["hash"] + current_hash
            current_hash = hashlib.sha256(combined.encode()).hexdigest()

        return current_hash == self.root_hash

    @property
    def size(self) -> int:
        """Number of events in memory"""
        return len(self._leaves)

    def recent(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get recent events"""
        return [leaf.data for leaf in self._leaves[-limit:] if leaf.data]

    def stats(self) -> Dict[str, Any]:
        """Memory statistics"""
        return {
            "name": self.name,
            "size": self.size,
            "root_hash": self.root_hash[:16] if self.root_hash else None,
            "max_capacity": self._max_leaves,
        }
