"""
shared_core.orchestration.dependency_graph — Smart dependency graph with impact analysis.

Provides a directed graph for tracking service dependencies, with features
including cycle detection, impact analysis, topological sorting, resilience
scoring, and single-point-of-failure identification.

Zero-cost: All graph operations are in-process, no external services required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set


@dataclass
class GraphNode:
    """A node in the dependency graph."""

    name: str
    node_type: str = "service"
    health: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "node_type": self.node_type,
            "health": self.health,
            "metadata": self.metadata,
        }


@dataclass
class GraphEdge:
    """A directed edge in the dependency graph (source depends on target)."""

    source: str
    target: str
    dep_type: str = "runtime"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "target": self.target,
            "dep_type": self.dep_type,
        }


@dataclass
class ImpactAnalysis:
    """Result of impact analysis for a node failure."""

    root_node: str
    impacted_nodes: List[str] = field(default_factory=list)
    mitigation_suggestions: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "root_node": self.root_node,
            "impacted_nodes": self.impacted_nodes,
            "mitigation_suggestions": self.mitigation_suggestions,
        }


class SmartDependencyGraph:
    """Smart dependency graph with impact analysis and cycle detection.

    Tracks directed dependencies between services (source depends on target)
    and provides impact analysis, topological sorting, and resilience scoring.

    Edges represent "source depends on target" — so if auth depends on db,
    add_edge("auth", "db") means auth -> db (auth requires db).
    """

    def __init__(self) -> None:
        self._nodes: Dict[str, GraphNode] = {}
        self._edges: List[GraphEdge] = []
        self._impact_callbacks: List[Callable] = []

    def add_node(
        self,
        name: str,
        node_type: str = "service",
        health: str = "unknown",
        **metadata: Any,
    ) -> GraphNode:
        """Add a node to the graph.

        Args:
            name: Unique node name.
            node_type: Type of node (service, database, etc.).
            health: Initial health status.
            **metadata: Additional node metadata.

        Returns:
            The created GraphNode.
        """
        node = GraphNode(name=name, node_type=node_type, health=health, metadata=metadata)
        self._nodes[name] = node
        return node

    def get_node(self, name: str) -> Optional[GraphNode]:
        """Get a node by name."""
        return self._nodes.get(name)

    def get_all_nodes(self) -> List[GraphNode]:
        """Get all nodes."""
        return list(self._nodes.values())

    def add_edge(
        self,
        source: str,
        target: str,
        dep_type: str = "runtime",
    ) -> Optional[GraphEdge]:
        """Add a directed edge (source depends on target).

        Args:
            source: The dependent node.
            target: The dependency node.
            dep_type: Type of dependency.

        Returns:
            The created GraphEdge, or None if it would create a cycle.
        """
        # Check for cycle: would adding source->target create a path from target to source?
        if self._would_create_cycle(source, target):
            return None

        edge = GraphEdge(source=source, target=target, dep_type=dep_type)
        self._edges.append(edge)
        return edge

    def _would_create_cycle(self, source: str, target: str) -> bool:
        """Check if adding source->target would create a cycle.

        A cycle exists if there is already a path from target to source.
        """
        visited: Set[str] = set()
        return self._has_path(target, source, visited)

    def _has_path(self, from_node: str, to_node: str, visited: Set[str]) -> bool:
        """Check if there is a path from from_node to to_node."""
        if from_node == to_node:
            return True
        if from_node in visited:
            return False
        visited.add(from_node)
        # Follow edges from from_node
        for edge in self._edges:
            if edge.source == from_node:
                if self._has_path(edge.target, to_node, visited):
                    return True
        return False

    def get_dependents(self, name: str) -> List[str]:
        """Get nodes that depend on the given node.

        Returns names of nodes where source == name in an edge,
        meaning nodes that list 'name' as a dependency.
        """
        # A dependent of 'name' is a node that has an edge pointing TO 'name'
        # i.e., edge.target == name, so edge.source depends on name
        return [edge.source for edge in self._edges if edge.target == name]

    def get_dependencies(self, name: str) -> List[str]:
        """Get nodes that the given node depends on.

        Returns names of nodes where target is in an edge from name,
        meaning nodes that 'name' depends on.
        """
        return [edge.target for edge in self._edges if edge.source == name]

    def analyze_impact(self, name: str) -> ImpactAnalysis:
        """Analyze the impact of a node failure.

        Traces all dependents (transitively) that would be affected.

        Args:
            name: The node that might fail.

        Returns:
            ImpactAnalysis with impacted nodes and mitigation suggestions.
        """
        impacted: List[str] = []
        suggestions: List[str] = []
        visited: Set[str] = set()

        # BFS from the failed node through dependents
        queue = [name]
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if current != name:
                impacted.append(current)

            # Find dependents (nodes that depend on current)
            dependents = self.get_dependents(current)
            for dep in dependents:
                if dep not in visited:
                    queue.append(dep)

        # Generate mitigation suggestions
        deps = self.get_dependencies(name)
        if len(deps) == 0:
            suggestions.append(f"Consider adding backup for {name}")
        for dep in deps:
            suggestions.append(f"Consider fallback for {name} -> {dep}")

        return ImpactAnalysis(
            root_node=name,
            impacted_nodes=impacted,
            mitigation_suggestions=suggestions,
        )

    def topological_sort(self) -> List[str]:
        """Return nodes in topological order (dependents before dependencies).

        Uses Kahn's algorithm. Nodes with no dependents (in-degree 0) come first.
        """
        # Build in-degree map (how many nodes depend on this node)
        in_degree: Dict[str, int] = dict.fromkeys(self._nodes, 0)
        for _edge in self._edges:
            # _edge.source depends on _edge.target
            # so _edge.target has in-degree incremented (it's depended upon)
            # In our topological sort, dependents come first
            # So we need out-degree from the dependent perspective
            pass

        # Actually, for "dependents before dependencies":
        # The graph has edges source->target (source depends on target)
        # We want dependents first, so sources before targets
        # In-degree for topological sort = number of edges pointing TO this node
        in_degree = dict.fromkeys(self._nodes, 0)
        for edge in self._edges:
            in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        # Start with nodes that have no incoming edges (no one depends on them, they depend on others)
        queue = [name for name, deg in in_degree.items() if deg == 0]
        result: List[str] = []

        while queue:
            node = queue.pop(0)
            result.append(node)
            # Process outgoing edges from this node
            for edge in self._edges:
                if edge.source == node:
                    in_degree[edge.target] -= 1
                    if in_degree[edge.target] == 0:
                        queue.append(edge.target)

        return result

    def startup_order(self) -> List[str]:
        """Return nodes in startup order (dependencies before dependents)."""
        return list(reversed(self.topological_sort()))

    def shutdown_order(self) -> List[str]:
        """Return nodes in shutdown order (dependents before dependencies)."""
        return self.topological_sort()

    def resilience_score(self, name: str) -> float:
        """Compute resilience score for a node (0.0 to 1.0).

        Higher score means more resilient (more redundant dependencies).

        Args:
            name: Node name.

        Returns:
            Resilience score between 0.0 and 1.0.
        """
        deps = self.get_dependencies(name)
        if not deps:
            return 0.0

        # Check for redundant dependencies (same node_type)
        dep_types: Dict[str, int] = {}
        for dep_name in deps:
            dep_node = self._nodes.get(dep_name)
            if dep_node:
                dep_types[dep_node.node_type] = dep_types.get(dep_node.node_type, 0) + 1

        # Score based on redundancy
        total_deps = len(deps)
        redundant_deps = sum(count - 1 for count in dep_types.values() if count > 1)
        if total_deps == 0:
            return 0.0

        return min(1.0, redundant_deps / max(total_deps, 1) + 0.1 * total_deps)

    def single_points_of_failure(self) -> List[str]:
        """Identify nodes that are single points of failure.

        A node is a SPOF if multiple other nodes depend on it and
        there are no alternatives (same node_type).
        """
        spofs: List[str] = []
        for name, node in self._nodes.items():
            dependents = self.get_dependents(name)
            if len(dependents) >= 2:
                # Check if there are alternatives (same node_type)
                alternatives = [
                    n
                    for n, nd in self._nodes.items()
                    if nd.node_type == node.node_type and n != name
                ]
                if not alternatives:
                    spofs.append(name)
        return spofs

    def remove_node(self, name: str) -> None:
        """Remove a node and all its edges."""
        self._nodes.pop(name, None)
        self._edges = [e for e in self._edges if e.source != name and e.target != name]

    def get_subgraph(self, root: str, max_depth: int = 3) -> Dict[str, Any]:
        """Get a subgraph starting from a root node.

        Args:
            root: Starting node.
            max_depth: Maximum traversal depth.

        Returns:
            Dict with "nodes" and "edges" lists.
        """
        visited_nodes: Set[str] = set()
        visited_edges: List[GraphEdge] = []
        queue = [(root, 0)]

        while queue:
            current, depth = queue.pop(0)
            if current in visited_nodes or depth > max_depth:
                continue
            visited_nodes.add(current)

            for edge in self._edges:
                if edge.source == current:
                    visited_edges.append(edge)
                    if edge.target not in visited_nodes:
                        queue.append((edge.target, depth + 1))
                elif edge.target == current:
                    visited_edges.append(edge)
                    if edge.source not in visited_nodes:
                        queue.append((edge.source, depth + 1))

        return {
            "nodes": list(visited_nodes),
            "edges": [e.to_dict() for e in visited_edges],
        }

    def on_impact(self, callback: Callable) -> None:
        """Register a callback for impact events."""
        self._impact_callbacks.append(callback)

    def update_node_health(self, name: str, health: str) -> None:
        """Update a node's health status.

        Args:
            name: Node name.
            health: New health status.
        """
        node = self._nodes.get(name)
        if node:
            old_health = node.health
            node.health = health
            # If health degraded, notify impact callbacks
            if health == "unhealthy" and old_health != "unhealthy":
                impact = self.analyze_impact(name)
                for cb in self._impact_callbacks:
                    try:
                        cb(name, impact)
                    except Exception:
                        pass

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the entire graph."""
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
        }
