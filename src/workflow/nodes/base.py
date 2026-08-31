"""
src/workflow/nodes/base.py — Core types for The Digital Grid workflow nodes.

Defines NodeType, NodeConfig, NodeResult, BaseNode ABC, and the _deep_get helper.
"""

from __future__ import annotations

import ast
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




def _safe_eval(expr: str, local_ns: Dict[str, Any]) -> Any:
    """Safely evaluates mathematical and logical expressions, supporting basic literals, unary ops, attributes and limited calls."""
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.List):
            return [_eval(elt) for elt in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(_eval(elt) for elt in node.elts)
        elif isinstance(node, ast.Dict):
            return {_eval(k): _eval(v) for k, v in zip(node.keys, node.values, strict=False) if k is not None}
        elif isinstance(node, ast.Name):
            if node.id in local_ns:
                return local_ns[node.id]
            if node.id == "True":
                return True
            if node.id == "False":
                return False
            if node.id == "None":
                return None
            raise ValueError(f"Unknown variable: {node.id}")
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.USub):
                return -operand
            elif isinstance(node.op, ast.UAdd):
                return +operand
            elif isinstance(node.op, ast.Not):
                return not operand
            elif isinstance(node.op, ast.Invert):
                return ~operand
            raise ValueError(f"Unsupported unary operator: {type(node.op)}")
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            elif isinstance(node.op, ast.Sub):
                return left - right
            elif isinstance(node.op, ast.Mult):
                if isinstance(left, str) and isinstance(right, int) and right > 1000:
                    raise ValueError("String multiplication limit exceeded")
                return left * right
            elif isinstance(node.op, ast.Div):
                return left / right
            elif isinstance(node.op, ast.Mod):
                return left % right
            elif isinstance(node.op, ast.Pow):
                if (isinstance(left, (int, float)) and left > 1000) or (
                    isinstance(right, (int, float)) and right > 1000
                ):
                    raise ValueError("Power operation limit exceeded")
                return left**right
            elif isinstance(node.op, ast.FloorDiv):
                return left // right
            raise ValueError(f"Unsupported binary operator: {type(node.op)}")
        elif isinstance(node, ast.Compare):
            left = _eval(node.left)
            if len(node.ops) != 1 or len(node.comparators) != 1:
                raise ValueError("Multiple comparisons not supported")
            op = node.ops[0]
            right = _eval(node.comparators[0])
            if isinstance(op, ast.Eq):
                return left == right
            elif isinstance(op, ast.NotEq):
                return left != right
            elif isinstance(op, ast.Lt):
                return left < right
            elif isinstance(op, ast.LtE):
                return left <= right
            elif isinstance(op, ast.Gt):
                return left > right
            elif isinstance(op, ast.GtE):
                return left >= right
            elif isinstance(op, ast.In):
                return left in right
            elif isinstance(op, ast.NotIn):
                return left not in right
            raise ValueError(f"Unsupported comparison operator: {type(op)}")
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                return all(_eval(v) for v in node.values)
            elif isinstance(node.op, ast.Or):
                return any(_eval(v) for v in node.values)
            raise ValueError(f"Unsupported boolean operator: {type(node.op)}")
        elif isinstance(node, ast.Subscript):
            value = _eval(node.value)
            if isinstance(node.slice, getattr(ast, "Index", type(None))):
                slice_val = _eval(node.slice.value)  # type: ignore
            else:
                slice_val = _eval(node.slice)
            return value[slice_val]
        elif isinstance(node, ast.Attribute):
            val = _eval(node.value)
            # Avoid private/dunder attribute access
            if node.attr.startswith("_"):
                raise ValueError(f"Access to private attribute '{node.attr}' is denied")
            if not hasattr(val, node.attr):
                raise ValueError(f"Attribute '{node.attr}' not found")
            return getattr(val, node.attr)
        elif isinstance(node, ast.Call):
            func = _eval(node.func)
            # Protect against built-in dangerous functions if they somehow slip through
            # Only allow calling methods of standard objects or specific whitelisted functions.
            # E.g. strings, dicts, ints, etc. We can check if it's a built-in method or safe callable.
            if callable(func):
                # Extra safety: limit calls to specific types
                safe_types = (str, dict, list, set, int, float, bool, tuple)
                if getattr(func, "__self__", None) is not None:
                    if not isinstance(func.__self__, safe_types):
                        raise ValueError("Method call on non-standard type is denied")
                elif func not in {len, str, int, float, bool, list, dict, set, max, min, abs, sum}:
                    raise ValueError("Function call is denied")

                args = [_eval(arg) for arg in node.args]
                # kwargs are skipped for simplicity unless really needed, let's just support basic args
                return func(*args)
            raise ValueError(f"Unsupported function call: {ast.dump(node)}")
        else:
            raise ValueError(f"Unsupported node type: {type(node)}")

    return _eval(tree)


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
    "_safe_eval",
]
