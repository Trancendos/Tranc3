"""
src/workflow/nodes/base.py — Core types for The Digital Grid workflow nodes.

Defines NodeType, NodeConfig, NodeResult, BaseNode ABC, and the _deep_get helper.
"""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    LLM = "LLM"
    CODE_EXEC = "CODE_EXEC"
    HTTP_REQUEST = "HTTP_REQUEST"
    CONDITION = "CONDITION"
    TRANSFORM = "TRANSFORM"
    VECTOR_SEARCH = "VECTOR_SEARCH"
    SPARK_TOOL = "SPARK_TOOL"
    PARALLEL = "PARALLEL"
    LOOP = "LOOP"
    MERGE = "MERGE"
    OUTPUT = "OUTPUT"
    TRIGGER = "TRIGGER"
    SKILL_CALL = "SKILL_CALL"
    ML_PREDICT = "ML_PREDICT"


@dataclass
class NodeConfig:
    id: str
    type: NodeType
    name: str
    config: Dict[str, Any] = field(default_factory=dict)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    timeout_sec: float = 30.0
    retry_count: int = 3


@dataclass
class NodeResult:
    node_id: str
    success: bool
    output: Any
    error: Optional[str]
    duration_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseNode(ABC):
    """Abstract base for all workflow nodes."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.type}.{config.id}")

    @abstractmethod
    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        raise NotImplementedError

    async def _with_timeout(self, coro, timeout: float):
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Node '{self.config.id}' timed out after {timeout}s") from None

    async def _retry(self, coro_factory: Callable, retries: int):
        last_exc: Optional[Exception] = None
        for attempt in range(max(retries, 1)):
            try:
                return await coro_factory()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries - 1:
                    wait = 2**attempt
                    self.logger.warning(
                        "Attempt %d failed (%s); retrying in %ss", attempt + 1, exc, wait
                    )
                    await asyncio.sleep(wait)
                else:
                    self.logger.error("All %d attempts failed: %s", retries, exc)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"All {retries} attempts failed with unknown error")

    def _make_result(
        self,
        output: Any,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        metadata: Optional[Dict] = None,
    ) -> NodeResult:
        return NodeResult(
            node_id=self.config.id,
            success=success,
            output=output,
            error=error,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )


def _deep_get(obj: Any, path: str) -> Any:
    """Navigate nested dicts/lists using dot-notation path, e.g. 'a.b.0.c'."""
    if not path:
        return obj
    parts = path.split(".")
    current = obj
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return current


__all__ = [
    "NodeType",
    "NodeConfig",
    "NodeResult",
    "BaseNode",
    "_deep_get",
]
