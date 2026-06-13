"""
Trancendos The Grid API — Self-Hosted Worker (The Digital Grid)
===============================================================
Replaces CF the-grid-api.
Workflow orchestration engine with DAG-based execution, step dependencies,
and SQLite persistence. Powers The Digital Grid.

Port: 8010
Maps to: The Digital Grid / workflow orchestration
Zero-cost: Pure in-process Python, SQLite storage, no external workflow engines.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from Dimensional.error_handlers import safe_error_detail
from Dimensional.sanitize import sanitize_for_log
from shared_core.url_validation import SSRFError, validate_webhook_url
from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
WORKER_PORT = 8010
WORKER_NAME = "the-grid-api"
DB_PATH = Path(__file__).parent / "data" / "grid.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class WorkflowStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class StepStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"


class WorkflowStep(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    action: str  # e.g. "http_call", "transform", "notify", "script"
    config: Dict[str, Any] = Field(default_factory=dict)
    depends_on: List[str] = Field(default_factory=list)  # step_ids
    retry_count: int = 0
    max_retries: int = 3
    timeout_seconds: int = 300


class WorkflowDefinition(BaseModel):
    workflow_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    description: str = ""
    steps: List[WorkflowStep]
    metadata: Dict[str, Any] = Field(default_factory=dict)
    version: int = 1


class WorkflowExecution(BaseModel):
    execution_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.pending
    input_data: Dict[str, Any] = Field(default_factory=dict)
    output_data: Dict[str, Any] = Field(default_factory=dict)
    step_results: Dict[str, Any] = Field(default_factory=dict)
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


class GridDatabase:
    """SQLite-backed storage for workflow definitions and executions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    workflow_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT DEFAULT '',
                    steps TEXT NOT NULL DEFAULT '[]',
                    metadata TEXT DEFAULT '{}',
                    version INTEGER DEFAULT 1,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    execution_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    input_data TEXT DEFAULT '{}',
                    output_data TEXT DEFAULT '{}',
                    step_results TEXT DEFAULT '{}',
                    error_message TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_exec_workflow ON workflow_executions(workflow_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_exec_status ON workflow_executions(status)")

    def save_definition(self, wf: WorkflowDefinition) -> WorkflowDefinition:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO workflow_definitions (workflow_id, name, description, steps, metadata, version, created_at) VALUES (?,?,?,?,?,?,?)",
                (
                    wf.workflow_id,
                    wf.name,
                    wf.description,
                    json.dumps([s.model_dump() for s in wf.steps]),
                    json.dumps(wf.metadata),
                    wf.version,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return wf

    def get_definition(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM workflow_definitions WHERE workflow_id=?", (workflow_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_definitions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM workflow_definitions ORDER BY name LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
        return [dict(r) for r in rows]

    def delete_definition(self, workflow_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM workflow_definitions WHERE workflow_id=?", (workflow_id,))
            return cur.rowcount > 0

    def save_execution(self, execn: WorkflowExecution) -> WorkflowExecution:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO workflow_executions (execution_id, workflow_id, status, input_data, output_data, step_results, error_message, started_at, completed_at, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    execn.execution_id,
                    execn.workflow_id,
                    execn.status.value,
                    json.dumps(execn.input_data),
                    json.dumps(execn.output_data),
                    json.dumps(execn.step_results),
                    execn.error_message,
                    execn.started_at.isoformat() if execn.started_at else None,
                    execn.completed_at.isoformat() if execn.completed_at else None,
                    execn.created_at.isoformat(),
                ),
            )
        return execn

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM workflow_executions WHERE execution_id=?", (execution_id,)
        ).fetchone()
        return dict(row) if row else None

    def list_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        conn = self._get_conn()
        query = "SELECT * FROM workflow_executions WHERE 1=1"
        params: list = []
        if workflow_id:
            query += " AND workflow_id=?"
            params.append(workflow_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Workflow Engine
# ---------------------------------------------------------------------------


class WorkflowEngine:
    """Executes workflow steps in dependency order (topological sort)."""

    def __init__(self, db: GridDatabase):
        self.db = db

    async def execute(self, workflow_id: str, input_data: Dict[str, Any]) -> WorkflowExecution:
        """Execute a workflow by ID with the given input data."""
        defn_data = self.db.get_definition(workflow_id)
        if not defn_data:
            raise ValueError(f"Workflow not found: {workflow_id}")

        steps = [WorkflowStep(**s) for s in json.loads(defn_data["steps"])]
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            input_data=input_data,
            status=WorkflowStatus.running,
            started_at=datetime.now(timezone.utc),
        )
        self.db.save_execution(execution)

        try:
            # Topological sort of steps
            ordered = self._topological_sort(steps)
            step_results: Dict[str, Any] = {}

            for step in ordered:
                # Check if dependencies are met
                deps_met = all(
                    step_results.get(dep_id, {}).get("status") == "completed"
                    for dep_id in step.depends_on
                    if dep_id in step_results
                )
                if not deps_met and step.depends_on:
                    step_results[step.step_id] = {
                        "status": "skipped",
                        "reason": "Dependencies not met",
                    }
                    continue

                # Execute step
                result = await self._execute_step(step, step_results, input_data)
                step_results[step.step_id] = result

                if result.get("status") == "failed":
                    execution.status = WorkflowStatus.failed
                    execution.error_message = (
                        f"Step '{step.name}' failed: {result.get('error', 'unknown')}"
                    )
                    execution.step_results = step_results
                    execution.completed_at = datetime.now(timezone.utc)
                    self.db.save_execution(execution)
                    return execution

            execution.status = WorkflowStatus.completed
            execution.step_results = step_results
            execution.output_data = self._aggregate_outputs(step_results)
            execution.completed_at = datetime.now(timezone.utc)
            self.db.save_execution(execution)
            return execution

        except Exception as e:
            execution.status = WorkflowStatus.failed
            execution.error_message = str(e)
            execution.completed_at = datetime.now(timezone.utc)
            self.db.save_execution(execution)
            return execution

    async def _execute_step(
        self, step: WorkflowStep, step_results: Dict[str, Any], input_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single workflow step."""
        logger.info("Executing step: %s (action: %s)", step.name, step.action)
        try:
            if step.action == "http_call":
                return await self._action_http_call(step, step_results, input_data)
            elif step.action == "transform":
                return await self._action_transform(step, step_results, input_data)
            elif step.action == "notify":
                return await self._action_notify(step, step_results, input_data)
            elif step.action == "script":
                return await self._action_script(step, step_results, input_data)
            elif step.action == "delay":
                import asyncio

                delay = step.config.get("seconds", 1)
                await asyncio.sleep(delay)
                return {"status": "completed", "output": {"delayed": delay}}
            else:
                return {
                    "status": "completed",
                    "output": {"message": f"Action '{step.action}' acknowledged"},
                }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def _action_http_call(
        self, step: WorkflowStep, step_results: Dict, input_data: Dict
    ) -> Dict[str, Any]:
        import urllib.request

        url = step.config.get("url", "")
        method = step.config.get("method", "GET").upper()
        try:
            if method == "GET":
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode()
                    return {
                        "status": "completed",
                        "output": {"status_code": resp.status, "body": body[:5000]},
                    }
            else:
                data = json.dumps(step.config.get("body", {})).encode()
                req = urllib.request.Request(url, data=data, method=method)
                req.add_header("Content-Type", "application/json")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode()
                    return {
                        "status": "completed",
                        "output": {"status_code": resp.status, "body": body[:5000]},
                    }
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    async def _action_transform(
        self, step: WorkflowStep, step_results: Dict, input_data: Dict
    ) -> Dict[str, Any]:
        """Transform data using simple mappings."""
        mapping = step.config.get("mapping", {})
        source = step.config.get("source", "input")
        data = input_data if source == "input" else step_results.get(source, {})
        result = {}
        for target_key, source_path in mapping.items():
            parts = source_path.split(".")
            val = data
            for part in parts:
                val = val.get(part, None) if isinstance(val, dict) else None
                if val is None:
                    break
            result[target_key] = val
        return {"status": "completed", "output": result}

    async def _action_notify(
        self, step: WorkflowStep, step_results: Dict, input_data: Dict
    ) -> Dict[str, Any]:
        """Send a notification (via the notifications service)."""
        import urllib.request

        notif_url = step.config.get("notifications_url", "http://localhost:8008/notifications/send")
        payload = {
            "user_id": step.config.get("user_id", "system"),
            "channel": step.config.get("channel", "in_app"),
            "subject": step.config.get("subject", "Workflow Notification"),
            "body": step.config.get("body", ""),
        }
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(notif_url, data=data, method="POST")
            req.add_header("Content-Type", "application/json")
            with urllib.request.urlopen(req, timeout=10):
                return {"status": "completed", "output": {"notified": True}}
        except Exception as e:
            return {"status": "completed", "output": {"notified": False, "error": str(e)}}

    async def _action_script(
        self, step: WorkflowStep, step_results: Dict, input_data: Dict
    ) -> Dict[str, Any]:
        """Execute a simple inline Python script (sandboxed)."""
        script = step.config.get("code", "result = input_data")
        local_vars = {"input_data": input_data, "step_results": step_results, "result": None}
        try:
            exec(script, {"__builtins__": {}}, local_vars)
            return {"status": "completed", "output": local_vars.get("result", {})}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    @staticmethod
    def _topological_sort(steps: List[WorkflowStep]) -> List[WorkflowStep]:
        """Sort steps by dependencies (Kahn's algorithm)."""
        step_map = {s.step_id: s for s in steps}
        in_degree = {s.step_id: 0 for s in steps}
        adj = defaultdict(list)
        for s in steps:
            for dep in s.depends_on:
                if dep in step_map:
                    adj[dep].append(s.step_id)
                    in_degree[s.step_id] += 1
        queue = [sid for sid, deg in in_degree.items() if deg == 0]
        result = []
        while queue:
            sid = queue.pop(0)
            result.append(step_map[sid])
            for neighbor in adj[sid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        return result

    @staticmethod
    def _aggregate_outputs(step_results: Dict[str, Any]) -> Dict[str, Any]:
        outputs = {}
        for sid, result in step_results.items():
            if isinstance(result, dict) and "output" in result:
                outputs[sid] = result["output"]
        return outputs


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

db = GridDatabase(DB_PATH)
engine = WorkflowEngine(db)

app = FastAPI(
    title="The Digital Grid — Workflow API",
    description="Self-hosted DAG-based workflow orchestration. Replaces CF the-grid-api.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
STARTED_AT = datetime.now(timezone.utc)


@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
    }


# ---------------------------------------------------------------------------
# Workflow Definitions
# ---------------------------------------------------------------------------


@_router.post("/workflows")
async def create_workflow(wf: WorkflowDefinition):
    """Create a new workflow definition."""
    saved = db.save_definition(wf)
    return {"ok": True, "workflow_id": saved.workflow_id}


@_router.get("/workflows")
async def list_workflows(limit: int = 50, offset: int = 0):
    """List all workflow definitions."""
    return {"workflows": db.list_definitions(limit=limit, offset=offset)}


@_router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get a specific workflow definition."""
    wf = db.get_definition(workflow_id)
    if not wf:
        raise HTTPException(404, f"Workflow not found: {workflow_id}")
    return wf


@_router.delete("/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    """Delete a workflow definition."""
    if not db.delete_definition(workflow_id):
        raise HTTPException(404, f"Workflow not found: {workflow_id}")
    return {"ok": True, "deleted": workflow_id}


# ---------------------------------------------------------------------------
# Workflow Executions
# ---------------------------------------------------------------------------


@_router.post("/workflows/{workflow_id}/execute")
async def execute_workflow(workflow_id: str, input_data: Dict[str, Any] = None):
    """Execute a workflow with the given input data."""
    if input_data is None:
        input_data = {}
    try:
        execution = await engine.execute(workflow_id, input_data)
        return {
            "ok": True,
            "execution_id": execution.execution_id,
            "status": execution.status.value,
        }
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    except Exception as e:
        raise HTTPException(500, f"Execution failed: {e}") from None


@_router.get("/executions")
async def list_executions(
    workflow_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List workflow executions."""
    return {
        "executions": db.list_executions(
            workflow_id=workflow_id, status=status, limit=limit, offset=offset
        )
    }


@_router.get("/executions/{execution_id}")
async def get_execution(execution_id: str):
    """Get a specific workflow execution."""
    execution = db.get_execution(execution_id)
    if not execution:
        raise HTTPException(404, f"Execution not found: {execution_id}")
    return execution


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
