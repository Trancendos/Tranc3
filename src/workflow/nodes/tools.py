"""
src/workflow/nodes/tools.py — Spark tool and skill invocation nodes for The Digital Grid.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Dict

from Dimensional.error_handlers import safe_error_detail

from .base import BaseNode, NodeResult

logger = logging.getLogger(__name__)

# The Digital Grid's local Spark tool registry: name -> async callable
# Takes precedence over The Spark's global registry for workflow-local overrides.
_SPARK_TOOL_REGISTRY: Dict[str, Callable] = {}

# Global skill registry: name -> async callable
_SKILL_REGISTRY: Dict[str, Callable] = {}


def register_spark_tool(name: str, fn: Callable) -> None:
    """Register a Spark tool callable for use in SparkToolNode within The Digital Grid."""
    _SPARK_TOOL_REGISTRY[name] = fn


def register_skill(name: str, fn: Callable) -> None:
    """Register a skill callable for use in SkillCallNode."""
    _SKILL_REGISTRY[name] = fn


class SparkToolNode(BaseNode):
    """A Digital Grid node that calls a registered Spark (MCP) tool by name."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        tool_name = self.config.config.get("tool_name", "")
        tool_args = {**self.config.config.get("args", {}), **inputs}

        if not tool_name:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error="No 'tool_name' specified in config"
            )

        fn = _SPARK_TOOL_REGISTRY.get(tool_name)
        _uses_kwargs = True

        if fn is None:
            try:
                from src.mcp.tools import registry as _spark_registry  # noqa: PLC0415

                spark_tool = _spark_registry.get(tool_name)
                if spark_tool is not None:
                    fn = spark_tool.handler
                    _uses_kwargs = False
            except ImportError:
                logger.debug("Graceful degradation: %s", "unknown")  # nosec B110

        if fn is None:
            duration_ms = (time.monotonic() - t0) * 1000
            available = list(_SPARK_TOOL_REGISTRY.keys())
            try:
                from src.mcp.tools import registry as _spark_registry  # noqa: PLC0415

                available += [t["name"] for t in _spark_registry.list_tools()]
            except ImportError:
                logger.debug("Graceful degradation: %s", "unknown")  # nosec B110
            return self._make_result(
                None,
                duration_ms,
                success=False,
                error=f"Spark tool '{tool_name}' not found. Available: {available}",
            )

        async def _call() -> Any:
            if _uses_kwargs:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(**tool_args)
                return fn(**tool_args)
            else:
                if asyncio.iscoroutinefunction(fn):
                    return await fn(tool_args)
                return fn(tool_args)

        try:
            result = await self._retry(
                lambda: self._with_timeout(_call(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(result, duration_ms, metadata={"tool_name": tool_name})
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


class SkillCallNode(BaseNode):
    """Looks up a skill in the registry and executes it."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        skill_name = self.config.config.get("skill_name", inputs.get("skill_name", ""))
        skill_args = {**self.config.config.get("args", {}), **inputs}
        skill_args.pop("skill_name", None)

        if not skill_name:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error="No 'skill_name' specified"
            )

        fn = _SKILL_REGISTRY.get(skill_name)
        if fn is None:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None,
                duration_ms,
                success=False,
                error=f"Skill '{skill_name}' not registered. "
                f"Available: {list(_SKILL_REGISTRY.keys())}",
            )

        async def _call() -> Any:
            if asyncio.iscoroutinefunction(fn):
                return await fn(**skill_args)
            return fn(**skill_args)

        try:
            result = await self._retry(
                lambda: self._with_timeout(_call(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(result, duration_ms, metadata={"skill_name": skill_name})
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


__all__ = [
    "_SPARK_TOOL_REGISTRY",
    "_SKILL_REGISTRY",
    "register_spark_tool",
    "register_skill",
    "SparkToolNode",
    "SkillCallNode",
]
