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


def safe_eval(expr: str, context: Dict[str, Any]) -> Any:
    """
    Safely evaluate a Python expression string using an AST traversal.
    Supports basic literals, dicts, lists, tuples, attribute access,
    subscripting, basic binary/unary operators, comparisons, and safe calls.
    """
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Invalid syntax in expression: {exc}") from exc

    safe_builtins = {
        "True": True,
        "False": False,
        "None": None,
        "dict": dict,
        "list": list,
        "set": set,
        "str": str,
        "int": int,
        "float": float,
        "len": len,
        "max": max,
        "min": min,
        "sum": sum,
        "abs": abs,
        "bool": bool,
    }

    def _eval(node: ast.AST) -> Any:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant):
            return node.value
        elif isinstance(node, ast.Name):
            if node.id in context:
                return context[node.id]
            if node.id in safe_builtins:
                return safe_builtins[node.id]
            raise NameError(f"name '{node.id}' is not defined")
        elif isinstance(node, ast.Dict):
            return {
                _eval(k): _eval(v)
                for k, v in zip(node.keys, node.values, strict=False)
                if k is not None
            }
        elif isinstance(node, ast.List):
            return [_eval(elt) for elt in node.elts]
        elif isinstance(node, ast.Tuple):
            return tuple(_eval(elt) for elt in node.elts)
        elif isinstance(node, ast.Set):
            return {_eval(elt) for elt in node.elts}
        elif isinstance(node, ast.Subscript):
            value = _eval(node.value)
            if isinstance(node.slice, ast.Slice):
                lower = _eval(node.slice.lower) if node.slice.lower else None
                upper = _eval(node.slice.upper) if node.slice.upper else None
                step = _eval(node.slice.step) if node.slice.step else None
                return value[slice(lower, upper, step)]
            else:
                return value[_eval(node.slice)]
        elif isinstance(node, ast.Attribute):
            value = _eval(node.value)
            if node.attr.startswith("_"):
                raise AttributeError(f"Access to private attribute '{node.attr}' is not allowed")
            return getattr(value, node.attr)
        elif isinstance(node, ast.Call):
            func = _eval(node.func)
            args = [_eval(arg) for arg in node.args]
            kwargs = {kw.arg: _eval(kw.value) for kw in node.keywords if kw.arg}
            return func(*args, **kwargs)
        elif isinstance(node, ast.Compare):
            left = _eval(node.left)
            for op, comparator in zip(node.ops, node.comparators, strict=False):
                right = _eval(comparator)
                if isinstance(op, ast.Eq):
                    if not (left == right):
                        return False
                elif isinstance(op, ast.NotEq):
                    if not (left != right):
                        return False
                elif isinstance(op, ast.Lt):
                    if not (left < right):
                        return False
                elif isinstance(op, ast.LtE):
                    if not (left <= right):
                        return False
                elif isinstance(op, ast.Gt):
                    if not (left > right):
                        return False
                elif isinstance(op, ast.GtE):
                    if not (left >= right):
                        return False
                elif isinstance(op, ast.In):
                    if left not in right:
                        return False
                elif isinstance(op, ast.NotIn):
                    if not (left not in right):
                        return False
                elif isinstance(op, ast.Is):
                    if left is not right:
                        return False
                elif isinstance(op, ast.IsNot):
                    if not (left is not right):
                        return False
                else:
                    raise ValueError(f"Unsupported comparison operator: {type(op)}")
                left = right
            return True
        elif isinstance(node, ast.BinOp):
            left = _eval(node.left)
            right = _eval(node.right)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.FloorDiv):
                return left // right
            if isinstance(node.op, ast.Mod):
                return left % right
            if isinstance(node.op, ast.Pow):
                return left**right
            if isinstance(node.op, ast.BitAnd):
                return left & right
            if isinstance(node.op, ast.BitOr):
                return left | right
            if isinstance(node.op, ast.BitXor):
                return left ^ right
            raise ValueError(f"Unsupported binary operator: {type(node.op)}")
        elif isinstance(node, ast.UnaryOp):
            operand = _eval(node.operand)
            if isinstance(node.op, ast.UAdd):
                return +operand
            if isinstance(node.op, ast.USub):
                return -operand
            if isinstance(node.op, ast.Not):
                return not operand
            if isinstance(node.op, ast.Invert):
                return ~operand
            raise ValueError(f"Unsupported unary operator: {type(node.op)}")
        elif isinstance(node, ast.BoolOp):
            if isinstance(node.op, ast.And):
                for val in node.values:
                    res = _eval(val)
                    if not res:
                        return res
                return res
            elif isinstance(node.op, ast.Or):
                for val in node.values:
                    res = _eval(val)
                    if res:
                        return res
                return res
            raise ValueError(f"Unsupported boolean operator: {type(node.op)}")
        elif isinstance(node, ast.IfExp):
            test = _eval(node.test)
            return _eval(node.body) if test else _eval(node.orelse)
        else:
            raise ValueError(f"Unsupported AST node type: {type(node).__name__}")

    return _eval(tree)
