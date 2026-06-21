"""
src/workflow/nodes/neural.py — Phase 4 neural and memory nodes for The Digital Grid.

Covers: NeuralMeshNode, CollectiveMemoryNode, MetaLearnNode.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict

logger = logging.getLogger(__name__)


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


class NeuralMeshNode:
    """Emit a signal through the Tranc3 NeuralMesh or retrieve pending signals."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("NeuralMeshNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

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


class CollectiveMemoryNode:
    """Store or retrieve entries from the Tranc3 CollectiveMemory."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("CollectiveMemoryNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

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
                priority = (
                    MemoryPriority[pstr]
                    if pstr in MemoryPriority.__members__
                    else MemoryPriority.NORMAL
                )
                source = cfg.get("source", context.get("workflow_id", "workflow"))
                entry_id = await cm.store(
                    key=key, value=value, topic=topic, tags=tags, ttl=ttl,
                    priority=priority, source=source,
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


class MetaLearnNode:
    """Adapt workflow task parameters using the MetaLearner few-shot engine."""

    def __init__(self, config: Any) -> None:
        self.config = config
        self.logger = logger.getChild("MetaLearnNode")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> Any:
        from src.workflow.nodes.base import NodeResult

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
            result = await ml.adapt(
                domain=domain,
                task_type=task_type,
                input_signature=dict.fromkeys(input_schema, "str"),
                output_signature=dict.fromkeys(output_schema, "str"),
                tags=tags,
                current_parameters=base_params,
            )
            output = {
                "adapted": result is not None,
                "parameters": result.adapted_parameters if result else base_params,
                "confidence": result.confidence if result else 0.0,
                "prototype_id": result.prototype_id if result else None,
            }
            if cfg.get("record_outcome") and result:
                outcome_key = cfg.get("outcome_key", "success")
                success = bool(inputs.get(outcome_key, True))
                await ml.record_outcome(
                    result.prototype_id, success=success, parameters=base_params
                )
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


__all__ = ["NeuralMeshNode", "CollectiveMemoryNode", "MetaLearnNode"]
