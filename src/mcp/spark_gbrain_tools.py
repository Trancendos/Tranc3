"""
spark_gbrain_tools.py — GBrain Bridge tools for The Spark MCP server.

Registers 7 SparkTool instances exposing The Library / GBrain-Bridge (port 8030):

  Nodes:
    - gbrain_add_node        — add a knowledge node to the graph
    - gbrain_get_node        — retrieve a node and its PageRank score
    - gbrain_neighbourhood   — fetch multi-hop neighbourhood of a node

  Edges:
    - gbrain_add_edge        — create a directed relationship between two nodes

  Search & Ranking:
    - gbrain_search          — full-text + PageRank-boosted graph search
    - gbrain_recompute       — trigger PageRank recomputation

  Housekeeping:
    - gbrain_stats           — graph statistics (node count, edge count, PageRank ready)

All handlers are async and call the gbrain-bridge worker (port 8030) via httpx.
If the worker is unavailable, tools return a structured error rather than raising.

Usage:
    from src.mcp.spark_gbrain_tools import register_gbrain_tools
    register_gbrain_tools(registry)   # registry: SparkToolRegistry
"""

from __future__ import annotations

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

_GBRAIN_URL = "http://localhost:8030"


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------


async def _gbrain_get(path: str, **params: Any) -> Dict[str, Any]:
    try:
        import httpx  # type: ignore[import-not-found]

        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(f"{_GBRAIN_URL}{path}", params=params or None)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        return {"error": str(exc), "ok": False}


async def _gbrain_post(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    try:
        import httpx  # type: ignore[import-not-found]

        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.post(f"{_GBRAIN_URL}{path}", json=payload)
            r.raise_for_status()
            return r.json()
    except Exception as exc:
        return {"error": str(exc), "ok": False}


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _handle_gbrain_add_node(params: Dict[str, Any]) -> Dict[str, Any]:
    """Add a knowledge node to the GBrain graph."""
    label = params.get("label")
    if not label:
        return {"error": "label is required", "ok": False}
    payload: Dict[str, Any] = {
        "label": label,
        "node_type": params.get("node_type", "concept"),
    }
    if "content" in params:
        payload["content"] = params["content"]
    if "tags" in params:
        payload["tags"] = params["tags"]
    if "metadata" in params:
        payload["metadata"] = params["metadata"]
    return await _gbrain_post("/nodes", payload)


async def _handle_gbrain_get_node(params: Dict[str, Any]) -> Dict[str, Any]:
    """Retrieve a graph node and its PageRank score."""
    node_id = params.get("node_id", "")
    if not node_id:
        return {"error": "node_id is required", "ok": False}
    return await _gbrain_get(f"/nodes/{node_id}")


async def _handle_gbrain_neighbourhood(params: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch the multi-hop neighbourhood of a graph node."""
    node_id = params.get("node_id", "")
    if not node_id:
        return {"error": "node_id is required", "ok": False}
    depth = int(params.get("depth", 2))
    return await _gbrain_get(f"/nodes/{node_id}/neighbourhood", depth=depth)


async def _handle_gbrain_add_edge(params: Dict[str, Any]) -> Dict[str, Any]:
    """Create a directed edge between two knowledge nodes."""
    payload: Dict[str, Any] = {
        "source_id": params["source_id"],
        "target_id": params["target_id"],
        "relation": params.get("relation", "related_to"),
        "weight": float(params.get("weight", 1.0)),
    }
    return await _gbrain_post("/edges", payload)


async def _handle_gbrain_search(params: Dict[str, Any]) -> Dict[str, Any]:
    """Full-text search over the GBrain knowledge graph with PageRank boosting."""
    payload: Dict[str, Any] = {
        "query": params["query"],
        "limit": int(params.get("limit", 10)),
        "use_pagerank": bool(params.get("use_pagerank", True)),
        "node_types": params.get("node_types"),
    }
    return await _gbrain_post("/search", payload)


async def _handle_gbrain_recompute(params: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
    """Trigger PageRank recomputation across the entire knowledge graph."""
    return await _gbrain_post("/pagerank/recompute", {})


async def _handle_gbrain_stats(params: Dict[str, Any]) -> Dict[str, Any]:  # noqa: ARG001
    """Return graph statistics: node count, edge count, PageRank status."""
    return await _gbrain_get("/graph/stats")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_gbrain_tools(registry: Any) -> int:
    """Register all GBrain Bridge tools into *registry*.

    Returns the number of tools registered.
    """
    from src.mcp.tools import SparkTool  # codeql[py/cyclic-import]

    tools = [
        SparkTool(
            name="gbrain_add_node",
            description=(
                "Add a knowledge node to The Library's GBrain knowledge graph. "
                "Nodes represent concepts, facts, agents, documents, or events."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "label": {"type": "string", "description": "Human-readable node label"},
                    "node_type": {
                        "type": "string",
                        "enum": ["concept", "fact", "agent", "document", "event", "entity"],
                        "default": "concept",
                    },
                    "content": {"type": "string", "description": "Optional node text content"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional tags",
                    },
                    "metadata": {"type": "object", "description": "Optional structured metadata"},
                },
                "required": ["label"],
            },
            handler=_handle_gbrain_add_node,
            category="knowledge",
        ),
        SparkTool(
            name="gbrain_get_node",
            description=(
                "Retrieve a GBrain knowledge node by ID, including its PageRank score "
                "and temporal decay factor."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID of the node to retrieve"},
                },
                "required": ["node_id"],
            },
            handler=_handle_gbrain_get_node,
            category="knowledge",
        ),
        SparkTool(
            name="gbrain_neighbourhood",
            description=(
                "Fetch the multi-hop neighbourhood of a GBrain node — returns all "
                "nodes reachable within *depth* hops, ordered by PageRank."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "node_id": {"type": "string", "description": "UUID of the root node"},
                    "depth": {
                        "type": "integer",
                        "default": 2,
                        "minimum": 1,
                        "maximum": 4,
                        "description": "Maximum hop depth (1–4)",
                    },
                },
                "required": ["node_id"],
            },
            handler=_handle_gbrain_neighbourhood,
            category="knowledge",
        ),
        SparkTool(
            name="gbrain_add_edge",
            description=(
                "Create a directed relationship (edge) between two GBrain knowledge nodes. "
                "Edge weight influences PageRank propagation."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "source_id": {"type": "string", "description": "UUID of the source node"},
                    "target_id": {"type": "string", "description": "UUID of the target node"},
                    "relation": {
                        "type": "string",
                        "description": "Relationship type, e.g. 'related_to', 'part_of', 'causes'",
                        "default": "related_to",
                    },
                    "weight": {
                        "type": "number",
                        "default": 1.0,
                        "minimum": 0.0,
                        "maximum": 10.0,
                        "description": "Edge weight for PageRank propagation",
                    },
                },
                "required": ["source_id", "target_id"],
            },
            handler=_handle_gbrain_add_edge,
            category="knowledge",
        ),
        SparkTool(
            name="gbrain_search",
            description=(
                "Search the GBrain knowledge graph using full-text matching with optional "
                "PageRank-boosted re-ranking. Returns nodes ordered by relevance × importance."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "limit": {
                        "type": "integer",
                        "default": 10,
                        "minimum": 1,
                        "maximum": 50,
                        "description": "Maximum number of results",
                    },
                    "use_pagerank": {
                        "type": "boolean",
                        "default": True,
                        "description": "Apply PageRank re-ranking on top of text score",
                    },
                    "node_types": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Filter by node types (empty = all types)",
                    },
                },
                "required": ["query"],
            },
            handler=_handle_gbrain_search,
            category="knowledge",
        ),
        SparkTool(
            name="gbrain_recompute",
            description=(
                "Trigger a full PageRank recomputation across the GBrain knowledge graph. "
                "Run after bulk ingestion to update node importance scores."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_handle_gbrain_recompute,
            category="knowledge",
        ),
        SparkTool(
            name="gbrain_stats",
            description=(
                "Return GBrain knowledge graph statistics: node count, edge count, "
                "PageRank readiness, and consolidation status."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=_handle_gbrain_stats,
            category="knowledge",
        ),
    ]

    count = 0
    for tool in tools:
        registry.register(tool)
        count += 1

    logger.info("GBrain Spark tools registered: %d tools", count)
    return count
