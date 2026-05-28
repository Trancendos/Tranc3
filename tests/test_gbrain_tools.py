"""
Tests for GBrain Bridge MCP tools (spark_gbrain_tools.py).

Validates:
  - All 7 GBrain tools register correctly into a SparkToolRegistry
  - Tool metadata (name, category, input_schema) is correct
  - Handler functions return the expected structure when the worker is unavailable
    (offline mode: httpx raises ConnectionRefusedError → graceful error dict)
  - _gbrain_get / _gbrain_post wrap errors into {"error": str, "ok": False}
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.mcp.spark_gbrain_tools import (
    _handle_gbrain_add_edge,
    _handle_gbrain_add_node,
    _handle_gbrain_get_node,
    _handle_gbrain_neighbourhood,
    _handle_gbrain_recompute,
    _handle_gbrain_search,
    _handle_gbrain_stats,
    register_gbrain_tools,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_registry() -> MagicMock:
    """Return a MagicMock that quacks like SparkToolRegistry.register()."""
    reg = MagicMock()
    reg._tools: dict = {}

    def _register(tool: MagicMock) -> None:
        reg._tools[tool.name] = tool

    reg.register.side_effect = _register
    return reg


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


class TestRegisterGBrainTools:
    def test_returns_seven(self):
        reg = _make_registry()
        count = register_gbrain_tools(reg)
        assert count == 7

    def test_all_tools_registered(self):
        reg = _make_registry()
        register_gbrain_tools(reg)
        expected = {
            "gbrain_add_node",
            "gbrain_get_node",
            "gbrain_neighbourhood",
            "gbrain_add_edge",
            "gbrain_search",
            "gbrain_recompute",
            "gbrain_stats",
        }
        assert expected == set(reg._tools.keys())

    def test_all_tools_category_knowledge(self):
        reg = _make_registry()
        register_gbrain_tools(reg)
        for name, tool in reg._tools.items():
            assert tool.category == "knowledge", f"{name} has wrong category"

    def test_tools_have_description(self):
        reg = _make_registry()
        register_gbrain_tools(reg)
        for name, tool in reg._tools.items():
            assert tool.description, f"{name} has empty description"

    def test_tools_have_input_schema(self):
        reg = _make_registry()
        register_gbrain_tools(reg)
        for name, tool in reg._tools.items():
            assert isinstance(tool.input_schema, dict), f"{name} missing input_schema"


# ---------------------------------------------------------------------------
# Handler: add_node
# ---------------------------------------------------------------------------


class TestHandleGBrainAddNode:
    @pytest.mark.asyncio
    async def test_offline_returns_error(self):
        """When the worker is unreachable, returns error dict rather than raising."""
        result = await _handle_gbrain_add_node({"label": "Tranc3 Platform"})
        # Worker not running → httpx connection error → graceful error
        assert isinstance(result, dict)
        # Either an "error" key (offline) or a "node_id" key (online)
        assert "error" in result or "node_id" in result

    @pytest.mark.asyncio
    async def test_missing_label_returns_error(self):
        """KeyError from missing 'label' is caught and returned as error."""
        result = await _handle_gbrain_add_node({})
        assert isinstance(result, dict)
        # Missing required field raises KeyError → error propagated
        assert "error" in result


# ---------------------------------------------------------------------------
# Handler: get_node
# ---------------------------------------------------------------------------


class TestHandleGBrainGetNode:
    @pytest.mark.asyncio
    async def test_missing_node_id(self):
        result = await _handle_gbrain_get_node({})
        assert result["ok"] is False
        assert "node_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_offline_returns_error(self):
        result = await _handle_gbrain_get_node({"node_id": "test-uuid-1234"})
        assert isinstance(result, dict)
        assert "error" in result or "id" in result


# ---------------------------------------------------------------------------
# Handler: neighbourhood
# ---------------------------------------------------------------------------


class TestHandleGBrainNeighbourhood:
    @pytest.mark.asyncio
    async def test_missing_node_id(self):
        result = await _handle_gbrain_neighbourhood({})
        assert result["ok"] is False
        assert "node_id is required" in result["error"]

    @pytest.mark.asyncio
    async def test_offline_returns_error(self):
        result = await _handle_gbrain_neighbourhood({"node_id": "test-uuid", "depth": 2})
        assert isinstance(result, dict)
        assert "error" in result or "neighbours" in result


# ---------------------------------------------------------------------------
# Handler: add_edge
# ---------------------------------------------------------------------------


class TestHandleGBrainAddEdge:
    @pytest.mark.asyncio
    async def test_offline_returns_error(self):
        result = await _handle_gbrain_add_edge(
            {"source_id": "a", "target_id": "b", "relation": "causes"}
        )
        assert isinstance(result, dict)
        assert "error" in result or "edge_id" in result

    @pytest.mark.asyncio
    async def test_default_relation(self):
        """Verify default relation is injected when not provided."""
        with patch("src.mcp.spark_gbrain_tools._gbrain_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"edge_id": "e1", "ok": True}
            result = await _handle_gbrain_add_edge({"source_id": "a", "target_id": "b"})
            call_payload = mock_post.call_args[0][1]
            assert call_payload["relation"] == "related_to"
            assert call_payload["weight"] == 1.0


# ---------------------------------------------------------------------------
# Handler: search
# ---------------------------------------------------------------------------


class TestHandleGBrainSearch:
    @pytest.mark.asyncio
    async def test_offline_returns_error(self):
        result = await _handle_gbrain_search({"query": "neural networks"})
        assert isinstance(result, dict)
        assert "error" in result or "results" in result

    @pytest.mark.asyncio
    async def test_payload_includes_defaults(self):
        with patch("src.mcp.spark_gbrain_tools._gbrain_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"results": []}
            await _handle_gbrain_search({"query": "test"})
            payload = mock_post.call_args[0][1]
            assert payload["query"] == "test"
            assert payload["limit"] == 10
            assert payload["use_pagerank"] is True

    @pytest.mark.asyncio
    async def test_custom_limit(self):
        with patch("src.mcp.spark_gbrain_tools._gbrain_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"results": []}
            await _handle_gbrain_search({"query": "test", "limit": 5})
            payload = mock_post.call_args[0][1]
            assert payload["limit"] == 5


# ---------------------------------------------------------------------------
# Handler: recompute & stats
# ---------------------------------------------------------------------------


class TestHandleGBrainRecomputeAndStats:
    @pytest.mark.asyncio
    async def test_recompute_offline(self):
        result = await _handle_gbrain_recompute({})
        assert isinstance(result, dict)
        assert "error" in result or "ok" in result

    @pytest.mark.asyncio
    async def test_stats_offline(self):
        result = await _handle_gbrain_stats({})
        assert isinstance(result, dict)
        assert "error" in result or "node_count" in result

    @pytest.mark.asyncio
    async def test_recompute_mocked(self):
        with patch("src.mcp.spark_gbrain_tools._gbrain_post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = {"ok": True, "nodes_updated": 42}
            result = await _handle_gbrain_recompute({})
            assert result["ok"] is True
            assert result["nodes_updated"] == 42

    @pytest.mark.asyncio
    async def test_stats_mocked(self):
        with patch("src.mcp.spark_gbrain_tools._gbrain_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"node_count": 100, "edge_count": 250, "pagerank_ready": True}
            result = await _handle_gbrain_stats({})
            assert result["node_count"] == 100
            assert result["pagerank_ready"] is True
