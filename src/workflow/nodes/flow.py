"""
src/workflow/nodes/flow.py — Control-flow nodes for The Digital Grid.

Covers: ConditionNode, ParallelNode, LoopNode, MergeNode.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List

from Dimensional.error_handlers import safe_error_detail

from .base import BaseNode, NodeConfig, NodeResult, NodeType


class ConditionNode(BaseNode):
    """Evaluates a Python expression against inputs; branches on true/false."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        expression = self.config.config.get("expression", "True")
        local_ns: Dict[str, Any] = {"inputs": inputs, "context": context, **inputs}
        try:
            result = bool(eval(expression, {"__builtins__": {}}, local_ns))  # noqa: S307  # nosec B307
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                {"condition": result, "branch": "true" if result else "false"},
                duration_ms,
                metadata={"expression": expression},
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                {"condition": False, "branch": "false"},
                duration_ms,
                success=False,
                error=safe_error_detail(exc, 500),
            )


class ParallelNode(BaseNode):
    """Runs a list of child NodeConfigs concurrently and merges their results."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        from .registry import create_node

        t0 = time.monotonic()
        child_configs_raw: List[Dict] = self.config.config.get("nodes", [])
        if not child_configs_raw:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result({"results": []}, duration_ms, metadata={"parallel_count": 0})

        child_configs = [
            NodeConfig(
                id=c.get("id", f"parallel_child_{i}"),
                type=NodeType(c["type"]),
                name=c.get("name", f"child_{i}"),
                config=c.get("config", {}),
                inputs=c.get("inputs", []),
                outputs=c.get("outputs", []),
                timeout_sec=c.get("timeout_sec", self.config.timeout_sec),
                retry_count=c.get("retry_count", self.config.retry_count),
            )
            for i, c in enumerate(child_configs_raw)
        ]

        tasks = [create_node(cc).execute(inputs, context) for cc in child_configs]
        results: List[NodeResult] = await asyncio.gather(*tasks, return_exceptions=False)

        merged: Dict[str, Any] = {}
        errors: List[str] = []
        for res in results:
            if res.success:
                merged[res.node_id] = res.output
            else:
                errors.append(f"{res.node_id}: {res.error}")

        duration_ms = (time.monotonic() - t0) * 1000
        all_ok = len(errors) == 0
        return self._make_result(
            {"results": merged, "errors": errors},
            duration_ms,
            success=all_ok,
            error="; ".join(errors) if errors else None,
            metadata={"parallel_count": len(child_configs)},
        )


class LoopNode(BaseNode):
    """Iterates over inputs['items'], running inner node configs for each element."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        from .registry import create_node

        t0 = time.monotonic()
        items: List[Any] = inputs.get("items", self.config.config.get("items", []))
        inner_configs_raw: List[Dict] = self.config.config.get("nodes", [])
        max_concurrency = int(self.config.config.get("max_concurrency", 1))

        if not inner_configs_raw:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result({"loop_results": []}, duration_ms, metadata={"item_count": 0})

        inner_configs = [
            NodeConfig(
                id=c.get("id", f"loop_inner_{i}"),
                type=NodeType(c["type"]),
                name=c.get("name", f"inner_{i}"),
                config=c.get("config", {}),
                inputs=c.get("inputs", []),
                outputs=c.get("outputs", []),
                timeout_sec=c.get("timeout_sec", self.config.timeout_sec),
                retry_count=c.get("retry_count", self.config.retry_count),
            )
            for i, c in enumerate(inner_configs_raw)
        ]

        semaphore = asyncio.Semaphore(max(max_concurrency, 1))

        async def _run_item(item: Any, idx: int) -> Any:
            async with semaphore:
                item_inputs = {**inputs, "item": item, "index": idx}
                item_result: Any = item
                for nc in inner_configs:
                    node = create_node(nc)
                    res = await node.execute(item_inputs, context)
                    if res.success:
                        item_inputs.update({"previous": res.output})
                        item_result = res.output
                    else:
                        return {"error": res.error, "item": item}
                return item_result

        loop_results = await asyncio.gather(
            *[_run_item(item, idx) for idx, item in enumerate(items)]
        )

        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(
            {"loop_results": list(loop_results)},
            duration_ms,
            metadata={"item_count": len(items)},
        )


class MergeNode(BaseNode):
    """Merges all incoming inputs into a single dict output."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        strategy = self.config.config.get("strategy", "merge")
        if strategy == "first":
            output = next(iter(inputs.values()), {}) if inputs else {}
        elif strategy == "last":
            output = next(reversed(list(inputs.values())), {}) if inputs else {}
        else:
            output = {}
            for v in inputs.values():
                if isinstance(v, dict):
                    output.update(v)
                else:
                    output[f"input_{id(v)}"] = v
        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(output, duration_ms, metadata={"strategy": strategy})


__all__ = ["ConditionNode", "ParallelNode", "LoopNode", "MergeNode"]
