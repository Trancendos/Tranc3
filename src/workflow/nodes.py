# All node types for the workflow DAG
import asyncio
import io
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Type

import httpx

from Dimensional.error_handlers import safe_error_detail

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node type enum
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Abstract base node
# ---------------------------------------------------------------------------


class BaseNode:
    """Abstract base for all workflow nodes."""

    def __init__(self, config: NodeConfig) -> None:
        self.config = config
        self.logger = logging.getLogger(f"{__name__}.{config.type}.{config.id}")

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:  # noqa: E501
        raise NotImplementedError(f"{self.__class__.__name__} must implement execute()")

    async def _with_timeout(self, coro, timeout: float):
        """Wrap a coroutine with asyncio.timeout (Python 3.11+) or wait_for."""
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        except asyncio.TimeoutError:
            raise TimeoutError(f"Node '{self.config.id}' timed out after {timeout}s") from None
        return None

    async def _retry(self, coro_factory: Callable, retries: int):
        """Execute coro_factory() up to `retries` times with exponential backoff."""
        last_exc: Optional[Exception] = None
        for attempt in range(max(retries, 1)):
            try:
                return await coro_factory()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt < retries - 1:
                    wait = 2**attempt
                    self.logger.warning(
                        "Attempt %d failed (%s); retrying in %ss",
                        attempt + 1,
                        exc,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    self.logger.error("All %d attempts failed: %s", retries, exc)
        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f"All {retries} attempts failed with unknown error")
        return None

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


# ---------------------------------------------------------------------------
# LLM Node — uses local TRANC3 inference engine (no external API)
# ---------------------------------------------------------------------------


class LLMNode(BaseNode):
    """Generates text using the local TRANC3 model. No external API required."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config

        personality = cfg.get("personality", "tranc3-base")
        system_prompt = cfg.get("system_prompt", "")
        max_tokens = int(cfg.get("max_tokens", 512))
        temperature = float(cfg.get("temperature", 0.8))

        # Build user message from inputs or config
        user_message = cfg.get("prompt", "")
        if not user_message:
            user_message = str(next(iter(inputs.values()), "")) if inputs else ""

        # Template substitution
        for k, v in inputs.items():
            user_message = user_message.replace(f"{{{{{k}}}}}", str(v))

        try:
            from src.core.tranc3_inference import (
                get_engine,  # noqa: F401  # intentional top-level import
            )

            engine = get_engine()
            gen = await engine.generate(
                prompt=user_message,
                personality=personality,
                system_prompt=system_prompt or None,
                max_new_tokens=max_tokens,
                temperature=temperature,
            )
            result_text = gen.get("response", "")
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                result_text,
                duration_ms,
                metadata={
                    "model": gen.get("model", "tranc3-local"),
                    "personality": personality,
                    "tokens": gen.get("tokens", 0),
                    "trained": gen.get("trained", True),
                },
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


# ---------------------------------------------------------------------------
# Code Execution Node — restricted Python sandbox
# ---------------------------------------------------------------------------


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

        # Merge inputs into execution locals.
        # Also expose the raw 'inputs' dict so code can call inputs.get(...)
        local_ns: Dict[str, Any] = dict(inputs)
        local_ns["inputs"] = inputs
        local_ns["context"] = context
        local_ns["result"] = None

        safe_globals: Dict[str, Any] = {
            "__builtins__": {
                k: v
                for k, v in __builtins__.items()  # type: ignore[union-attr]
                if k in self._SAFE_BUILTINS
            }
            if isinstance(__builtins__, dict)
            else {
                k: getattr(__builtins__, k) for k in self._SAFE_BUILTINS if hasattr(__builtins__, k)
            },
            "math": __import__("math"),
            "json": __import__("json"),
            "re": __import__("re"),
            "datetime": __import__("datetime"),
        }

        stdout_capture = io.StringIO()
        original_stdout = sys.stdout

        async def _exec() -> Dict[str, Any]:
            nonlocal local_ns
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
        return None


# ---------------------------------------------------------------------------
# HTTP Node — generic HTTP request
# ---------------------------------------------------------------------------


class HTTPNode(BaseNode):
    """Makes HTTP requests (GET/POST/PUT) and returns parsed JSON or text."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        method = cfg.get("method", "GET").upper()
        url = cfg.get("url", inputs.get("url", ""))
        headers = {**cfg.get("headers", {}), **inputs.get("headers", {})}
        params = {**cfg.get("params", {}), **inputs.get("params", {})}
        body = inputs.get("body", cfg.get("body"))
        timeout = self.config.timeout_sec

        async def _request() -> Any:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method == "GET":
                    resp = await client.get(url, headers=headers, params=params)
                elif method == "POST":
                    resp = await client.post(url, headers=headers, params=params, json=body)
                elif method == "PUT":
                    resp = await client.put(url, headers=headers, params=params, json=body)
                elif method == "DELETE":
                    resp = await client.delete(url, headers=headers, params=params)
                elif method == "PATCH":
                    resp = await client.patch(url, headers=headers, params=params, json=body)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "application/json" in content_type:
                    return {"status_code": resp.status_code, "body": resp.json()}
                return {"status_code": resp.status_code, "body": resp.text}
            return None

        try:
            output = await self._retry(
                lambda: self._with_timeout(_request(), timeout),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(output, duration_ms, metadata={"method": method, "url": url})
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


# ---------------------------------------------------------------------------
# Condition Node — evaluates Python expression, routes true/false
# ---------------------------------------------------------------------------


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
        return None


# ---------------------------------------------------------------------------
# Transform Node — dict/path-based data transformation
# ---------------------------------------------------------------------------


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


class TransformNode(BaseNode):
    """Transforms data using a mapping spec (dot-path extraction or simple template)."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        mapping: Dict[str, str] = cfg.get("mapping", {})
        # mapping: output_key -> dot-path into inputs
        # e.g. {"title": "document.title", "items": "results.0"}
        output: Dict[str, Any] = {}

        if mapping:
            for out_key, src_path in mapping.items():
                output[out_key] = _deep_get(inputs, src_path)
        else:
            # No mapping — pass through all inputs
            output = dict(inputs)

        # Optional: apply a Python expression transform
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


# ---------------------------------------------------------------------------
# Vector Search Node — queries Qdrant
# ---------------------------------------------------------------------------


class VectorSearchNode(BaseNode):
    """Performs a nearest-neighbour search against a Qdrant collection."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        qdrant_url = cfg.get("qdrant_url") or os.environ.get("QDRANT_URL", "http://localhost:6333")
        collection = cfg.get("collection", inputs.get("collection", "default"))
        top_k = int(cfg.get("top_k", 5))
        vector = inputs.get("vector") or cfg.get("vector")
        score_threshold = cfg.get("score_threshold", 0.0)
        with_payload = cfg.get("with_payload", True)

        if not vector:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None,
                duration_ms,
                success=False,
                error="No query vector provided in inputs",
            )

        payload: Dict[str, Any] = {
            "vector": vector,
            "limit": top_k,
            "with_payload": with_payload,
            "score_threshold": score_threshold,
        }

        url = f"{qdrant_url.rstrip('/')}/collections/{collection}/points/search"

        async def _search() -> Any:
            async with httpx.AsyncClient(timeout=self.config.timeout_sec) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json().get("result", [])
            return None

        try:
            results = await self._retry(
                lambda: self._with_timeout(_search(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                {"results": results, "count": len(results)},
                duration_ms,
                metadata={"collection": collection, "top_k": top_k},
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


# ---------------------------------------------------------------------------
# MCP Tool Node — invokes a registered MCP tool
# ---------------------------------------------------------------------------

# The Digital Grid's local Spark tool registry: name -> async callable
# Takes precedence over The Spark's global registry for workflow-local overrides.
_SPARK_TOOL_REGISTRY: Dict[str, Callable] = {}


def register_spark_tool(name: str, fn: Callable) -> None:
    """Register a Spark tool callable for use in SparkToolNode within The Digital Grid."""
    _SPARK_TOOL_REGISTRY[name] = fn


class SparkToolNode(BaseNode):
    """A Digital Grid node that calls a registered Spark (MCP) tool by name."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        tool_name = self.config.config.get("tool_name", "")
        tool_args = {**self.config.config.get("args", {}), **inputs}

        if not tool_name:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None,
                duration_ms,
                success=False,
                error="No 'tool_name' specified in config",
            )

        fn = _SPARK_TOOL_REGISTRY.get(tool_name)
        # Spark registry handlers use fn(params: dict); workflow-local ones use fn(**kwargs).
        # Track which convention applies so we can call correctly below.
        _uses_kwargs = True

        # Fall back to The Spark's global tool registry (lazy import avoids circularity)
        if fn is None:
            try:
                from src.mcp.tools import registry as _spark_registry  # noqa: PLC0415

                spark_tool = _spark_registry.get(tool_name)
                if spark_tool is not None:
                    fn = spark_tool.handler
                    _uses_kwargs = False  # Spark handlers receive a single params dict
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


# ---------------------------------------------------------------------------
# Parallel Node — runs child node configs concurrently
# ---------------------------------------------------------------------------


class ParallelNode(BaseNode):
    """Runs a list of child NodeConfigs concurrently and merges their results."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
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


# ---------------------------------------------------------------------------
# Loop Node — iterates over a list, runs inner nodes per item
# ---------------------------------------------------------------------------


class LoopNode(BaseNode):
    """Iterates over inputs['items'], running inner node configs for each element."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
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
        loop_results: List[Any] = []

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
            return None

        tasks = [_run_item(item, idx) for idx, item in enumerate(items)]
        loop_results = await asyncio.gather(*tasks)

        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(
            {"loop_results": list(loop_results)},
            duration_ms,
            metadata={"item_count": len(items)},
        )


# ---------------------------------------------------------------------------
# Skill Call Node — looks up and executes a Tranc3 skill
# ---------------------------------------------------------------------------

# Global skill registry: name -> async callable
_SKILL_REGISTRY: Dict[str, Callable] = {}


def register_skill(name: str, fn: Callable) -> None:
    """Register a skill callable for use in SkillCallNode."""
    _SKILL_REGISTRY[name] = fn


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


# ---------------------------------------------------------------------------
# ML Predict Node — calls Tranc3 model inference endpoint
# ---------------------------------------------------------------------------


class MLPredictNode(BaseNode):
    """Calls the Tranc3 model inference endpoint for ML predictions."""

    _DEFAULT_ENDPOINT = "http://localhost:8080/predict"

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        endpoint = cfg.get("endpoint") or os.environ.get(
            "TRANC3_MODEL_ENDPOINT", self._DEFAULT_ENDPOINT
        )
        model_name = cfg.get("model_name", "tranc3-base")
        payload = {
            "model": model_name,
            "inputs": {**cfg.get("static_inputs", {}), **inputs},
        }
        headers = {"Content-Type": "application/json"}
        api_key = cfg.get("api_key") or os.environ.get("TRANC3_API_KEY", "")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async def _infer() -> Any:
            async with httpx.AsyncClient(timeout=self.config.timeout_sec) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                return resp.json()
            return None

        try:
            result = await self._retry(
                lambda: self._with_timeout(_infer(), self.config.timeout_sec),
                self.config.retry_count,
            )
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                result,
                duration_ms,
                metadata={"model_name": model_name, "endpoint": endpoint},
            )
        except Exception as exc:
            duration_ms = (time.monotonic() - t0) * 1000
            return self._make_result(
                None, duration_ms, success=False, error=safe_error_detail(exc, 500)
            )


# ---------------------------------------------------------------------------
# Merge Node — merges outputs from multiple upstream nodes
# ---------------------------------------------------------------------------


class MergeNode(BaseNode):
    """Merges all incoming inputs into a single dict output."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        strategy = self.config.config.get("strategy", "merge")  # merge | first | last
        if strategy == "first":
            output = next(iter(inputs.values()), {}) if inputs else {}
        elif strategy == "last":
            output = next(reversed(list(inputs.values())), {}) if inputs else {}
        else:
            # Deep merge all inputs
            output = {}
            for v in inputs.values():
                if isinstance(v, dict):
                    output.update(v)
                else:
                    output[f"input_{id(v)}"] = v
        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(output, duration_ms, metadata={"strategy": strategy})


# ---------------------------------------------------------------------------
# Output Node — terminal node that records final workflow output
# ---------------------------------------------------------------------------


class OutputNode(BaseNode):
    """Terminal node — collects and formats the final workflow output."""

    async def execute(self, inputs: Dict[str, Any], context: Dict[str, Any]) -> NodeResult:
        t0 = time.monotonic()
        cfg = self.config.config
        keys = cfg.get("keys")  # Optional list of keys to pick from inputs
        if keys:
            output = {k: inputs.get(k) for k in keys}
        else:
            output = dict(inputs)
        duration_ms = (time.monotonic() - t0) * 1000
        return self._make_result(output, duration_ms, metadata={"is_terminal": True})


# ---------------------------------------------------------------------------
# Trigger Node — entry-point that accepts external event data
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Node registry and factory
# ---------------------------------------------------------------------------

NODE_REGISTRY: Dict[NodeType, Type[BaseNode]] = {
    NodeType.LLM: LLMNode,
    NodeType.CODE_EXEC: CodeExecNode,
    NodeType.HTTP_REQUEST: HTTPNode,
    NodeType.CONDITION: ConditionNode,
    NodeType.TRANSFORM: TransformNode,
    NodeType.VECTOR_SEARCH: VectorSearchNode,
    NodeType.SPARK_TOOL: SparkToolNode,
    NodeType.PARALLEL: ParallelNode,
    NodeType.LOOP: LoopNode,
    NodeType.MERGE: MergeNode,
    NodeType.OUTPUT: OutputNode,
    NodeType.TRIGGER: TriggerNode,
    NodeType.SKILL_CALL: SkillCallNode,
    NodeType.ML_PREDICT: MLPredictNode,
}


def create_node(config: NodeConfig) -> BaseNode:
    """Factory: instantiate the correct BaseNode subclass for a given NodeConfig."""
    _ensure_phase4_nodes_loaded()
    node_class = NODE_REGISTRY.get(config.type)
    # Phase 4 fallback: look up by string type name for extended node types
    if node_class is None:
        node_class = _PHASE4_NODE_REGISTRY.get(config.type)
    if node_class is None:
        raise ValueError(
            f"Unknown node type: {config.type!r}. "
            f"Available types: {[t.value for t in NODE_REGISTRY] + list(_PHASE4_NODE_REGISTRY.keys())}"
        )
    return node_class(config)


# ---------------------------------------------------------------------------
# Phase 4 node registry extension (string-keyed, populated at import time)
# ---------------------------------------------------------------------------
_PHASE4_NODE_REGISTRY: Dict[str, Any] = {}
_PHASE4_LOADED = False


def _ensure_phase4_nodes_loaded() -> None:
    """Lazily populate _PHASE4_NODE_REGISTRY to avoid cyclic imports."""
    global _PHASE4_LOADED
    if _PHASE4_LOADED:
        return
    _PHASE4_LOADED = (
        True  # codeql[py/unused-global] – used as lazy-load guard in _ensure_phase4_nodes_loaded
    )
    try:
        from src.workflow.phase4_nodes import (
            PHASE4_NODE_TYPES as _p4_types,  # codeql[py/cyclic-import]
        )

        _PHASE4_NODE_REGISTRY.update(_p4_types)
        logger.info("Phase 4 workflow nodes loaded: %s", list(_p4_types.keys()))
    except Exception as _p4_exc:
        logger.warning("Phase 4 workflow nodes unavailable: %s", _p4_exc)
    try:
        from src.workflow.phase5_nodes import (
            PHASE5_NODE_TYPES as _p5_types,  # codeql[py/cyclic-import]
        )

        _PHASE4_NODE_REGISTRY.update(_p5_types)
        logger.info("Phase 5 workflow nodes loaded: %s", list(_p5_types.keys()))
    except Exception as _p5_exc:
        logger.warning("Phase 5 workflow nodes unavailable: %s", _p5_exc)
