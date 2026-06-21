"""
src/workflow/nodes/data.py — Data manipulation, output, and trigger nodes for The Digital Grid.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List

from Dimensional.error_handlers import safe_error_detail

from .base import BaseNode, NodeResult, _deep_get


class TransformNode(BaseNode):
    """Transforms data using a mapping spec (dot-path extraction or simple template)."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        mapping: Dict[str, str] = cfg.get("mapping", {})
        output: Dict[str, Any] = {}

        if mapping:
            for out_key, src_path in mapping.items():
                output[out_key] = _deep_get(inputs, src_path)
        else:
            output = dict(inputs)

        expression = cfg.get("expression")
        if expression:
            try:
                local_ns = {"data": output, "inputs": inputs, "context": context}
                eval_result = eval(expression, {"__builtins__": {}}, local_ns)  # noqa: S307  # nosec B307
                output = eval_result if isinstance(eval_result, dict) else {"result": eval_result}
            except Exception as exc:
                duration_ms = (time.monotonic() - t0) * 1000
                return self._make_result(
                    None, duration_ms, success=False, error=safe_error_detail(exc, 500)
                )

        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(
            output, duration_ms, metadata={"mapping_keys": list(mapping.keys())}
        )


class OutputNode(BaseNode):
    """Terminal node — collects and formats the final workflow output."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        keys = cfg.get("keys")
        if keys:
            output = {k: inputs.get(k) for k in keys}
        else:
            output = dict(inputs)
        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(output, duration_ms, metadata={"is_terminal": True})


class TriggerNode(BaseNode):
    """Workflow entry-point that validates and passes through trigger data."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        required_fields: List[str] = cfg.get("required_fields", [])
        missing = [f for f in required_fields if f not in inputs]
        if missing:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None,
                duration_ms,
                success=False,
                error=f"Trigger missing required fields: {missing}",
            )
        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(
            inputs,
            duration_ms,
            metadata={"trigger_type": cfg.get("trigger_type", "manual")},
        )


__all__ = ["TransformNode", "OutputNode", "TriggerNode"]
