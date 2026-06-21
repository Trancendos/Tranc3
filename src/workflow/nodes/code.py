"""
src/workflow/nodes/code.py — Python sandbox execution node for The Digital Grid.
"""

from __future__ import annotations

import io
import sys
import time
from typing import Any, Dict

from Dimensional.error_handlers import safe_error_detail

from .base import BaseNode, NodeResult


class CodeExecNode(BaseNode):
    """Executes Python code in a restricted sandbox, capturing stdout."""

    _SAFE_BUILTINS = {
        # Intentionally excludes: setattr, getattr, input, exec, eval, open,
        # __import__, compile, vars, dir, id, object, super, type, property
        # — these are sandbox escape vectors.
        "abs",
        "all",
        "any",
        "bin",
        "bool",
        "bytearray",
        "bytes",
        "callable",
        "chr",
        "complex",
        "dict",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "hash",
        "hex",
        "int",
        "isinstance",
        "issubclass",
        "iter",
        "len",
        "list",
        "map",
        "max",
        "min",
        "next",
        "oct",
        "ord",
        "pow",
        "print",
        "range",
        "repr",
        "reversed",
        "round",
        "set",
        "slice",
        "sorted",
        "str",
        "sum",
        "tuple",
        "zip",
        "True",
        "False",
        "None",
    }

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        code = self.config.config.get("code", "")
        if not code:
            code = inputs.get("code", "")

        local_ns: Dict[str, Any] = dict(inputs)
        local_ns["inputs"] = inputs
        local_ns["context"] = context
        local_ns["result"] = None

        _b: Any = __builtins__
        if isinstance(_b, dict):
            _safe_builtins: Dict[str, Any] = {
                k: v for k, v in _b.items() if k in self._SAFE_BUILTINS
            }
        else:
            _safe_builtins = {k: getattr(_b, k) for k in self._SAFE_BUILTINS if hasattr(_b, k)}
        safe_globals: Dict[str, Any] = {
            "__builtins__": _safe_builtins,
            "math": __import__("math"),
            "json": __import__("json"),
            "re": __import__("re"),
            "datetime": __import__("datetime"),
        }

        stdout_capture = io.StringIO()
        original_stdout = sys.stdout

        async def _exec() -> Dict[str, Any]:
            sys.stdout = stdout_capture
            try:
                exec(compile(code, "<workflow_node>", "exec"), safe_globals, local_ns)  # noqa: S102  # nosec B102
            finally:
                sys.stdout = original_stdout
            return {
                "result": local_ns.get("result"),
                "stdout": stdout_capture.getvalue(),
            }

        try:
            output = await self._retry(
                lambda: self._with_timeout(_exec(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(output, duration_ms)
        except Exception as exc:
            sys.stdout = original_stdout
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                {"stdout": stdout_capture.getvalue()},
                duration_ms,
                success=False,
                error=safe_error_detail(exc, 500),
            )


__all__ = ["CodeExecNode"]
