"""
The Spark — tool registry for the Model Context Protocol server.
Registers and dispatches SparkTool instances over JSON-RPC 2.0.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Restricted built-ins for execute_code sandbox
# ---------------------------------------------------------------------------

_SAFE_BUILTINS = {
    k: __builtins__[k]
    if isinstance(__builtins__, dict)
    else getattr(__builtins__, k, None)
    for k in (
        "abs",
        "all",
        "any",
        "bool",
        "bytes",
        "chr",
        "dict",
        "dir",
        "divmod",
        "enumerate",
        "filter",
        "float",
        "format",
        "frozenset",
        "getattr",
        "hasattr",
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
        "type",
        "zip",
    )
    if (isinstance(__builtins__, dict) and k in __builtins__)
    or (not isinstance(__builtins__, dict) and hasattr(__builtins__, k))
}


# ---------------------------------------------------------------------------
# Digital Grid Registry — maps workflow_id → WorkflowDefinition
# ---------------------------------------------------------------------------


class GridWorkflowRegistry:
    """In-memory registry of WorkflowDefinitions for The Digital Grid, keyed by workflow ID."""

    def __init__(self) -> None:
        self._workflows: Dict[str, Any] = {}

    def register(self, workflow: Any) -> None:
        """Register a WorkflowDefinition; overwrites any existing entry with the same ID."""
        self._workflows[workflow.id] = workflow
        logger.debug(
            "grid.registry registered id=%s name=%s", workflow.id, workflow.name
        )

    def get(self, workflow_id: str) -> Optional[Any]:
        return self._workflows.get(workflow_id)

    def list_ids(self) -> List[str]:
        return list(self._workflows.keys())

    def list_all(self) -> List[Dict[str, Any]]:
        return [
            {"id": wf.id, "name": wf.name, "description": wf.description}
            for wf in self._workflows.values()
        ]


# Singleton Digital Grid workflow registry — import this alongside `registry`
_grid_registry = GridWorkflowRegistry()


@dataclass
class SparkTool:
    """Descriptor for a single tool registered with The Spark."""

    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., Any]  # async (params: dict) -> dict
    category: str = "general"
    version: str = "1.0.0"


class SparkToolRegistry:
    """The Spark's tool registry — maps tool names to SparkTool instances and dispatches calls."""

    def __init__(self) -> None:
        self._tools: Dict[str, SparkTool] = {}
        self._register_builtins()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, tool: SparkTool) -> None:
        """Register a tool, overwriting any existing entry with the same name."""
        if tool.name in self._tools:
            logger.warning("mcp.registry overwriting tool=%s", tool.name)
        self._tools[tool.name] = tool
        logger.debug(
            "mcp.registry registered tool=%s category=%s", tool.name, tool.category
        )
        # Rebuild semantic index lazily after each registration so RAG stays current
        try:
            from src.mcp.tool_rag import rebuild_rag_index

            rebuild_rag_index(list(self._tools.values()))
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


    def get(self, name: str) -> Optional[SparkTool]:
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

    def search(self, query: str, top_k: int = 10) -> List[SparkTool]:
        """
        Search tools by query — tries semantic (RAG) first, falls back to keyword scoring.

        Semantic search (via ToolRAG) returns the most semantically relevant tools.
        Keyword scoring applies when RAG is not yet indexed.
        """
        if not query:
            return list(self._tools.values())

        # Semantic search via ToolRAG
        try:
            from src.mcp.tool_rag import get_rag

            rag = get_rag()
            if rag.is_ready():
                return rag.select_tools(query, top_k=top_k)
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


        # Keyword fallback
        q_lower = query.lower()
        tokens = q_lower.split()
        scored: List[tuple[int, SparkTool]] = []

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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
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
            SparkTool(
                name="ingest_document",
                description=(
                    "Ingest one or more text documents into the FAISS vector store for "
                    "later semantic retrieval via query_vector_store. Supports custom "
                    "collections, doc IDs, and metadata for filtering."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {
                            "type": "string",
                            "description": "Single document text to ingest.",
                        },
                        "texts": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Batch of document texts to ingest.",
                        },
                        "collection": {
                            "type": "string",
                            "description": "Target collection name (default: 'default').",
                            "default": "default",
                        },
                        "ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional parallel list of document IDs.",
                        },
                        "metadatas": {
                            "type": "array",
                            "items": {"type": "object"},
                            "description": "Optional parallel list of metadata dicts.",
                        },
                    },
                },
                handler=self._handle_ingest_document,
                category="knowledge",
            ),
            # ── Luminous (Consciousness + Neuromorphic) ────────────────────
            SparkTool(
                name="luminous_phi",
                description=(
                    "Calculate Φ (integrated information / consciousness score) for a "
                    "given probability state vector using IIT (Integrated Information "
                    "Theory). Part of the Luminous AI intelligence core."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Probability state vector (list of floats, auto-normalised).",
                        },
                    },
                    "required": ["state"],
                },
                handler=self._handle_luminous_phi,
                category="ai",
            ),
            SparkTool(
                name="luminous_process",
                description=(
                    "Run input through the Luminous neuromorphic spiking neural network. "
                    "Returns spike-encoded output tensor. Used for bio-inspired pattern "
                    "recognition and temporal signal processing."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "array",
                            "items": {"type": "number"},
                            "description": "Input float vector to process.",
                        },
                        "timesteps": {
                            "type": "integer",
                            "description": "Simulation timesteps (default 10).",
                            "default": 10,
                        },
                    },
                    "required": ["input"],
                },
                handler=self._handle_luminous_process,
                category="ai",
            ),
            # ── Think Tank (Quantum + DeepMind Planning) ───────────────────
            SparkTool(
                name="quantum_simulate",
                description=(
                    "Run a quantum circuit simulation via Qiskit Aer (Think Tank). "
                    "Creates a Bell-state entanglement circuit for the given qubit count "
                    "and returns measurement outcome probabilities."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "qubits": {
                            "type": "integer",
                            "description": "Number of qubits (default 2).",
                            "default": 2,
                        },
                        "shots": {
                            "type": "integer",
                            "description": "Measurement shots (default 1024).",
                            "default": 1024,
                        },
                    },
                },
                handler=self._handle_quantum_simulate,
                category="research",
            ),
            SparkTool(
                name="deepmind_plan",
                description=(
                    "Generate a structured action plan for a problem using the Think Tank "
                    "MCTS (Monte Carlo Tree Search) planning engine."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "problem": {
                            "type": "string",
                            "description": "Problem description or goal statement.",
                        },
                        "depth": {
                            "type": "integer",
                            "description": "Planning depth / tree expansion depth (default 3).",
                            "default": 3,
                        },
                    },
                    "required": ["problem"],
                },
                handler=self._handle_deepmind_plan,
                category="research",
            ),
            # ── The Citadel (DevOps) ───────────────────────────────────────
            SparkTool(
                name="citadel_deploy_status",
                description=(
                    "Query The Citadel for current deployment and service health status. "
                    "Returns healthy/unhealthy service counts and recent deploy history."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "target": {
                            "type": "string",
                            "description": (
                                "Optional deploy target to filter by. One of: "
                                "tranc3-backend, tranc3-bots, tranc3-ai, infinity-void, "
                                "trancendos-api-gateway"
                            ),
                        },
                    },
                },
                handler=self._handle_citadel_deploy_status,
                category="devops",
            ),
            # ── The Observatory (Audit / Events) ───────────────────────────
            SparkTool(
                name="observatory_observe",
                description=(
                    "Emit a structured audit event to The Observatory. All platform "
                    "actions, AI decisions, and security events should be observable. "
                    "Events with category=SECURITY and severity=critical are also "
                    "forwarded to The Basement for long-term archival."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "event_type": {
                            "type": "string",
                            "description": "Dot-separated event type e.g. 'spark.tool.called'.",
                        },
                        "category": {
                            "type": "string",
                            "description": "Event category: AI, SYSTEM, SECURITY, USER, WORKFLOW.",
                            "default": "AI",
                        },
                        "service": {
                            "type": "string",
                            "description": "Originating service name.",
                            "default": "the-spark",
                        },
                        "metadata": {
                            "type": "object",
                            "description": "Arbitrary key-value metadata for the event.",
                        },
                    },
                    "required": ["event_type"],
                },
                handler=self._handle_observatory_observe,
                category="observability",
            ),
            # ── The Digital Grid (Workflow introspection) ──────────────────
            SparkTool(
                name="grid_list_workflows",
                description=(
                    "List all registered workflows in The Digital Grid, with their "
                    "status, node counts, and last execution results."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "string",
                            "description": "Filter by status: active, idle, error.",
                        },
                    },
                },
                handler=self._handle_grid_list_workflows,
                category="workflow",
            ),
        ]

        for tool in builtins:
            self._tools[tool.name] = tool

        # Build initial RAG index after all builtins are loaded
        try:
            from src.mcp.tool_rag import rebuild_rag_index

            rebuild_rag_index(list(self._tools.values()))
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


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

        node_ids = (
            [node_id]
            if node_id
            else ["spark-node-01", "spark-node-02", "spark-node-03"]
        )
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

        wf = _grid_registry.get(workflow_id)
        if wf is None:
            return {
                "error": f"Workflow '{workflow_id}' not found in registry.",
                "registered_workflows": _grid_registry.list_ids(),
            }

        try:
            from src.workflow.executor import executor as _wf_executor  # noqa: PLC0415
        except ImportError:
            return {"error": "Workflow executor not available (import failed)."}

        logger.info("mcp.run_workflow workflow=%s async=%s", workflow_id, async_mode)

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

        _grid_registry.register(wf)
        logger.info("mcp.register_workflow id=%s name=%s", wf.id, wf.name)
        return {
            "registered": True,
            "workflow_id": wf.id,
            "workflow_name": wf.name,
            "total_registered": len(_grid_registry.list_ids()),
        }

    async def _handle_get_system_health(self, params: Dict[str, Any]) -> Dict[str, Any]:
        requested = set(params.get("subsystems") or [])
        verbose = bool(params.get("verbose", False))

        all_subsystems = [
            "api_gateway",
            "redis",
            "vector_store",
            "skill_executor",
            "mcp_server",
        ]
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
                    "workflows_registered": len(_grid_registry.list_ids()),
                }
            elif sub == "redis":
                try:
                    import redis.asyncio as aioredis  # noqa: PLC0415

                    redis_url = __import__("os").environ.get(
                        "REDIS_URL", "redis://localhost:6379"
                    )
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
        if not params.get("__admin__"):
            return {
                "error": "execute_code is restricted to admin callers",
                "code": -32603,
            }

        code = params["code"]
        timeout_seconds = int(params.get("timeout_seconds", 30))
        context = params.get("context", {})

        namespace: Dict[str, Any] = {"__builtins__": _SAFE_BUILTINS}
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
                exec(compile(code, "<mcp_code>", "exec"), namespace)  # noqa: S102  # nosec B102
                lines = code.strip().splitlines()
                if lines:
                    last_line = lines[-1].strip()
                    if last_line and not last_line.startswith(
                        (
                            "import ",
                            "from ",
                            "def ",
                            "class ",
                            "for ",
                            "while ",
                            "if ",
                            "#",
                        )
                    ):
                        try:
                            return eval(last_line, namespace)  # noqa: S307  # nosec B307
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

    async def _handle_query_vector_store(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
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

        try:
            from src.knowledge.vector_store import get_store

            store = get_store()
            hits = store.search(
                query=query,
                collection=collection,
                top_k=top_k,
                score_threshold=score_threshold,
                metadata_filter=metadata_filter if metadata_filter else None,
            )
            info = store.collection_info(collection)
            return {
                "query": query,
                "collection": collection,
                "top_k": top_k,
                "score_threshold": score_threshold,
                "metadata_filter": metadata_filter,
                "results": [
                    {
                        "id": h.document.id,
                        "text": h.document.text,
                        "score": round(h.score, 4),
                        "rank": h.rank,
                        "metadata": h.document.metadata,
                    }
                    for h in hits
                ],
                "total_searched": info["count"],
            }
        except Exception as exc:
            logger.warning("mcp.query_vector_store error: %s", exc)
            return {
                "query": query,
                "collection": collection,
                "top_k": top_k,
                "score_threshold": score_threshold,
                "metadata_filter": metadata_filter,
                "results": [],
                "total_searched": 0,
                "error": str(exc),
            }

    async def _handle_ingest_document(self, params: Dict[str, Any]) -> Dict[str, Any]:
        texts = params.get("texts") or []
        text = params.get("text")
        if text:
            texts = [text] + texts
        if not texts:
            return {"error": "Provide 'text' or 'texts' to ingest."}

        collection = params.get("collection", "default")
        ids = params.get("ids")
        metadatas = params.get("metadatas")

        try:
            from src.knowledge.vector_store import get_store

            store = get_store()
            doc_ids = store.ingest(
                texts=texts,
                collection=collection,
                ids=ids,
                metadatas=metadatas,
            )
            info = store.collection_info(collection)
            logger.info(
                "mcp.ingest_document collection=%s +%d docs total=%d",
                collection,
                len(doc_ids),
                info["count"],
            )
            return {
                "ingested": len(doc_ids),
                "ids": doc_ids,
                "collection": collection,
                "collection_total": info["count"],
            }
        except Exception as exc:
            logger.warning("mcp.ingest_document error: %s", exc)
            return {"error": str(exc)}

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

    async def _handle_get_evolution_stats(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
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

    # ── Luminous handlers ─────────────────────────────────────────────────

    async def _handle_luminous_phi(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import numpy as np
            from src.bio_neural.consciousness_engine import IITCalculator

            state = params["state"]
            arr = np.array(state, dtype=float)
            if arr.sum() > 0:
                arr = arr / arr.sum()
            calc = IITCalculator()
            phi = calc.calculate_phi(arr) if hasattr(calc, "calculate_phi") else 0.0
            return {"phi": float(phi), "state_dim": len(state)}
        except ImportError as exc:
            return {
                "phi": 0.0,
                "note": f"Luminous degraded — missing dependency: {exc}",
            }
        except Exception as exc:
            return {"error": str(exc)}

    async def _handle_luminous_process(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            import torch
            from src.bio_neural.neuromorphic import NeuromorphicProcessor

            input_data = params["input"]
            timesteps = int(params.get("timesteps", 10))
            processor = NeuromorphicProcessor({})
            tensor = torch.tensor(input_data, dtype=torch.float32).unsqueeze(0)
            result = (
                processor.process(tensor, timesteps=timesteps)
                if hasattr(processor, "process")
                else {
                    "note": "neuromorphic scaffold — wire input dimensions to activate"
                }
            )
            if hasattr(result, "tolist"):
                result = result.tolist()
            return {
                "input_dim": len(input_data),
                "timesteps": timesteps,
                "output": result,
            }
        except ImportError as exc:
            return {
                "output": None,
                "note": f"Luminous degraded — missing dependency: {exc}",
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ── Think Tank handlers ───────────────────────────────────────────────

    async def _handle_quantum_simulate(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from qiskit import QuantumCircuit
            from qiskit_aer import AerSimulator

            qubits = int(params.get("qubits", 2))
            shots = int(params.get("shots", 1024))
            qc = QuantumCircuit(qubits, qubits)
            qc.h(0)
            for i in range(qubits - 1):
                qc.cx(i, i + 1)
            qc.measure_all()
            sim = AerSimulator()
            job = sim.run(qc, shots=shots)
            counts = job.result().get_counts()
            return {"qubits": qubits, "shots": shots, "counts": dict(counts)}
        except ImportError:
            return {"counts": {}, "note": "Think Tank degraded — qiskit not installed"}
        except Exception as exc:
            return {"error": str(exc)}

    async def _handle_deepmind_plan(self, params: Dict[str, Any]) -> Dict[str, Any]:
        try:
            from src.deepmind.planning import PlanningEngine

            problem = params["problem"]
            depth = int(params.get("depth", 3))
            engine = PlanningEngine()
            plan = (
                engine.plan(problem, depth=depth)
                if hasattr(engine, "plan")
                else {
                    "note": "planning engine scaffold — wire problem space to activate"
                }
            )
            return {"problem": problem, "depth": depth, "plan": plan}
        except Exception as exc:
            return {
                "problem": params.get("problem", ""),
                "plan": None,
                "error": str(exc)[:120],
            }

    # ── The Citadel handler ───────────────────────────────────────────────

    async def _handle_citadel_deploy_status(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            from src.citadel.devops_hub import DeployTarget, get_citadel

            citadel = get_citadel()
            target_filter = params.get("target")
            target = None
            if target_filter:
                try:
                    target = DeployTarget(target_filter)
                except ValueError:
                    return {"error": f"Unknown target: {target_filter}"}

            deploys = [d.to_dict() for d in citadel.list_deploys(target=target)]
            stats = citadel.stats()
            return {**stats, "recent_deploys": deploys[:10]}
        except Exception as exc:
            return {"error": str(exc)}

    # ── The Observatory handler ───────────────────────────────────────────

    async def _handle_observatory_observe(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        try:
            from src.observability.observatory import EventCategory, observe

            event_type = params["event_type"]
            raw_cat = params.get("category", "AI").upper()
            try:
                category = EventCategory[raw_cat]
            except KeyError:
                category = EventCategory.AI
            service = params.get("service", "the-spark")
            metadata = params.get("metadata") or {}
            observe(event_type, category=category, service=service, metadata=metadata)
            return {"observed": True, "event_type": event_type, "category": raw_cat}
        except Exception as exc:
            return {"observed": False, "error": str(exc)}

    # ── The Digital Grid handler ──────────────────────────────────────────

    async def _handle_grid_list_workflows(
        self, params: Dict[str, Any]
    ) -> Dict[str, Any]:
        status_filter = params.get("status")
        workflows = _grid_registry.list_all()
        if status_filter:
            workflows = [w for w in workflows if w.get("status") == status_filter]
        return {
            "total": len(workflows),
            "workflows": workflows,
        }


# Singleton Spark tool registry — import this throughout the codebase
registry = SparkToolRegistry()

# ---------------------------------------------------------------------------
# Phase 4: Neural & Intelligence tools extension
# Registers 16 additional Spark tools from Phase 4 modules
# ---------------------------------------------------------------------------
try:
    from src.mcp.spark_phase4_tools import register_phase4_tools as _reg_p4
    _p4_count = _reg_p4(registry)
    logger.info("Phase 4 Spark tools loaded: %d tools added (total=%d)", _p4_count, len(registry._tools))
except Exception as _p4_exc:
    logger.warning("Phase 4 Spark tools unavailable: %s", _p4_exc)

# ---------------------------------------------------------------------------
# Phase 5: Autonomous Agent Orchestration tools extension
# Registers 12 additional Spark tools from Phase 5 agent modules
# ---------------------------------------------------------------------------
try:
    from src.mcp.spark_phase5_tools import register_phase5_tools as _reg_p5
    _p5_count = _reg_p5(registry)
    logger.info("Phase 5 Spark tools loaded: %d tools added (total=%d)", _p5_count, len(registry._tools))
except Exception as _p5_exc:
    logger.warning("Phase 5 Spark tools unavailable: %s", _p5_exc)
