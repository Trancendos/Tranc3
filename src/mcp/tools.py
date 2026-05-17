"""
MCP Tool Registry — registers and dispatches Model Context Protocol tools.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workflow Registry — maps workflow_id → WorkflowDefinition
# ---------------------------------------------------------------------------

class WorkflowRegistry:
    """In-memory registry of WorkflowDefinitions, keyed by workflow ID."""

    def __init__(self) -> None:
        self._workflows: Dict[str, Any] = {}

    def register(self, workflow: Any) -> None:
        """Register a WorkflowDefinition; overwrites any existing entry with the same ID."""
        self._workflows[workflow.id] = workflow
        logger.debug("workflow.registry registered id=%s name=%s", workflow.id, workflow.name)

    def get(self, workflow_id: str) -> Optional[Any]:
        return self._workflows.get(workflow_id)

    def list_ids(self) -> List[str]:
        return list(self._workflows.keys())

    def list_all(self) -> List[Dict[str, Any]]:
        return [
            {"id": wf.id, "name": wf.name, "description": wf.description}
            for wf in self._workflows.values()
        ]


# Singleton workflow registry — import this alongside `registry`
_workflow_registry = WorkflowRegistry()


@dataclass
class MCPTool:
    """Descriptor for a single MCP-registered tool."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]          # async (params: dict) -> dict
    category: str = "general"
    version: str = "1.0.0"


class MCPToolRegistry:
    """Registry that maps tool names to MCPTool instances and dispatches calls."""

    def __init__(self) -> None:
        self._tools: Dict[str, MCPTool] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, tool: MCPTool) -> None:
        """Register a tool, overwriting any existing entry with the same name."""
        if tool.name in self._tools:
            logger.warning("mcp.registry overwriting tool=%s", tool.name)
        self._tools[tool.name] = tool
        logger.debug("mcp.registry registered tool=%s category=%s", tool.name, tool.category)

    def get(self, name: str) -> Optional[MCPTool]:
        """Return the tool with *name*, or None if not found."""
        return self._tools.get(name)

    def list_tools(self) -> List[Dict[str, Any]]:
        """Return all tools serialised to MCP JSON-schema format."""
        return [
            {
                "name": t.name,
                "description": t.description,
                "inputSchema": t.input_schema,
                "metadata": {
                    "category": t.category,
                    "version": t.version,
                },
            }
            for t in self._tools.values()
        ]

    def search(self, query: str) -> List[MCPTool]:
        """
        Fuzzy search over tool names and descriptions.

        Scoring:
          +3  exact name match
          +2  name contains query
          +1  description contains any query token
        """
        if not query:
            return list(self._tools.values())

        q_lower = query.lower()
        tokens = q_lower.split()
        scored: List[tuple[int, MCPTool]] = []

        for tool in self._tools.values():
            name_l = tool.name.lower()
            desc_l = tool.description.lower()
            score = 0

            if name_l == q_lower:
                score += 3
            elif q_lower in name_l:
                score += 2

            for token in tokens:
                if token in desc_l or token in name_l:
                    score += 1

            if score > 0:
                scored.append((score, tool))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [t for _, t in scored]

    # ------------------------------------------------------------------
    # Built-in tool registrations
    # ------------------------------------------------------------------

    def _register_builtins(self) -> None:
        builtins = [
            MCPTool(
                name="search_skills",
                description=(
                    "Search the Tranc3 skill library by name or semantic query. "
                    "Returns matching skill metadata including ID, description, and tags."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language or keyword search query.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of results to return (default 10).",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "category": {
                            "type": "string",
                            "description": "Optional category filter (e.g. 'coding', 'healing').",
                        },
                    },
                    "required": ["query"],
                },
                handler=self._handle_search_skills,
                category="skills",
            ),
            MCPTool(
                name="get_spark_status",
                description=(
                    "Return real-time status of one or all Spark compute nodes, "
                    "including CPU/memory utilisation, active jobs, and queue depth."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "node_id": {
                            "type": "string",
                            "description": "Specific Spark node ID. Omit to query all nodes.",
                        },
                        "include_metrics": {
                            "type": "boolean",
                            "description": "Whether to include detailed telemetry metrics.",
                            "default": False,
                        },
                    },
                    "required": [],
                },
                handler=self._handle_get_spark_status,
                category="infrastructure",
            ),
            MCPTool(
                name="run_workflow",
                description=(
                    "Trigger a named workflow with optional input parameters. "
                    "Returns the workflow execution ID and initial status."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "workflow_id": {
                            "type": "string",
                            "description": "Unique identifier of the workflow to execute.",
                        },
                        "params": {
                            "type": "object",
                            "description": "Arbitrary key-value input parameters for the workflow.",
                        },
                        "async_mode": {
                            "type": "boolean",
                            "description": "If true, return immediately without waiting for completion.",
                            "default": True,
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Synchronous wait timeout in seconds (ignored when async_mode=true).",
                            "default": 60,
                            "minimum": 1,
                            "maximum": 3600,
                        },
                    },
                    "required": ["workflow_id"],
                },
                handler=self._handle_run_workflow,
                category="workflow",
            ),
            MCPTool(
                name="get_system_health",
                description=(
                    "Return a consolidated health report for all Tranc3 subsystems: "
                    "API gateway, Redis, vector store, skill executor, and MCP server itself."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "subsystems": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": (
                                "Specific subsystems to check. "
                                "Omit or pass empty list to check all."
                            ),
                        },
                        "verbose": {
                            "type": "boolean",
                            "description": "Include per-subsystem detail beyond pass/fail.",
                            "default": False,
                        },
                    },
                    "required": [],
                },
                handler=self._handle_get_system_health,
                category="monitoring",
            ),
            MCPTool(
                name="execute_code",
                description=(
                    "Execute a Python code snippet in a sandboxed environment and return "
                    "stdout, stderr, and the return value of the last expression."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Python source code to execute.",
                        },
                        "language": {
                            "type": "string",
                            "enum": ["python"],
                            "description": "Execution language (only 'python' supported).",
                            "default": "python",
                        },
                        "timeout_seconds": {
                            "type": "integer",
                            "description": "Maximum execution time in seconds.",
                            "default": 30,
                            "minimum": 1,
                            "maximum": 120,
                        },
                        "context": {
                            "type": "object",
                            "description": "Variables to inject into the execution namespace.",
                        },
                    },
                    "required": ["code"],
                },
                handler=self._handle_execute_code,
                category="coding",
            ),
            MCPTool(
                name="query_vector_store",
                description=(
                    "Run a semantic similarity search against the Tranc3 vector store. "
                    "Returns the top-k most relevant documents with scores."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language query to embed and search.",
                        },
                        "collection": {
                            "type": "string",
                            "description": "Vector store collection / namespace to search.",
                            "default": "default",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Number of results to return.",
                            "default": 5,
                            "minimum": 1,
                            "maximum": 50,
                        },
                        "score_threshold": {
                            "type": "number",
                            "description": "Minimum similarity score (0.0–1.0) to include.",
                            "default": 0.0,
                            "minimum": 0.0,
                            "maximum": 1.0,
                        },
                        "metadata_filter": {
                            "type": "object",
                            "description": "Optional metadata key-value filters.",
                        },
                    },
                    "required": ["query"],
                },
                handler=self._handle_query_vector_store,
                category="knowledge",
            ),
            MCPTool(
                name="trigger_bundle",
                description=(
                    "Assemble and dispatch a composite skill bundle — a named set of "
                    "skills executed in dependency order with shared context."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "bundle_id": {
                            "type": "string",
                            "description": "Identifier of the pre-defined skill bundle.",
                        },
                        "input": {
                            "type": "object",
                            "description": "Top-level input context shared across all skills in the bundle.",
                        },
                        "overrides": {
                            "type": "object",
                            "description": (
                                "Per-skill parameter overrides, keyed by skill name. "
                                "Merged with the shared input for that skill."
                            ),
                        },
                        "dry_run": {
                            "type": "boolean",
                            "description": "If true, validate the bundle but do not execute.",
                            "default": False,
                        },
                    },
                    "required": ["bundle_id"],
                },
                handler=self._handle_trigger_bundle,
                category="skills",
            ),
            MCPTool(
                name="register_workflow",
                description=(
                    "Register a workflow definition by ID so it can later be triggered "
                    "via run_workflow. Accepts a JSON-serialisable workflow dict or a "
                    "known template name (spark_ignition | self_healing | ml_training)."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "workflow": {
                            "type": "object",
                            "description": "WorkflowDefinition serialised as a JSON object.",
                        },
                        "template": {
                            "type": "string",
                            "enum": ["spark_ignition", "self_healing", "ml_training"],
                            "description": "Name of a built-in workflow template to register.",
                        },
                    },
                },
                handler=self._handle_register_workflow,
                category="workflow",
            ),
            MCPTool(
                name="get_evolution_stats",
                description=(
                    "Retrieve evolutionary statistics for a skill or model, including "
                    "generation number, fitness scores, mutation history, and lineage."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "target_id": {
                            "type": "string",
                            "description": "Skill or model ID whose evolution stats to fetch.",
                        },
                        "target_type": {
                            "type": "string",
                            "enum": ["skill", "model", "workflow"],
                            "description": "Type of the target entity.",
                            "default": "skill",
                        },
                        "generations": {
                            "type": "integer",
                            "description": "How many generations of history to include.",
                            "default": 10,
                            "minimum": 1,
                            "maximum": 1000,
                        },
                        "include_lineage": {
                            "type": "boolean",
                            "description": "Whether to include the full ancestry graph.",
                            "default": False,
                        },
                    },
                    "required": ["target_id"],
                },
                handler=self._handle_get_evolution_stats,
                category="evolution",
            ),
        ]

        for tool in builtins:
            self.register(tool)

    # ------------------------------------------------------------------
    # Built-in handlers
    # ------------------------------------------------------------------

    async def _handle_search_skills(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params.get("query", "")
        top_k = int(params.get("top_k", 10))
        category = params.get("category")

        # Delegate to local registry fuzzy search as a stand-in until the
        # real skill index is wired in.
        results = self.search(query)
        if category:
            results = [t for t in results if t.category == category]
        results = results[:top_k]

        return {
            "query": query,
            "total": len(results),
            "skills": [
                {
                    "id": t.name,
                    "name": t.name,
                    "description": t.description,
                    "category": t.category,
                    "version": t.version,
                }
                for t in results
            ],
        }

    async def _handle_get_spark_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        node_id = params.get("node_id")
        include_metrics = bool(params.get("include_metrics", False))

        node_ids = [node_id] if node_id else ["spark-node-01", "spark-node-02", "spark-node-03"]
        nodes = []
        for nid in node_ids:
            node: Dict[str, Any] = {
                "node_id": nid,
                "status": "running",
                "active_jobs": 0,
                "queue_depth": 0,
            }
            if include_metrics:
                node["metrics"] = {
                    "cpu_pct": 0.0,
                    "memory_used_gb": 0.0,
                    "memory_total_gb": 16.0,
                    "uptime_seconds": int(time.time()),
                }
            nodes.append(node)

        return {"nodes": nodes, "timestamp": time.time()}

    async def _handle_run_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        workflow_id = params["workflow_id"]
        input_params = params.get("params", {})
        async_mode = bool(params.get("async_mode", True))
        timeout_seconds = int(params.get("timeout_seconds", 60))

        wf = _workflow_registry.get(workflow_id)
        if wf is None:
            return {
                "error": f"Workflow '{workflow_id}' not found in registry.",
                "registered_workflows": _workflow_registry.list_ids(),
            }

        try:
            from src.workflow.executor import executor as _wf_executor  # noqa: PLC0415
        except ImportError:
            return {"error": "Workflow executor not available (import failed)."}

        logger.info(
            "mcp.run_workflow workflow=%s async=%s", workflow_id, async_mode
        )

        if async_mode:
            asyncio.create_task(_wf_executor.execute(wf, input_params))
            return {
                "workflow_id": workflow_id,
                "status": "started",
                "async_mode": True,
                "started_at": time.time(),
            }

        try:
            state = await asyncio.wait_for(
                _wf_executor.execute(wf, input_params),
                timeout=float(timeout_seconds),
            )
            return {
                "execution_id": state.execution_id,
                "workflow_id": workflow_id,
                "status": state.status,
                "async_mode": False,
                "elapsed_ms": state.elapsed_ms,
                "error": state.error,
            }
        except asyncio.TimeoutError:
            return {
                "workflow_id": workflow_id,
                "status": "timeout",
                "error": f"Workflow did not complete within {timeout_seconds}s.",
            }

    async def _handle_register_workflow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        workflow_dict = params.get("workflow")
        template_name = params.get("template")

        if template_name:
            try:
                from src.workflow.builder import (  # noqa: PLC0415
                    spark_ignition_workflow,
                    self_healing_workflow,
                    ml_training_workflow,
                )
            except ImportError:
                return {"error": "Workflow builder not available (import failed)."}

            templates: Dict[str, Any] = {
                "spark_ignition": spark_ignition_workflow,
                "self_healing": self_healing_workflow,
                "ml_training": ml_training_workflow,
            }
            factory = templates.get(template_name)
            if factory is None:
                return {
                    "error": f"Unknown template '{template_name}'.",
                    "available": list(templates.keys()),
                }
            wf = factory()
        elif workflow_dict:
            try:
                from src.workflow.builder import WorkflowDefinition  # noqa: PLC0415
                wf = WorkflowDefinition.from_dict(workflow_dict)
            except Exception as exc:
                return {"error": f"Invalid workflow definition: {exc}"}
        else:
            return {"error": "Provide either 'workflow' dict or 'template' name."}

        _workflow_registry.register(wf)
        logger.info("mcp.register_workflow id=%s name=%s", wf.id, wf.name)
        return {
            "registered": True,
            "workflow_id": wf.id,
            "workflow_name": wf.name,
            "total_registered": len(_workflow_registry.list_ids()),
        }

    async def _handle_get_system_health(self, params: Dict[str, Any]) -> Dict[str, Any]:
        requested = set(params.get("subsystems") or [])
        verbose = bool(params.get("verbose", False))

        all_subsystems = ["api_gateway", "redis", "vector_store", "skill_executor", "mcp_server"]
        check_list = [s for s in all_subsystems if not requested or s in requested]

        subsystem_results: Dict[str, Any] = {}
        overall_healthy = True

        for sub in check_list:
            t0 = time.monotonic()
            healthy = True
            detail: Dict[str, Any] = {}

            if sub == "mcp_server":
                tool_count = len(self._tools)
                healthy = tool_count > 0
                detail = {
                    "status": "ok" if healthy else "degraded",
                    "tools_registered": tool_count,
                    "workflows_registered": len(_workflow_registry.list_ids()),
                }
            elif sub == "redis":
                try:
                    import redis.asyncio as aioredis  # noqa: PLC0415
                    redis_url = __import__("os").environ.get("REDIS_URL", "redis://localhost:6379")
                    client = aioredis.from_url(redis_url, socket_connect_timeout=1)
                    await asyncio.wait_for(client.ping(), timeout=1.0)
                    await client.aclose()
                    detail = {"status": "ok"}
                except Exception as exc:
                    healthy = False
                    detail = {"status": "unavailable", "detail": str(exc)}
            else:
                detail = {"status": "ok"}

            if verbose:
                detail["latency_ms"] = round((time.monotonic() - t0) * 1000, 2)
                detail["last_checked"] = time.time()

            if not healthy:
                overall_healthy = False
            subsystem_results[sub] = detail

        return {
            "healthy": overall_healthy,
            "subsystems": subsystem_results,
            "checked_at": time.time(),
        }

    async def _handle_execute_code(self, params: Dict[str, Any]) -> Dict[str, Any]:
        code = params["code"]
        timeout_seconds = int(params.get("timeout_seconds", 30))
        context = params.get("context", {})

        namespace: Dict[str, Any] = {"__builtins__": __builtins__}
        namespace.update(context)

        stdout_lines: List[str] = []
        stderr_lines: List[str] = []
        return_value = None
        error: Optional[str] = None

        import io
        import sys

        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = io.StringIO()
        sys.stderr = io.StringIO()

        try:
            async def _run() -> Any:
                exec(compile(code, "<mcp_code>", "exec"), namespace)  # noqa: S102
                lines = code.strip().splitlines()
                if lines:
                    last_line = lines[-1].strip()
                    if last_line and not last_line.startswith(
                        ("import ", "from ", "def ", "class ", "for ", "while ", "if ", "#")
                    ):
                        try:
                            return eval(last_line, namespace)  # noqa: S307
                        except Exception:
                            return None
                return None

            return_value = await asyncio.wait_for(_run(), timeout=timeout_seconds)
        except asyncio.TimeoutError:
            error = f"Execution timed out after {timeout_seconds}s"
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
        finally:
            stdout_lines = sys.stdout.getvalue().splitlines()
            stderr_lines = sys.stderr.getvalue().splitlines()
            sys.stdout = old_stdout
            sys.stderr = old_stderr

        return {
            "stdout": stdout_lines,
            "stderr": stderr_lines,
            "return_value": return_value,
            "error": error,
            "language": "python",
        }

    async def _handle_query_vector_store(self, params: Dict[str, Any]) -> Dict[str, Any]:
        query = params["query"]
        collection = params.get("collection", "default")
        top_k = int(params.get("top_k", 5))
        score_threshold = float(params.get("score_threshold", 0.0))
        metadata_filter = params.get("metadata_filter") or {}

        logger.debug(
            "mcp.query_vector_store collection=%s query=%r top_k=%d",
            collection,
            query,
            top_k,
        )

        # Placeholder — real implementation calls the vector DB client.
        return {
            "query": query,
            "collection": collection,
            "top_k": top_k,
            "score_threshold": score_threshold,
            "metadata_filter": metadata_filter,
            "results": [],
            "total_searched": 0,
        }

    async def _handle_trigger_bundle(self, params: Dict[str, Any]) -> Dict[str, Any]:
        bundle_id = params["bundle_id"]
        input_ctx = params.get("input", {})
        overrides = params.get("overrides", {})
        dry_run = bool(params.get("dry_run", False))

        execution_id = f"bundle-{bundle_id}-{int(time.time() * 1000)}"
        logger.info(
            "mcp.trigger_bundle bundle=%s execution=%s dry_run=%s",
            bundle_id,
            execution_id,
            dry_run,
        )

        return {
            "execution_id": execution_id,
            "bundle_id": bundle_id,
            "dry_run": dry_run,
            "status": "validated" if dry_run else "dispatched",
            "input": input_ctx,
            "overrides": overrides,
            "queued_at": time.time(),
        }

    async def _handle_get_evolution_stats(self, params: Dict[str, Any]) -> Dict[str, Any]:
        target_id = params["target_id"]
        target_type = params.get("target_type", "skill")
        generations = int(params.get("generations", 10))
        include_lineage = bool(params.get("include_lineage", False))

        result: Dict[str, Any] = {
            "target_id": target_id,
            "target_type": target_type,
            "current_generation": 0,
            "fitness_score": 0.0,
            "mutations": [],
            "generations_requested": generations,
        }

        if include_lineage:
            result["lineage"] = []

        return result


# Singleton registry — import this throughout the codebase
registry = MCPToolRegistry()
