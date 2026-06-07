#!/usr/bin/env python3
"""DeepAgents Orchestrator Service — Port 8037.

Smart, adaptive multi-agent orchestration with delegation depth limits,
skill-based routing, and execution logging. Zero-cost self-hosted design.
"""

import asyncio
import json
import os
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
)
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from src.database.encrypted_sqlite import connect as sqlite3_connect

# ── Config ───────────────────────────────────────────────────────────────────
SERVICE_NAME = "deepagents-orchestrator"
PORT = 8037
DB_PATH = Path(__file__).parent / "deepagents.db"
MAX_DELEGATION_DEPTH = 5


@asynccontextmanager
async def _lifespan(app):
    """Initialize database on startup."""
    init_db()
    yield


app = FastAPI(title=f"Tranc3 {SERVICE_NAME}", version="0.6.0", lifespan=_lifespan)

_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])

# ── Pydantic schemas ─────────────────────────────────────────────────────────


class AgentCreate(BaseModel):
    name: str
    capabilities: list[str] = Field(default_factory=list)
    model_binding: str | None = None
    tools: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] | None = None


class AgentUpdate(BaseModel):
    name: str | None = None
    capabilities: list[str] | None = None
    model_binding: str | None = None
    tools: list[str] | None = None
    status: str | None = None
    metadata: dict[str, Any] | None = None


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    required_capabilities: list[str] = Field(default_factory=list)
    priority: int = 5
    parent_task_id: str | None = None
    metadata: dict[str, Any] | None = None


class TaskUpdate(BaseModel):
    status: str | None = None
    assigned_agent_id: str | None = None
    result: str | None = None
    error: str | None = None
    priority: int | None = None


class DelegationRequest(BaseModel):
    task_id: str
    from_agent_id: str
    to_agent_id: str
    reason: str = ""


class SkillCreate(BaseModel):
    name: str
    category: str
    description: str = ""
    proficiency_levels: list[str] = Field(
        default_factory=lambda: ["beginner", "intermediate", "advanced", "expert"],
    )


# ── Database ─────────────────────────────────────────────────────────────────


def get_db() -> sqlite3.Connection:
    db = sqlite3_connect(str(DB_PATH), timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    return db


def init_db() -> None:
    db = get_db()
    db.executescript("""
        CREATE TABLE IF NOT EXISTS agents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            capabilities TEXT DEFAULT '[]',
            model_binding TEXT,
            tools TEXT DEFAULT '[]',
            status TEXT DEFAULT 'active',
            metadata TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            required_capabilities TEXT DEFAULT '[]',
            priority INTEGER DEFAULT 5,
            status TEXT DEFAULT 'pending',
            assigned_agent_id TEXT,
            parent_task_id TEXT,
            delegation_depth INTEGER DEFAULT 0,
            result TEXT,
            error TEXT,
            metadata TEXT DEFAULT '{}',
            created_at REAL,
            updated_at REAL,
            completed_at REAL
        );
        CREATE TABLE IF NOT EXISTS delegations (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            from_agent_id TEXT NOT NULL,
            to_agent_id TEXT NOT NULL,
            reason TEXT DEFAULT '',
            depth_at_delegation INTEGER DEFAULT 0,
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS skills (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            proficiency_levels TEXT DEFAULT '["beginner","intermediate","advanced","expert"]',
            created_at REAL
        );
        CREATE TABLE IF NOT EXISTS agent_skills (
            id TEXT PRIMARY KEY,
            agent_id TEXT NOT NULL,
            skill_id TEXT NOT NULL,
            proficiency TEXT DEFAULT 'beginner',
            acquired_at REAL,
            UNIQUE(agent_id, skill_id)
        );
        CREATE TABLE IF NOT EXISTS execution_logs (
            id TEXT PRIMARY KEY,
            agent_id TEXT,
            task_id TEXT,
            action TEXT NOT NULL,
            details TEXT DEFAULT '{}',
            created_at REAL
        );
    """)
    # Seed default skills
    default_skills = [
        ("reasoning", "cognitive", "Logical reasoning and deduction"),
        ("coding", "technical", "Software development and programming"),
        ("analysis", "cognitive", "Data analysis and interpretation"),
        ("planning", "cognitive", "Strategic planning and organization"),
        ("communication", "social", "Natural language communication"),
        ("research", "cognitive", "Information gathering and synthesis"),
        ("math", "technical", "Mathematical computation"),
        ("creativity", "cognitive", "Creative thinking and ideation"),
        ("debugging", "technical", "Debugging and troubleshooting"),
        ("review", "social", "Code and document review"),
    ]
    now = time.time()
    for s_name, s_cat, s_desc in default_skills:
        existing = db.execute("SELECT id FROM skills WHERE name=?", (s_name,)).fetchone()
        if not existing:
            db.execute(
                "INSERT INTO skills (id,name,category,description,created_at) VALUES (?,?,?,?,?)",
                (str(uuid.uuid4()), s_name, s_cat, s_desc, now),
            )
    db.commit()
    db.close()


# ── Helpers ──────────────────────────────────────────────────────────────────


def _now() -> float:
    return time.time()


def _log(
    agent_id: str | None,
    task_id: str | None,
    action: str,
    details: dict | None = None,
) -> None:
    db = get_db()
    db.execute(
        "INSERT INTO execution_logs (id,agent_id,task_id,action,details,created_at) VALUES (?,?,?,?,?,?)",
        (str(uuid.uuid4()), agent_id, task_id, action, json.dumps(details or {}), _now()),
    )
    db.commit()
    db.close()


# ── Routes ───────────────────────────────────────────────────────────────────


@app.get("/health")
def health():
    db = get_db()
    agent_count = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    task_count = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    skill_count = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    db.close()
    from src.entities.health_metadata import health_entity_block

    return {
        "status": "healthy",
        "service": SERVICE_NAME,
        "port": PORT,
        "agents": agent_count,
        "tasks": task_count,
        "skills": skill_count,
        "entity": health_entity_block(PORT, SERVICE_NAME),
    }


# ── Agent CRUD ───────────────────────────────────────────────────────────────


@_router.post("/agents")
def create_agent(body: AgentCreate):
    aid = str(uuid.uuid4())
    now = _now()
    db = get_db()
    db.execute(
        "INSERT INTO agents (id,name,capabilities,model_binding,tools,metadata,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)",
        (
            aid,
            body.name,
            json.dumps(body.capabilities),
            body.model_binding,
            json.dumps(body.tools),
            json.dumps(body.metadata or {}),
            now,
            now,
        ),
    )
    db.commit()
    db.close()
    _log(aid, None, "agent_created", {"name": body.name})
    return {"id": aid, "name": body.name, "status": "active"}


@_router.get("/agents")
def list_agents(status: str | None = None):
    db = get_db()
    if status:
        rows = db.execute(
            "SELECT * FROM agents WHERE status=? ORDER BY created_at DESC",
            (status,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM agents ORDER BY created_at DESC").fetchall()
    db.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "capabilities": json.loads(r["capabilities"]),
                "model_binding": r["model_binding"],
                "tools": json.loads(r["tools"]),
                "status": r["status"],
                "metadata": json.loads(r["metadata"]),
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            },
        )
    return {"agents": result, "total": len(result)}


@_router.get("/agents/{agent_id}")
def get_agent(agent_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Agent not found") from None
    return {
        "id": row["id"],
        "name": row["name"],
        "capabilities": json.loads(row["capabilities"]),
        "model_binding": row["model_binding"],
        "tools": json.loads(row["tools"]),
        "status": row["status"],
        "metadata": json.loads(row["metadata"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


@_router.patch("/agents/{agent_id}")
def update_agent(agent_id: str, body: AgentUpdate):
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Agent not found") from None
    updates = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.capabilities is not None:
        updates["capabilities"] = json.dumps(body.capabilities)
    if body.model_binding is not None:
        updates["model_binding"] = body.model_binding
    if body.tools is not None:
        updates["tools"] = json.dumps(body.tools)
    if body.status is not None:
        updates["status"] = body.status
    if body.metadata is not None:
        updates["metadata"] = json.dumps(body.metadata)
    updates["updated_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db.execute(f"UPDATE agents SET {set_clause} WHERE id=?", (*updates.values(), agent_id))
    db.commit()
    db.close()
    _log(agent_id, None, "agent_updated", updates)
    return {"id": agent_id, "updated": True}


@_router.delete("/agents/{agent_id}")
def deregister_agent(agent_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Agent not found") from None
    db.execute("DELETE FROM agent_skills WHERE agent_id=?", (agent_id,))
    db.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    db.commit()
    db.close()
    _log(agent_id, None, "agent_deregistered")
    return {"id": agent_id, "deregistered": True}


# ── Task CRUD ────────────────────────────────────────────────────────────────


@_router.post("/tasks")
def create_task(body: TaskCreate):
    tid = str(uuid.uuid4())
    now = _now()
    depth = 0
    db = get_db()
    if body.parent_task_id:
        parent = db.execute(
            "SELECT delegation_depth FROM tasks WHERE id=?",
            (body.parent_task_id,),
        ).fetchone()
        if parent:
            depth = parent["delegation_depth"] + 1
    db.execute(
        "INSERT INTO tasks (id,title,description,required_capabilities,priority,status,parent_task_id,delegation_depth,metadata,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (
            tid,
            body.title,
            body.description,
            json.dumps(body.required_capabilities),
            body.priority,
            "pending",
            body.parent_task_id,
            depth,
            json.dumps(body.metadata or {}),
            now,
            now,
        ),
    )
    db.commit()
    db.close()
    _log(None, tid, "task_created", {"title": body.title, "priority": body.priority})
    return {"id": tid, "title": body.title, "status": "pending", "delegation_depth": depth}


@_router.get("/tasks")
def list_tasks(status: str | None = None, priority: int | None = None):
    db = get_db()
    query = "SELECT * FROM tasks WHERE 1=1"
    params: list[Any] = []
    if status:
        query += " AND status=?"
        params.append(status)
    if priority is not None:
        query += " AND priority=?"
        params.append(priority)
    query += " ORDER BY priority DESC, created_at DESC"
    rows = db.execute(query, params).fetchall()
    db.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "title": r["title"],
                "description": r["description"],
                "required_capabilities": json.loads(r["required_capabilities"]),
                "priority": r["priority"],
                "status": r["status"],
                "assigned_agent_id": r["assigned_agent_id"],
                "parent_task_id": r["parent_task_id"],
                "delegation_depth": r["delegation_depth"],
                "result": r["result"],
                "error": r["error"],
                "created_at": r["created_at"],
                "updated_at": r["updated_at"],
            },
        )
    return {"tasks": result, "total": len(result)}


@_router.get("/tasks/{task_id}")
def get_task(task_id: str):
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    db.close()
    if not row:
        raise HTTPException(404, "Task not found") from None
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "required_capabilities": json.loads(row["required_capabilities"]),
        "priority": row["priority"],
        "status": row["status"],
        "assigned_agent_id": row["assigned_agent_id"],
        "parent_task_id": row["parent_task_id"],
        "delegation_depth": row["delegation_depth"],
        "result": row["result"],
        "error": row["error"],
        "metadata": json.loads(row["metadata"]),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
    }


@_router.patch("/tasks/{task_id}")
def update_task(task_id: str, body: TaskUpdate):
    db = get_db()
    row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
    if not row:
        db.close()
        raise HTTPException(404, "Task not found") from None
    updates = {}
    if body.status is not None:
        updates["status"] = body.status
    if body.assigned_agent_id is not None:
        updates["assigned_agent_id"] = body.assigned_agent_id
    if body.result is not None:
        updates["result"] = body.result
    if body.error is not None:
        updates["error"] = body.error
    if body.priority is not None:
        updates["priority"] = body.priority
    updates["updated_at"] = _now()
    if body.status in ("completed", "failed"):
        updates["completed_at"] = _now()
    set_clause = ", ".join(f"{k}=?" for k in updates)
    db.execute(f"UPDATE tasks SET {set_clause} WHERE id=?", (*updates.values(), task_id))
    db.commit()
    db.close()
    _log(body.assigned_agent_id, task_id, "task_updated", updates)
    return {"id": task_id, "updated": True}


# ── Delegation ───────────────────────────────────────────────────────────────


@_router.post("/delegate")
def delegate_task(body: DelegationRequest):
    db = get_db()
    # Verify task
    task = db.execute("SELECT * FROM tasks WHERE id=?", (body.task_id,)).fetchone()
    if not task:
        db.close()
        raise HTTPException(404, "Task not found") from None
    # Verify agents
    from_agent = db.execute("SELECT * FROM agents WHERE id=?", (body.from_agent_id,)).fetchone()
    if not from_agent:
        db.close()
        raise HTTPException(404, "Source agent not found") from None
    to_agent = db.execute("SELECT * FROM agents WHERE id=?", (body.to_agent_id,)).fetchone()
    if not to_agent:
        db.close()
        raise HTTPException(404, "Target agent not found") from None
    # Check delegation depth
    current_depth = task["delegation_depth"]
    if current_depth >= MAX_DELEGATION_DEPTH:
        db.close()
        raise HTTPException(400, f"Max delegation depth ({MAX_DELEGATION_DEPTH}) reached") from None
    # Create sub-task
    sub_id = str(uuid.uuid4())
    now = _now()
    new_depth = current_depth + 1
    db.execute(
        "INSERT INTO tasks (id,title,description,required_capabilities,priority,status,parent_task_id,delegation_depth,assigned_agent_id,metadata,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            sub_id,
            f"[Delegated] {task['title']}",
            task["description"],
            task["required_capabilities"],
            task["priority"],
            "assigned",
            body.task_id,
            new_depth,
            body.to_agent_id,
            task["metadata"],
            now,
            now,
        ),
    )
    # Record delegation
    del_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO delegations (id,task_id,from_agent_id,to_agent_id,reason,depth_at_delegation,created_at) VALUES (?,?,?,?,?,?,?)",
        (del_id, body.task_id, body.from_agent_id, body.to_agent_id, body.reason, new_depth, now),
    )
    db.commit()
    db.close()
    _log(body.from_agent_id, sub_id, "task_delegated", {"to": body.to_agent_id, "depth": new_depth})
    return {
        "delegation_id": del_id,
        "sub_task_id": sub_id,
        "from_agent": body.from_agent_id,
        "to_agent": body.to_agent_id,
        "depth": new_depth,
    }


@_router.get("/delegations")
def list_delegations(task_id: str | None = None):
    db = get_db()
    if task_id:
        rows = db.execute(
            "SELECT * FROM delegations WHERE task_id=? ORDER BY created_at DESC",
            (task_id,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM delegations ORDER BY created_at DESC").fetchall()
    db.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "task_id": r["task_id"],
                "from_agent_id": r["from_agent_id"],
                "to_agent_id": r["to_agent_id"],
                "reason": r["reason"],
                "depth_at_delegation": r["depth_at_delegation"],
                "created_at": r["created_at"],
            },
        )
    return {"delegations": result, "total": len(result)}


# ── Skills ───────────────────────────────────────────────────────────────────


@_router.post("/skills")
def create_skill(body: SkillCreate):
    sid = str(uuid.uuid4())
    now = _now()
    db = get_db()
    try:
        db.execute(
            "INSERT INTO skills (id,name,category,description,proficiency_levels,created_at) VALUES (?,?,?,?,?,?)",
            (
                sid,
                body.name,
                body.category,
                body.description,
                json.dumps(body.proficiency_levels),
                now,
            ),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        raise HTTPException(409, "Skill already exists") from None
    db.close()
    return {"id": sid, "name": body.name, "category": body.category}


@_router.get("/skills")
def list_skills(category: str | None = None):
    db = get_db()
    if category:
        rows = db.execute(
            "SELECT * FROM skills WHERE category=? ORDER BY name",
            (category,),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM skills ORDER BY name").fetchall()
    db.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "name": r["name"],
                "category": r["category"],
                "description": r["description"],
                "proficiency_levels": json.loads(r["proficiency_levels"]),
                "created_at": r["created_at"],
            },
        )
    return {"skills": result, "total": len(result)}


@_router.post("/agents/{agent_id}/skills/{skill_id}")
def assign_skill(agent_id: str, skill_id: str, proficiency: str = "beginner"):
    db = get_db()
    agent = db.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        db.close()
        raise HTTPException(404, "Agent not found") from None
    skill = db.execute("SELECT * FROM skills WHERE id=?", (skill_id,)).fetchone()
    if not skill:
        db.close()
        raise HTTPException(404, "Skill not found") from None
    now = _now()
    try:
        db.execute(
            "INSERT INTO agent_skills (id,agent_id,skill_id,proficiency,acquired_at) VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), agent_id, skill_id, proficiency, now),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.close()
        raise HTTPException(409, "Skill already assigned to agent") from None
    db.close()
    _log(agent_id, None, "skill_assigned", {"skill_id": skill_id, "proficiency": proficiency})
    return {"agent_id": agent_id, "skill_id": skill_id, "proficiency": proficiency}


@_router.get("/agents/{agent_id}/skills")
def get_agent_skills(agent_id: str):
    db = get_db()
    agent = db.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        db.close()
        raise HTTPException(404, "Agent not found") from None
    rows = db.execute(
        "SELECT as2.*, s.name as skill_name, s.category FROM agent_skills as2 JOIN skills s ON as2.skill_id=s.id WHERE as2.agent_id=?",
        (agent_id,),
    ).fetchall()
    db.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "skill_id": r["skill_id"],
                "skill_name": r["skill_name"],
                "category": r["category"],
                "proficiency": r["proficiency"],
                "acquired_at": r["acquired_at"],
            },
        )
    return {"skills": result, "total": len(result)}


# ── Execution Logs ───────────────────────────────────────────────────────────


@_router.get("/logs")
def get_logs(agent_id: str | None = None, task_id: str | None = None, limit: int = 100):
    db = get_db()
    query = "SELECT * FROM execution_logs WHERE 1=1"
    params: list[Any] = []
    if agent_id:
        query += " AND agent_id=?"
        params.append(agent_id)
    if task_id:
        query += " AND task_id=?"
        params.append(task_id)
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = db.execute(query, params).fetchall()
    db.close()
    result = []
    for r in rows:
        result.append(
            {
                "id": r["id"],
                "agent_id": r["agent_id"],
                "task_id": r["task_id"],
                "action": r["action"],
                "details": json.loads(r["details"]),
                "created_at": r["created_at"],
            },
        )
    return {"logs": result, "total": len(result)}


# ── Stats ────────────────────────────────────────────────────────────────────


@_router.get("/stats")
def get_stats():
    db = get_db()
    agents_total = db.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
    agents_active = db.execute("SELECT COUNT(*) FROM agents WHERE status='active'").fetchone()[0]
    tasks_total = db.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    tasks_pending = db.execute("SELECT COUNT(*) FROM tasks WHERE status='pending'").fetchone()[0]
    tasks_running = db.execute(
        "SELECT COUNT(*) FROM tasks WHERE status='assigned' OR status='running'",
    ).fetchone()[0]
    tasks_completed = db.execute("SELECT COUNT(*) FROM tasks WHERE status='completed'").fetchone()[
        0
    ]
    tasks_failed = db.execute("SELECT COUNT(*) FROM tasks WHERE status='failed'").fetchone()[0]
    delegations_total = db.execute("SELECT COUNT(*) FROM delegations").fetchone()[0]
    skills_total = db.execute("SELECT COUNT(*) FROM skills").fetchone()[0]
    logs_total = db.execute("SELECT COUNT(*) FROM execution_logs").fetchone()[0]
    db.close()
    return {
        "service": SERVICE_NAME,
        "port": PORT,
        "agents": {"total": agents_total, "active": agents_active},
        "tasks": {
            "total": tasks_total,
            "pending": tasks_pending,
            "running": tasks_running,
            "completed": tasks_completed,
            "failed": tasks_failed,
        },
        "delegations": delegations_total,
        "skills": skills_total,
        "execution_logs": logs_total,
    }


def _get_stats() -> dict:
    """Return basic service stats for real-time endpoints."""
    try:
        # Try calling the /stats handler synchronously if possible
        import inspect

        stats_fn = get_stats
        if not inspect.iscoroutinefunction(stats_fn):
            result = stats_fn()
            if isinstance(result, dict):
                result["service"] = SERVICE_NAME
                result["port"] = PORT
                return result
    except Exception:
        pass
    return {"service": SERVICE_NAME, "port": PORT}


# ── Real-time endpoints (Phase 21) ────────────────────────────────

_connected_ws: list[WebSocket] = []


@app.websocket("/ws")
async def _ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    _connected_ws.append(ws)
    try:
        # Push initial state
        stats = _get_stats()
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
            stats = _get_stats()
            yield {"event": "stats", "data": json.dumps(stats)}
            await asyncio.sleep(5)

    return EventSourceResponse(_generator())


@_router.get("/dashboard/summary")
async def _dashboard_summary():
    """Aggregated summary optimized for dashboard consumption."""
    stats = _get_stats()
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


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=PORT)
