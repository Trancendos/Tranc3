# FID: TRANC3-GBRAIN-002 | Version: 1.0.0 | Module: gbrain
"""
src/gbrain/client.py — Async HTTP client for the GBrain bridge worker.

Wraps the GBrain REST API (port 8030) with typed methods and graceful
degradation: every method catches transport errors and returns a sentinel
value so callers are never interrupted by GBrain unavailability.

Zero-cost: uses httpx (already a project dependency) — no paid services.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "http://localhost:8030"
_TIMEOUT = 5.0  # seconds — keeps ingestion from blocking hot paths


class GBrainClient:
    """
    Async client for the GBrain bridge API.

    Usage::

        async with GBrainClient() as c:
            node_id = await c.create_node("Quantum IIT", "Phi > 3.14 ...", source="agent")
            await c.create_edge(node_id, other_id, relation="supports")
    """

    def __init__(self, base_url: str = _DEFAULT_BASE_URL) -> None:
        self._base_url = base_url.rstrip("/")
        self._client: Any = None

    async def __aenter__(self) -> "GBrainClient":
        try:
            import httpx

            self._client = httpx.AsyncClient(base_url=self._base_url, timeout=_TIMEOUT)
        except ImportError:
            logger.warning("gbrain.client: httpx not available — GBrain sync disabled")
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── Node operations ───────────────────────────────────────────────────────

    async def create_node(
        self,
        title: str,
        content: str,
        source: str = "tranc3-agent",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        importance: float = 0.5,
    ) -> Optional[str]:
        """Create a knowledge node and return its node_id, or None on failure."""
        if self._client is None:
            return None
        try:
            payload: Dict[str, Any] = {
                "title": title,
                "content": content,
                "source": source,
                "importance": importance,
            }
            if tags:
                payload["tags"] = tags
            if metadata:
                payload["metadata"] = metadata
            resp = await self._client.post("/nodes", json=payload)
            resp.raise_for_status()
            return resp.json().get("node_id")
        except Exception as exc:
            logger.debug("gbrain.client create_node failed: %s", exc)
            return None

    async def get_node(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a node by ID, or None if unavailable."""
        if self._client is None:
            return None
        try:
            resp = await self._client.get(f"/nodes/{node_id}")
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("gbrain.client get_node failed: %s", exc)
            return None

    # ── Edge operations ───────────────────────────────────────────────────────

    async def create_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str = "related_to",
        weight: float = 1.0,
    ) -> Optional[str]:
        """Create a directed edge and return its edge_id, or None on failure."""
        if self._client is None:
            return None
        try:
            resp = await self._client.post(
                "/edges",
                json={
                    "source_id": source_id,
                    "target_id": target_id,
                    "relation": relation,
                    "weight": weight,
                },
            )
            resp.raise_for_status()
            return resp.json().get("edge_id")
        except Exception as exc:
            logger.debug("gbrain.client create_edge failed: %s", exc)
            return None

    # ── Search ────────────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        max_results: int = 10,
        use_graph_expansion: bool = True,
    ) -> List[Dict[str, Any]]:
        """Search the knowledge graph, returning a list of result nodes."""
        if self._client is None:
            return []
        try:
            resp = await self._client.post(
                "/search",
                json={
                    "query": query,
                    "max_results": max_results,
                    "use_graph_expansion": use_graph_expansion,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("direct_results", []) + data.get("expanded_results", [])
        except Exception as exc:
            logger.debug("gbrain.client search failed: %s", exc)
            return []

    # ── Graph ops ─────────────────────────────────────────────────────────────

    async def recompute_pagerank(self) -> bool:
        """Trigger PageRank recomputation; returns True on success."""
        if self._client is None:
            return False
        try:
            resp = await self._client.post("/pagerank/recompute")
            resp.raise_for_status()
            return resp.json().get("status") == "recomputed"
        except Exception as exc:
            logger.debug("gbrain.client pagerank failed: %s", exc)
            return False

    async def health(self) -> bool:
        """Return True if GBrain bridge is reachable and healthy."""
        if self._client is None:
            return False
        try:
            resp = await self._client.get("/health")
            resp.raise_for_status()
            return resp.json().get("status") == "healthy"
        except Exception:
            return False

    async def stats(self) -> Dict[str, Any]:
        """Return graph statistics, or empty dict on failure."""
        if self._client is None:
            return {}
        try:
            resp = await self._client.get("/graph/stats")
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            logger.debug("gbrain.client stats failed: %s", exc)
            return {}
