"""
The Digital Grid — workflow DSL builder.

Defines, validates, serialises, and templates workflow DAGs.
Workflows registered here are executable by the Grid executor and
visible to The Spark (MCP) via the register_workflow / run_workflow tools.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .nodes import NodeConfig, NodeType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# WorkflowDefinition
# ---------------------------------------------------------------------------

GRID_ENGINE = "the-digital-grid"
GRID_VERSION = "1.0.0"


@dataclass
class WorkflowDefinition:
    """Complete, serialisable description of a Digital Grid workflow DAG."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    version: str = "1.0"
    nodes: Dict[str, NodeConfig] = field(default_factory=dict)
    # edges: list of (from_node_id, to_node_id, edge_label)
    edges: List[Tuple[str, str, str]] = field(default_factory=list)
    triggers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    # ------------------------------------------------------------------
    # Serialization helpers
    # ------------------------------------------------------------------

    def _node_config_to_dict(self, nc: NodeConfig) -> dict:
        return {
            "id": nc.id,
            "type": nc.type.value,
            "name": nc.name,
            "config": nc.config,
            "inputs": nc.inputs,
            "outputs": nc.outputs,
            "timeout_sec": nc.timeout_sec,
            "retry_count": nc.retry_count,
        }

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "engine": GRID_ENGINE,
            "nodes": {
                nid: self._node_config_to_dict(nc) for nid, nc in self.nodes.items()
            },
            "edges": [
                {"from": e[0], "to": e[1], "label": e[2]} for e in self.edges
            ],
            "triggers": self.triggers,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), default_flow_style=False, sort_keys=False)

    # ------------------------------------------------------------------
    # Deserialization
    # ------------------------------------------------------------------

    @classmethod
    def _node_config_from_dict(cls, d: dict) -> NodeConfig:
        return NodeConfig(
            id=d["id"],
            type=NodeType(d["type"]),
            name=d.get("name", d["id"]),
            config=d.get("config", {}),
            inputs=d.get("inputs", []),
            outputs=d.get("outputs", []),
            timeout_sec=float(d.get("timeout_sec", 30.0)),
            retry_count=int(d.get("retry_count", 3)),
        )

    @classmethod
    def from_dict(cls, d: dict) -> "WorkflowDefinition":
        nodes = {
            nid: cls._node_config_from_dict(nc_dict)
            for nid, nc_dict in d.get("nodes", {}).items()
        }
        edges: List[Tuple[str, str, str]] = [
            (e["from"], e["to"], e.get("label", "default"))
            for e in d.get("edges", [])
        ]
        return cls(
            id=d.get("id", str(uuid.uuid4())),
            name=d.get("name", ""),
            description=d.get("description", ""),
            version=d.get("version", "1.0"),
            nodes=nodes,
            edges=edges,
            triggers=d.get("triggers", []),
            metadata=d.get("metadata", {}),
        )

    @classmethod
    def from_json(cls, s: str) -> "WorkflowDefinition":
        return cls.from_dict(json.loads(s))

    @classmethod
    def from_yaml(cls, s: str) -> "WorkflowDefinition":
        return cls.from_dict(yaml.safe_load(s))


# ---------------------------------------------------------------------------
# WorkflowBuilder — fluent API
# ---------------------------------------------------------------------------

class WorkflowBuilder:
    """Fluent builder for constructing WorkflowDefinitions programmatically."""

    def __init__(self, name: str, description: str = "") -> None:
        self._id = str(uuid.uuid4())
        self._name = name
        self._description = description
        self._nodes: Dict[str, NodeConfig] = {}
        self._edges: List[Tuple[str, str, str]] = []
        self._triggers: List[str] = []
        self._metadata: Dict[str, Any] = {}

    def add_node(
        self,
        node_type: NodeType,
        name: str,
        config: dict = None,  # type: ignore[assignment]
        timeout: float = 30.0,
        retry_count: int = 3,
        node_id: Optional[str] = None,
    ) -> str:
        """Add a node; returns its generated (or provided) node_id."""
        if config is None:
            config = {}
        nid = node_id or str(uuid.uuid4())
        self._nodes[nid] = NodeConfig(
            id=nid,
            type=node_type,
            name=name,
            config=config,
            inputs=[],
            outputs=[],
            timeout_sec=timeout,
            retry_count=retry_count,
        )
        return nid

    def connect(
        self, from_id: str, to_id: str, label: str = "default"
    ) -> "WorkflowBuilder":
        """Add a directed edge from_id -> to_id with an optional label."""
        if from_id not in self._nodes:
            raise ValueError(f"Source node '{from_id}' not found in this workflow.")
        if to_id not in self._nodes:
            raise ValueError(f"Target node '{to_id}' not found in this workflow.")
        self._edges.append((from_id, to_id, label))
        # Keep outputs/inputs in sync
        self._nodes[from_id].outputs.append(to_id)
        self._nodes[to_id].inputs.append(from_id)
        return self

    def set_trigger(self, *event_names: str) -> "WorkflowBuilder":
        """Set one or more event names that will trigger this workflow."""
        self._triggers.extend(event_names)
        return self

    def set_metadata(self, **kwargs: Any) -> "WorkflowBuilder":
        """Attach arbitrary metadata key/value pairs."""
        self._metadata.update(kwargs)
        return self

    def build(self) -> WorkflowDefinition:
        """Construct and return the WorkflowDefinition."""
        return WorkflowDefinition(
            id=self._id,
            name=self._name,
            description=self._description,
            nodes=dict(self._nodes),
            edges=list(self._edges),
            triggers=list(self._triggers),
            metadata=dict(self._metadata),
        )

    def validate(self) -> List[str]:
        """
        Validate the workflow definition.

        Returns a list of error strings. An empty list means the workflow
        is structurally valid.
        """
        errors: List[str] = []

        if not self._name:
            errors.append("Workflow 'name' is required.")

        if not self._nodes:
            errors.append("Workflow has no nodes.")
            return errors  # no point checking edges

        node_ids = set(self._nodes.keys())

        # --- Edge referential integrity ---
        for from_id, to_id, label in self._edges:
            if from_id not in node_ids:
                errors.append(f"Edge references unknown source node: '{from_id}'.")
            if to_id not in node_ids:
                errors.append(f"Edge references unknown target node: '{to_id}'.")

        # --- Cycle detection (DFS) ---
        adj: Dict[str, List[str]] = {nid: [] for nid in node_ids}
        for from_id, to_id, _ in self._edges:
            if from_id in adj:
                adj[from_id].append(to_id)

        WHITE, GRAY, BLACK = 0, 1, 2
        color: Dict[str, int] = {nid: WHITE for nid in node_ids}

        def dfs(v: str) -> bool:
            color[v] = GRAY
            for u in adj.get(v, []):
                if color[u] == GRAY:
                    return True  # back-edge → cycle
                if color[u] == WHITE and dfs(u):
                    return True
            color[v] = BLACK
            return False

        for nid in node_ids:
            if color[nid] == WHITE:
                if dfs(nid):
                    errors.append("Workflow DAG contains a cycle.")
                    break

        # --- Orphan node detection (nodes with no edges at all) ---
        connected: set = set()
        for from_id, to_id, _ in self._edges:
            connected.add(from_id)
            connected.add(to_id)
        orphans = node_ids - connected
        # Single-node workflows are fine; only flag orphans in multi-node graphs
        if len(node_ids) > 1 and orphans:
            errors.append(
                f"Orphan nodes (no edges): {sorted(orphans)}. "
                "Connect them or remove them."
            )

        # --- Trigger node presence ---
        trigger_nodes = [
            nid for nid, nc in self._nodes.items() if nc.type == NodeType.TRIGGER
        ]
        if self._triggers and not trigger_nodes:
            errors.append(
                "Workflow has triggers set but no TRIGGER-type node defined."
            )

        return errors


# ---------------------------------------------------------------------------
# Pre-built workflow templates
# ---------------------------------------------------------------------------

def spark_ignition_workflow() -> WorkflowDefinition:
    """
    Detects build intent → loads relevant skills → executes LLM for code generation.

    Topology:
        TRIGGER → SKILL_CALL (load skills) → LLM → OUTPUT
    """
    b = WorkflowBuilder(
        name="Spark Ignition",
        description=(
            "Detects a build intent from an incoming event, loads the relevant "
            "Tranc3 skills, and feeds everything into an LLM to generate code."
        ),
    )
    b.set_trigger("build.intent.detected", "code.request")

    trigger_id = b.add_node(
        NodeType.TRIGGER,
        "Trigger: Build Intent",
        config={"trigger_type": "event", "required_fields": ["intent", "language"]},
        timeout=10.0,
    )

    condition_id = b.add_node(
        NodeType.CONDITION,
        "Check Intent",
        config={"expression": "inputs.get('intent', '') != ''"},
        timeout=5.0,
    )

    skill_id = b.add_node(
        NodeType.SKILL_CALL,
        "Load Matching Skills",
        config={
            "skill_name": "skill_lookup",
            "args": {"max_results": 5},
        },
        timeout=15.0,
    )

    llm_id = b.add_node(
        NodeType.LLM,
        "Generate Code with LLM",
        config={
            "model": "claude-3-5-sonnet-20241022",
            "max_tokens": 2048,
            "system_prompt": (
                "You are Tranc3, an expert AI coding assistant. "
                "Generate production-quality code based on the user's intent and available skills."
            ),
            "prompt": (
                "Intent: {{intent}}\n"
                "Language: {{language}}\n"
                "Available Skills: {{skills}}\n\n"
                "Generate the implementation."
            ),
        },
        timeout=60.0,
    )

    output_id = b.add_node(
        NodeType.OUTPUT,
        "Return Generated Code",
        config={"keys": ["code", "explanation"]},
        timeout=5.0,
    )

    (
        b.connect(trigger_id, condition_id)
         .connect(condition_id, skill_id, label="true")
         .connect(skill_id, llm_id)
         .connect(llm_id, output_id)
    )

    b.set_metadata(
        category="code_generation",
        tags=["spark", "llm", "skills"],
    )
    return b.build()


def self_healing_workflow() -> WorkflowDefinition:
    """
    Monitors system health → detects an issue → dispatches a healing bot → validates fix.

    Topology:
        TRIGGER → HTTP (health check) → CONDITION → PARALLEL(ML_PREDICT + SKILL_CALL) → CODE_EXEC → OUTPUT
    """
    b = WorkflowBuilder(
        name="Self-Healing",
        description=(
            "Continuously monitors system health endpoints, detects issues, "
            "dispatches the healing bot, and validates the fix."
        ),
    )
    b.set_trigger("health.check.scheduled", "alert.raised")

    trigger_id = b.add_node(
        NodeType.TRIGGER,
        "Trigger: Health Alert",
        config={"trigger_type": "scheduled", "required_fields": ["target_service"]},
        timeout=5.0,
    )

    health_check_id = b.add_node(
        NodeType.HTTP_REQUEST,
        "Health Check",
        config={
            "method": "GET",
            "url": "{{target_service}}/health",
            "headers": {"Accept": "application/json"},
        },
        timeout=10.0,
        retry_count=2,
    )

    condition_id = b.add_node(
        NodeType.CONDITION,
        "Issue Detected?",
        config={"expression": "inputs.get('body', {}).get('status') != 'ok'"},
        timeout=5.0,
    )

    parallel_id = b.add_node(
        NodeType.PARALLEL,
        "Diagnose in Parallel",
        config={
            "nodes": [
                {
                    "id": "ml_diagnose",
                    "type": "ML_PREDICT",
                    "name": "ML Diagnosis",
                    "config": {
                        "model_name": "tranc3-health-classifier",
                        "static_inputs": {"task": "diagnose"},
                    },
                    "timeout_sec": 20.0,
                    "retry_count": 2,
                },
                {
                    "id": "skill_remediation",
                    "type": "SKILL_CALL",
                    "name": "Lookup Remediation",
                    "config": {
                        "skill_name": "remediation_lookup",
                        "args": {},
                    },
                    "timeout_sec": 15.0,
                    "retry_count": 2,
                },
            ]
        },
        timeout=30.0,
    )

    heal_id = b.add_node(
        NodeType.CODE_EXEC,
        "Execute Healing Script",
        config={
            "code": (
                "import json\n"
                "diagnosis = inputs.get('results', {}).get('ml_diagnose', {})\n"
                "remediation = inputs.get('results', {}).get('skill_remediation', {})\n"
                "# In a real system, this would invoke the actual fix\n"
                "result = {\n"
                "    'action_taken': remediation.get('action', 'restart'),\n"
                "    'severity': diagnosis.get('severity', 'unknown'),\n"
                "    'timestamp': __import__('datetime').datetime.utcnow().isoformat(),\n"
                "}\n"
            )
        },
        timeout=45.0,
        retry_count=1,
    )

    validate_id = b.add_node(
        NodeType.HTTP_REQUEST,
        "Validate Fix",
        config={
            "method": "GET",
            "url": "{{target_service}}/health",
        },
        timeout=10.0,
        retry_count=3,
    )

    output_id = b.add_node(
        NodeType.OUTPUT,
        "Healing Report",
        config={"keys": ["action_taken", "severity", "timestamp", "status_code"]},
        timeout=5.0,
    )

    (
        b.connect(trigger_id, health_check_id)
         .connect(health_check_id, condition_id)
         .connect(condition_id, parallel_id, label="true")
         .connect(parallel_id, heal_id)
         .connect(heal_id, validate_id)
         .connect(validate_id, output_id)
    )

    b.set_metadata(
        category="ops",
        tags=["healing", "monitoring", "autonomous"],
    )
    return b.build()


def ml_training_workflow() -> WorkflowDefinition:
    """
    Loads data → preprocesses → trains → evaluates → saves model.

    Topology:
        TRIGGER → HTTP (load dataset) → CODE_EXEC (preprocess) → ML_PREDICT (train) →
        CODE_EXEC (evaluate) → TRANSFORM (format metrics) → OUTPUT
    """
    b = WorkflowBuilder(
        name="ML Training Pipeline",
        description=(
            "End-to-end ML training: fetches a dataset, preprocesses it, "
            "kicks off a training run, evaluates results, and saves the model."
        ),
    )
    b.set_trigger("training.scheduled", "training.manual_start")

    trigger_id = b.add_node(
        NodeType.TRIGGER,
        "Trigger: Training Start",
        config={
            "trigger_type": "manual",
            "required_fields": ["dataset_url", "model_name"],
        },
        timeout=5.0,
    )

    load_id = b.add_node(
        NodeType.HTTP_REQUEST,
        "Load Dataset",
        config={
            "method": "GET",
            "headers": {"Accept": "application/json"},
        },
        timeout=60.0,
        retry_count=3,
    )

    preprocess_id = b.add_node(
        NodeType.CODE_EXEC,
        "Preprocess Data",
        config={
            "code": (
                "import json, math\n"
                "raw = inputs.get('body', [])\n"
                "if isinstance(raw, dict):\n"
                "    raw = raw.get('data', [])\n"
                "# Normalise numeric fields\n"
                "def normalise(row):\n"
                "    return {k: (float(v) if isinstance(v, (int, float)) else v)\n"
                "            for k, v in row.items()}\n"
                "processed = [normalise(r) for r in raw if isinstance(r, dict)]\n"
                "result = {\n"
                "    'samples': processed,\n"
                "    'sample_count': len(processed),\n"
                "    'feature_keys': list(processed[0].keys()) if processed else [],\n"
                "}\n"
            )
        },
        timeout=120.0,
        retry_count=1,
    )

    train_id = b.add_node(
        NodeType.ML_PREDICT,
        "Train Model",
        config={
            "model_name": "tranc3-trainer",
            "static_inputs": {"task": "train", "epochs": 10},
        },
        timeout=600.0,
        retry_count=1,
    )

    evaluate_id = b.add_node(
        NodeType.CODE_EXEC,
        "Evaluate Model",
        config={
            "code": (
                "train_result = inputs.get('predictions', inputs)\n"
                "metrics = train_result.get('metrics', {})\n"
                "accuracy = metrics.get('accuracy', 0.0)\n"
                "loss = metrics.get('loss', float('inf'))\n"
                "passed = accuracy >= 0.8\n"
                "result = {\n"
                "    'accuracy': accuracy,\n"
                "    'loss': loss,\n"
                "    'passed_threshold': passed,\n"
                "    'model_id': train_result.get('model_id'),\n"
                "}\n"
            )
        },
        timeout=30.0,
        retry_count=1,
    )

    transform_id = b.add_node(
        NodeType.TRANSFORM,
        "Format Training Metrics",
        config={
            "mapping": {
                "accuracy": "result.accuracy",
                "loss": "result.loss",
                "passed": "result.passed_threshold",
                "model_id": "result.model_id",
            }
        },
        timeout=5.0,
    )

    output_id = b.add_node(
        NodeType.OUTPUT,
        "Training Complete",
        config={"keys": ["accuracy", "loss", "passed", "model_id"]},
        timeout=5.0,
    )

    (
        b.connect(trigger_id, load_id)
         .connect(load_id, preprocess_id)
         .connect(preprocess_id, train_id)
         .connect(train_id, evaluate_id)
         .connect(evaluate_id, transform_id)
         .connect(transform_id, output_id)
    )

    b.set_metadata(
        category="ml",
        tags=["training", "pipeline", "automation"],
    )
    return b.build()
