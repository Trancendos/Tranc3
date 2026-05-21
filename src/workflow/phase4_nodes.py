"""
phase4_nodes.py — Phase 4 Neural & Intelligence workflow nodes for The Digital Grid.

Adds 7 new node types that expose Phase 4 capabilities as first-class
workflow steps in the DAG executor:

  NEURAL_MESH      — emit / receive signals via NeuralMesh
  COLLECTIVE_MEM   — store / retrieve from CollectiveMemory
  META_LEARN       — few-shot task adaptation via MetaLearner
  ATTENTION_ROUTE  — transformer-style service routing
  CAUSAL_REASON    — causal inference (predict / diagnose / counterfactual)
  KNOWLEDGE_GRAPH  — structured knowledge queries (add / query / path / expand)
  FORESIGHT        — adaptive trajectory prediction

Each node follows the BaseNode contract: async execute(inputs, context) → NodeResult.
All Phase 4 components are imported lazily; the workflow executor starts cleanly
even if optional dependencies are absent.

Integration:
    Import register_phase4_nodes() and call it once at startup, or import
    and call extend_node_registry() to patch the existing NODE_REGISTRY dict.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Lazy component accessors (same pattern as spark_phase4_tools)
# ---------------------------------------------------------------------------

def _neural_mesh():
    try:
        from src.neural.neural_mesh import NeuralMesh
        if not hasattr(_neural_mesh, "_inst") or _neural_mesh._inst is None:
            _neural_mesh._inst = NeuralMesh()
        return _neural_mesh._inst
    except Exception as exc:
        logger.warning("NeuralMesh unavailable: %s", exc)
        return None


def _collective_memory():
    try:
        from src.neural.collective_memory import CollectiveMemory
        if not hasattr(_collective_memory, "_inst") or _collective_memory._inst is None:
            _collective_memory._inst = CollectiveMemory()
        return _collective_memory._inst
    except Exception as exc:
        logger.warning("CollectiveMemory unavailable: %s", exc)
        return None


def _meta_learner():
    try:
        from src.neural.meta_learner import MetaLearner
        if not hasattr(_meta_learner, "_inst") or _meta_learner._inst is None:
            _meta_learner._inst = MetaLearner()
        return _meta_learner._inst
    except Exception as exc:
        logger.warning("MetaLearner unavailable: %s", exc)
        return None


def _attention_router():
    try:
        from src.neural.attention_router import AttentionRouter
        if not hasattr(_attention_router, "_inst") or _attention_router._inst is None:
            _attention_router._inst = AttentionRouter()
        return _attention_router._inst
    except Exception as exc:
        logger.warning("AttentionRouter unavailable: %s", exc)
        return None


def _causal_reasoner():
    try:
        from src.intelligence.causal_reasoner import CausalReasoner
        if not hasattr(_causal_reasoner, "_inst") or _causal_reasoner._inst is None:
            _causal_reasoner._inst = CausalReasoner()
        return _causal_reasoner._inst
    except Exception as exc:
        logger.warning("CausalReasoner unavailable: %s", exc)
        return None


def _knowledge_graph():
    try:
        from src.intelligence.semantic_knowledge import SemanticKnowledgeGraph
        if not hasattr(_knowledge_graph, "_inst") or _knowledge_graph._inst is None:
            _knowledge_graph._inst = SemanticKnowledgeGraph()
        return _knowledge_graph._inst
    except Exception as exc:
        logger.warning("SemanticKnowledgeGraph unavailable: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Import base types from nodes.py (late import to avoid circular deps)
# ---------------------------------------------------------------------------

def _import_base():
    from src.workflow.nodes import BaseNode, NodeConfig, NodeResult, NodeType
    return BaseNode, NodeConfig, NodeResult, NodeType


# ---------------------------------------------------------------------------
# NeuralMeshNode
# ---------------------------------------------------------------------------

class NeuralMeshNode:
    """
    Emit a signal through the Tranc3 NeuralMesh or retrieve pending signals.

    Config keys:
        action (str):       "emit" (default) or "receive".
        source_id (str):    Sending node id (default "workflow").
        signal_type (str):  Signal category (default "workflow_event").
        payload_key (str):  Input key to use as signal payload (default uses whole inputs).
        ttl (int):          Hop limit for emitted signals (default 5).
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("NeuralMeshNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        action = cfg.get("action", "emit")
        try:
            mesh = _neural_mesh()
            if mesh is None:
                raise RuntimeError("NeuralMesh not available")
            if action == "emit":
                from src.neural.neural_mesh import MeshNode, Signal
                source_id = cfg.get("source_id", "workflow")
                signal_type = cfg.get("signal_type", "workflow_event")
                payload_key = cfg.get("payload_key")
                payload = inputs.get(payload_key, inputs) if payload_key else inputs
                ttl = int(cfg.get("ttl", 5))
                if source_id not in mesh._nodes:
                    node = MeshNode(id=source_id, service_name="workflow", host="internal", port=0)
                    await mesh.register_node(node)
                signal = Signal(
                    source_id=source_id,
                    signal_type=signal_type,
                    payload=dict(payload) if isinstance(payload, dict) else {"data": payload},
                    ttl=ttl,
                )
                delivered = await mesh.emit(signal)
                output = {"action": "emit", "delivered_to": delivered, "signal_type": signal_type}
            else:
                node_id = cfg.get("source_id", "workflow")
                signals = await mesh.receive(node_id)
                output = {
                    "action": "receive",
                    "signals": [
                        {"type": s.signal_type, "payload": s.payload, "source": s.source_id}
                        for s in (signals or [])
                    ],
                    "count": len(signals or []),
                }
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("NeuralMeshNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# CollectiveMemoryNode
# ---------------------------------------------------------------------------

class CollectiveMemoryNode:
    """
    Store or retrieve entries from the Tranc3 CollectiveMemory.

    Config keys:
        action (str):       "store" | "retrieve" | "query_topic" | "query_tag".
        key (str):          Memory key (for store/retrieve).
        value_key (str):    Input key to use as stored value (default "output").
        topic (str):        Topic for store/query_topic.
        tag (str):          Tag for query_tag.
        tags (list[str]):   Tags to attach on store.
        ttl (float):        TTL in seconds for store (default 3600).
        priority (str):     LOW|NORMAL|HIGH|CRITICAL for store.
        source (str):       Provenance label for store.
        limit (int):        Max results for query operations (default 20).
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("CollectiveMemoryNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        action = cfg.get("action", "store")
        try:
            cm = _collective_memory()
            if cm is None:
                raise RuntimeError("CollectiveMemory not available")
            if action == "store":
                from src.neural.collective_memory import MemoryPriority
                key = cfg.get("key") or context.get("workflow_id", "unknown")
                value_key = cfg.get("value_key", "output")
                value = inputs.get(value_key, inputs)
                topic = cfg.get("topic", "workflow")
                tags = set(cfg.get("tags", []))
                ttl = float(cfg.get("ttl", 3600))
                pstr = cfg.get("priority", "NORMAL").upper()
                priority = MemoryPriority[pstr] if pstr in MemoryPriority.__members__ else MemoryPriority.NORMAL
                source = cfg.get("source", context.get("workflow_id", "workflow"))
                entry_id = await cm.store(
                    key=key, value=value, topic=topic, tags=tags,
                    ttl=ttl, priority=priority, source=source,
                )
                output = {"action": "store", "key": key, "entry_id": entry_id}
            elif action == "retrieve":
                key = cfg.get("key") or inputs.get("key")
                entry = await cm.retrieve(key)
                output = {
                    "action": "retrieve",
                    "found": entry is not None,
                    "value": entry.value if entry else None,
                    "topic": entry.topic if entry else None,
                }
            elif action == "query_topic":
                topic = cfg.get("topic", "workflow")
                limit = int(cfg.get("limit", 20))
                entries = await cm.query_by_topic(topic, limit=limit)
                output = {
                    "action": "query_topic",
                    "topic": topic,
                    "results": [{"key": e.key, "value": e.value} for e in entries],
                    "count": len(entries),
                }
            elif action == "query_tag":
                tag = cfg.get("tag", "")
                limit = int(cfg.get("limit", 20))
                entries = await cm.query_by_tag(tag, limit=limit)
                output = {
                    "action": "query_tag",
                    "tag": tag,
                    "results": [{"key": e.key, "value": e.value} for e in entries],
                    "count": len(entries),
                }
            else:
                output = {"error": f"Unknown action: {action}"}
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("CollectiveMemoryNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# MetaLearnNode
# ---------------------------------------------------------------------------

class MetaLearnNode:
    """
    Adapt workflow task parameters using the MetaLearner few-shot engine.
    Useful for injecting adaptive configuration into downstream nodes.

    Config keys:
        domain (str):           Task domain.
        task_type (str):        Task type.
        input_schema (list):    Input field names.
        output_schema (list):   Output field names.
        tags (list[str]):       Descriptive tags.
        base_params (dict):     Starting parameter dict to adapt.
        record_outcome (bool):  Record this adaptation's outcome (default false).
        outcome_key (str):      Input key containing bool success signal.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("MetaLearnNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        try:
            ml = _meta_learner()
            if ml is None:
                raise RuntimeError("MetaLearner not available")
            domain = cfg.get("domain", inputs.get("domain", "general"))
            task_type = cfg.get("task_type", inputs.get("task_type", "generic"))
            input_schema = list(cfg.get("input_schema", []))
            output_schema = list(cfg.get("output_schema", []))
            tags = list(cfg.get("tags", []))
            base_params = dict(cfg.get("base_params", inputs.get("parameters", {})))
            # Use keyword-arg API: adapt(domain, task_type, input_signature,
            # output_signature, tags, current_parameters)
            result = await ml.adapt(
                domain=domain,
                task_type=task_type,
                input_signature={k: "str" for k in input_schema},
                output_signature={k: "str" for k in output_schema},
                tags=tags,
                current_parameters=base_params,
            )
            output = {
                "adapted": result is not None,
                "parameters": result.adapted_parameters if result else base_params,
                "confidence": result.confidence if result else 0.0,
                "prototype_id": result.prototype_id if result else None,
            }
            # Optionally record outcome for future learning
            if cfg.get("record_outcome") and result:
                outcome_key = cfg.get("outcome_key", "success")
                success = bool(inputs.get(outcome_key, True))
                await ml.record_outcome(result.prototype_id, success=success, parameters=base_params)
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("MetaLearnNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# AttentionRouteNode
# ---------------------------------------------------------------------------

class AttentionRouteNode:
    """
    Select the optimal downstream service using transformer-style attention routing.
    Injects routing decision into context for downstream nodes.

    Config keys:
        query (str):                   What is needed (can use {input_key} template).
        required_capabilities (list):  Must-have capability tags.
        preferred_tags (list):         Nice-to-have tags.
        exclude_tags (list):           Tags to avoid.
        top_k (int):                   Number of candidates to return (default 3).
        query_input_key (str):         Input key to use as query text.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AttentionRouteNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        try:
            router = _attention_router()
            if router is None:
                raise RuntimeError("AttentionRouter not available")
            from src.neural.attention_router import RoutingRequest
            # Resolve query from config or input
            query_key = cfg.get("query_input_key")
            query = str(inputs.get(query_key, "")) if query_key else cfg.get("query", "")
            req = RoutingRequest(
                query=query,
                required_capabilities=list(cfg.get("required_capabilities", [])),
                preferred_tags=list(cfg.get("preferred_tags", [])),
                exclude_tags=list(cfg.get("exclude_tags", [])),
                top_k=int(cfg.get("top_k", 3)),
            )
            decision = await router.route(req)
            if decision is None:
                output = {"routed": False, "primary_service": None, "candidates": []}
            else:
                output = {
                    "routed": True,
                    "primary_service": decision.primary_service,
                    "candidates": decision.candidates,
                    "scores": decision.scores,
                }
                # Inject into context for downstream nodes
                context["routed_service"] = decision.primary_service
                context["routing_candidates"] = decision.candidates
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("AttentionRouteNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# CausalReasonNode
# ---------------------------------------------------------------------------

class CausalReasonNode:
    """
    Apply causal inference in a workflow step: predict, diagnose, or counterfactual.

    Config keys:
        action (str):               "predict" | "diagnose" | "counterfactual".
        observations_key (str):     Input key for evidence dict (default "observations").
        interventions_key (str):    Input key for interventions dict (counterfactual only).
        target_variables (list):    Restrict output predictions.
        threshold (float):          Min probability for predict (default 0.1).
        max_causes (int):           Max root causes for diagnose (default 5).
        static_observations (dict): Fixed observations to merge with input.
        static_interventions (dict): Fixed interventions for counterfactual.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("CausalReasonNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        action = cfg.get("action", "predict")
        try:
            cr = _causal_reasoner()
            if cr is None:
                raise RuntimeError("CausalReasoner not available")
            obs_key = cfg.get("observations_key", "observations")
            observations = {**dict(cfg.get("static_observations", {})),
                            **dict(inputs.get(obs_key, {}))}
            # All CausalReasoner methods are async — must await each call.
            for var, val in observations.items():
                await cr.observe(var, float(val) if isinstance(val, (int, float)) else 1.0)
            if action == "predict":
                # predict(causes: List[str], max_results=10) → InferenceResult
                target_vars = list(cfg.get("target_variables", []))
                cause_list = target_vars or list(observations.keys())
                result = await cr.predict(causes=cause_list, max_results=10)
                output = {
                    "action": "predict",
                    # InferenceResult.effects: List[Tuple[str, float]]
                    "predictions": {e: round(p, 4) for e, p in result.effects},
                    "confidence": result.confidence,
                }
            elif action == "diagnose":
                max_results = int(cfg.get("max_causes", 5))
                # diagnose(effects: List[str], max_results=10) → InferenceResult
                effect_list = list(cfg.get("target_variables", []))
                if not effect_list:
                    effect_list = list(observations.keys())
                result = await cr.diagnose(effects=effect_list, max_results=max_results)
                # InferenceResult.causes: List[Tuple[str, float]]
                output = {
                    "action": "diagnose",
                    "root_causes": [c for c, _ in result.causes],
                    "probabilities": {c: round(p, 4) for c, p in result.causes},
                    "confidence": result.confidence,
                }
            elif action == "counterfactual":
                int_key = cfg.get("interventions_key", "interventions")
                interventions = {**dict(cfg.get("static_interventions", {})),
                                 **dict(inputs.get(int_key, {}))}
                target_vars = list(cfg.get("target_variables", []))
                observed_effects = target_vars or list(observations.keys())
                # counterfactual(observed_effects, intervention, max_results)
                # The API takes a single intervention string; use first key if dict
                intervention_str = (
                    next(iter(interventions.keys()), "")
                    if interventions else ""
                )
                result = await cr.counterfactual(
                    observed_effects=observed_effects,
                    intervention=intervention_str,
                    max_results=10,
                )
                output = {
                    "action": "counterfactual",
                    "predictions": {e: round(p, 4) for e, p in result.effects},
                    "delta": {e: round(p, 4) for e, p in result.effects},
                    "confidence": result.confidence,
                    "interventions": interventions,
                }
            else:
                output = {"error": f"Unknown action: {action}"}
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("CausalReasonNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# KnowledgeGraphNode
# ---------------------------------------------------------------------------

class KnowledgeGraphNode:
    """
    Interact with the Tranc3 Semantic Knowledge Graph in a workflow step.

    Config keys:
        action (str):           "add" | "query" | "path" | "expand".
        node_label (str):       Label for the new node (add action).
        node_type (str):        Semantic type for new node (add action).
        node_tags (list[str]):  Tags for new node.
        node_attributes (dict): Attributes for new node.
        confidence (float):     Node confidence.
        provenance (str):       Origin label.
        query_type (str):       "semantic_type"|"tag"|"label" filter key (query).
        query_value (str):      Filter value (query).
        source_id_key (str):    Input key for source node id (path/expand).
        target_id_key (str):    Input key for target node id (path).
        edge_type (str):        EdgeType name (path filter).
        depth (int):            Expansion depth (expand, default 2).
        all_paths (bool):       Return all paths vs shortest (path, default false).
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("KnowledgeGraphNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        action = cfg.get("action", "query")
        try:
            kg = _knowledge_graph()
            if kg is None:
                raise RuntimeError("SemanticKnowledgeGraph not available")
            if action == "add":
                from src.intelligence.semantic_knowledge import KnowledgeNode
                node = KnowledgeNode(
                    label=cfg.get("node_label", inputs.get("label", "")),
                    semantic_type=cfg.get("node_type", "entity"),
                    tags=set(cfg.get("node_tags", [])),
                    attributes=dict(cfg.get("node_attributes", {})),
                    confidence=float(cfg.get("confidence", 0.8)),
                    provenance=cfg.get("provenance", "workflow"),
                )
                node_id = await kg.add_node(node)
                stats = await kg.stats()
                output = {"action": "add", "node_id": node_id,
                          "fingerprint": node.fingerprint, "stats": stats}
            elif action == "query":
                criteria = {}
                for k in ("semantic_type", "tag", "label", "min_confidence", "provenance"):
                    cfg_key = f"query_{k}" if k not in cfg else k
                    if cfg_key in cfg:
                        criteria[k] = cfg[cfg_key]
                    elif "query_type" in cfg and cfg["query_type"] == k and "query_value" in cfg:
                        criteria[k] = cfg["query_value"]
                limit = int(cfg.get("limit", 20))
                nodes = await kg.query_nodes(**criteria)
                output = {
                    "action": "query",
                    "nodes": [{"id": n.id, "label": n.label,
                               "semantic_type": n.semantic_type,
                               "confidence": n.confidence} for n in nodes[:limit]],
                    "count": len(nodes),
                }
            elif action == "path":
                from src.intelligence.semantic_knowledge import EdgeType
                src_key = cfg.get("source_id_key", "source_id")
                tgt_key = cfg.get("target_id_key", "target_id")
                src_id = inputs.get(src_key, cfg.get("source_id"))
                tgt_id = inputs.get(tgt_key, cfg.get("target_id"))
                etype_str = cfg.get("edge_type", "").upper()
                etype = EdgeType[etype_str] if etype_str in EdgeType.__members__ else None
                if cfg.get("all_paths"):
                    paths = await kg.all_paths(src_id, tgt_id,
                                               max_depth=int(cfg.get("max_depth", 6)),
                                               edge_type=etype)
                    output = {"action": "path", "mode": "all", "paths": paths,
                              "count": len(paths)}
                else:
                    path = await kg.shortest_path(src_id, tgt_id, edge_type=etype)
                    output = {"action": "path", "mode": "shortest", "path": path,
                              "length": len(path) - 1 if path else None}
            elif action == "expand":
                src_key = cfg.get("source_id_key", "node_id")
                node_id = inputs.get(src_key, cfg.get("node_id"))
                depth = int(cfg.get("depth", 2))
                min_conf = float(cfg.get("min_confidence", 0.0))
                expanded = await kg.semantic_expand(node_id, depth=depth,
                                                    min_confidence=min_conf)
                output = {
                    "action": "expand",
                    "seed": node_id,
                    "expanded": [
                        {"id": nid, "label": n.label,
                         "confidence": round(c, 4)}
                        for nid, (n, c) in expanded.items()
                    ],
                    "count": len(expanded),
                }
            else:
                output = {"error": f"Unknown action: {action}"}
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("KnowledgeGraphNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# ForesightNode
# ---------------------------------------------------------------------------

class ForesightNode:
    """
    Adaptive trajectory / intent prediction step in a workflow.
    Uses the Foresight and/or Analytics engines to predict next states.

    Config keys:
        mode (str):         "foresight" (default) | "intent" | "both".
        history_key (str):  Input key for message/event history list.
        message_key (str):  Input key for single message (intent mode).
        top_n (int):        Top N outcomes (default 3).
        context_keys (list): Input keys to include as context.
        branch_on_intent (bool): Emit intent as routing hint in context.
    """

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("ForesightNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes import NodeResult
        t0 = time.monotonic()
        cfg = self.config.config
        mode = cfg.get("mode", "foresight")
        top_n = int(cfg.get("top_n", 3))
        output: Dict[str, Any] = {"mode": mode}
        try:
            if mode in ("foresight", "both"):
                try:
                    from src.adaptive.foresight import ConversationTrajectoryPredictor
                    predictor = ConversationTrajectoryPredictor()
                    hist_key = cfg.get("history_key", "history")
                    history = inputs.get(hist_key, [])
                    if isinstance(history, str):
                        history = [history]
                    ctx_keys = cfg.get("context_keys", [])
                    ctx = {k: inputs[k] for k in ctx_keys if k in inputs}
                    for msg in history:
                        predictor.observe(str(msg))
                    prediction = predictor.predict(context=ctx)
                    top = prediction.top(top_n) if prediction else []
                    output["foresight"] = {
                        "top_outcomes": [{"outcome": o, "p": round(p, 4)} for o, p in top],
                        "confidence": round(prediction.confidence(), 4) if prediction else 0.0,
                        "entropy": round(prediction.entropy(), 4) if prediction else 0.0,
                    }
                except Exception as fe:
                    output["foresight_error"] = str(fe)
            if mode in ("intent", "both"):
                try:
                    from src.analytics.predictive import IntentPredictor
                    predictor = IntentPredictor()
                    msg_key = cfg.get("message_key", "message")
                    message = str(inputs.get(msg_key, ""))
                    intents = predictor.classify(message)
                    primary = intents[0][0] if intents else "unknown"
                    output["intent"] = {
                        "primary": primary,
                        "scores": [{"intent": i, "score": round(s, 4)} for i, s in intents],
                    }
                    if cfg.get("branch_on_intent"):
                        context["predicted_intent"] = primary
                except Exception as ie:
                    output["intent_error"] = str(ie)
            return NodeResult(
                node_id=self.config.id,
                success=True,
                output=output,
                error=None,
                duration_ms=(time.monotonic() - t0) * 1000,
            )
        except Exception as exc:
            self.logger.exception("ForesightNode error")
            return NodeResult(
                node_id=self.config.id,
                success=False,
                output=None,
                error=str(exc),
                duration_ms=(time.monotonic() - t0) * 1000,
            )


# ---------------------------------------------------------------------------
# Phase 4 NodeType values (string enum extensions)
# ---------------------------------------------------------------------------

PHASE4_NODE_TYPES = {
    "NEURAL_MESH": NeuralMeshNode,
    "COLLECTIVE_MEM": CollectiveMemoryNode,
    "META_LEARN": MetaLearnNode,
    "ATTENTION_ROUTE": AttentionRouteNode,
    "CAUSAL_REASON": CausalReasonNode,
    "KNOWLEDGE_GRAPH": KnowledgeGraphNode,
    "FORESIGHT": ForesightNode,
}


def extend_node_registry(registry: Dict[str, Any]) -> int:
    """
    Extend an existing NODE_REGISTRY dict with Phase 4 node types.

    The registry keys should be NodeType enum members or plain strings.
    This function adds string keys as a fallback and attempts to extend
    the NodeType enum if the 'aenum' library is available.

    Returns the number of nodes registered.
    """
    registered = 0
    for type_name, node_class in PHASE4_NODE_TYPES.items():
        # Try to find matching enum member
        try:
            from src.workflow.nodes import NodeType
            if hasattr(NodeType, type_name):
                registry[NodeType(type_name)] = node_class
            else:
                # Register as string key for create_node() fallback
                registry[type_name] = node_class
            registered += 1
            logger.debug("Registered Phase 4 node: %s", type_name)
        except Exception as exc:
            logger.warning("Failed to register Phase 4 node %s: %s", type_name, exc)
    logger.info("Phase 4 workflow nodes registered: %d", registered)
    return registered
