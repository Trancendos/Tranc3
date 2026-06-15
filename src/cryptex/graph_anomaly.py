"""Graph anomaly detection for service call graph lateral movement."""

from __future__ import annotations

try:
    import networkx as nx  # type: ignore

    _NX_AVAILABLE = True
except ImportError:
    _NX_AVAILABLE = False


class ServiceCallGraph:
    def __init__(self) -> None:
        self._nx_available: bool = _NX_AVAILABLE
        # Adjacency dict: src -> {dst -> weight}
        self._graph: dict[str, dict[str, int]] = {}
        self._baseline_adj: dict[str, dict[str, int]] = {}

        if self._nx_available:
            self._nx_graph: "nx.DiGraph" = nx.DiGraph()
            self._nx_baseline: "nx.DiGraph" = nx.DiGraph()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _adj_nodes(self, adj: dict[str, dict[str, int]]) -> set[str]:
        nodes: set[str] = set()
        for src, dsts in adj.items():
            nodes.add(src)
            nodes.update(dsts.keys())
        return nodes

    def _degree(self, adj: dict[str, dict[str, int]], node: str) -> int:
        """Out-degree + in-degree for a node in the adjacency dict."""
        out_deg = len(adj.get(node, {}))
        in_deg = sum(1 for dsts in adj.values() if node in dsts)
        return out_deg + in_deg

    def _centrality(self, adj: dict[str, dict[str, int]]) -> dict[str, float]:
        """Degree centrality: degree / max(1, n-1)."""
        nodes = self._adj_nodes(adj)
        n = len(nodes)
        if n <= 1:
            return dict.fromkeys(nodes, 0.0)
        return {node: self._degree(adj, node) / (n - 1) for node in nodes}

    def _find_paths_through_new_edges(self) -> list[list[str]]:
        """BFS/DFS paths of length >= 3 that include at least one new edge."""
        baseline_edges: set[tuple[str, str]] = set()
        for src, dsts in self._baseline_adj.items():
            for dst in dsts:
                baseline_edges.add((src, dst))

        current_edges: set[tuple[str, str]] = set()
        for src, dsts in self._graph.items():
            for dst in dsts:
                current_edges.add((src, dst))

        new_edges = current_edges - baseline_edges
        if not new_edges:
            return []

        # Build adjacency list for current graph
        adj_list: dict[str, list[str]] = {}
        for src, dst in current_edges:
            adj_list.setdefault(src, []).append(dst)

        paths: list[list[str]] = []
        visited_paths: set[tuple[str, ...]] = set()

        def dfs(path: list[str], has_new_edge: bool) -> None:
            if len(path) >= 3 and has_new_edge:
                key = tuple(path)
                if key not in visited_paths:
                    visited_paths.add(key)
                    paths.append(list(path))

            if len(path) >= 6:  # cap to avoid explosion
                return

            current = path[-1]
            for nxt in adj_list.get(current, []):
                if nxt not in path:  # no cycles
                    edge = (current, nxt)
                    dfs(path + [nxt], has_new_edge or edge in new_edges)

        # Start DFS from each node that has a new edge
        new_edge_nodes = {src for src, _ in new_edges} | {dst for _, dst in new_edges}
        for start in new_edge_nodes:
            dfs([start], False)

        return paths

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def record_call(self, src: str, dst: str, weight: int = 1) -> None:
        """Add or increment an edge in the call graph."""
        self._graph.setdefault(src, {})
        self._graph[src][dst] = self._graph[src].get(dst, 0) + weight

        if self._nx_available:
            if self._nx_graph.has_edge(src, dst):
                self._nx_graph[src][dst]["weight"] = (
                    self._nx_graph[src][dst].get("weight", 0) + weight
                )
            else:
                self._nx_graph.add_edge(src, dst, weight=weight)

    def baseline(self) -> None:
        """Snapshot the current graph state as the normal baseline."""
        import copy

        self._baseline_adj = copy.deepcopy(self._graph)

        if self._nx_available:
            self._nx_baseline = self._nx_graph.copy()

    def detect_anomalies(self) -> list[dict]:
        """Compare current graph to baseline and return anomaly records."""
        anomalies: list[dict] = []

        baseline_nodes = self._adj_nodes(self._baseline_adj)
        current_nodes = self._adj_nodes(self._graph)

        # New nodes
        for node in current_nodes - baseline_nodes:
            anomalies.append({"type": "new_node", "src": node, "dst": "", "score": 1.0})

        # Edge anomalies
        for src, dsts in self._graph.items():
            for dst, weight in dsts.items():
                baseline_weight = self._baseline_adj.get(src, {}).get(dst)
                if baseline_weight is None:
                    # New edge
                    anomalies.append(
                        {
                            "type": "new_edge",
                            "src": src,
                            "dst": dst,
                            "score": min(1.0, weight / 10.0),
                        }
                    )
                elif weight > 3 * baseline_weight:
                    ratio = weight / max(1, baseline_weight)
                    anomalies.append(
                        {
                            "type": "weight_spike",
                            "src": src,
                            "dst": dst,
                            "score": min(1.0, ratio / 10.0),
                        }
                    )

        return anomalies

    def detect_lateral_movement(self) -> list[dict]:
        """Find paths of length >= 3 through new edges."""
        paths = self._find_paths_through_new_edges()
        results: list[dict] = []
        for path in paths:
            # Longer paths or paths through many new edges are higher risk
            risk: str = "high" if len(path) >= 5 else "medium"
            results.append({"path": path, "risk": risk})
        return results

    def centrality_anomalies(self) -> list[dict]:
        """Return nodes whose degree centrality increased >50% vs baseline."""
        baseline_cent = self._centrality(self._baseline_adj)
        current_cent = self._centrality(self._graph)

        results: list[dict] = []
        for node, current_c in current_cent.items():
            baseline_c = baseline_cent.get(node, 0.0)
            if baseline_c == 0.0:
                # New node — skip (already reported as new_node anomaly)
                continue
            increase = (current_c - baseline_c) / max(1e-9, baseline_c)
            if increase > 0.5:
                results.append(
                    {
                        "node": node,
                        "baseline_centrality": round(baseline_c, 6),
                        "current_centrality": round(current_c, 6),
                    }
                )
        return results

    def summary(self) -> dict:
        """High-level summary of graph state and anomaly counts."""
        nodes = self._adj_nodes(self._graph)
        edge_count = sum(len(dsts) for dsts in self._graph.values())
        anomalies = self.detect_anomalies()
        lateral = self.detect_lateral_movement()
        return {
            "node_count": len(nodes),
            "edge_count": edge_count,
            "anomaly_count": len(anomalies),
            "lateral_movement_paths_count": len(lateral),
        }
