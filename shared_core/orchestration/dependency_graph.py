# shared_core/orchestration/dependency_graph.py
# Smart dependency graph with impact analysis, cycle detection,
# and proactive degradation warnings.

import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Set, Tuple

from shared_core.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class DependencyEdge:
    """A directed edge in the dependency graph."""
    __slots__ = ("source", "target", "dep_type", "weight", "metadata")

    def __init__(
        self,
        source: str,
        target: str,
        dep_type: str = "runtime",
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.source = source
        self.target = target
        self.dep_type = dep_type  # "runtime", "build", "config", "data"
        self.weight = weight
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "dep_type": self.dep_type,
            "weight": self.weight,
            "metadata": self.metadata,
        }


@dataclass
class DependencyNode:
    """A node in the dependency graph representing a service or component."""
    name: str
    node_type: str = "service"  # "service", "database", "cache", "queue", "external"
    health: str = "healthy"
    version: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    added_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "node_type": self.node_type,
            "health": self.health,
            "version": self.version,
            "metadata": self.metadata,
        }


class ImpactLevel(str, Enum):
    """Impact severity level."""
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class ImpactAnalysis:
    """Result of analyzing the impact of a node failure or degradation."""
    root_node: str
    impacted_nodes: List[str]
    impact_levels: Dict[str, ImpactLevel]
    critical_paths: List[List[str]]
    total_depth: int
    mitigation_suggestions: List[str]
    timestamp: float = field(default_factory=time.time)

    @property
    def has_critical_impact(self) -> bool:
        return any(v == ImpactLevel.CRITICAL for v in self.impact_levels.values())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_node": self.root_node,
            "impacted_nodes": self.impacted_nodes,
            "impact_levels": {k: v.value for k, v in self.impact_levels.items()},
            "critical_paths": self.critical_paths,
            "total_depth": self.total_depth,
            "mitigation_suggestions": self.mitigation_suggestions,
            "has_critical_impact": self.has_critical_impact,
            "timestamp": self.timestamp,
        }


class SmartDependencyGraph:
    """
    Smart dependency graph with impact analysis and proactive warnings.

    Features:
      - Directed acyclic graph (DAG) of service dependencies
      - Cycle detection with automatic prevention
      - Impact analysis: what happens if node X goes down?
      - Critical path identification
      - Proactive degradation warnings based on dependency chain health
      - Topological sort for startup/shutdown ordering
      - Dependency distance metrics for resilience scoring
    """

    def __init__(self):
        self._nodes: Dict[str, DependencyNode] = {}
        self._edges: List[DependencyEdge] = []
        self._adjacency: Dict[str, List[str]] = defaultdict(list)  # source -> [targets]
        self._reverse_adj: Dict[str, List[str]] = defaultdict(list)  # target -> [sources]
        self._callbacks: List[Callable] = []
        self._cycle_cache: Optional[List[List[str]]] = None
        self._topo_cache: Optional[List[str]] = None

    # ── Node Management ───────────────────────────────────────────

    def add_node(
        self,
        name: str,
        node_type: str = "service",
        health: str = "healthy",
        version: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DependencyNode:
        """Add a node to the dependency graph."""
        node = DependencyNode(
            name=name,
            node_type=node_type,
            health=health,
            version=version,
            metadata=metadata or {},
        )
        self._nodes[name] = node
        self._invalidate_caches()
        logger.debug("Added node: %s (type=%s)", sanitize_for_log(name), node_type)
        return node

    def remove_node(self, name: str) -> Optional[DependencyNode]:
        """Remove a node and all its edges from the graph."""
        node = self._nodes.pop(name, None)
        if node:
            # Remove all edges involving this node
            self._edges = [
                e for e in self._edges
                if e.source != name and e.target != name
            ]
            # Rebuild adjacency lists
            self._rebuild_adjacency()
            self._invalidate_caches()
            logger.debug("Removed node: %s", sanitize_for_log(name))
        return node

    def update_node_health(self, name: str, health: str) -> None:
        """Update a node's health status and trigger impact analysis."""
        node = self._nodes.get(name)
        if node and node.health != health:
            old_health = node.health
            node.health = health
            logger.info("Node %s health: %s → %s", sanitize_for_log(name), old_health, health)
            # If degraded/unhealthy, analyze impact
            if health in ("unhealthy", "degraded"):
                impact = self.analyze_impact(name)
                self._notify_impact(name, old_health, health, impact)

    def get_node(self, name: str) -> Optional[DependencyNode]:
        """Get a node by name."""
        return self._nodes.get(name)

    # ── Edge Management ───────────────────────────────────────────

    def add_edge(
        self,
        source: str,
        target: str,
        dep_type: str = "runtime",
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[DependencyEdge]:
        """
        Add a directed edge (source depends on target).
        Returns None if the edge would create a cycle.
        """
        if source not in self._nodes or target not in self._nodes:
            logger.warning("Cannot add edge: node not found (%s → %s)",
                           sanitize_for_log(source), sanitize_for_log(target))
            return None

        # Check for cycle: would adding source→target create a path from target to source?
        if self._would_create_cycle(source, target):
            logger.warning("Rejecting edge %s → %s: would create cycle",
                           sanitize_for_log(source), sanitize_for_log(target))
            return None

        edge = DependencyEdge(
            source=source,
            target=target,
            dep_type=dep_type,
            weight=weight,
            metadata=metadata or {},
        )
        self._edges.append(edge)
        self._adjacency[source].append(target)
        self._reverse_adj[target].append(source)
        self._invalidate_caches()
        return edge

    def remove_edge(self, source: str, target: str) -> bool:
        """Remove an edge from the graph."""
        original_len = len(self._edges)
        self._edges = [e for e in self._edges if not (e.source == source and e.target == target)]
        if len(self._edges) < original_len:
            self._rebuild_adjacency()
            self._invalidate_caches()
            return True
        return False

    # ── Impact Analysis ───────────────────────────────────────────

    def analyze_impact(self, node_name: str, max_depth: int = 10) -> ImpactAnalysis:
        """
        Analyze the blast radius of a node failure.
        Traverses reverse dependencies (who depends on this node).
        """
        if node_name not in self._nodes:
            return ImpactAnalysis(
                root_node=node_name,
                impacted_nodes=[],
                impact_levels={},
                critical_paths=[],
                total_depth=0,
                mitigation_suggestions=["Node not found in graph"],
            )

        impacted: Dict[str, ImpactLevel] = {}
        critical_paths: List[List[str]] = []
        max_reached_depth = 0

        # BFS from node through reverse adjacency (dependents)
        queue: deque = deque()
        queue.append((node_name, 0, [node_name]))

        while queue:
            current, depth, path = queue.popleft()
            if depth > max_depth:
                continue

            # Find who depends on current (reverse edges)
            dependents = self._reverse_adj.get(current, [])
            for dep in dependents:
                if dep in path:
                    continue  # Avoid revisiting in same path

                new_path = path + [dep]
                dep_depth = depth + 1
                max_reached_depth = max(max_reached_depth, dep_depth)

                # Determine impact level based on depth, node type, and edge weight
                impact = self._compute_impact_level(node_name, dep, dep_depth)
                existing = impacted.get(dep)
                if existing is None or impact.value > existing.value:
                    impacted[dep] = impact

                # Track critical paths (paths that reach critical services)
                dep_node = self._nodes.get(dep)
                if dep_node and dep_node.node_type in ("service", "external"):
                    critical_paths.append(new_path)

                queue.append((dep, dep_depth, new_path))

        # Generate mitigation suggestions
        suggestions = self._generate_mitigations(node_name, impacted)

        return ImpactAnalysis(
            root_node=node_name,
            impacted_nodes=list(impacted.keys()),
            impact_levels=impacted,
            critical_paths=critical_paths[:20],  # Cap at 20 paths
            total_depth=max_reached_depth,
            mitigation_suggestions=suggestions,
        )

    def _compute_impact_level(self, root: str, dependent: str, depth: int) -> ImpactLevel:
        """Compute the impact level of root's failure on dependent."""
        dep_node = self._nodes.get(dependent)
        if not dep_node:
            return ImpactLevel.NONE

        # Base impact from depth
        if depth == 1:
            base = ImpactLevel.HIGH
        elif depth == 2:
            base = ImpactLevel.MEDIUM
        elif depth <= 4:
            base = ImpactLevel.LOW
        else:
            base = ImpactLevel.NONE

        # Upgrade if dependent is critical
        if dep_node.node_type == "external":
            base = ImpactLevel.CRITICAL
        elif dep_node.metadata.get("critical", False):
            if base.value < ImpactLevel.HIGH.value:
                base = ImpactLevel.HIGH

        # Downgrade if redundant (has other healthy dependencies)
        all_deps_of_dependent = self._adjacency.get(dependent, [])
        healthy_alternatives = [
            d for d in all_deps_of_dependent
            if d != root and self._nodes.get(d, DependencyNode(name=d)).health == "healthy"
        ]
        if len(healthy_alternatives) >= 2 and base.value > ImpactLevel.LOW.value:
            base = ImpactLevel(max(base.value - 1, ImpactLevel.LOW.value))

        return base

    def _generate_mitigations(
        self, node_name: str, impacted: Dict[str, ImpactLevel]
    ) -> List[str]:
        """Generate mitigation suggestions based on impact analysis."""
        suggestions = []
        node = self._nodes.get(node_name)

        if not node:
            return suggestions

        # Check for redundancy
        dependents = self._reverse_adj.get(node_name, [])
        if dependents and node.health == "unhealthy":
            suggestions.append(
                f"Consider failing over {node_name} to a healthy replica"
            )

        # Check for critical impacts
        critical_deps = [name for name, level in impacted.items() if level == ImpactLevel.CRITICAL]
        if critical_deps:
            suggestions.append(
                f"CRITICAL: {', '.join(critical_deps)} will be directly affected. "
                f"Activate circuit breakers and notify on-call."
            )

        high_deps = [name for name, level in impacted.items() if level == ImpactLevel.HIGH]
        if high_deps:
            suggestions.append(
                f"HIGH: {', '.join(high_deps)} will experience degraded service. "
                f"Pre-warm caches and enable graceful degradation."
            )

        # Check for cascading risk
        depth_2_plus = [name for name, level in impacted.items() if level.value >= ImpactLevel.MEDIUM.value]
        if len(depth_2_plus) > 5:
            suggestions.append(
                f"CASCADE RISK: {len(depth_2_plus)} services at medium+ impact. "
                f"Consider isolating {node_name} to prevent cascade."
            )

        if not suggestions:
            suggestions.append("Impact is limited. Monitor for changes.")

        return suggestions

    # ── Cycle Detection ───────────────────────────────────────────

    def _would_create_cycle(self, source: str, target: str) -> bool:
        """Check if adding source→target would create a cycle."""
        # A cycle exists if there's already a path from target to source
        visited: Set[str] = set()
        queue: deque = deque([target])
        while queue:
            current = queue.popleft()
            if current == source:
                return True
            if current in visited:
                continue
            visited.add(current)
            for neighbor in self._adjacency.get(current, []):
                queue.append(neighbor)
        return False

    def detect_cycles(self) -> List[List[str]]:
        """Detect all cycles in the graph using DFS."""
        cycles = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self._adjacency.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor)
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    cycles.append(cycle)

            path.pop()
            rec_stack.discard(node)

        for node_name in self._nodes:
            if node_name not in visited:
                dfs(node_name)

        return cycles

    # ── Topological Sort ──────────────────────────────────────────

    def topological_sort(self) -> List[str]:
        """
        Return nodes in topological order (dependencies first).
        Useful for startup ordering (start dependencies before dependents).
        """
        if self._topo_cache is not None:
            return self._topo_cache

        # Kahn's algorithm
        in_degree: Dict[str, int] = defaultdict(int)
        for node_name in self._nodes:
            if node_name not in in_degree:
                in_degree[node_name] = 0
        for edge in self._edges:
            in_degree[edge.target] += 1

        queue: deque = deque([n for n, d in in_degree.items() if d == 0])
        result: List[str] = []

        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in self._adjacency.get(node, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        self._topo_cache = result
        return result

    def startup_order(self) -> List[str]:
        """Alias for topological_sort — dependencies started first."""
        return self.topological_sort()

    def shutdown_order(self) -> List[str]:
        """Reverse of topological sort — dependents stopped first."""
        return list(reversed(self.topological_sort()))

    # ── Resilience Scoring ────────────────────────────────────────

    def resilience_score(self, node_name: str) -> float:
        """
        Compute a 0-1 resilience score for a node.
        Higher = more resilient (more alternative paths, fewer single points of failure).
        """
        if node_name not in self._nodes:
            return 0.0

        # Count dependencies of this node
        deps = self._adjacency.get(node_name, [])
        if not deps:
            return 1.0  # No dependencies = fully resilient

        # For each dependency, check if there are alternatives
        resilient_deps = 0
        for dep in deps:
            dep_node = self._nodes.get(dep)
            if not dep_node:
                continue
            # Check if other nodes provide the same capability
            # (same type, healthy)
            alternatives = [
                n for n, nd in self._nodes.items()
                if n != dep
                and nd.node_type == dep_node.node_type
                and nd.health == "healthy"
            ]
            if alternatives:
                resilient_deps += 1

        return resilient_deps / len(deps)

    def single_points_of_failure(self) -> List[str]:
        """Identify nodes whose failure would have critical/high impact on many services."""
        spofs = []
        for node_name in self._nodes:
            impact = self.analyze_impact(node_name)
            high_plus = sum(1 for v in impact.impact_levels.values() if v.value >= ImpactLevel.HIGH.value)
            if high_plus >= 3 or impact.has_critical_impact:
                spofs.append(node_name)
        return spofs

    # ── Query & Introspection ─────────────────────────────────────

    def get_dependencies(self, node_name: str) -> List[str]:
        """Get direct dependencies of a node."""
        return list(self._adjacency.get(node_name, []))

    def get_dependents(self, node_name: str) -> List[str]:
        """Get nodes that depend on this node."""
        return list(self._reverse_adj.get(node_name, []))

    def get_all_nodes(self) -> List[Dict[str, Any]]:
        """Get all nodes with their info."""
        return [n.to_dict() for n in self._nodes.values()]

    def get_all_edges(self) -> List[Dict[str, Any]]:
        """Get all edges."""
        return [e.to_dict() for e in self._edges]

    def get_subgraph(self, root: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get a subgraph starting from root, up to max_depth."""
        nodes = {}
        edges = []
        visited: Set[str] = set()
        queue: deque = deque([(root, 0)])

        while queue:
            current, depth = queue.popleft()
            if current in visited or depth > max_depth:
                continue
            visited.add(current)

            node = self._nodes.get(current)
            if node:
                nodes[current] = node.to_dict()

            for target in self._adjacency.get(current, []):
                edges.append({"source": current, "target": target})
                queue.append((target, depth + 1))

        return {"nodes": nodes, "edges": edges}

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire graph."""
        return {
            "nodes": self.get_all_nodes(),
            "edges": self.get_all_edges(),
            "topological_order": self.topological_sort(),
            "single_points_of_failure": self.single_points_of_failure(),
        }

    # ── Callbacks ─────────────────────────────────────────────────

    def on_impact(self, callback: Callable) -> None:
        """Register a callback for impact analysis results."""
        self._callbacks.append(callback)

    def _notify_impact(self, node_name: str, old_health: str, new_health: str, impact: ImpactAnalysis) -> None:
        """Notify callbacks of an impact event."""
        for cb in self._callbacks:
            try:
                cb(node_name, old_health, new_health, impact)
            except Exception as e:
                logger.error("Impact callback error: %s", sanitize_for_log(str(e)))

    # ── Internal ──────────────────────────────────────────────────

    def _rebuild_adjacency(self) -> None:
        """Rebuild adjacency lists from edges."""
        self._adjacency.clear()
        self._reverse_adj.clear()
        for edge in self._edges:
            self._adjacency[edge.source].append(edge.target)
            self._reverse_adj[edge.target].append(edge.source)

    def _invalidate_caches(self) -> None:
        """Invalidate computed caches."""
        self._topo_cache = None
        self._cycle_cache = None
