"""
Trancendos workflow-engine-service — Self-Hosted Worker
========================================================
DAG-based workflow execution inspired by LangGraph.

Features:
    - Workflow definition with steps and dependencies
    - DAG validation with cycle detection (DFS)
    - Topological sort for execution ordering
    - Step-level state management with checkpoint/resume
    - Conditional branching support
    - Run tracking and execution logs

Port: 8034
Zero-cost: FastAPI + SQLite, no external orchestration required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.entities.health_metadata import health_entity_block

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "workflow-engine-service"
PORT = 8034

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("WORKFLOW_DB_PATH", "data/workflow.db")

logger = logging.getLogger("workflow-engine-service")

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3_connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS workflows (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            steps TEXT NOT NULL DEFAULT '[]',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            workflow_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            input_data TEXT DEFAULT '{}',
            output_data TEXT DEFAULT '{}',
            step_states TEXT DEFAULT '{}',
            current_step TEXT DEFAULT '',
            error_message TEXT,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (workflow_id) REFERENCES workflows(id)
        );

        CREATE TABLE IF NOT EXISTS checkpoints (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL,
            step_id TEXT NOT NULL,
            data TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            FOREIGN KEY (run_id) REFERENCES runs(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow_id);
        CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# DAG Validation
# ---------------------------------------------------------------------------


def _detect_cycle(steps: List[Dict]) -> bool:
    """Detect cycles in step dependency graph using DFS."""
    adj: Dict[str, List[str]] = defaultdict(list)
    step_ids = set()
    for step in steps:
        sid = step.get("id", "")
        step_ids.add(sid)
        for dep in step.get("depends_on", []):
            adj[dep].append(sid)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = dict.fromkeys(step_ids, WHITE)

    def dfs(node: str) -> bool:
        color[node] = GRAY
        for neighbor in adj[node]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and dfs(neighbor):
                return True
        color[node] = BLACK
        return False

    for sid in step_ids:
        if color[sid] == WHITE and dfs(sid):
            return True
    return False


def _topological_sort(steps: List[Dict]) -> List[str]:
    """Return execution order via topological sort."""
    adj: Dict[str, List[str]] = defaultdict(list)
    in_degree: Dict[str, int] = {}
    step_ids = []

    for step in steps:
        sid = step.get("id", "")
        step_ids.append(sid)
        if sid not in in_degree:
            in_degree[sid] = 0
        for dep in step.get("depends_on", []):
            adj[dep].append(sid)
            in_degree[sid] = in_degree.get(sid, 0) + 1

    queue = [sid for sid in step_ids if in_degree.get(sid, 0) == 0]
    result = []

    while queue:
        node = queue.pop(0)
        result.append(node)
        for neighbor in adj[node]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    return result


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    steps: List[Dict[str, Any]] = Field(default_factory=list)


class WorkflowResponse(BaseModel):
    id: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    is_active: int
    created_at: str
    updated_at: str


class RunStart(BaseModel):
    input_data: Dict[str, Any] = Field(default_factory=dict)


class StepComplete(BaseModel):
    output: Dict[str, Any] = Field(default_factory=dict)


class StepFail(BaseModel):
    error: str = "Step failed"


class CheckpointCreate(BaseModel):
    step_id: str
    data: Dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("workflow-engine-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 Workflow Engine Service", version="0.1.0", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])
# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "workflow-engine-service",
        "port": 8034,
        "entity": health_entity_block(8034, "workflow-engine-service"),
    }


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------


@_router.post("/workflows", status_code=201)
async def create_workflow(body: WorkflowCreate):
    # Validate DAG
    if body.steps and _detect_cycle(body.steps):
        raise HTTPException(400, "Workflow contains a cycle — DAG required") from None

    conn = _get_db()
    now = _now()
    wid = _new_id()
    try:
        conn.execute(
            "INSERT INTO workflows (id, name, description, steps, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (wid, body.name, body.description, json.dumps(body.steps), now, now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Workflow '{body.name}' already exists") from None
    conn.close()

    # Compute execution order
    exec_order = _topological_sort(body.steps) if body.steps else []

    return {
        "id": wid,
        "name": body.name,
        "description": body.description,
        "steps": body.steps,
        "is_active": 1,
        "execution_order": exec_order,
        "created_at": now,
        "updated_at": now,
    }


@_router.get("/workflows")
async def list_workflows(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM workflows ORDER BY updated_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    ).fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r["description"],
            "steps": json.loads(r["steps"]),
            "is_active": r["is_active"],
            "created_at": r["created_at"],
            "updated_at": r["updated_at"],
        }
        for r in rows
    ]


@_router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Workflow not found") from None
    return {
        "id": row["id"],
        "name": row["name"],
        "description": row["description"],
        "steps": json.loads(row["steps"]),
        "is_active": row["is_active"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------


@_router.post("/workflows/{workflow_id}/runs", status_code=201)
async def start_run(workflow_id: str, body: RunStart = None):
    conn = _get_db()
    wf = conn.execute("SELECT * FROM workflows WHERE id=?", (workflow_id,)).fetchone()
    if not wf:
        conn.close()
        raise HTTPException(404, "Workflow not found") from None

    now = _now()
    rid = _new_id()
    input_data = body.input_data if body else {}

    # Determine initial step
    steps = json.loads(wf["steps"])
    step_states = {}
    if steps:
        exec_order = _topological_sort(steps)
        current_step = exec_order[0] if exec_order else ""
        for step in steps:
            step_states[step.get("id", "")] = "pending"
        if current_step:
            step_states[current_step] = "running"
    else:
        current_step = ""

    conn.execute(
        "INSERT INTO runs (id, workflow_id, status, input_data, step_states, current_step, started_at, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            rid,
            workflow_id,
            "running" if steps else "completed",
            json.dumps(input_data),
            json.dumps(step_states),
            current_step,
            now,
            now,
        ),
    )
    conn.commit()
    conn.close()

    return {
        "id": rid,
        "workflow_id": workflow_id,
        "status": "running" if steps else "completed",
        "current_step": current_step,
        "step_states": step_states,
        "created_at": now,
    }


@_router.get("/runs/{run_id}")
async def get_run(run_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Run not found") from None
    return {
        "id": row["id"],
        "workflow_id": row["workflow_id"],
        "status": row["status"],
        "input_data": json.loads(row["input_data"]),
        "output_data": json.loads(row["output_data"] or "{}"),
        "step_states": json.loads(row["step_states"] or "{}"),
        "current_step": row["current_step"],
        "error_message": row["error_message"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "created_at": row["created_at"],
    }


@_router.put("/runs/{run_id}/steps/{step_id}/complete")
async def complete_step(run_id: str, step_id: str, body: StepComplete = None):
    conn = _get_db()
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        conn.close()
        raise HTTPException(404, "Run not found") from None

    now = _now()
    step_states = json.loads(run["step_states"] or "{}")
    step_states[step_id] = "completed"

    # Determine next step
    wf = conn.execute("SELECT steps FROM workflows WHERE id=?", (run["workflow_id"],)).fetchone()
    steps = json.loads(wf["steps"]) if wf else []
    exec_order = _topological_sort(steps) if steps else []

    # Find next pending step whose deps are all completed
    next_step = ""
    for sid in exec_order:
        if step_states.get(sid) == "pending":
            step_def = next((s for s in steps if s.get("id") == sid), {})
            deps = step_def.get("depends_on", [])
            if all(step_states.get(d) == "completed" for d in deps):
                next_step = sid
                step_states[sid] = "running"
                break

    # Check if all done
    all_done = all(s in ("completed", "failed", "skipped") for s in step_states.values())
    run_status = "completed" if all_done else run["status"]

    output_data = json.loads(run["output_data"] or "{}")
    if body and body.output:
        output_data[step_id] = body.output

    conn.execute(
        "UPDATE runs SET step_states=?, current_step=?, status=?, output_data=?, updated_at=? WHERE id=?",
        (json.dumps(step_states), next_step, run_status, json.dumps(output_data), now, run_id),
    )
    conn.commit()
    conn.close()

    return {
        "run_id": run_id,
        "step_id": step_id,
        "step_status": "completed",
        "run_status": run_status,
    }


@_router.put("/runs/{run_id}/steps/{step_id}/fail")
async def fail_step(run_id: str, step_id: str, body: StepFail = None):
    conn = _get_db()
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        conn.close()
        raise HTTPException(404, "Run not found") from None

    now = _now()
    step_states = json.loads(run["step_states"] or "{}")
    step_states[step_id] = "failed"

    conn.execute(
        "UPDATE runs SET step_states=?, status='failed', error_message=?, completed_at=?, updated_at=? WHERE id=?",
        (json.dumps(step_states), (body.error if body else "Step failed"), now, now, run_id),
    )
    conn.commit()
    conn.close()

    return {"run_id": run_id, "step_id": step_id, "step_status": "failed"}


# ---------------------------------------------------------------------------
# Checkpoints
# ---------------------------------------------------------------------------


@_router.post("/runs/{run_id}/checkpoint", status_code=201)
async def create_checkpoint(run_id: str, body: CheckpointCreate):
    conn = _get_db()
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if not run:
        conn.close()
        raise HTTPException(404, "Run not found") from None

    now = _now()
    cid = _new_id()
    conn.execute(
        "INSERT INTO checkpoints (id, run_id, step_id, data, created_at) VALUES (?,?,?,?,?)",
        (cid, run_id, body.step_id, json.dumps(body.data), now),
    )
    conn.commit()
    conn.close()

    return {"id": cid, "run_id": run_id, "step_id": body.step_id, "created_at": now}


# ---------------------------------------------------------------------------
# Logs
# ---------------------------------------------------------------------------


@_router.get("/runs/{run_id}/logs")
async def get_run_logs(run_id: str):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM checkpoints WHERE run_id=? ORDER BY created_at",
        (run_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@_router.get("/stats")
async def get_stats():
    conn = _get_db()
    total_wf = conn.execute("SELECT COUNT(*) as c FROM workflows").fetchone()["c"]
    total_runs = conn.execute("SELECT COUNT(*) as c FROM runs").fetchone()["c"]
    completed = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status='completed'").fetchone()[
        "c"
    ]
    failed = conn.execute("SELECT COUNT(*) as c FROM runs WHERE status='failed'").fetchone()["c"]
    conn.close()
    return {
        "total_workflows": total_wf,
        "total_runs": total_runs,
        "completed_runs": completed,
        "failed_runs": failed,
    }


_connected_ws: list[WebSocket] = []


@app.websocket("/ws")
async def _ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connected_ws.append(ws)
    try:
        # Push initial state
        stats = await _get_stats_async()
        await ws.send_text(json.dumps({"type": "initial_state", "data": stats}))
        # Keep alive — listen for client messages
        while True:
            raw = await ws.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                msg = {"type": "ping"}
            if msg.get("type") == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))
            elif msg.get("type") == "get_stats":
                await ws.send_text(json.dumps({"type": "stats", "data": _get_stats()}))
    except WebSocketDisconnect:
        pass
    finally:
        if ws in _connected_ws:
            _connected_ws.remove(ws)


async def _broadcast_event(event_type: str, data: dict) -> None:
    msg = json.dumps({"type": event_type, "data": data})
    stale = []
    for ws in _connected_ws:
        try:
            await ws.send_text(msg)
        except Exception:
            stale.append(ws)
    for ws in stale:
        _connected_ws.remove(ws)


@_router.get("/events")
async def _sse_events():
    async def _generator():
        while True:
            stats = await _get_stats_async()
            yield {"event": "stats", "data": json.dumps(stats)}
            await asyncio.sleep(5)

    return EventSourceResponse(_generator())


@_router.get("/dashboard/summary")
async def _dashboard_summary():
    """Aggregated summary optimized for dashboard consumption."""
    stats = await _get_stats_async()
    return {
        "service": stats.get("service", SERVICE_NAME),
        "port": stats.get("port", PORT),
        "status": "healthy",
        "summary": stats,
        "real_time": {
            "websocket": f"ws://localhost:{PORT}/ws",
            "sse": f"http://localhost:{PORT}/events",
        },
    }


async def _get_stats_async() -> dict:
    """Async version for use in async contexts."""
    try:
        result = await get_stats()
        if isinstance(result, dict):
            result["service"] = SERVICE_NAME
            result["port"] = PORT
            return result
    except Exception:
        pass
    return {"service": SERVICE_NAME, "port": PORT}


def _get_stats() -> dict:
    """Return basic service stats for real-time endpoints (sync fallback)."""
    return {"service": SERVICE_NAME, "port": PORT}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8034)
