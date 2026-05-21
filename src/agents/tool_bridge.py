"""
tool_bridge.py — Unified Tool Execution Bridge for Tranc3 Platform (Phase 5)

Provides a single, unified interface for an autonomous agent to invoke any
tool in the Tranc3 platform, regardless of where the tool is registered:

  1. The Spark's MCP tool registry (src/mcp/tools.py::SparkToolRegistry)
  2. The Digital Grid's workflow registry (src/workflow/nodes.py)
  3. Phase 4 neural & intelligence tools (src/mcp/spark_phase4_tools.py)
  4. Phase 5 agent tools (src/mcp/spark_phase5_tools.py)
  5. Direct Python function calls (registered at runtime)

The ToolBridge:
  - Resolves tool names to executable handlers
  - Handles async/sync dispatch transparently
  - Records execution metrics (duration, success/failure)
  - Provides a ToolResult dataclass for uniform return types
  - Supports tool capability tagging for AttentionRouter integration

All components are lazy-loaded: the ToolBridge starts empty and discovers
tools on first use. This ensures zero-cost startup.

Zero-cost: pure Python, no external dependencies or API calls.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """
    Uniform result type returned by all tool invocations through ToolBridge.

    Attributes:
        tool_name: name of the tool that was invoked
        success: whether the invocation completed without error
        data: the result payload (if successful)
        error: error message (if failed)
        duration_ms: wall-clock execution time in milliseconds
        metadata: additional metadata about the invocation
        invocation_id: unique ID for this particular invocation
    """

    tool_name: str = ""
    success: bool = True
    data: Any = None
    error: Optional[str] = None
    duration_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    invocation_id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "duration_ms": round(self.duration_ms, 2),
            "metadata": self.metadata,
            "invocation_id": self.invocation_id,
        }


# ---------------------------------------------------------------------------
# Tool descriptor (internal)
# ---------------------------------------------------------------------------


@dataclass
class _ToolDescriptor:
    """Internal descriptor for a registered tool."""

    name: str
    handler: Callable[..., Any]
    is_async: bool
    source: str  # "mcp", "workflow", "direct", "phase4", "phase5"
    capability_tags: Set[str] = field(default_factory=set)
    description: str = ""


# ---------------------------------------------------------------------------
# Tool Bridge
# ---------------------------------------------------------------------------


class ToolBridge:
    """
    Unified tool execution bridge for autonomous agents.

    Resolves tool names to handlers across all Tranc3 tool registries
    and provides uniform invocation with metrics and error handling.

    Usage:
        bridge = ToolBridge()
        result = await bridge.execute(
            tool_name="execute_code",
            args={"code": "print('hello')"},
            agent_id="agent-abc123",
        )
        if result.success:
            print(result.data)
    """

    def __init__(self, max_history: int = 200) -> None:
        self._direct_tools: Dict[str, _ToolDescriptor] = {}
        self._invocation_history: List[ToolResult] = []
        self._max_history = max_history
        self._discovered_mcp = False
        self._discovered_workflow = False

    # -------------------------------------------------------------------
    # Tool registration (direct)
    # -------------------------------------------------------------------

    def register_tool(
        self,
        name: str,
        handler: Callable[..., Any],
        capability_tags: Optional[Set[str]] = None,
        description: str = "",
    ) -> None:
        """
        Register a tool directly with the bridge.

        Direct registrations take precedence over discovered tools from
        the MCP or workflow registries.
        """
        is_async = asyncio.iscoroutinefunction(handler)
        self._direct_tools[name] = _ToolDescriptor(
            name=name,
            handler=handler,
            is_async=is_async,
            source="direct",
            capability_tags=capability_tags or set(),
            description=description,
        )
        logger.debug("ToolBridge: registered direct tool '%s' (async=%s)", name, is_async)

    def unregister_tool(self, name: str) -> bool:
        """Remove a directly registered tool."""
        if name in self._direct_tools:
            del self._direct_tools[name]
            return True
        return False

    # -------------------------------------------------------------------
    # Tool execution
    # -------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        agent_id: Optional[str] = None,
        timeout_sec: float = 30.0,
    ) -> ToolResult:
        """
        Execute a tool by name with the given arguments.

        Resolution order:
        1. Direct registrations (highest priority)
        2. The Spark's MCP tool registry
        3. The Digital Grid's workflow node registry

        Returns a ToolResult with the outcome.
        """
        args = args or {}
        t0 = time.monotonic()

        # Add agent context to args
        if agent_id:
            args["_agent_id"] = agent_id

        # 1. Try direct tools
        descriptor = self._direct_tools.get(tool_name)

        # 2. Try MCP registry
        if descriptor is None:
            descriptor = self._resolve_mcp_tool(tool_name)

        # 3. Try workflow registry
        if descriptor is None:
            descriptor = self._resolve_workflow_tool(tool_name)

        # Not found
        if descriptor is None:
            available = self.list_available_tools()
            duration_ms = (time.monotonic() - t0) * 1000
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool '{tool_name}' not found. Available: {available[:20]}",
                duration_ms=duration_ms,
                metadata={"agent_id": agent_id},
            )
            self._record_invocation(result)
            return result

        # Execute the handler
        try:
            if descriptor.is_async:
                # MCP tools take a single params dict
                if descriptor.source in ("mcp", "phase4", "phase5"):
                    data = await asyncio.wait_for(
                        descriptor.handler(args),
                        timeout=timeout_sec,
                    )
                else:
                    data = await asyncio.wait_for(
                        descriptor.handler(**args),
                        timeout=timeout_sec,
                    )
            else:
                if descriptor.source in ("mcp", "phase4", "phase5"):
                    data = descriptor.handler(args)
                else:
                    data = descriptor.handler(**args)

            duration_ms = (time.monotonic() - t0) * 1000
            result = ToolResult(
                tool_name=tool_name,
                success=True,
                data=data,
                duration_ms=duration_ms,
                metadata={
                    "agent_id": agent_id,
                    "source": descriptor.source,
                },
            )
        except asyncio.TimeoutError:
            duration_ms = (time.monotonic() - t0) * 1000
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                error=f"Tool execution timed out after {timeout_sec}s",
                duration_ms=duration_ms,
                metadata={"agent_id": agent_id, "source": descriptor.source},
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            result = ToolResult(
                tool_name=tool_name,
                success=False,
                error=str(exc),
                duration_ms=duration_ms,
                metadata={"agent_id": agent_id, "source": descriptor.source},
            )
            logger.warning(
                "ToolBridge: tool '%s' failed: %s", tool_name, exc,
            )

        self._record_invocation(result)
        return result

    # -------------------------------------------------------------------
    # Tool discovery
    # -------------------------------------------------------------------

    def list_available_tools(self) -> List[str]:
        """Return a list of all available tool names across all registries."""
        tools = set(self._direct_tools.keys())

        # Discover MCP tools
        try:
            from src.mcp.tools import registry as _spark_registry
            tools.update(t.name for t in _spark_registry._tools.values())
        except Exception:
            logger.debug("Graceful degradation in Exception")  # nosec B110

        return sorted(tools)

    def get_tool_info(self, tool_name: str) -> Optional[Dict[str, Any]]:
        """Return metadata about a specific tool."""
        # Check direct tools
        desc = self._direct_tools.get(tool_name)
        if desc:
            return {
                "name": desc.name,
                "source": desc.source,
                "is_async": desc.is_async,
                "capability_tags": sorted(desc.capability_tags),
                "description": desc.description,
            }

        # Check MCP tools
        try:
            from src.mcp.tools import registry as _spark_registry
            tool = _spark_registry.get(tool_name)
            if tool:
                return {
                    "name": tool.name,
                    "source": "mcp",
                    "is_async": asyncio.iscoroutinefunction(tool.handler),
                    "capability_tags": [],
                    "description": tool.description,
                    "category": tool.category,
                    "version": tool.version,
                }
        except Exception:
            logger.debug("Graceful degradation in Exception")  # nosec B110

        return None

    # -------------------------------------------------------------------
    # Invocation history
    # -------------------------------------------------------------------

    def get_invocation_history(self, tool_name: Optional[str] = None, limit: int = 50) -> List[ToolResult]:
        """
        Return recent invocation history, optionally filtered by tool name.
        Returns the most recent invocations first.
        """
        results = self._invocation_history
        if tool_name:
            results = [r for r in results if r.tool_name == tool_name]
        return list(reversed(results[-limit:]))

    def get_metrics(self) -> Dict[str, Any]:
        """Return aggregate metrics about tool invocations."""
        if not self._invocation_history:
            return {
                "total_invocations": 0,
                "successful": 0,
                "failed": 0,
                "avg_duration_ms": 0.0,
                "tools_used": [],
            }

        successful = sum(1 for r in self._invocation_history if r.success)
        failed = len(self._invocation_history) - successful
        avg_duration = sum(r.duration_ms for r in self._invocation_history) / len(self._invocation_history)
        tools_used = sorted(set(r.tool_name for r in self._invocation_history))

        return {
            "total_invocations": len(self._invocation_history),
            "successful": successful,
            "failed": failed,
            "avg_duration_ms": round(avg_duration, 2),
            "tools_used": tools_used,
        }

    # -------------------------------------------------------------------
    # Internal: tool resolution
    # -------------------------------------------------------------------

    def _resolve_mcp_tool(self, tool_name: str) -> Optional[_ToolDescriptor]:
        """Resolve a tool from The Spark's MCP registry."""
        try:
            from src.mcp.tools import registry as _spark_registry
            tool = _spark_registry.get(tool_name)
            if tool is not None:
                return _ToolDescriptor(
                    name=tool.name,
                    handler=tool.handler,
                    is_async=asyncio.iscoroutinefunction(tool.handler),
                    source="mcp",
                    description=tool.description,
                )
        except Exception:
            logger.debug("Graceful degradation in Exception")  # nosec B110
        return None

    def _resolve_workflow_tool(self, tool_name: str) -> Optional[_ToolDescriptor]:
        """Resolve a tool from the Digital Grid's workflow registry."""
        try:
            from src.workflow.nodes import _SPARK_TOOL_REGISTRY
            handler = _SPARK_TOOL_REGISTRY.get(tool_name)
            if handler is not None:
                return _ToolDescriptor(
                    name=tool_name,
                    handler=handler,
                    is_async=asyncio.iscoroutinefunction(handler),
                    source="workflow",
                )
        except Exception:
            logger.debug("Graceful degradation in Exception")  # nosec B110
        return None

    def _record_invocation(self, result: ToolResult) -> None:
        """Record an invocation result and enforce history size limit."""
        self._invocation_history.append(result)
        while len(self._invocation_history) > self._max_history:
            self._invocation_history.pop(0)
