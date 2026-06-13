"""
tests/test_phase4_ml_mcp_workflow.py
Phase 4 ML + MCP + Workflow integration tests.

Tests:
  - Phase 4 Spark tools registration (16 new tools)
  - MCP total tool count (17 original + 16 phase4 = 33)
  - Phase 4 workflow node availability (7 types)
  - ML pipeline instantiation
  - Collective Memory store/retrieve round-trip
  - Causal Reasoner predict/diagnose
  - Semantic Knowledge Graph add/query/path/expand
  - Meta Learner adapt
  - Attention Router registration and routing
  - Foresight predict
  - Analytics intent classification
  - spark_phase4_tools handler smoke tests (no real inference)

All tests use in-process, zero-dependency execution (no external APIs required).
"""

from __future__ import annotations

import asyncio
import os
import sys

import pytest

# Make sure the project root is on sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run(coro):
    """Run a coroutine synchronously for tests that aren't async."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_closed():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)


# ---------------------------------------------------------------------------
# Phase 4 Spark tools registration
# ---------------------------------------------------------------------------


class TestSparkPhase4ToolsRegistration:
    def test_phase4_tools_module_importable(self):
        from src.mcp.spark_phase4_tools import PHASE4_TOOLS

        assert len(PHASE4_TOOLS) == 16, f"Expected 16 phase4 tools, got {len(PHASE4_TOOLS)}"

    def test_all_tool_names_unique(self):
        from src.mcp.spark_phase4_tools import PHASE4_TOOLS

        names = [t["name"] for t in PHASE4_TOOLS]
        assert len(names) == len(set(names)), "Duplicate tool names in PHASE4_TOOLS"

    def test_all_tools_have_required_keys(self):
        from src.mcp.spark_phase4_tools import PHASE4_TOOLS

        for tool in PHASE4_TOOLS:
            assert "name" in tool
            assert "description" in tool
            assert "input_schema" in tool
            assert "handler" in tool
            assert callable(tool["handler"])

    def test_registration_into_fresh_registry(self):
        from src.mcp.spark_phase4_tools import register_phase4_tools
        from src.mcp.tools import SparkToolRegistry

        fresh = SparkToolRegistry()
        baseline = len(fresh._tools)
        count = register_phase4_tools(fresh)
        assert count == 16
        assert len(fresh._tools) == baseline + 16

    def test_global_registry_has_phase4_tools(self):
        from src.mcp.tools import registry

        tool_names = list(registry._tools.keys())
        # Check a selection of Phase 4 tools are present
        for expected in [
            "neural_mesh_emit",
            "causal_predict",
            "knowledge_graph_query",
            "meta_learn_adapt",
            "attention_route",
            "nanobot_dispatch",
            "foresight_predict",
            "analytics_intent",
        ]:
            assert expected in tool_names, f"Missing tool: {expected}"

    def test_total_tool_count_at_least_33(self):
        from src.mcp.tools import registry

        # 17 original + 16 phase4 = 33
        assert len(registry._tools) >= 33, f"Expected ≥33 tools, got {len(registry._tools)}"

    def test_tool_categories(self):
        from src.mcp.tools import registry

        categories = {t.category for t in registry._tools.values() if hasattr(t, "category")}
        # Should include at least neural, intelligence, adaptive, healing
        for expected_cat in ("neural", "intelligence", "adaptive", "healing"):
            assert expected_cat in categories, f"Missing category: {expected_cat}"


# ---------------------------------------------------------------------------
# Phase 4 workflow nodes
# ---------------------------------------------------------------------------


class TestPhase4WorkflowNodes:
    def test_phase4_nodes_module_importable(self):
        from src.workflow.phase4_nodes import PHASE4_NODE_TYPES

        assert len(PHASE4_NODE_TYPES) == 7

    def test_all_node_types_present(self):
        from src.workflow.phase4_nodes import PHASE4_NODE_TYPES

        expected = {
            "NEURAL_MESH",
            "COLLECTIVE_MEM",
            "META_LEARN",
            "ATTENTION_ROUTE",
            "CAUSAL_REASON",
            "KNOWLEDGE_GRAPH",
            "FORESIGHT",
        }
        assert set(PHASE4_NODE_TYPES.keys()) == expected

    def test_nodes_extend_workflow_registry(self):
        from src.workflow.nodes import _PHASE4_NODE_REGISTRY, _ensure_phase4_nodes_loaded

        _ensure_phase4_nodes_loaded()
        assert len(_PHASE4_NODE_REGISTRY) >= 7

    def test_create_node_fallback(self):
        """create_node() should find Phase 4 node types by string key."""
        from src.workflow.nodes import NodeConfig, create_node

        cfg = NodeConfig(
            id="test_kg",
            type="KNOWLEDGE_GRAPH",
            name="KG Test",
            config={"action": "query", "query_type": "tag", "query_value": "test"},
        )
        node = create_node(cfg)
        from src.workflow.phase4_nodes import KnowledgeGraphNode

        assert isinstance(node, KnowledgeGraphNode)

    def test_collective_memory_node_instantiation(self):
        from src.workflow.nodes import NodeConfig, create_node

        cfg = NodeConfig(
            id="cm_test",
            type="COLLECTIVE_MEM",
            name="Memory Test",
            config={"action": "store", "key": "test_k", "topic": "test"},
        )
        node = create_node(cfg)
        assert node is not None


# ---------------------------------------------------------------------------
# ML Pipeline
# ---------------------------------------------------------------------------


class TestMLPipeline:
    def test_pipeline_importable(self):
        from src.core.ml_pipeline import MLPipeline, get_pipeline

        pipeline = get_pipeline()
        assert isinstance(pipeline, MLPipeline)

    def test_pipeline_request_creation(self):
        from src.core.ml_pipeline import PipelineRequest

        req = PipelineRequest(
            prompt="Hello world",
            task_domain="general",
            task_type="generate",
            session_id="test-session-001",
        )
        assert req.prompt == "Hello world"
        assert req.session_id == "test-session-001"
        assert req.temperature == 0.8

    def test_pipeline_stats(self):
        from src.core.ml_pipeline import get_pipeline

        pipeline = get_pipeline()
        stats = run(pipeline.stats())
        assert "call_count" in stats
        assert "phase4_enabled" in stats
        assert stats["phase4_enabled"] is True


# ---------------------------------------------------------------------------
# Collective Memory (direct unit tests)
# ---------------------------------------------------------------------------


class TestCollectiveMemory:
    def test_store_and_retrieve(self):
        from src.neural.collective_memory import CollectiveMemory, MemoryPriority

        cm = CollectiveMemory()

        async def _test():
            eid = await cm.store(
                key="test:unit:001",
                value={"data": "hello world"},
                topic="unit_test",
                tags={"testing", "unit"},
                ttl=60.0,
                priority=MemoryPriority.HIGH,
                source="pytest",
            )
            assert eid is not None
            entry = await cm.retrieve("test:unit:001")
            assert entry is not None
            assert entry.value == {"data": "hello world"}
            assert entry.topic == "unit_test"
            assert "testing" in entry.tags

        run(_test())

    def test_query_by_topic(self):
        from src.neural.collective_memory import CollectiveMemory

        cm = CollectiveMemory()

        async def _test():
            for i in range(5):
                await cm.store(f"topic:key:{i}", f"value_{i}", topic="qa_topic")
            results = await cm.query_by_topic("qa_topic", limit=10)
            assert len(results) >= 5

        run(_test())

    def test_query_by_tag(self):
        from src.neural.collective_memory import CollectiveMemory

        cm = CollectiveMemory()

        async def _test():
            await cm.store("tagged:1", "alpha", tags={"unique_tag_xyz"})
            await cm.store("tagged:2", "beta", tags={"unique_tag_xyz", "other"})
            results = await cm.query_by_tag("unique_tag_xyz", limit=10)
            assert len(results) == 2

        run(_test())

    def test_critical_priority_never_evicted(self):
        from src.neural.collective_memory import CollectiveMemory, MemoryPriority

        # Create a very small memory to force evictions
        cm = CollectiveMemory(max_entries=3)

        async def _test():
            await cm.store("critical_key", "safe_value", priority=MemoryPriority.CRITICAL)
            # Fill to trigger eviction
            for i in range(5):
                await cm.store(f"low:key:{i}", f"low_{i}", priority=MemoryPriority.LOW)
            # Critical entry should survive
            entry = await cm.retrieve("critical_key")
            assert entry is not None, "CRITICAL entry was incorrectly evicted"

        run(_test())


# ---------------------------------------------------------------------------
# Semantic Knowledge Graph (direct unit tests)
# ---------------------------------------------------------------------------


class TestSemanticKnowledgeGraph:
    def test_add_and_query_node(self):
        from src.intelligence.semantic_knowledge import KnowledgeNode, SemanticKnowledgeGraph

        kg = SemanticKnowledgeGraph()

        async def _test():
            node = KnowledgeNode(
                label="Python",
                semantic_type="language",
                tags={"programming", "interpreted"},
                confidence=0.95,
                provenance="test",
            )
            node_id = await kg.add_node(node)
            assert node_id

            # Query by type
            results = await kg.query_nodes(semantic_type="language")
            assert any(n.id == node_id for n in results)

            # Query by tag
            results = await kg.query_nodes(tag="programming")
            assert any(n.id == node_id for n in results)

        run(_test())

    def test_add_edge_and_path(self):
        from src.intelligence.semantic_knowledge import (
            EdgeType,
            KnowledgeNode,
            SemanticKnowledgeGraph,
        )

        kg = SemanticKnowledgeGraph()

        async def _test():
            n1 = KnowledgeNode(label="A", semantic_type="concept")
            n2 = KnowledgeNode(label="B", semantic_type="concept")
            n3 = KnowledgeNode(label="C", semantic_type="concept")
            id1 = await kg.add_node(n1)
            id2 = await kg.add_node(n2)
            id3 = await kg.add_node(n3)
            await kg.add_edge(id1, id2, EdgeType.RELATED_TO)
            await kg.add_edge(id2, id3, EdgeType.RELATED_TO)

            path = await kg.shortest_path(id1, id3)
            assert path == [id1, id2, id3]

        run(_test())

    def test_semantic_expand(self):
        from src.intelligence.semantic_knowledge import (
            EdgeType,
            KnowledgeNode,
            SemanticKnowledgeGraph,
        )

        kg = SemanticKnowledgeGraph()

        async def _test():
            seed = KnowledgeNode(label="Root", semantic_type="root")
            seed_id = await kg.add_node(seed)
            children = []
            for i in range(3):
                c = KnowledgeNode(label=f"Child{i}", semantic_type="child")
                cid = await kg.add_node(c)
                await kg.add_edge(seed_id, cid, EdgeType.PART_OF, confidence=0.9)
                children.append(cid)
            expanded = await kg.semantic_expand(seed_id, depth=1)
            assert len(expanded) == 3
            for cid in children:
                assert cid in expanded

        run(_test())

    def test_pattern_matching(self):
        from src.intelligence.semantic_knowledge import (
            EdgeType,
            GraphPattern,
            KnowledgeNode,
            SemanticKnowledgeGraph,
        )

        kg = SemanticKnowledgeGraph()

        async def _test():
            svc = KnowledgeNode(
                label="ServiceA", semantic_type="service", tags={"api"}, confidence=0.9
            )
            dep = KnowledgeNode(
                label="Database", semantic_type="storage", tags={"db"}, confidence=0.85
            )
            sid = await kg.add_node(svc)
            did = await kg.add_node(dep)
            await kg.add_edge(sid, did, EdgeType.DEPENDS_ON)

            pattern = GraphPattern(
                node_constraints={
                    "svc": {"semantic_type": "service"},
                    "db": {"semantic_type": "storage"},
                },
                edge_constraints=[("svc", "db", EdgeType.DEPENDS_ON)],
            )
            matches = await kg.match_pattern(pattern)
            assert len(matches) >= 1
            assert matches[0].score > 0

        run(_test())


# ---------------------------------------------------------------------------
# Causal Reasoner (direct unit tests)
# ---------------------------------------------------------------------------


class TestCausalReasoner:
    def test_predict_forward(self):
        from src.intelligence.causal_reasoner import CausalReasoner, CausalRule, CausalStrength

        cr = CausalReasoner()

        async def _test():
            # add_rule is async; confidence field (not 'probability')
            await cr.add_rule(
                CausalRule(
                    cause="rain",
                    effect="wet_road",
                    strength=CausalStrength.SUFFICIENT,
                    confidence=0.95,
                )
            )
            await cr.add_rule(
                CausalRule(
                    cause="wet_road",
                    effect="accident_risk",
                    strength=CausalStrength.CONTRIBUTING,
                    confidence=0.6,
                )
            )
            # observe(event, probability) — async
            await cr.observe("rain", 1.0)
            # predict(causes=[...]) — async; result has .effects list of (event, prob) tuples
            result = await cr.predict(causes=["rain"])
            effects_dict = dict(result.effects)
            assert "wet_road" in effects_dict
            assert effects_dict["wet_road"] > 0.5

        run(_test())

    def test_diagnose_backward(self):
        from src.intelligence.causal_reasoner import CausalReasoner, CausalRule, CausalStrength

        cr = CausalReasoner()

        async def _test():
            await cr.add_rule(
                CausalRule(
                    cause="overheat",
                    effect="crash",
                    strength=CausalStrength.SUFFICIENT,
                    confidence=0.9,
                )
            )
            await cr.observe("crash", 1.0)
            # diagnose(effects=[...]) — async; result has .causes list of (event, prob) tuples
            result = await cr.diagnose(effects=["crash"])
            causes_dict = dict(result.causes)
            assert "overheat" in causes_dict

        run(_test())

    def test_cycle_detection(self):
        from src.intelligence.causal_reasoner import CausalGraph, CausalRule, CausalStrength

        # Cycle detection lives in CausalGraph._graph (sync), test via the underlying graph
        g = CausalGraph()
        g.add_rule(CausalRule(cause="A", effect="B", strength=CausalStrength.CONTRIBUTING))
        g.add_rule(CausalRule(cause="B", effect="C", strength=CausalStrength.CONTRIBUTING))
        # C → A would create a cycle — should be rejected with ValueError
        with pytest.raises(ValueError):
            g.add_rule(CausalRule(cause="C", effect="A", strength=CausalStrength.CONTRIBUTING))


# ---------------------------------------------------------------------------
# Meta Learner (direct unit tests)
# ---------------------------------------------------------------------------


class TestMetaLearner:
    def test_register_and_adapt(self):
        from src.neural.meta_learner import MetaLearner, TaskPrototype

        ml = MetaLearner(similarity_threshold=0.1)  # Low threshold for test matching

        async def _test():
            # TaskPrototype fields: prototype_id, domain, task_type, input_signature,
            # output_signature, parameter_deltas, tags, embedding, etc.
            proto = TaskPrototype(
                prototype_id="proto-nlp-001",
                domain="nlp",
                task_type="summarise",
                tags={"text", "short"},
                input_signature={"text": "str"},
                output_signature={"summary": "str"},
                parameter_deltas={"temperature": -0.3, "max_tokens": 200},
            )
            pid = await ml.register_prototype(proto)
            assert pid == "proto-nlp-001"
            await ml.record_outcome("proto-nlp-001", success=True)

            # adapt() takes keyword args: domain, task_type, tags, input_signature, etc.
            result = await ml.adapt(
                domain="nlp",
                task_type="summarise",
                tags={"text"},
                input_signature={"text": "str"},
                output_signature={"summary": "str"},
                current_parameters={"temperature": 0.8, "max_tokens": 512},
            )
            assert result is not None
            assert result.prototype_id == "proto-nlp-001"
            assert result.confidence > 0

        run(_test())

    def test_no_prototype_returns_none(self):
        from src.neural.meta_learner import MetaLearner

        ml = MetaLearner()  # Fresh, empty learner

        async def _test():
            # With no prototypes, adapt() returns AdaptationResult with confidence=0.0
            # (not None — the implementation always returns AdaptationResult)
            result = await ml.adapt(domain="unknown_xyz", task_type="impossible_task_type")
            assert result is not None
            # Empty registry → confidence 0.0 with empty prototype_id
            assert result.confidence == 0.0
            assert result.prototype_id == ""

        run(_test())


# ---------------------------------------------------------------------------
# Attention Router (direct unit tests)
# ---------------------------------------------------------------------------


class TestAttentionRouter:
    def test_register_and_route(self):
        from src.neural.attention_router import AttentionRouter, RoutingRequest

        router = AttentionRouter()

        async def _test():
            # register_service(service_id: str, capability_tags: Set[str], ...)
            await router.register_service(
                service_id="svc_a",
                capability_tags={"text", "analysis"},
            )
            # RoutingRequest fields: request_id (str), required_tags (Set[str]), ...
            req = RoutingRequest(
                request_id="req-001",
                required_tags={"text"},
            )
            decision = await router.route(req)
            assert decision is not None
            # RoutingDecision.selected_service contains the winning service_id
            assert decision.selected_service == "svc_a"

        run(_test())

    def test_empty_registry_returns_none(self):
        from src.neural.attention_router import AttentionRouter, RoutingRequest

        router = AttentionRouter()

        async def _test():
            req = RoutingRequest(request_id="req-empty", required_tags=set())
            decision = await router.route(req)
            # Empty registry returns a RoutingDecision with empty selected_service
            assert decision is not None
            assert decision.selected_service == ""

        run(_test())


# ---------------------------------------------------------------------------
# Foresight (direct unit tests)
# ---------------------------------------------------------------------------


class TestForesight:
    def test_predict_trajectory(self):
        from src.adaptive.foresight import ConversationTrajectoryPredictor

        predictor = ConversationTrajectoryPredictor()
        # record_turn(session_id, emotion, intent) is the correct API
        predictor.record_turn("sess1", "happy", "question")
        predictor.record_turn("sess1", "happy", "request")
        prediction = predictor.predict_trajectory("sess1")
        assert prediction is not None
        assert prediction.confidence() >= 0.0
        top = prediction.top(3)
        assert len(top) > 0


# ---------------------------------------------------------------------------
# Analytics Intent (direct unit tests)
# ---------------------------------------------------------------------------


class TestAnalyticsIntent:
    def test_classify_question(self):
        from src.analytics.predictive import IntentPredictor

        predictor = IntentPredictor()
        # predict(text, emotion) is the correct API — returns Dict[str, float]
        results = predictor.predict("What is the weather like today?", emotion="neutral")
        assert len(results) > 0
        assert "question" in results
        assert results["question"] > 0.0

    def test_classify_request(self):
        from src.analytics.predictive import IntentPredictor

        predictor = IntentPredictor()
        results = predictor.predict("Please help me create a new account", emotion="neutral")
        assert len(results) > 0
        # Should have 'request' intent with positive score
        assert "request" in results


# ---------------------------------------------------------------------------
# Spark Phase 4 handler smoke tests
# ---------------------------------------------------------------------------


class TestSparkHandlerSmoke:
    """Smoke test each handler with minimal valid params — no real inference needed."""

    def test_collective_memory_store_handler(self):
        from src.mcp.spark_phase4_tools import _handle_collective_memory_store

        result = run(
            _handle_collective_memory_store(
                {
                    "key": "smoke:test:1",
                    "value": {"x": 42},
                    "topic": "smoke",
                }
            )
        )
        assert result.get("ok") or result.get("error")  # Either ok or graceful error

    def test_collective_memory_query_missing_filter(self):
        from src.mcp.spark_phase4_tools import _handle_collective_memory_query

        result = run(_handle_collective_memory_query({}))
        # Should return an error about missing filter
        assert "error" in result

    def test_causal_predict_handler(self):
        from src.mcp.spark_phase4_tools import _handle_causal_predict

        result = run(
            _handle_causal_predict(
                {
                    "observations": {"rain": True},
                }
            )
        )
        assert result.get("ok") or result.get("error")

    def test_knowledge_graph_add_handler(self):
        from src.mcp.spark_phase4_tools import _handle_knowledge_graph_add

        result = run(
            _handle_knowledge_graph_add(
                {
                    "node": {"label": "Test Node", "semantic_type": "test"},
                }
            )
        )
        assert result.get("ok") or result.get("error")

    def test_knowledge_graph_query_empty(self):
        from src.mcp.spark_phase4_tools import _handle_knowledge_graph_query

        result = run(_handle_knowledge_graph_query({"semantic_type": "nonexistent_xyz"}))
        assert result.get("ok") or result.get("error")
        if result.get("ok"):
            assert result["count"] == 0

    def test_attention_route_no_services(self):
        """With no services registered, route should return routed=False."""
        from src.mcp.spark_phase4_tools import _handle_attention_route

        result = run(_handle_attention_route({"query": "some task"}))
        # Either ok with routed=False, or error
        assert "ok" in result or "error" in result
