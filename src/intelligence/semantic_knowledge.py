"""
semantic_knowledge.py — Semantic Knowledge Graph for Tranc3 Intelligence Layer

Provides a structured, relational knowledge graph supporting typed edges,
attribute queries, path finding, semantic expansion, and SPARQL-inspired
pattern matching — all in pure Python with zero external dependencies.

Design Principles:
  - Zero-cost: no graph database, no vector DB, pure in-process structures
  - Bounded: LRU eviction keeps memory footprint predictable
  - Indexed: tag, type, and source indices enable efficient lookups
  - Provenance-tracked: every node and edge records its origin

Complements (does not replace) src/vector_store.py which handles
similarity search; this module handles structured relational queries.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class EdgeType(Enum):
    """Semantic relationship types for knowledge graph edges."""

    IS_A = "is_a"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    DEPENDS_ON = "depends_on"
    PRODUCES = "produces"
    CONSUMES = "consumes"
    SIMILAR_TO = "similar_to"
    INSTANCE_OF = "instance_of"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class KnowledgeNode:
    """
    A node in the semantic knowledge graph.

    Attributes:
        id:         Unique identifier (auto-generated if omitted).
        semantic_type: Category / ontology class of the node.
        label:      Human-readable name.
        tags:       Mutable set of free-form tags for indexing.
        attributes: Arbitrary key-value metadata.
        confidence: Belief score in [0, 1].
        provenance: Origin descriptor (e.g. "causal_reasoner", "user_input").
        created_at: Epoch seconds when the node was created.
        updated_at: Epoch seconds when the node was last updated.
        _access_at: Internal LRU tracking timestamp.
    """

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    semantic_type: str = "entity"
    label: str = ""
    tags: Set[str] = field(default_factory=set)
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.8
    provenance: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    _access_at: float = field(default_factory=time.time, repr=False)

    # -- matching helpers ---------------------------------------------------

    def matches(self, **criteria) -> bool:
        """Return True if this node satisfies *all* given criteria.

        Supported keyword filters:
          semantic_type, label (substring), tag (single tag present),
          min_confidence, provenance, attribute key presence.
        """
        if "semantic_type" in criteria and self.semantic_type != criteria["semantic_type"]:
            return False
        if "label" in criteria and criteria["label"].lower() not in self.label.lower():
            return False
        if "tag" in criteria and criteria["tag"] not in self.tags:
            return False
        if "min_confidence" in criteria and self.confidence < criteria["min_confidence"]:
            return False
        if "provenance" in criteria and self.provenance != criteria["provenance"]:
            return False
        if "attribute" in criteria and criteria["attribute"] not in self.attributes:
            return False
        return True

    @property
    def fingerprint(self) -> str:
        """Deterministic hash of the node's semantic identity (type + sorted tags + label)."""
        raw = f"{self.semantic_type}|{'|'.join(sorted(self.tags))}|{self.label}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


@dataclass
class KnowledgeEdge:
    """
    A directed, typed relationship between two knowledge nodes.

    Attributes:
        source_id:  Origin node id.
        target_id:  Destination node id.
        edge_type:  Semantic relationship category.
        confidence: Belief score in [0, 1].
        weight:     Numeric weight (default 1.0).
        provenance: Origin descriptor.
        attributes: Arbitrary key-value metadata.
        created_at: Epoch seconds when the edge was created.
    """

    source_id: str = ""
    target_id: str = ""
    edge_type: EdgeType = EdgeType.RELATED_TO
    confidence: float = 0.8
    weight: float = 1.0
    provenance: str = ""
    attributes: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass
class GraphPattern:
    """
    SPARQL-inspired graph pattern for structured matching.

    A pattern specifies:
      - node_constraints:  dict of node_id → criteria dict  (matched via KnowledgeNode.matches)
      - edge_constraints:  list of (source_id, target_id, edge_type) triples
      - variable_bindings: dict of variable_name → node_id to bind free variables

    Matching resolves variable bindings so that all node and edge constraints
    are simultaneously satisfied in the graph.
    """

    node_constraints: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    edge_constraints: List[Tuple[str, str, Optional[EdgeType]]] = field(default_factory=list)
    variable_bindings: Dict[str, str] = field(default_factory=dict)


@dataclass
class PatternMatch:
    """
    A single match result from pattern matching.

    Attributes:
        bindings:   Resolved variable → node_id mapping.
        nodes:      Dict of node_id → KnowledgeNode for matched nodes.
        edges:      List of KnowledgeEdge objects satisfying edge constraints.
        score:      Aggregate confidence of the match.
    """

    bindings: Dict[str, str] = field(default_factory=dict)
    nodes: Dict[str, KnowledgeNode] = field(default_factory=dict)
    edges: List[KnowledgeEdge] = field(default_factory=list)
    score: float = 0.0


# ---------------------------------------------------------------------------
# Semantic Knowledge Graph
# ---------------------------------------------------------------------------


class SemanticKnowledgeGraph:
    """
    In-process semantic knowledge graph with indexed queries, path finding,
    semantic expansion, and SPARQL-inspired pattern matching.

    Parameters:
        max_nodes:          Upper bound on stored nodes (LRU eviction).
        max_paths:          Safety cap on all_paths traversal results.
        default_confidence: Confidence assigned when not explicitly provided.
    """

    def __init__(
        self,
        max_nodes: int = 50_000,
        max_paths: int = 100,
        default_confidence: float = 0.8,
    ) -> None:
        self.max_nodes = max_nodes
        self.max_paths = max_paths
        self.default_confidence = default_confidence

        # --- core storage ---
        self._nodes: Dict[str, KnowledgeNode] = {}
        self._edges: Dict[str, KnowledgeEdge] = {}  # edge_id → edge

        # --- adjacency (forward & reverse) ---
        self._out: Dict[str, List[KnowledgeEdge]] = defaultdict(list)
        self._in: Dict[str, List[KnowledgeEdge]] = defaultdict(list)

        # --- indices ---
        self._tag_index: Dict[str, Set[str]] = defaultdict(set)  # tag → node_ids
        self._type_index: Dict[str, Set[str]] = defaultdict(set)  # type → node_ids
        self._source_index: Dict[str, Set[str]] = defaultdict(set)  # provenance → node_ids

        # --- LRU order (oldest first) ---
        self._lru_order: deque = deque()

        self._lock = asyncio.Lock() if asyncio.get_event_loop().is_running() else None
        logger.info(
            "SemanticKnowledgeGraph initialised (max_nodes=%d, max_paths=%d)",
            self.max_nodes,
            self.max_paths,
        )

    # -- helper: deterministic edge id --------------------------------------

    @staticmethod
    def _edge_id(src: str, tgt: str, etype: EdgeType) -> str:
        return f"{src}→{tgt}:{etype.value}"

    # ======================================================================
    # Node CRUD
    # ======================================================================

    async def add_node(self, node: KnowledgeNode) -> str:
        """Add a node to the graph. Returns the node id.

        If a node with the same id already exists it is updated in place.
        When the graph exceeds *max_nodes*, the least-recently-accessed
        node with the lowest confidence is evicted.
        """
        if self._lock:
            await self._lock.acquire()
        try:
            # Update existing
            if node.id in self._nodes:
                self._update_indices_remove(node.id)
                old = self._nodes[node.id]
                node.created_at = old.created_at
                node.updated_at = time.time()
                node._access_at = time.time()
                self._nodes[node.id] = node
                self._update_indices_add(node)
                return node.id

            # Evict if at capacity
            while len(self._nodes) >= self.max_nodes:
                self._evict_one()

            node.confidence = node.confidence or self.default_confidence
            node._access_at = time.time()
            self._nodes[node.id] = node
            self._lru_order.append(node.id)
            self._update_indices_add(node)
            logger.debug("Added node %s (%s)", node.id, node.semantic_type)
            return node.id
        finally:
            if self._lock:
                self._lock.release()

    async def get_node(self, node_id: str) -> Optional[KnowledgeNode]:
        """Retrieve a node by id, updating LRU access time."""
        node = self._nodes.get(node_id)
        if node is not None:
            node._access_at = time.time()
        return node

    async def update_node(self, node_id: str, **updates) -> bool:
        """Apply partial updates to a node. Returns True if node existed."""
        node = self._nodes.get(node_id)
        if node is None:
            return False
        if self._lock:
            await self._lock.acquire()
        try:
            self._update_indices_remove(node_id)
            for k, v in updates.items():
                if k == "tags" and isinstance(v, (set, list)):
                    node.tags = set(v)
                elif k == "attributes" and isinstance(v, dict):
                    node.attributes.update(v)
                elif hasattr(node, k) and not k.startswith("_"):
                    setattr(node, k, v)
            node.updated_at = time.time()
            node._access_at = time.time()
            self._update_indices_add(node)
            return True
        finally:
            if self._lock:
                self._lock.release()

    async def remove_node(self, node_id: str) -> bool:
        """Remove a node and all its incident edges. Returns True if existed."""
        if node_id not in self._nodes:
            return False
        if self._lock:
            await self._lock.acquire()
        try:
            # Remove incident edges first
            edges_to_remove = [
                self._edge_id(e.source_id, e.target_id, e.edge_type)
                for e in list(self._out.get(node_id, []))
            ] + [
                self._edge_id(e.source_id, e.target_id, e.edge_type)
                for e in list(self._in.get(node_id, []))
            ]
            for eid in set(edges_to_remove):
                self._remove_edge_raw(eid)
            # Remove node
            self._update_indices_remove(node_id)
            del self._nodes[node_id]
            self._out.pop(node_id, None)
            self._in.pop(node_id, None)
            logger.debug("Removed node %s", node_id)
            return True
        finally:
            if self._lock:
                self._lock.release()

    # ======================================================================
    # Edge CRUD
    # ======================================================================

    async def add_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType = EdgeType.RELATED_TO,
        confidence: Optional[float] = None,
        weight: float = 1.0,
        provenance: str = "",
        attributes: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Add a directed typed edge. Returns the edge id, or None if endpoints missing."""
        if source_id not in self._nodes or target_id not in self._nodes:
            logger.warning("Edge endpoints missing: %s → %s", source_id, target_id)
            return None
        edge = KnowledgeEdge(
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            confidence=confidence or self.default_confidence,
            weight=weight,
            provenance=provenance,
            attributes=attributes or {},
        )
        if self._lock:
            await self._lock.acquire()
        try:
            eid = self._edge_id(source_id, target_id, edge_type)
            # Remove old edge if overwriting
            if eid in self._edges:
                self._remove_edge_raw(eid)
            self._edges[eid] = edge
            self._out[source_id].append(edge)
            self._in[target_id].append(edge)
            logger.debug("Added edge %s", eid)
            return eid
        finally:
            if self._lock:
                self._lock.release()

    async def remove_edge(self, source_id: str, target_id: str, edge_type: EdgeType) -> bool:
        """Remove a specific edge. Returns True if it existed."""
        eid = self._edge_id(source_id, target_id, edge_type)
        if self._lock:
            await self._lock.acquire()
        try:
            return self._remove_edge_raw(eid)
        finally:
            if self._lock:
                self._lock.release()

    def _remove_edge_raw(self, eid: str) -> bool:
        """Internal: remove edge by id without locking."""
        edge = self._edges.pop(eid, None)
        if edge is None:
            return False
        if edge in self._out.get(edge.source_id, []):
            self._out[edge.source_id].remove(edge)
        if edge in self._in.get(edge.target_id, []):
            self._in[edge.target_id].remove(edge)
        return True

    # ======================================================================
    # Queries
    # ======================================================================

    async def query_nodes(self, **criteria) -> List[KnowledgeNode]:
        """Return all nodes matching the given criteria (delegated to KnowledgeNode.matches)."""
        # Use index shortcuts when possible
        candidate_ids: Optional[Set[str]] = None

        if "tag" in criteria:
            tag_set = self._tag_index.get(criteria["tag"], set())
            candidate_ids = tag_set if candidate_ids is None else candidate_ids & tag_set

        if "semantic_type" in criteria:
            type_set = self._type_index.get(criteria["semantic_type"], set())
            candidate_ids = type_set if candidate_ids is None else candidate_ids & type_set

        if "provenance" in criteria:
            src_set = self._source_index.get(criteria["provenance"], set())
            candidate_ids = src_set if candidate_ids is None else candidate_ids & src_set

        if candidate_ids is not None:
            results = [self._nodes[nid] for nid in candidate_ids if nid in self._nodes]
        else:
            results = list(self._nodes.values())

        return [n for n in results if n.matches(**criteria)]

    async def get_neighbors(
        self,
        node_id: str,
        direction: str = "outgoing",
        edge_type: Optional[EdgeType] = None,
    ) -> List[Tuple[KnowledgeNode, KnowledgeEdge]]:
        """Return (neighbor_node, edge) pairs for a node.

        Args:
            direction: "outgoing", "incoming", or "both".
            edge_type: Optional filter on edge type.
        """
        if node_id not in self._nodes:
            return []
        pairs: List[Tuple[KnowledgeNode, KnowledgeEdge]] = []
        edges: List[KnowledgeEdge] = []

        if direction in ("outgoing", "both"):
            edges.extend(self._out.get(node_id, []))
        if direction in ("incoming", "both"):
            edges.extend(self._in.get(node_id, []))

        seen_edge_ids = set()
        for e in edges:
            eid = self._edge_id(e.source_id, e.target_id, e.edge_type)
            if eid in seen_edge_ids:
                continue
            seen_edge_ids.add(eid)
            if edge_type is not None and e.edge_type != edge_type:
                continue
            neighbor_id = e.target_id if e.source_id == node_id else e.source_id
            neighbor = self._nodes.get(neighbor_id)
            if neighbor is not None:
                pairs.append((neighbor, e))
        return pairs

    # ======================================================================
    # Path finding
    # ======================================================================

    async def shortest_path(
        self,
        source_id: str,
        target_id: str,
        edge_type: Optional[EdgeType] = None,
    ) -> Optional[List[str]]:
        """BFS shortest path between two nodes. Returns ordered node ids or None."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return None
        if source_id == target_id:
            return [source_id]

        visited: Set[str] = {source_id}
        queue: deque = deque([(source_id, [source_id])])

        while queue:
            current, path = queue.popleft()
            for edge in self._out.get(current, []):
                if edge_type is not None and edge.edge_type != edge_type:
                    continue
                nxt = edge.target_id
                if nxt in visited:
                    continue
                new_path = path + [nxt]
                if nxt == target_id:
                    return new_path
                visited.add(nxt)
                queue.append((nxt, new_path))
        return None

    async def all_paths(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 6,
        edge_type: Optional[EdgeType] = None,
    ) -> List[List[str]]:
        """DFS all simple paths up to *max_depth*. Capped at *max_paths* results."""
        if source_id not in self._nodes or target_id not in self._nodes:
            return []
        results: List[List[str]] = []

        def _dfs(current: str, path: List[str], visited: Set[str]) -> None:
            if len(results) >= self.max_paths:
                return
            if current == target_id:
                results.append(list(path))
                return
            if len(path) > max_depth:
                return
            for edge in self._out.get(current, []):
                if edge_type is not None and edge.edge_type != edge_type:
                    continue
                nxt = edge.target_id
                if nxt in visited:
                    continue
                visited.add(nxt)
                path.append(nxt)
                _dfs(nxt, path, visited)
                path.pop()
                visited.discard(nxt)

        _dfs(source_id, [source_id], {source_id})
        return results

    # ======================================================================
    # Semantic expansion
    # ======================================================================

    async def semantic_expand(
        self,
        node_id: str,
        depth: int = 2,
        edge_types: Optional[List[EdgeType]] = None,
        min_confidence: float = 0.0,
    ) -> Dict[str, Tuple[KnowledgeNode, float]]:
        """Expand semantically from a node, returning reachable nodes with accumulated confidence.

        Returns:
            Dict mapping node_id → (KnowledgeNode, accumulated_confidence).
            Accumulated confidence is the product of edge confidences along the best path.
        """
        if node_id not in self._nodes:
            return {}
        result: Dict[str, Tuple[KnowledgeNode, float]] = {}
        # BFS with confidence tracking
        visited: Dict[str, float] = {node_id: 1.0}
        queue: deque = deque([(node_id, 1.0, 0)])

        while queue:
            current, conf, d = queue.popleft()
            if d >= depth:
                continue
            for edge in self._out.get(current, []):
                if edge_types is not None and edge.edge_type not in edge_types:
                    continue
                if edge.confidence < min_confidence:
                    continue
                new_conf = conf * edge.confidence * edge.weight
                nxt = edge.target_id
                if nxt not in visited or new_conf > visited.get(nxt, 0.0):
                    visited[nxt] = new_conf
                    node = self._nodes.get(nxt)
                    if node is not None:
                        result[nxt] = (node, new_conf)
                    queue.append((nxt, new_conf, d + 1))
        return result

    # ======================================================================
    # Pattern matching (SPARQL-inspired)
    # ======================================================================

    async def match_pattern(self, pattern: GraphPattern) -> List[PatternMatch]:
        """Match a GraphPattern against the knowledge graph.

        The algorithm:
          1. For each constrained node variable, find candidate node ids.
          2. Seed any variables that appear only in edge constraints (not in
             node_constraints) with the full set of known node ids so they
             can be bound during edge-constraint checking.
          3. Bind free variables by checking edge constraints.
          4. Score matches by average confidence of involved nodes and edges.
        """
        # Step 1: resolve candidates for each constrained node variable
        candidates: Dict[str, List[str]] = {}
        for var, criteria in pattern.node_constraints.items():
            if var in pattern.variable_bindings:
                # Pre-bound variable — only that node id
                nid = pattern.variable_bindings[var]
                node = self._nodes.get(nid)
                if node and node.matches(**criteria):
                    candidates[var] = [nid]
                else:
                    candidates[var] = []
            else:
                matching = await self.query_nodes(**criteria)
                candidates[var] = [n.id for n in matching]

        # Step 2: seed variables that appear only in edge constraints but not
        # in node_constraints — without this they would never be bound.
        for src_var, tgt_var, _etype in pattern.edge_constraints:
            for var in (src_var, tgt_var):
                if var not in candidates:
                    if var in pattern.variable_bindings:
                        candidates[var] = [pattern.variable_bindings[var]]
                    else:
                        # No node-level filter: all known nodes are candidates
                        candidates[var] = list(self._nodes.keys())

        # If any variable has zero candidates, no matches possible
        if any(len(v) == 0 for v in candidates.values()):
            return []

        # Step 3: enumerate binding combinations and check edge constraints
        var_names = list(candidates.keys())
        matches: List[PatternMatch] = []

        def _enumerate(idx: int, bindings: Dict[str, str]) -> None:
            if idx == len(var_names):
                # All variables bound — verify edge constraints
                edges_ok: List[KnowledgeEdge] = []
                for src_var, tgt_var, etype in pattern.edge_constraints:
                    src_id = bindings.get(src_var)
                    tgt_id = bindings.get(tgt_var)
                    if src_id is None or tgt_id is None:
                        return
                    found = False
                    for e in self._out.get(src_id, []):
                        if e.target_id == tgt_id:
                            if etype is not None and e.edge_type != etype:
                                continue
                            edges_ok.append(e)
                            found = True
                            break
                    if not found:
                        return
                # Build match
                nodes_matched = {
                    v: self._nodes[bindings[v]] for v in var_names if bindings.get(v) in self._nodes
                }
                node_confs = [n.confidence for n in nodes_matched.values()]
                edge_confs = [e.confidence for e in edges_ok]
                all_confs = node_confs + edge_confs
                score = sum(all_confs) / len(all_confs) if all_confs else 0.0
                matches.append(
                    PatternMatch(
                        bindings=dict(bindings),
                        nodes=nodes_matched,
                        edges=edges_ok,
                        score=score,
                    ),
                )
                return
            var = var_names[idx]
            for nid in candidates[var]:
                bindings[var] = nid
                _enumerate(idx + 1, bindings)
                del bindings[var]

        _enumerate(0, {})

        # Sort by score descending
        matches.sort(key=lambda m: m.score, reverse=True)
        return matches

    # ======================================================================
    # Export / stats
    # ======================================================================

    async def export_graph(self) -> Dict[str, Any]:
        """Export the full graph as a JSON-serialisable dict."""
        nodes = []
        for n in self._nodes.values():
            nodes.append(
                {
                    "id": n.id,
                    "semantic_type": n.semantic_type,
                    "label": n.label,
                    "tags": sorted(n.tags),
                    "attributes": n.attributes,
                    "confidence": n.confidence,
                    "provenance": n.provenance,
                    "fingerprint": n.fingerprint,
                    "created_at": n.created_at,
                    "updated_at": n.updated_at,
                },
            )
        edges = []
        for e in self._edges.values():
            edges.append(
                {
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "edge_type": e.edge_type.value,
                    "confidence": e.confidence,
                    "weight": e.weight,
                    "provenance": e.provenance,
                    "attributes": e.attributes,
                    "created_at": e.created_at,
                },
            )
        return {
            "nodes": nodes,
            "edges": edges,
            "stats": await self.stats(),
        }

    async def stats(self) -> Dict[str, Any]:
        """Return summary statistics."""
        edge_type_counts: Dict[str, int] = defaultdict(int)
        for e in self._edges.values():
            edge_type_counts[e.edge_type.value] += 1
        return {
            "node_count": len(self._nodes),
            "edge_count": len(self._edges),
            "edge_types": dict(edge_type_counts),
            "tag_count": len(self._tag_index),
            "type_count": len(self._type_index),
            "source_count": len(self._source_index),
            "max_nodes": self.max_nodes,
            "max_paths": self.max_paths,
        }

    # ======================================================================
    # Internal helpers
    # ======================================================================

    def _update_indices_add(self, node: KnowledgeNode) -> None:
        """Add node to tag, type, and source indices."""
        self._type_index[node.semantic_type].add(node.id)
        for tag in node.tags:
            self._tag_index[tag].add(node.id)
        if node.provenance:
            self._source_index[node.provenance].add(node.id)

    def _update_indices_remove(self, node_id: str) -> None:
        """Remove node from tag, type, and source indices."""
        node = self._nodes.get(node_id)
        if node is None:
            return
        self._type_index[node.semantic_type].discard(node.id)
        for tag in node.tags:
            self._tag_index[tag].discard(node.id)
        if node.provenance:
            self._source_index[node.provenance].discard(node.id)

    def _evict_one(self) -> None:
        """Evict the least-recently-accessed node with the lowest confidence."""
        if not self._lru_order:
            return
        # Find candidate with lowest confidence among least-recently-accessed
        # Strategy: check the oldest 25% of LRU entries, pick lowest confidence
        check_count = max(1, len(self._lru_order) // 4)
        best_id: Optional[str] = None
        best_score = float("inf")  # lower = more evictable

        for _ in range(check_count):
            if not self._lru_order:
                break
            nid = self._lru_order[0]
            node = self._nodes.get(nid)
            if node is None:
                self._lru_order.popleft()  # stale entry
                continue
            # Eviction score: lower confidence + older access = more evictable
            score = node.confidence - (time.time() - node._access_at) * 0.0001
            if score < best_score:
                best_score = score
                best_id = nid
            break  # simplest: evict the oldest LRU entry

        # Fallback: just evict the oldest in LRU
        if best_id is None and self._lru_order:
            best_id = self._lru_order.popleft()

        if best_id and best_id in self._nodes:
            # Synchronous removal (called from within lock context)
            self._update_indices_remove(best_id)
            # Remove edges that originate from the evicted node and clean up
            # the stale back-references in the target nodes' _in adjacency lists.
            for e in list(self._out.get(best_id, [])):
                self._edges.pop(self._edge_id(e.source_id, e.target_id, e.edge_type), None)
                if e.target_id in self._in:
                    self._in[e.target_id] = [
                        x for x in self._in[e.target_id] if x.source_id != best_id
                    ]
            # Remove edges that point to the evicted node and clean up the
            # stale forward-references in the source nodes' _out adjacency lists.
            for e in list(self._in.get(best_id, [])):
                self._edges.pop(self._edge_id(e.source_id, e.target_id, e.edge_type), None)
                if e.source_id in self._out:
                    self._out[e.source_id] = [
                        x for x in self._out[e.source_id] if x.target_id != best_id
                    ]
            self._out.pop(best_id, None)
            self._in.pop(best_id, None)
            del self._nodes[best_id]
            logger.debug("Evicted node %s (LRU, confidence=%.2f)", best_id, best_score)
