# FID: TRANC3-TEST-016 | Version: 1.0.0 | Module: gbrain
"""
tests/test_gbrain_worker.py — Route-level tests for GBrain bridge worker.

Uses httpx.AsyncClient + ASGITransport to exercise the FastAPI app
in-process without starting a live uvicorn server.

All tests use an isolated SQLite database in a tmp_path so each test
run starts with a clean state.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Worker module loader (handles hyphen in directory name)
# ---------------------------------------------------------------------------

_WORKER_PATH = Path(__file__).parent.parent / "workers" / "gbrain-bridge" / "worker.py"


def _load_worker_module():
    """Import workers/gbrain-bridge/worker.py by file path."""
    spec = importlib.util.spec_from_file_location("gbrain_bridge_worker", _WORKER_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(coro):
    """Run coroutine synchronously — safe for use inside sync test methods."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def _worker(tmp_path, monkeypatch):
    """Yield the worker module with DB isolated to tmp_path."""
    db_path = tmp_path / "gbrain.db"

    # Remove cached module so each fixture gets a fresh instance
    mod_key = "gbrain_bridge_worker"
    if mod_key in sys.modules:
        del sys.modules[mod_key]

    # Load fresh module and patch DB_PATH before _DB.init() runs
    spec = importlib.util.spec_from_file_location(mod_key, _WORKER_PATH)
    mod = importlib.util.module_from_spec(spec)
    # Patch DB_PATH on the module object before exec_module runs init
    mod.__dict__["DB_PATH"] = db_path
    spec.loader.exec_module(mod)

    # Reinitialise the database with the patched path
    # (_DB creates schema lazily on first conn() call)
    mod._db._path = db_path
    mod._db._conn = None
    mod._db.conn()  # trigger schema creation synchronously

    sys.modules[mod_key] = mod
    yield mod


def _client(app, secret=""):
    import httpx

    headers = {"X-Internal-Secret": secret} if secret else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers,
    )


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


class TestHealthEndpoint:
    def test_health_returns_200(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.get("/health")

        resp = _run(_go())
        assert resp.status_code == 200

    def test_health_has_status_healthy(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.get("/health")).json()

        data = _run(_go())
        assert data["status"] == "healthy"

    def test_health_reports_node_count(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.get("/health")).json()

        data = _run(_go())
        assert "nodes" in data
        assert data["nodes"] == 0  # fresh DB


# ---------------------------------------------------------------------------
# Node CRUD
# ---------------------------------------------------------------------------


class TestNodeCRUD:
    def test_create_node_returns_201(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post(
                    "/nodes",
                    json={"title": "Test Node", "content": "hello", "source": "test"},
                )

        resp = _run(_go())
        assert resp.status_code == 201

    def test_create_node_returns_node_id(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={"title": "Node X", "content": "content", "source": "src"},
                )
                return r.json()

        data = _run(_go())
        assert "node_id" in data
        assert len(data["node_id"]) == 36  # UUID4

    def test_get_node_after_create(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                create = await c.post(
                    "/nodes",
                    json={"title": "Retrievable", "content": "body", "source": "s"},
                )
                nid = create.json()["node_id"]
                return await c.get(f"/nodes/{nid}")

        resp = _run(_go())
        assert resp.status_code == 200
        assert resp.json()["title"] == "Retrievable"

    def test_get_nonexistent_node_returns_404(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.get("/nodes/00000000-0000-0000-0000-000000000000")

        resp = _run(_go())
        assert resp.status_code == 404

    def test_create_multiple_nodes_increments_count(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                for i in range(3):
                    await c.post(
                        "/nodes",
                        json={"title": f"Node {i}", "content": "c", "source": "s"},
                    )
                return (await c.get("/health")).json()

        data = _run(_go())
        assert data["nodes"] == 3

    def test_create_node_with_tags(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={
                        "title": "Tagged Node",
                        "content": "content",
                        "source": "s",
                        "tags": ["ai", "knowledge"],
                    },
                )
                return r

        resp = _run(_go())
        assert resp.status_code == 201

    def test_create_node_with_metadata(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={
                        "title": "Meta Node",
                        "content": "data",
                        "source": "s",
                        "metadata": {"author": "Norman", "version": 1},
                    },
                )
                return r

        resp = _run(_go())
        assert resp.status_code == 201


# ---------------------------------------------------------------------------
# Edge creation
# ---------------------------------------------------------------------------


class TestEdgeCreation:
    def _make_node(self, worker_mod, title="N"):
        async def _go():
            async with _client(worker_mod.app, getattr(worker_mod, "_INTERNAL_SECRET", "")) as c:
                r = await c.post("/nodes", json={"title": title, "content": "c", "source": "s"})
                return r.json()["node_id"]

        return _run(_go())

    def test_create_edge_returns_201(self, _worker):
        src = self._make_node(_worker, "Source")
        tgt = self._make_node(_worker, "Target")

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post(
                    "/edges",
                    json={"source_id": src, "target_id": tgt, "relation": "related_to"},
                )

        resp = _run(_go())
        assert resp.status_code == 201

    def test_create_edge_returns_edge_id(self, _worker):
        src = self._make_node(_worker, "A")
        tgt = self._make_node(_worker, "B")

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/edges",
                    json={"source_id": src, "target_id": tgt},
                )
                return r.json()

        data = _run(_go())
        assert "edge_id" in data

    def test_edge_count_in_health(self, _worker):
        src = self._make_node(_worker, "Src2")
        tgt = self._make_node(_worker, "Tgt2")

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                await c.post(
                    "/edges",
                    json={"source_id": src, "target_id": tgt},
                )
                return (await c.get("/health")).json()

        data = _run(_go())
        assert data["edges"] == 1


# ---------------------------------------------------------------------------
# Graph stats
# ---------------------------------------------------------------------------


class TestGraphStats:
    def test_stats_empty_graph(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.get("/graph/stats")).json()

        data = _run(_go())
        assert data["node_count"] == 0
        assert data["edge_count"] == 0

    def test_stats_after_insertion(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r1 = await c.post("/nodes", json={"title": "X", "content": "x", "source": "s"})
                r2 = await c.post("/nodes", json={"title": "Y", "content": "y", "source": "s"})
                await c.post(
                    "/edges",
                    json={"source_id": r1.json()["node_id"], "target_id": r2.json()["node_id"]},
                )
                return (await c.get("/graph/stats")).json()

        data = _run(_go())
        assert data["node_count"] == 2
        assert data["edge_count"] == 1

    def test_stats_has_avg_importance(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.get("/graph/stats")).json()

        data = _run(_go())
        assert "avg_importance" in data

    def test_stats_avg_degree_empty(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.get("/graph/stats")).json()

        data = _run(_go())
        assert data["avg_degree"] == 0.0


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class TestSearch:
    def test_search_empty_graph_returns_200(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post("/search", json={"query": "quantum consciousness"})

        resp = _run(_go())
        assert resp.status_code == 200

    def test_search_returns_query_echo(self, _worker):
        query = "test search query"

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.post("/search", json={"query": query})).json()

        data = _run(_go())
        assert data["query"] == query

    def test_search_has_direct_and_expanded_results(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return (await c.post("/search", json={"query": "test"})).json()

        data = _run(_go())
        assert "direct_results" in data
        assert "expanded_results" in data
        assert "total" in data

    def test_search_after_node_insertion(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                await c.post(
                    "/nodes",
                    json={
                        "title": "Consciousness Theory",
                        "content": "IIT 4.0 integrated information theory",
                        "source": "research",
                    },
                )
                return (await c.post("/search", json={"query": "consciousness IIT"})).json()

        data = _run(_go())
        # Should find the node (or at minimum not error)
        assert isinstance(data["direct_results"], list)


# ---------------------------------------------------------------------------
# PageRank recompute
# ---------------------------------------------------------------------------


class TestPageRankRecompute:
    def test_recompute_on_empty_graph(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post("/pagerank/recompute")

        resp = _run(_go())
        assert resp.status_code == 200
        assert resp.json()["status"] == "recomputed"

    def test_recompute_returns_node_count(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                await c.post("/nodes", json={"title": "A", "content": "a", "source": "s"})
                return (await c.post("/pagerank/recompute")).json()

        data = _run(_go())
        assert data["node_count"] >= 1

    def test_recompute_with_graph_structure(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r1 = await c.post("/nodes", json={"title": "Hub", "content": "c", "source": "s"})
                r2 = await c.post("/nodes", json={"title": "Leaf", "content": "c", "source": "s"})
                nid1 = r1.json()["node_id"]
                nid2 = r2.json()["node_id"]
                await c.post("/edges", json={"source_id": nid1, "target_id": nid2})
                result = await c.post("/pagerank/recompute")
                return result.json()

        data = _run(_go())
        assert data["node_count"] == 2


# ---------------------------------------------------------------------------
# Neighbourhood
# ---------------------------------------------------------------------------


class TestNeighbourhood:
    def test_neighbourhood_nonexistent_node_404(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.get("/nodes/00000000-0000-0000-0000-000000000000/neighbourhood")

        resp = _run(_go())
        assert resp.status_code == 404

    def test_neighbourhood_isolated_node_empty(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes", json={"title": "Isolated", "content": "alone", "source": "s"},
                )
                nid = r.json()["node_id"]
                return (await c.get(f"/nodes/{nid}/neighbourhood")).json()

        data = _run(_go())
        assert "neighbourhood" in data
        assert data["total"] == 0

    def test_neighbourhood_with_connected_node(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r1 = await c.post("/nodes", json={"title": "Hub", "content": "c", "source": "s"})
                r2 = await c.post("/nodes", json={"title": "Spoke", "content": "c", "source": "s"})
                hub_id = r1.json()["node_id"]
                spoke_id = r2.json()["node_id"]
                await c.post(
                    "/edges",
                    json={"source_id": hub_id, "target_id": spoke_id, "relation": "links_to"},
                )
                return (await c.get(f"/nodes/{hub_id}/neighbourhood?max_hops=1")).json()

        data = _run(_go())
        assert data["total"] >= 1

    def test_neighbourhood_respects_max_hops_param(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post("/nodes", json={"title": "Root", "content": "c", "source": "s"})
                nid = r.json()["node_id"]
                # max_hops=1 should work without error
                resp = await c.get(f"/nodes/{nid}/neighbourhood?max_hops=1")
                return resp

        resp = _run(_go())
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# NodeCreate.importance field (contract alignment fix)
# ---------------------------------------------------------------------------


class TestNodeImportance:
    """Verify the importance field is accepted and persisted in the database."""

    def test_create_node_default_importance(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={"title": "Default Imp", "content": "x", "source": "s"},
                )
                nid = r.json()["node_id"]
                return (await c.get(f"/nodes/{nid}")).json()

        node = _run(_go())
        # default importance is 0.5 per model definition
        assert node["importance"] == pytest.approx(0.5, abs=1e-6)

    def test_create_node_custom_importance(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={
                        "title": "High Imp",
                        "content": "important content",
                        "source": "s",
                        "importance": 0.9,
                    },
                )
                nid = r.json()["node_id"]
                return (await c.get(f"/nodes/{nid}")).json()

        node = _run(_go())
        assert node["importance"] == pytest.approx(0.9, abs=1e-6)

    def test_create_node_low_importance(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={
                        "title": "Low Imp",
                        "content": "trivial",
                        "source": "s",
                        "importance": 0.1,
                    },
                )
                nid = r.json()["node_id"]
                return (await c.get(f"/nodes/{nid}")).json()

        node = _run(_go())
        assert node["importance"] == pytest.approx(0.1, abs=1e-6)

    def test_importance_boundary_zero(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={"title": "Zero Imp", "content": "x", "source": "s", "importance": 0.0},
                )
                nid = r.json()["node_id"]
                return (await c.get(f"/nodes/{nid}")).json()

        node = _run(_go())
        assert node["importance"] == pytest.approx(0.0, abs=1e-6)

    def test_importance_boundary_one(self, _worker):
        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={"title": "Max Imp", "content": "x", "source": "s", "importance": 1.0},
                )
                nid = r.json()["node_id"]
                return (await c.get(f"/nodes/{nid}")).json()

        node = _run(_go())
        assert node["importance"] == pytest.approx(1.0, abs=1e-6)

    def test_importance_out_of_range_rejected(self, _worker):
        """Values outside [0, 1] must be rejected by pydantic validation."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r = await c.post(
                    "/nodes",
                    json={"title": "Bad Imp", "content": "x", "source": "s", "importance": 1.5},
                )
                return r

        resp = _run(_go())
        assert resp.status_code == 422

    def test_avg_importance_reflects_stored_values(self, _worker):
        """graph/stats avg_importance should reflect the stored importance values."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                await c.post(
                    "/nodes",
                    json={"title": "A", "content": "x", "source": "s", "importance": 0.2},
                )
                await c.post(
                    "/nodes",
                    json={"title": "B", "content": "x", "source": "s", "importance": 0.8},
                )
                return (await c.get("/graph/stats")).json()

        data = _run(_go())
        # avg of 0.2 and 0.8 = 0.5
        assert data["avg_importance"] == pytest.approx(0.5, abs=0.01)


# ---------------------------------------------------------------------------
# SearchRequest contract alignment (max_results / use_graph_expansion)
# ---------------------------------------------------------------------------


class TestSearchContract:
    """Verify the search endpoint accepts the client-contract field names."""

    def test_search_with_max_results_field(self, _worker):
        """Search must accept max_results (not top_k)."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post(
                    "/search",
                    json={"query": "knowledge graph", "max_results": 5},
                )

        resp = _run(_go())
        assert resp.status_code == 200

    def test_search_max_results_limits_output(self, _worker):
        """Inserting many nodes then capping via max_results should not exceed the cap."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                for i in range(15):
                    await c.post(
                        "/nodes",
                        json={
                            "title": f"Knowledge Node {i}",
                            "content": f"knowledge graph content {i}",
                            "source": "s",
                        },
                    )
                data = (
                    await c.post("/search", json={"query": "knowledge", "max_results": 3})
                ).json()
                return data

        data = _run(_go())
        total_returned = len(data.get("direct_results", [])) + len(data.get("expanded_results", []))
        assert total_returned <= 3

    def test_search_with_use_graph_expansion_false(self, _worker):
        """use_graph_expansion=False must be accepted without error."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post(
                    "/search",
                    json={"query": "test", "use_graph_expansion": False},
                )

        resp = _run(_go())
        assert resp.status_code == 200

    def test_search_graph_expansion_false_skips_bfs(self, _worker):
        """With use_graph_expansion=False, expanded_results must be empty."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r1 = await c.post(
                    "/nodes",
                    json={"title": "Hub Node", "content": "hub knowledge", "source": "s"},
                )
                r2 = await c.post(
                    "/nodes",
                    json={"title": "Leaf Node", "content": "leaf details", "source": "s"},
                )
                await c.post(
                    "/edges",
                    json={
                        "source_id": r1.json()["node_id"],
                        "target_id": r2.json()["node_id"],
                        "relation": "links_to",
                    },
                )
                return (
                    await c.post(
                        "/search",
                        json={"query": "hub knowledge", "use_graph_expansion": False},
                    )
                ).json()

        data = _run(_go())
        assert data["expanded_results"] == []

    def test_search_graph_expansion_true_enables_bfs(self, _worker):
        """With use_graph_expansion=True (default), expanded_results may be non-empty."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                r1 = await c.post(
                    "/nodes",
                    json={
                        "title": "Central Concept",
                        "content": "central concept info",
                        "source": "s",
                    },
                )
                r2 = await c.post(
                    "/nodes",
                    json={"title": "Related Detail", "content": "related expanded", "source": "s"},
                )
                await c.post(
                    "/edges",
                    json={
                        "source_id": r1.json()["node_id"],
                        "target_id": r2.json()["node_id"],
                        "relation": "related_to",
                    },
                )
                return (
                    await c.post(
                        "/search",
                        json={"query": "central concept", "use_graph_expansion": True},
                    )
                ).json()

        data = _run(_go())
        # expanded_results is a list (may or may not have entries but field exists)
        assert isinstance(data["expanded_results"], list)

    def test_search_missing_query_returns_422(self, _worker):
        """Omitting required query field must return 422 Unprocessable Entity."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post("/search", json={"max_results": 5})

        resp = _run(_go())
        assert resp.status_code == 422

    def test_search_default_max_results_is_ten(self, _worker):
        """Omitting max_results should default to 10 (no 422 error)."""

        async def _go():
            async with _client(_worker.app, getattr(_worker, "_INTERNAL_SECRET", "")) as c:
                return await c.post("/search", json={"query": "anything"})

        resp = _run(_go())
        assert resp.status_code == 200
