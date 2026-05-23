"""
spark_phase4_tools.py — Phase 4 Neural & Intelligence tools for The Spark MCP server.

Registers 15 new SparkTool instances exposing Phase 4 capabilities:
  Neural Layer (src/neural/):
    - neural_mesh_emit        — emit a signal through the NeuralMesh
    - neural_mesh_topology    — snapshot the current mesh topology
    - collective_memory_store — persist an entry in CollectiveMemory
    - collective_memory_query — query CollectiveMemory by topic / tag
    - meta_learn_adapt        — few-shot task adaptation via MetaLearner
    - attention_route         — transformer-style service routing

  Intelligence Layer (src/intelligence/):
    - causal_predict          — forward causal prediction via CausalReasoner
    - causal_diagnose         — backward causal diagnosis
    - causal_counterfactual   — counterfactual "what if" query
    - knowledge_graph_add     — add a node/edge to SemanticKnowledgeGraph
    - knowledge_graph_query   — structured node query
    - knowledge_graph_path    — BFS shortest path
    - knowledge_graph_expand  — semantic expansion from a seed node

  Adaptive / Analytics:
    - foresight_predict       — conversation trajectory prediction
    - analytics_intent        — user intent classification
    - nanobot_dispatch        — dispatch a NanoCode repair bot

All handlers are async. Each module is imported lazily so the server
starts cleanly even if optional heavy deps (numpy, etc.) are absent.

Usage:
    from src.mcp.spark_phase4_tools import register_phase4_tools  # noqa: F401  # intentional top-level import
    register_phase4_tools(registry)   # registry: SparkToolRegistry
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

from shared_core.error_handlers import safe_error_detail

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy singletons for Phase 4 components
# ---------------------------------------------------------------------------

_neural_mesh = None
_collective_memory = None
_meta_learner = None
_attention_router = None
_causal_reasoner = None
_knowledge_graph = None


def _get_neural_mesh():
    global _neural_mesh
    if _neural_mesh is None:
        try:
            from src.neural.neural_mesh import NeuralMesh  # noqa: F401  # intentional top-level import
            _neural_mesh = NeuralMesh()
        except Exception as exc:
            logger.warning("NeuralMesh unavailable: %s", exc)
    return _neural_mesh


def _get_collective_memory():
    global _collective_memory
    if _collective_memory is None:
        try:
            from src.neural.collective_memory import CollectiveMemory  # noqa: F401  # intentional top-level import
            _collective_memory = CollectiveMemory()
        except Exception as exc:
            logger.warning("CollectiveMemory unavailable: %s", exc)
    return _collective_memory


def _get_meta_learner():
    global _meta_learner
    if _meta_learner is None:
        try:
            from src.neural.meta_learner import MetaLearner  # noqa: F401  # intentional top-level import
            _meta_learner = MetaLearner()
        except Exception as exc:
            logger.warning("MetaLearner unavailable: %s", exc)
    return _meta_learner


def _get_attention_router():
    global _attention_router
    if _attention_router is None:
        try:
            from src.neural.attention_router import AttentionRouter  # noqa: F401  # intentional top-level import
            _attention_router = AttentionRouter()
        except Exception as exc:
            logger.warning("AttentionRouter unavailable: %s", exc)
    return _attention_router


def _get_causal_reasoner():
    global _causal_reasoner
    if _causal_reasoner is None:
        try:
            from src.intelligence.causal_reasoner import CausalReasoner  # noqa: F401  # intentional top-level import
            _causal_reasoner = CausalReasoner()
        except Exception as exc:
            logger.warning("CausalReasoner unavailable: %s", exc)
    return _causal_reasoner


def _get_knowledge_graph():
    global _knowledge_graph
    if _knowledge_graph is None:
        try:
            from src.intelligence.semantic_knowledge import SemanticKnowledgeGraph  # noqa: F401  # intentional top-level import
            _knowledge_graph = SemanticKnowledgeGraph()
        except Exception as exc:
            logger.warning("SemanticKnowledgeGraph unavailable: %s", exc)
    return _knowledge_graph


# ---------------------------------------------------------------------------
# Helper: error response
# ---------------------------------------------------------------------------

def _err(msg: str) -> Dict[str, Any]:
    return {"error": msg, "ok": False}


def _ok(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"ok": True, "ts": time.time(), **data}


# ---------------------------------------------------------------------------
# Neural Mesh handlers
# ---------------------------------------------------------------------------

async def _handle_neural_mesh_emit(params: Dict[str, Any]) -> Dict[str, Any]:
    """Emit a named signal from a source node through the neural mesh.

    Params:
        source_id (str): Sending mesh node id.
        signal_type (str): Signal category / event name.
        payload (dict): Arbitrary signal data.
        ttl (int, optional): Hop limit (default 5).
    """
    mesh = _get_neural_mesh()
    if mesh is None:
        return _err("NeuralMesh not initialised")
    source_id = params.get("source_id", "spark")
    signal_type = params.get("signal_type", "event")
    payload = params.get("payload", {})
    ttl = int(params.get("ttl", 5))
    try:
        from src.neural.neural_mesh import MeshNode, Signal  # noqa: F401  # intentional top-level import
        # Auto-register source node if absent
        if source_id not in mesh._nodes:
            node = MeshNode(id=source_id, service_name="spark", host="internal", port=0)
            await mesh.register_node(node)
        signal = Signal(
            source_id=source_id,
            signal_type=signal_type,
            payload=payload,
            ttl=ttl,
        )
        delivered = await mesh.emit(signal)
        return _ok({"delivered_to": delivered, "signal_type": signal_type})
    except Exception as exc:
        logger.exception("neural_mesh_emit error")
        return _err(safe_error_detail(exc, 500))


async def _handle_neural_mesh_topology(params: Dict[str, Any]) -> Dict[str, Any]:
    """Return a snapshot of the current NeuralMesh topology.

    Params: none required.
    """
    mesh = _get_neural_mesh()
    if mesh is None:
        return _err("NeuralMesh not initialised")
    try:
        snapshot = mesh.topology_snapshot()
        partitions = mesh.find_partitions()
        return _ok({
            "nodes": snapshot.get("nodes", []),
            "edges": snapshot.get("edges", []),
            "partition_count": len(partitions),
            "partitions": [list(p) for p in partitions],
        })
    except Exception as exc:
        logger.exception("neural_mesh_topology error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Collective Memory handlers
# ---------------------------------------------------------------------------

async def _handle_collective_memory_store(params: Dict[str, Any]) -> Dict[str, Any]:
    """Store a value in CollectiveMemory.

    Params:
        key (str): Unique memory key.
        value (any): Value to store (JSON-serialisable).
        topic (str, optional): Logical grouping topic.
        tags (list[str], optional): Tag list.
        ttl (float, optional): Time-to-live in seconds (default 3600).
        priority (str, optional): LOW | NORMAL | HIGH | CRITICAL (default NORMAL).
        source (str, optional): Origin identifier.
    """
    cm = _get_collective_memory()
    if cm is None:
        return _err("CollectiveMemory not initialised")
    try:
        from src.neural.collective_memory import MemoryPriority  # noqa: F401  # intentional top-level import
        key = params.get("key")
        if not key:
            return _err("'key' is required")
        value = params.get("value")
        topic = params.get("topic", "general")
        tags = set(params.get("tags", []))
        ttl = float(params.get("ttl", 3600))
        priority_str = params.get("priority", "NORMAL").upper()
        priority = MemoryPriority[priority_str] if priority_str in MemoryPriority.__members__ else MemoryPriority.NORMAL
        source = params.get("source", "spark")
        entry_id = await cm.store(
            key=key,
            value=value,
            topic=topic,
            tags=tags,
            ttl=ttl,
            priority=priority,
            source=source,
        )
        return _ok({"stored": True, "key": key, "entry_id": entry_id})
    except Exception as exc:
        logger.exception("collective_memory_store error")
        return _err(safe_error_detail(exc, 500))


async def _handle_collective_memory_query(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query CollectiveMemory by key, topic, or tag.

    Params:
        key (str, optional): Direct key lookup.
        topic (str, optional): Topic filter.
        tag (str, optional): Tag filter.
        limit (int, optional): Max results (default 20).
    """
    cm = _get_collective_memory()
    if cm is None:
        return _err("CollectiveMemory not initialised")
    try:
        key = params.get("key")
        topic = params.get("topic")
        tag = params.get("tag")
        limit = int(params.get("limit", 20))
        results = []
        if key:
            entry = await cm.retrieve(key)
            if entry:
                results = [{"key": entry.key, "value": entry.value,
                            "topic": entry.topic, "tags": sorted(entry.tags),
                            "priority": entry.priority.name}]
        elif topic:
            entries = await cm.query_by_topic(topic, limit=limit)
            results = [{"key": e.key, "value": e.value,
                        "topic": e.topic, "tags": sorted(e.tags),
                        "priority": e.priority.name} for e in entries]
        elif tag:
            entries = await cm.query_by_tag(tag, limit=limit)
            results = [{"key": e.key, "value": e.value,
                        "topic": e.topic, "tags": sorted(e.tags),
                        "priority": e.priority.name} for e in entries]
        else:
            return _err("Provide at least one of: key, topic, tag")
        stats = cm.stats()
        return _ok({"results": results, "count": len(results),
                    "memory_stats": stats})
    except Exception as exc:
        logger.exception("collective_memory_query error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Meta Learner handlers
# ---------------------------------------------------------------------------

async def _handle_meta_learn_adapt(params: Dict[str, Any]) -> Dict[str, Any]:
    """Adapt task parameters for a new task using few-shot prototype matching.

    Params:
        domain (str): Task domain (e.g. "nlp", "code", "analytics").
        task_type (str): Specific task type (e.g. "summarise", "classify").
        input_signature (dict, optional): Input field names → types.
        output_signature (dict, optional): Output field names → types.
        tags (list[str], optional): Descriptive tags.
        current_parameters (dict, optional): Base parameters to adapt.
    """
    ml = _get_meta_learner()
    if ml is None:
        return _err("MetaLearner not initialised")
    try:
        domain = params.get("domain", "general")
        task_type = params.get("task_type", "generic")
        input_signature = dict(params.get("input_signature", {}))
        output_signature = dict(params.get("output_signature", {}))
        tags = set(params.get("tags", []))
        base_params = dict(params.get("current_parameters", {}))
        result = await ml.adapt(
            domain=domain,
            task_type=task_type,
            input_signature=input_signature,
            output_signature=output_signature,
            tags=tags,
            current_parameters=base_params,
        )
        if result is None or result.confidence == 0.0:
            return _ok({
                "adapted": False,
                "parameters": base_params,
                "message": "No matching prototypes found; returned base parameters",
            })
        return _ok({
            "adapted": True,
            "prototype_id": result.prototype_id,
            "parameters": result.adapted_parameters,
            "confidence": result.confidence,
            "match_score": result.matched_score,
        })
    except Exception as exc:
        logger.exception("meta_learn_adapt error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Attention Router handlers
# ---------------------------------------------------------------------------

async def _handle_attention_route(params: Dict[str, Any]) -> Dict[str, Any]:
    """Route a request to the optimal registered service using transformer-style attention.

    Params:
        request_id (str, optional): Unique request ID.
        required_tags (list[str], optional): Must-have capability tags.
        context_vector (list[float], optional): Dense context embedding.
        priority (float, optional): Request priority (default 1.0).
    """
    router = _get_attention_router()
    if router is None:
        return _err("AttentionRouter not initialised")
    try:
        import uuid

        from src.neural.attention_router import RoutingRequest  # noqa: F401  # intentional top-level import
        request_id = params.get("request_id", uuid.uuid4().hex[:12])
        required_tags = set(params.get("required_tags", []))
        context_vector = list(params.get("context_vector", []))
        priority = float(params.get("priority", 1.0))
        req = RoutingRequest(
            request_id=request_id,
            required_tags=required_tags,
            context_vector=context_vector,
            priority=priority,
        )
        decision = await router.route(req)
        if not decision or not decision.selected_service:
            return _ok({"routed": False, "message": "No eligible services registered"})
        return _ok({
            "routed": True,
            "selected_service": decision.selected_service,
            "attention_weights": decision.attention_weights,
            "confidence": decision.confidence,
        })
    except Exception as exc:
        logger.exception("attention_route error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Causal Reasoner handlers
# ---------------------------------------------------------------------------

async def _handle_causal_predict(params: Dict[str, Any]) -> Dict[str, Any]:
    """Predict the likely effects of observed variables using the CausalReasoner.

    Params:
        causes (list[str]): The cause events to predict effects from.
        observations (dict, optional): Variable → probability mappings (0-1).
        max_results (int, optional): Max effects to return (default 10).
    """
    cr = _get_causal_reasoner()
    if cr is None:
        return _err("CausalReasoner not initialised")
    try:
        causes = list(params.get("causes", []))
        observations = dict(params.get("observations", {}))
        max_results = int(params.get("max_results", 10))
        # Record observations as evidence
        for var, prob in observations.items():
            await cr.observe(var, float(prob))
        result = await cr.predict(causes=causes, max_results=max_results)
        return _ok({
            "effects": dict(result.effects),
            "confidence": result.confidence,
            "reasoning_chain": result.reasoning_chain,
        })
    except Exception as exc:
        logger.exception("causal_predict error")
        return _err(safe_error_detail(exc, 500))


async def _handle_causal_diagnose(params: Dict[str, Any]) -> Dict[str, Any]:
    """Diagnose the most likely root causes of observed effects.

    Params:
        effects (list[str]): The observed effect events to diagnose.
        observations (dict, optional): Variable → probability mappings (0-1).
        max_results (int, optional): Max causes to return (default 10).
    """
    cr = _get_causal_reasoner()
    if cr is None:
        return _err("CausalReasoner not initialised")
    try:
        effects = list(params.get("effects", []))
        observations = dict(params.get("observations", {}))
        max_results = int(params.get("max_results", 10))
        for var, prob in observations.items():
            await cr.observe(var, float(prob))
        result = await cr.diagnose(effects=effects, max_results=max_results)
        return _ok({
            "causes": dict(result.causes),
            "confidence": result.confidence,
            "reasoning_chain": result.reasoning_chain,
        })
    except Exception as exc:
        logger.exception("causal_diagnose error")
        return _err(safe_error_detail(exc, 500))


async def _handle_causal_counterfactual(params: Dict[str, Any]) -> Dict[str, Any]:
    """Run a counterfactual query: "if we intervene on X, what changes?".

    Params:
        observed_effects (list[str]): Currently observed effects.
        intervention (str): The variable to do-intervene on.
        observations (dict, optional): Variable → probability mappings.
        max_results (int, optional): Max results to return (default 10).
    """
    cr = _get_causal_reasoner()
    if cr is None:
        return _err("CausalReasoner not initialised")
    try:
        observed_effects = list(params.get("observed_effects", []))
        intervention = str(params.get("intervention", ""))
        observations = dict(params.get("observations", {}))
        max_results = int(params.get("max_results", 10))
        for var, prob in observations.items():
            await cr.observe(var, float(prob))
        result = await cr.counterfactual(
            observed_effects=observed_effects,
            intervention=intervention,
            max_results=max_results,
        )
        return _ok({
            "counterfactual_effects": dict(result.effects),
            "causes": dict(result.causes),
            "confidence": result.confidence,
            "reasoning_chain": result.reasoning_chain,
            "intervention_applied": intervention,
        })
    except Exception as exc:
        logger.exception("causal_counterfactual error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Semantic Knowledge Graph handlers
# ---------------------------------------------------------------------------

async def _handle_knowledge_graph_add(params: Dict[str, Any]) -> Dict[str, Any]:
    """Add a node (and optional edge) to the SemanticKnowledgeGraph.

    Params:
        node (dict): {label, semantic_type, tags[], attributes{}, confidence, provenance}
        edge (dict, optional): {target_id, edge_type, confidence, weight, provenance}
    """
    kg = _get_knowledge_graph()
    if kg is None:
        return _err("SemanticKnowledgeGraph not initialised")
    try:
        from src.intelligence.semantic_knowledge import EdgeType, KnowledgeNode  # noqa: F401  # intentional top-level import
        node_data = params.get("node", {})
        node = KnowledgeNode(
            label=node_data.get("label", ""),
            semantic_type=node_data.get("semantic_type", "entity"),
            tags=set(node_data.get("tags", [])),
            attributes=dict(node_data.get("attributes", {})),
            confidence=float(node_data.get("confidence", 0.8)),
            provenance=node_data.get("provenance", "spark"),
        )
        node_id = await kg.add_node(node)
        edge_id = None
        if "edge" in params:
            ed = params["edge"]
            etype_str = ed.get("edge_type", "RELATED_TO").upper()
            etype = EdgeType[etype_str] if etype_str in EdgeType.__members__ else EdgeType.RELATED_TO
            edge_id = await kg.add_edge(
                source_id=node_id,
                target_id=ed["target_id"],
                edge_type=etype,
                confidence=float(ed.get("confidence", 0.8)),
                weight=float(ed.get("weight", 1.0)),
                provenance=ed.get("provenance", "spark"),
            )
        stats = await kg.stats()
        return _ok({"node_id": node_id, "edge_id": edge_id,
                    "fingerprint": node.fingerprint, "graph_stats": stats})
    except Exception as exc:
        logger.exception("knowledge_graph_add error")
        return _err(safe_error_detail(exc, 500))


async def _handle_knowledge_graph_query(params: Dict[str, Any]) -> Dict[str, Any]:
    """Query nodes from the SemanticKnowledgeGraph.

    Params:
        semantic_type (str, optional): Filter by type.
        tag (str, optional): Filter by tag.
        label (str, optional): Substring match on label.
        min_confidence (float, optional): Minimum confidence threshold.
        provenance (str, optional): Filter by provenance source.
        limit (int, optional): Max results (default 20).
    """
    kg = _get_knowledge_graph()
    if kg is None:
        return _err("SemanticKnowledgeGraph not initialised")
    try:
        criteria: Dict[str, Any] = {}
        for k in ("semantic_type", "tag", "label", "min_confidence", "provenance"):
            if k in params:
                criteria[k] = params[k]
        limit = int(params.get("limit", 20))
        nodes = await kg.query_nodes(**criteria)
        nodes = nodes[:limit]
        return _ok({
            "nodes": [
                {"id": n.id, "label": n.label, "semantic_type": n.semantic_type,
                 "tags": sorted(n.tags), "confidence": n.confidence,
                 "provenance": n.provenance, "fingerprint": n.fingerprint}
                for n in nodes
            ],
            "count": len(nodes),
        })
    except Exception as exc:
        logger.exception("knowledge_graph_query error")
        return _err(safe_error_detail(exc, 500))


async def _handle_knowledge_graph_path(params: Dict[str, Any]) -> Dict[str, Any]:
    """Find the shortest path between two nodes in the SemanticKnowledgeGraph.

    Params:
        source_id (str): Starting node id.
        target_id (str): Destination node id.
        edge_type (str, optional): Restrict traversal to this edge type.
        all_paths (bool, optional): Return all simple paths instead of shortest (default false).
        max_depth (int, optional): Max depth for all_paths (default 6).
    """
    kg = _get_knowledge_graph()
    if kg is None:
        return _err("SemanticKnowledgeGraph not initialised")
    try:
        from src.intelligence.semantic_knowledge import EdgeType  # noqa: F401  # intentional top-level import
        source_id = params.get("source_id")
        target_id = params.get("target_id")
        if not source_id or not target_id:
            return _err("'source_id' and 'target_id' are required")
        etype = None
        if "edge_type" in params:
            et = params["edge_type"].upper()
            etype = EdgeType[et] if et in EdgeType.__members__ else None
        use_all = bool(params.get("all_paths", False))
        max_depth = int(params.get("max_depth", 6))
        if use_all:
            paths = await kg.all_paths(source_id, target_id, max_depth=max_depth, edge_type=etype)
            return _ok({"paths": paths, "count": len(paths), "mode": "all"})
        else:
            path = await kg.shortest_path(source_id, target_id, edge_type=etype)
            return _ok({"path": path, "length": len(path) - 1 if path else None, "mode": "shortest"})
    except Exception as exc:
        logger.exception("knowledge_graph_path error")
        return _err(safe_error_detail(exc, 500))


async def _handle_knowledge_graph_expand(params: Dict[str, Any]) -> Dict[str, Any]:
    """Semantically expand from a seed node, traversing the knowledge graph outward.

    Params:
        node_id (str): Seed node to expand from.
        depth (int, optional): Traversal depth (default 2).
        edge_types (list[str], optional): Restrict to these edge types.
        min_confidence (float, optional): Minimum edge confidence threshold (default 0.0).
    """
    kg = _get_knowledge_graph()
    if kg is None:
        return _err("SemanticKnowledgeGraph not initialised")
    try:
        from src.intelligence.semantic_knowledge import EdgeType  # noqa: F401  # intentional top-level import
        node_id = params.get("node_id")
        if not node_id:
            return _err("'node_id' is required")
        depth = int(params.get("depth", 2))
        min_conf = float(params.get("min_confidence", 0.0))
        etype_strs = params.get("edge_types", [])
        etypes = None
        if etype_strs:
            etypes = [EdgeType[et.upper()] for et in etype_strs
                      if et.upper() in EdgeType.__members__]
        expanded = await kg.semantic_expand(
            node_id, depth=depth, edge_types=etypes, min_confidence=min_conf
        )
        return _ok({
            "expanded_nodes": [
                {"id": nid, "label": node.label, "semantic_type": node.semantic_type,
                 "accumulated_confidence": conf, "tags": sorted(node.tags)}
                for nid, (node, conf) in expanded.items()
            ],
            "count": len(expanded),
            "seed_node_id": node_id,
        })
    except Exception as exc:
        logger.exception("knowledge_graph_expand error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Adaptive Foresight handler
# ---------------------------------------------------------------------------

async def _handle_foresight_predict(params: Dict[str, Any]) -> Dict[str, Any]:
    """Predict the trajectory of a conversation using the ForesightEngine.

    Params:
        session_id (str): Session identifier.
        emotion (str, optional): Current detected emotion (default "neutral").
        intent (str, optional): Current detected intent (default "question").
        history (list[dict], optional): Prior turns [{emotion, intent}].
        top_n (int, optional): Top N outcomes to return (default 3).
    """
    try:
        from src.adaptive.foresight import ConversationTrajectoryPredictor  # noqa: F401  # intentional top-level import
        predictor = ConversationTrajectoryPredictor()
        session_id = str(params.get("session_id", "default"))
        emotion = str(params.get("emotion", "neutral"))
        intent = str(params.get("intent", "question"))
        history = list(params.get("history", []))
        top_n = int(params.get("top_n", 3))
        # Record prior history turns
        for turn in history:
            predictor.record_turn(
                session_id,
                str(turn.get("emotion", "neutral")),
                str(turn.get("intent", "question")),
            )
        # Record current turn
        predictor.record_turn(session_id, emotion, intent)
        prediction = predictor.predict_trajectory(session_id)
        top = prediction.top(top_n) if prediction else []
        entropy = prediction.entropy() if prediction else 0.0
        confidence = prediction.confidence() if prediction else 0.0
        return _ok({
            "top_outcomes": [{"outcome": o, "probability": round(p, 4)} for o, p in top],
            "entropy": round(entropy, 4),
            "confidence": round(confidence, 4),
        })
    except Exception as exc:
        logger.exception("foresight_predict error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Analytics Intent handler
# ---------------------------------------------------------------------------

async def _handle_analytics_intent(params: Dict[str, Any]) -> Dict[str, Any]:
    """Classify user intent from a message fragment.

    Params:
        message (str): The user message to classify.
        emotion (str, optional): Detected emotion for context (default "neutral").
    """
    try:
        from src.analytics.predictive import IntentPredictor  # noqa: F401  # intentional top-level import
        predictor = IntentPredictor()
        message = str(params.get("message", ""))
        emotion = str(params.get("emotion", "neutral"))
        # predict(partial_text, emotion) → Dict[str, float]
        scores = predictor.predict(message, emotion=emotion)
        # Sort by score descending
        sorted_intents = sorted(scores.items(), key=lambda x: -x[1])
        return _ok({
            "primary_intent": sorted_intents[0][0] if sorted_intents else "unknown",
            "intent_scores": [{"intent": i, "score": round(s, 4)} for i, s in sorted_intents],
            "dominant_intent": predictor.dominant_intent(scores),
            "message_length": len(message),
        })
    except Exception as exc:
        logger.exception("analytics_intent error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# NanoBot Dispatch handler
# ---------------------------------------------------------------------------

async def _handle_nanobot_dispatch(params: Dict[str, Any]) -> Dict[str, Any]:
    """Dispatch a NanoCode repair bot to address a detected failure mode.

    Params:
        failure_mode (str): FailureMode name (e.g. HIGH_LATENCY, MEMORY_LEAK,
                             CONNECTION_POOL_EXHAUSTED, VECTOR_DB_CORRUPT,
                             SERVICE_UNREACHABLE, CACHE_STALE, LOOP_DETECTED).
        metrics (dict, optional): Raw metrics dict for automatic mode inference.
        target_service_url (str, optional): Override service URL for the bot.
    """
    try:
        from src.healing.nanocode_bots import FailureMode, NanoCodeBotDispatcher  # noqa: F401  # intentional top-level import
        dispatcher = NanoCodeBotDispatcher()
        failure_mode_str = params.get("failure_mode")
        metrics = dict(params.get("metrics", {}))
        target_url = params.get("target_service_url")
        override_cfg = {}
        if target_url:
            override_cfg["service_url"] = target_url
        if failure_mode_str:
            fm_upper = failure_mode_str.upper()
            if fm_upper in FailureMode.__members__:
                failure_mode = FailureMode[fm_upper]
                report = await dispatcher.dispatch(failure_mode, config=override_cfg)
            else:
                return _err(f"Unknown failure_mode '{failure_mode_str}'. "
                            f"Valid: {[f.name for f in FailureMode]}")
        elif metrics:
            report = await dispatcher.dispatch_from_metrics(metrics, config=override_cfg)
        else:
            return _err("Provide 'failure_mode' or 'metrics'")
        return _ok({
            "dispatched": True,
            "bot_type": report.get("bot_type"),
            "success": report.get("success"),
            "actions_taken": report.get("actions_taken", []),
            "duration_ms": report.get("duration_ms"),
        })
    except Exception as exc:
        logger.exception("nanobot_dispatch error")
        return _err(safe_error_detail(exc, 500))


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

PHASE4_TOOLS = [
    {
        "name": "neural_mesh_emit",
        "description": (
            "Emit a typed signal from a source node through the Tranc3 NeuralMesh. "
            "The mesh routes the signal to all connected nodes using Hebbian-weighted "
            "fan-out propagation. Useful for cross-service event broadcasting."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string", "description": "Sending mesh node id (auto-created if absent)."},
                "signal_type": {"type": "string", "description": "Event/signal category name."},
                "payload": {"type": "object", "description": "Arbitrary signal data."},
                "ttl": {"type": "integer", "description": "Hop limit (default 5)."},
            },
            "required": ["signal_type"],
        },
        "handler": _handle_neural_mesh_emit,
        "category": "neural",
    },
    {
        "name": "neural_mesh_topology",
        "description": (
            "Return a real-time snapshot of the NeuralMesh topology: all registered nodes, "
            "weighted edges, and identified network partitions."
        ),
        "input_schema": {"type": "object", "properties": {}},
        "handler": _handle_neural_mesh_topology,
        "category": "neural",
    },
    {
        "name": "collective_memory_store",
        "description": (
            "Store a value in the Tranc3 CollectiveMemory — a shared, decay-based working "
            "memory pool accessible to all nanoservices. Supports priority levels, TTL, "
            "topic grouping, and tagging."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Unique memory key."},
                "value": {"description": "Value to store (any JSON-serialisable type)."},
                "topic": {"type": "string", "description": "Logical grouping topic."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tag list."},
                "ttl": {"type": "number", "description": "Time-to-live in seconds (default 3600)."},
                "priority": {"type": "string", "enum": ["LOW", "NORMAL", "HIGH", "CRITICAL"],
                             "description": "Eviction priority (default NORMAL)."},
                "source": {"type": "string", "description": "Origin identifier."},
            },
            "required": ["key", "value"],
        },
        "handler": _handle_collective_memory_store,
        "category": "neural",
    },
    {
        "name": "collective_memory_query",
        "description": (
            "Query the Tranc3 CollectiveMemory by key, topic, or tag. "
            "Retrieving an entry automatically reinforces it (extends TTL up to 3x)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Direct key lookup."},
                "topic": {"type": "string", "description": "Topic filter."},
                "tag": {"type": "string", "description": "Tag filter."},
                "limit": {"type": "integer", "description": "Max results (default 20)."},
            },
        },
        "handler": _handle_collective_memory_query,
        "category": "neural",
    },
    {
        "name": "meta_learn_adapt",
        "description": (
            "Adapt task parameters for a new task using few-shot prototype matching. "
            "The MetaLearner scores the task against known prototypes across domain, "
            "task type, tags, input/output signatures, and embedding similarity, "
            "then applies EMA parameter adaptation from the best-matching prototype."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Task domain (e.g. nlp, code, analytics)."},
                "task_type": {"type": "string", "description": "Specific task type (e.g. summarise)."},
                "input_signature": {"type": "object", "description": "Input field names → types."},
                "output_signature": {"type": "object", "description": "Output field names → types."},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Descriptive tags."},
                "current_parameters": {"type": "object", "description": "Base parameters to adapt."},
            },
            "required": ["domain", "task_type"],
        },
        "handler": _handle_meta_learn_adapt,
        "category": "neural",
    },
    {
        "name": "attention_route",
        "description": (
            "Route a request to the optimal registered service using transformer-style "
            "softmax attention. Scores services on capability matching, load, latency, "
            "error rate, and availability. Returns ranked candidates with scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Description of what is needed."},
                "required_capabilities": {"type": "array", "items": {"type": "string"},
                                          "description": "Must-have capability tags."},
                "preferred_tags": {"type": "array", "items": {"type": "string"},
                                   "description": "Nice-to-have tags."},
                "exclude_tags": {"type": "array", "items": {"type": "string"},
                                 "description": "Tags to avoid."},
                "top_k": {"type": "integer", "description": "Return top-k candidates (default 3)."},
            },
            "required": ["query"],
        },
        "handler": _handle_attention_route,
        "category": "neural",
    },
    {
        "name": "causal_predict",
        "description": (
            "Predict downstream effects of observed evidence using the Tranc3 CausalReasoner. "
            "Applies forward DAG traversal with noisy-OR combination of contributing causes."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "observations": {"type": "object", "description": "Variable → value evidence dict."},
                "target_variables": {"type": "array", "items": {"type": "string"},
                                     "description": "Restrict output to these variables."},
                "threshold": {"type": "number", "description": "Minimum probability to include (default 0.1)."},
            },
            "required": ["observations"],
        },
        "handler": _handle_causal_predict,
        "category": "intelligence",
    },
    {
        "name": "causal_diagnose",
        "description": (
            "Diagnose the most likely root causes of observed symptoms using backward "
            "causal traversal with approximate Bayesian reasoning."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "symptoms": {"type": "object", "description": "Symptom variable → observed value."},
                "max_causes": {"type": "integer", "description": "Max root causes to return (default 5)."},
            },
            "required": ["symptoms"],
        },
        "handler": _handle_causal_diagnose,
        "category": "intelligence",
    },
    {
        "name": "causal_counterfactual",
        "description": (
            "Run a counterfactual 'what if?' query using Pearl's do-calculus: forcibly "
            "intervene on selected variables and predict what would change."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "observed_effects": {"type": "array", "items": {"type": "string"},
                                     "description": "Currently observed effect variables."},
                "intervention": {"type": "string",
                                 "description": "The single variable to do-intervene on."},
                "observations": {"type": "object", "description": "Current observed evidence (var → probability)."},
                "max_results": {"type": "integer", "description": "Max results to return (default 10)."},
            },
            "required": ["observed_effects", "intervention"],
        },
        "handler": _handle_causal_counterfactual,
        "category": "intelligence",
    },
    {
        "name": "knowledge_graph_add",
        "description": (
            "Add a typed node (and optional directed edge) to the Tranc3 Semantic "
            "Knowledge Graph. Supports 8 edge types: IS_A, PART_OF, RELATED_TO, "
            "DEPENDS_ON, PRODUCES, CONSUMES, SIMILAR_TO, INSTANCE_OF."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node": {
                    "type": "object",
                    "description": "Node definition: label, semantic_type, tags[], attributes{}, confidence, provenance.",
                    "properties": {
                        "label": {"type": "string"},
                        "semantic_type": {"type": "string"},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "attributes": {"type": "object"},
                        "confidence": {"type": "number"},
                        "provenance": {"type": "string"},
                    },
                    "required": ["label"],
                },
                "edge": {
                    "type": "object",
                    "description": "Optional edge: target_id, edge_type, confidence, weight, provenance.",
                    "properties": {
                        "target_id": {"type": "string"},
                        "edge_type": {"type": "string"},
                        "confidence": {"type": "number"},
                        "weight": {"type": "number"},
                        "provenance": {"type": "string"},
                    },
                    "required": ["target_id"],
                },
            },
            "required": ["node"],
        },
        "handler": _handle_knowledge_graph_add,
        "category": "intelligence",
    },
    {
        "name": "knowledge_graph_query",
        "description": (
            "Query nodes in the Tranc3 Semantic Knowledge Graph using indexed filters: "
            "semantic type, tag, label substring, confidence threshold, or provenance source."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "semantic_type": {"type": "string"},
                "tag": {"type": "string"},
                "label": {"type": "string", "description": "Substring match."},
                "min_confidence": {"type": "number"},
                "provenance": {"type": "string"},
                "limit": {"type": "integer", "description": "Max results (default 20)."},
            },
        },
        "handler": _handle_knowledge_graph_query,
        "category": "intelligence",
    },
    {
        "name": "knowledge_graph_path",
        "description": (
            "Find the shortest path (BFS) or all simple paths (DFS) between two nodes "
            "in the Semantic Knowledge Graph, optionally restricted to a specific edge type."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "source_id": {"type": "string"},
                "target_id": {"type": "string"},
                "edge_type": {"type": "string", "description": "IS_A | PART_OF | RELATED_TO | etc."},
                "all_paths": {"type": "boolean", "description": "Return all paths instead of shortest."},
                "max_depth": {"type": "integer", "description": "Max depth for all_paths (default 6)."},
            },
            "required": ["source_id", "target_id"],
        },
        "handler": _handle_knowledge_graph_path,
        "category": "intelligence",
    },
    {
        "name": "knowledge_graph_expand",
        "description": (
            "Semantically expand from a seed node, traversing the Knowledge Graph "
            "outward up to a configurable depth. Returns reachable nodes with "
            "accumulated confidence scores (product of edge confidences along best path)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string", "description": "Seed node to expand from."},
                "depth": {"type": "integer", "description": "Traversal depth (default 2)."},
                "edge_types": {"type": "array", "items": {"type": "string"},
                               "description": "Restrict to these edge types."},
                "min_confidence": {"type": "number", "description": "Min edge confidence (default 0.0)."},
            },
            "required": ["node_id"],
        },
        "handler": _handle_knowledge_graph_expand,
        "category": "intelligence",
    },
    {
        "name": "foresight_predict",
        "description": (
            "Predict the trajectory of a conversation or event sequence using the "
            "Tranc3 Adaptive Foresight engine. Returns top outcomes ranked by "
            "probability plus Shannon entropy and confidence scores."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Session identifier (default 'default')."},
                "emotion": {"type": "string", "description": "Current emotion label (default 'neutral')."},
                "intent": {"type": "string", "description": "Current intent label (default 'question')."},
                "history": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "emotion": {"type": "string"},
                            "intent": {"type": "string"},
                        },
                        "required": ["emotion", "intent"],
                    },
                    "description": "Prior conversation turns as [{emotion, intent}, ...].",
                },
                "top_n": {"type": "integer", "description": "Top N outcomes to return (default 3)."},
            },
            "required": [],
        },
        "handler": _handle_foresight_predict,
        "category": "adaptive",
    },
    {
        "name": "analytics_intent",
        "description": (
            "Classify user intent from a message using Tranc3's predictive analytics engine. "
            "Detects: question, complaint, praise, request, creative, analytical, emotional. "
            "Supports partial/incomplete input for real-time intent prediction."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Message to classify."},
                "partial": {"type": "boolean", "description": "Treat as incomplete input (default false)."},
            },
            "required": ["message"],
        },
        "handler": _handle_analytics_intent,
        "category": "adaptive",
    },
    {
        "name": "nanobot_dispatch",
        "description": (
            "Dispatch a Tranc3 NanoCode repair bot to automatically remediate a service "
            "failure. Supports explicit failure mode selection or automatic inference from "
            "raw metrics. Failure modes: HIGH_LATENCY, MEMORY_LEAK, "
            "CONNECTION_POOL_EXHAUSTED, VECTOR_DB_CORRUPT, SERVICE_UNREACHABLE, "
            "CACHE_STALE, LOOP_DETECTED."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "failure_mode": {
                    "type": "string",
                    "description": "Explicit failure mode name.",
                    "enum": ["HIGH_LATENCY", "MEMORY_LEAK", "CONNECTION_POOL_EXHAUSTED",
                             "VECTOR_DB_CORRUPT", "SERVICE_UNREACHABLE", "CACHE_STALE", "LOOP_DETECTED"],
                },
                "metrics": {"type": "object", "description": "Raw metrics for automatic mode inference."},
                "target_service_url": {"type": "string", "description": "Override service URL for the bot."},
            },
        },
        "handler": _handle_nanobot_dispatch,
        "category": "healing",
    },
]


# ---------------------------------------------------------------------------
# Registration entry-point
# ---------------------------------------------------------------------------

def register_phase4_tools(registry: Any) -> int:
    """Register all Phase 4 tools into the given SparkToolRegistry.

    Returns the number of tools registered.
    """
    from src.mcp.tools import SparkTool  # codeql[py/cyclic-import]
    registered = 0
    for t in PHASE4_TOOLS:
        try:
            tool = SparkTool(
                name=t["name"],
                description=t["description"],
                input_schema=t["input_schema"],
                handler=t["handler"],
                category=t.get("category", "phase4"),
                version="4.0.0",
            )
            registry.register(tool)
            registered += 1
            logger.debug("Registered Phase 4 tool: %s", t["name"])
        except Exception as exc:
            logger.warning("Failed to register tool %s: %s", t["name"], exc)
    logger.info("Phase 4 tools registered: %d / %d", registered, len(PHASE4_TOOLS))
    return registered
