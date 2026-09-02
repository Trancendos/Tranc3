"""
src/workflow/nodes/base.py — Core types for The Digital Grid workflow nodes.

Defines NodeType, NodeConfig, NodeResult, BaseNode ABC, and the _deep_get helper.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import operator
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


# Ceilings for expression evaluation. The Digital Grid evaluates workflow
# expressions that reach it as untrusted JSON via POST /grid/workflows, so a
# single expression must not be able to exhaust the executor's memory.
_MAX_SEQ_LEN = 1_000_000
_MAX_INT_BITS = 100_000
# A literal is bounded by the size of the expression that spells it out, so
# the result ceilings alone do not stop a caller posting one enormous literal.
_MAX_EXPR_CHARS = 100_000


def _guard_size(value: Any) -> Any:
    """Reject a value already too large to be a legitimate workflow result."""
    if isinstance(value, (str, bytes, list, tuple, set, dict)) and len(value) > _MAX_SEQ_LEN:
        raise ValueError("Expression result exceeds the maximum allowed size")
    if isinstance(value, int) and not isinstance(value, bool):
        if value.bit_length() > _MAX_INT_BITS:
            raise ValueError("Expression result exceeds the maximum allowed size")
    return value


def _guard_repeat(length: int, count: int) -> None:
    """Reject a sequence repetition *before* it allocates."""
    if count > 0 and length * count > _MAX_SEQ_LEN:
        raise ValueError("Expression result exceeds the maximum allowed size")


# Methods on otherwise-safe builtin types that run their own attribute
# traversal internally, outside this evaluator's checks. str.format's mini
# language performs unrestricted getattr/getitem, so "{0.__class__}".format(x)
# reaches straight past the dunder-attribute rule below and reads private
# state off any object in scope. Blocking the names is the only reliable
# defence: the traversal happens inside CPython, not in the AST we walk.
# Methods that mutate their receiver. `inputs` and `context` enter the
# namespace by reference, so "context.clear()" wiped the running workflow's
# execution_id and workflow_id, and "inputs.pop(k)" removed data before
# downstream nodes saw it. An expression evaluator has no business changing
# its operands, so these are refused on any receiver — which also covers
# nested mutation like inputs['rows'].clear(), where copying the namespace
# would not.
_MUTATING_METHODS = frozenset(
    {
        "append",
        "extend",
        "insert",
        "remove",
        "pop",
        "clear",
        "sort",
        "reverse",
        "add",
        "discard",
        "update",
        "setdefault",
        "popitem",
        "difference_update",
        "intersection_update",
        "symmetric_difference_update",
    }
)

_DENIED_METHODS = frozenset({"format", "format_map"}) | _MUTATING_METHODS

# Builtins an expression may name and call. Name resolution consults this map
# and the call allowlist is derived from it, so the two cannot drift. Without
# the name-resolution half the allowlist is unreachable: the evaluator's
# namespace is built from workflow inputs alone, so "len(x)" failed with
# "Unknown variable: len" no matter what the call allowlist permitted.
_SAFE_BUILTINS: Dict[str, Any] = {
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "set": set,
    "max": max,
    "min": min,
    "abs": abs,
    "sum": sum,
    "round": round,
    "sorted": sorted,
    "any": any,
    "all": all,
}


# Operator tables. Keeping these out of the evaluator keeps _eval a dispatch
# over node types rather than a single function carrying every operator's
# branch as well.
_UNARY_OPS: Dict[type, Any] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
    ast.Not: operator.not_,
    ast.Invert: operator.invert,
}

_COMPARE_OPS: Dict[type, Any] = {
    ast.Eq: operator.eq,
    ast.NotEq: operator.ne,
    ast.Lt: operator.lt,
    ast.LtE: operator.le,
    ast.Gt: operator.gt,
    ast.GtE: operator.ge,
    ast.In: lambda a, b: a in b,
    ast.NotIn: lambda a, b: a not in b,
}


def _apply_binop(op: ast.operator, left: Any, right: Any) -> Any:
    """Apply a binary operator, enforcing the size ceilings as it goes."""
    if isinstance(op, ast.Add):
        return _guard_size(left + right)
    if isinstance(op, ast.Sub):
        return left - right
    if isinstance(op, ast.Mult):
        # Bound the *result*, not the operand. Guarding only the right-hand
        # operand ("repeat count <= 1000") is bypassed by chaining, because
        # each step's count stays under the limit while the sequence itself
        # keeps growing: 'a'*1000*1000*100 passes three such checks and
        # allocates 100 MB.
        if isinstance(left, (str, bytes, list, tuple)) and isinstance(right, int):
            _guard_repeat(len(left), right)
        if isinstance(right, (str, bytes, list, tuple)) and isinstance(left, int):
            _guard_repeat(len(right), left)
        return _guard_size(left * right)
    if isinstance(op, ast.Div):
        return left / right
    if isinstance(op, ast.Mod):
        return left % right
    if isinstance(op, ast.Pow):
        if (isinstance(left, (int, float)) and left > 1000) or (
            isinstance(right, (int, float)) and right > 1000
        ):
            raise ValueError("Power operation limit exceeded")
        return _guard_size(left**right)
    if isinstance(op, ast.FloorDiv):
        return left // right
    raise ValueError(f"Unsupported binary operator: {type(op)}")


def _check_callable(func: Any) -> None:
    """Refuse a callable the evaluator must not invoke."""
    fname = getattr(func, "__name__", "")
    if fname in _MUTATING_METHODS:
        raise ValueError(f"Call to '{fname}' is denied: it mutates its receiver")
    if fname in _DENIED_METHODS:
        raise ValueError(
            f"Call to '{fname}' is denied: it performs its own unrestricted attribute access"
        )
    receiver = getattr(func, "__self__", None)
    if receiver is not None:
        # A bound method. Allow it only on the ordinary data types a workflow
        # carries, or on the builtins module.
        safe_types = (str, dict, list, set, int, float, bool, tuple)
        if not isinstance(receiver, safe_types) and getattr(receiver, "__name__", "") != "builtins":
            raise ValueError("Method call on non-standard type is denied")
    elif func not in set(_SAFE_BUILTINS.values()):
        raise ValueError("Function call is denied")


def _safe_eval(expr: str, local_ns: Dict[str, Any]) -> Any:
    """Evaluate a workflow expression under an allowlist of AST node types.

    Only literals, collections, arithmetic, comparison, boolean logic,
    subscripting, public attribute access and a fixed set of builtins are
    permitted. Anything else raises ValueError rather than being evaluated.
    """
    if len(expr) > _MAX_EXPR_CHARS:
        raise ValueError("Expression exceeds the maximum allowed length")
    tree = ast.parse(expr, mode="eval")

    def _eval_name(node: ast.Name) -> Any:
        """Resolve a bare name from the caller namespace, then the safe builtins."""
        if node.id in local_ns:
            return local_ns[node.id]
        if node.id == "True":
            return True
        if node.id == "False":
            return False
        if node.id == "None":
            return None
        if node.id in _SAFE_BUILTINS:
            return _SAFE_BUILTINS[node.id]
        raise ValueError(f"Unknown variable: {node.id}")

    def _eval_dict(node: ast.Dict) -> Dict[Any, Any]:
        """Build a dict literal, merging any `**mapping` entries."""
        # A None key is `**mapping`. Skipping those silently returned an
        # incomplete dict — "{**data}" evaluated to {} — so a TransformNode
        # merging inputs produced empty output and reported success. The
        # entries are merged instead, and a non-mapping operand is refused
        # rather than dropped.
        out: Dict[Any, Any] = {}
        for k, v in zip(node.keys, node.values, strict=False):
            if k is None:
                spread = _eval(v)
                if not isinstance(spread, dict):
                    raise ValueError("Only a mapping can be unpacked with '**'")
                out.update(spread)
            else:
                out[_eval(k)] = _eval(v)
        return _guard_size(out)

    def _eval_boolop(node: ast.BoolOp) -> Any:
        """Evaluate and/or with short-circuiting, returning the deciding operand."""
        # all()/any() collapse the result to a bool. Python returns the
        # operand that decided the expression, and workflow transforms lean
        # on that: "data.get('name') or 'unknown'" is meant to yield the
        # name or the fallback, and returned True for both instead —
        # a silently wrong value rather than an error.
        if not isinstance(node.op, (ast.And, ast.Or)):
            raise ValueError(f"Unsupported boolean operator: {type(node.op)}")
        is_and = isinstance(node.op, ast.And)
        result = _eval(node.values[0])
        for operand in node.values[1:]:
            # Short-circuit, so the remaining operands are never evaluated.
            if is_and and not result:
                return result
            if not is_and and result:
                return result
            result = _eval(operand)
        return result

    def _eval_call(node: ast.Call) -> Any:
        """Invoke a permitted callable, merging any `**kwargs` entries."""
        func = _eval(node.func)
        if not callable(func):
            raise ValueError(f"Unsupported function call: {ast.dump(node)}")
        _check_callable(func)
        args = [_eval(arg) for arg in node.args]
        # kw.arg is None for `**kwargs`. Filtering those out called the
        # function with the arguments silently missing; they are merged.
        kwargs: Dict[str, Any] = {}

        def _bind(name: str, value: Any) -> None:
            # Python raises TypeError for "f(z=1, **{'z': 2})" rather than
            # letting one win. A plain dict.update() silently kept the last
            # value, which is a different answer from the one the same
            # expression gives outside the evaluator.
            if name in kwargs:
                raise ValueError(f"Got multiple values for keyword argument '{name}'")
            kwargs[name] = value

        for kw in node.keywords:
            if kw.arg is None:
                spread = _eval(kw.value)
                if not isinstance(spread, dict):
                    raise ValueError("Only a mapping can be unpacked with '**'")
                for key, value in spread.items():
                    _bind(key, value)
            else:
                _bind(kw.arg, _eval(kw.value))
        # A permitted builtin can still return more than the ceiling allows —
        # list(s) over a long string, or dict(**big) — so the result is bounded
        # like every other value the evaluator produces.
        return _guard_size(func(*args, **kwargs))

    def _eval_attribute(node: ast.Attribute) -> Any:
        """Read a public attribute; private and dunder names are refused."""
        val = _eval(node.value)
        # Avoid private/dunder attribute access
        if node.attr.startswith("_"):
            raise ValueError(f"Access to private attribute '{node.attr}' is denied")
        if not hasattr(val, node.attr):
            raise ValueError(f"Attribute '{node.attr}' not found")
        return getattr(val, node.attr)

    def _eval_compare(node: ast.Compare) -> Any:
        """Apply a single comparison operator; chained comparisons are refused."""
        if len(node.ops) != 1 or len(node.comparators) != 1:
            raise ValueError("Multiple comparisons not supported")
        op = node.ops[0]
        handler = _COMPARE_OPS.get(type(op))
        if handler is None:
            raise ValueError(f"Unsupported comparison operator: {type(op)}")
        return handler(_eval(node.left), _eval(node.comparators[0]))

    def _eval_subscript(node: ast.Subscript) -> Any:
        """Index into a value, across the Index-node shapes Python has used."""
        value = _eval(node.value)
        if isinstance(node.slice, getattr(ast, "Index", type(None))):
            slice_val = _eval(node.slice.value)  # type: ignore[attr-defined]
        else:
            slice_val = _eval(node.slice)
        return value[slice_val]

    def _eval(node: ast.AST) -> Any:
        """Dispatch one AST node to its handler, refusing any type not listed."""
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant):
            return _guard_size(node.value)
        if isinstance(node, ast.List):
            return _guard_size([_eval(elt) for elt in node.elts])
        if isinstance(node, ast.Tuple):
            return _guard_size(tuple(_eval(elt) for elt in node.elts))
        if isinstance(node, ast.Dict):
            return _eval_dict(node)
        if isinstance(node, ast.Name):
            return _eval_name(node)
        if isinstance(node, ast.UnaryOp):
            handler = _UNARY_OPS.get(type(node.op))
            if handler is None:
                raise ValueError(f"Unsupported unary operator: {type(node.op)}")
            return handler(_eval(node.operand))
        if isinstance(node, ast.BinOp):
            return _apply_binop(node.op, _eval(node.left), _eval(node.right))
        if isinstance(node, ast.Compare):
            return _eval_compare(node)
        if isinstance(node, ast.BoolOp):
            return _eval_boolop(node)
        if isinstance(node, ast.Subscript):
            return _eval_subscript(node)
        if isinstance(node, ast.Attribute):
            return _eval_attribute(node)
        if isinstance(node, ast.Call):
            return _eval_call(node)
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
