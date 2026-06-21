"""
src/workflow/nodes/reasoning.py — Phase 4 reasoning and intelligence nodes for The Digital Grid.

Covers: AttentionRouteNode, CausalReasonNode, KnowledgeGraphNode, ForesightNode.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


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


class AttentionRouteNode:
    """Select the optimal downstream service using transformer-style attention routing."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("AttentionRouteNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = self.config.config
        try:
            router = _attention_router()
            if router is None:
                raise RuntimeError("AttentionRouter not available")
            from src.neural.attention_router import RoutingRequest

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


class CausalReasonNode:
    """Apply causal inference in a workflow step: predict, diagnose, or counterfactual."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("CausalReasonNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

        t0 = time.monotonic()
        cfg = self.config.config
        action = cfg.get("action", "predict")
        try:
            cr = _causal_reasoner()
            if cr is None:
                raise RuntimeError("CausalReasoner not available")
            obs_key = cfg.get("observations_key", "observations")
            observations = {
                **dict(cfg.get("static_observations", {})),
                **dict(inputs.get(obs_key, {})),
            }
            for var, val in observations.items():
                await cr.observe(var, float(val) if isinstance(val, (int, float)) else 1.0)
            if action == "predict":
                target_vars = list(cfg.get("target_variables", []))
                cause_list = target_vars or list(observations.keys())
                result = await cr.predict(causes=cause_list, max_results=10)
                output = {
                    "action": "predict",
                    "predictions": {e: round(p, 4) for e, p in result.effects},
                    "confidence": result.confidence,
                }
            elif action == "diagnose":
                max_results = int(cfg.get("max_causes", 5))
                effect_list = list(cfg.get("target_variables", []))
                if not effect_list:
                    effect_list = list(observations.keys())
                result = await cr.diagnose(effects=effect_list, max_results=max_results)
                output = {
                    "action": "diagnose",
                    "root_causes": [c for c, _ in result.causes],
                    "probabilities": {c: round(p, 4) for c, p in result.causes},
                    "confidence": result.confidence,
                }
            elif action == "counterfactual":
                int_key = cfg.get("interventions_key", "interventions")
                interventions = {
                    **dict(cfg.get("static_interventions", {})),
                    **dict(inputs.get(int_key, {})),
                }
                target_vars = list(cfg.get("target_variables", []))
                observed_effects = target_vars or list(observations.keys())
                intervention_str = next(iter(interventions.keys()), "") if interventions else ""
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


class KnowledgeGraphNode:
    """Interact with the Tranc3 Semantic Knowledge Graph in a workflow step."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("KnowledgeGraphNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

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
                output = {
                    "action": "add",
                    "node_id": node_id,
                    "fingerprint": node.fingerprint,
                    "stats": stats,
                }
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
                    "nodes": [
                        {
                            "id": n.id,
                            "label": n.label,
                            "semantic_type": n.semantic_type,
                            "confidence": n.confidence,
                        }
                        for n in nodes[:limit]
                    ],
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
                    paths = await kg.all_paths(
                        src_id, tgt_id, max_depth=int(cfg.get("max_depth", 6)), edge_type=etype
                    )
                    output = {"action": "path", "mode": "all", "paths": paths, "count": len(paths)}
                else:
                    path = await kg.shortest_path(src_id, tgt_id, edge_type=etype)
                    output = {
                        "action": "path",
                        "mode": "shortest",
                        "path": path,
                        "length": len(path) - 1 if path else None,
                    }
            elif action == "expand":
                src_key = cfg.get("source_id_key", "node_id")
                node_id = inputs.get(src_key, cfg.get("node_id"))
                depth = int(cfg.get("depth", 2))
                min_conf = float(cfg.get("min_confidence", 0.0))
                expanded = await kg.semantic_expand(node_id, depth=depth, min_confidence=min_conf)
                output = {
                    "action": "expand",
                    "seed": node_id,
                    "expanded": [
                        {"id": nid, "label": n.label, "confidence": round(c, 4)}
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


class ForesightNode:
    """Adaptive trajectory / intent prediction step in a workflow."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("ForesightNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

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


__all__ = [
    "AttentionRouteNode",
    "CausalReasonNode",
    "KnowledgeGraphNode",
    "ForesightNode",
]
