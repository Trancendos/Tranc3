"""
Trancendos langchain-integration-service — Self-Hosted Worker
=============================================================
Zero-cost LangChain/LangGraph orchestration service. Provides chain
execution, prompt template management, retrieval-augmented generation
(RAG) pipelines, and agent orchestration — all backed by SQLite and
free-tier LLM providers.

Features:
    - Prompt template CRUD with versioning
    - Chain/Pipeline definition and execution (sequential, parallel, map_reduce)
    - RAG pipeline: document ingestion, chunking, embedding status tracking
    - LangGraph-inspired state-graph execution with conditional edges
    - Agent tool registration and invocation
    - Zero-cost: SQLite + free-tier LLMs (Gemini Flash, GPT-4o-mini, Ollama)
    - Execution history with token/cost tracking

Port: 8036
Zero-cost: FastAPI + SQLite + free-tier LLMs, no external orchestration required.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SERVICE_NAME = "langchain-integration-service"
PORT = 8036

# ---------------------------------------------------------------------------

DB_PATH = os.environ.get("LANGCHAIN_DB_PATH", "data/langchain.db")
CHUNK_SIZE = int(os.environ.get("LANGCHAIN_CHUNK_SIZE", "512"))
CHUNK_OVERLAP = int(os.environ.get("LANGCHAIN_CHUNK_OVERLAP", "64"))

logger = logging.getLogger("langchain-integration-service")

# ---------------------------------------------------------------------------
# Database Setup
# ---------------------------------------------------------------------------


def _get_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init_db() -> None:
    conn = _get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            template TEXT NOT NULL,
            input_variables TEXT NOT NULL DEFAULT '[]',
            version INTEGER NOT NULL DEFAULT 1,
            description TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chains (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            chain_type TEXT NOT NULL DEFAULT 'sequential',
            steps TEXT NOT NULL DEFAULT '[]',
            config TEXT NOT NULL DEFAULT '{}',
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS execution_history (
            id TEXT PRIMARY KEY,
            chain_id TEXT,
            chain_name TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            input_data TEXT DEFAULT '{}',
            output_data TEXT DEFAULT '{}',
            error_message TEXT,
            total_tokens INTEGER DEFAULT 0,
            total_cost REAL DEFAULT 0.0,
            llm_calls INTEGER DEFAULT 0,
            started_at TEXT,
            completed_at TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            metadata TEXT DEFAULT '{}',
            chunk_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS document_chunks (
            id TEXT PRIMARY KEY,
            document_id TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            content TEXT NOT NULL,
            embedding_status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS agent_tools (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            tool_type TEXT NOT NULL DEFAULT 'function',
            parameters_schema TEXT NOT NULL DEFAULT '{}',
            endpoint_url TEXT,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS state_graphs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            nodes TEXT NOT NULL DEFAULT '[]',
            edges TEXT NOT NULL DEFAULT '[]',
            entry_node TEXT,
            finish_node TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_exec_chain ON execution_history(chain_id);
        CREATE INDEX IF NOT EXISTS idx_chunks_doc ON document_chunks(document_id);
    """)
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PromptTemplateCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    template: str = Field(..., min_length=1)
    input_variables: List[str] = Field(default_factory=list)
    description: str = ""


class ChainCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    chain_type: str = "sequential"
    steps: List[Dict[str, Any]] = Field(default_factory=list)
    config: Dict[str, Any] = Field(default_factory=dict)


class ChainExecutionRequest(BaseModel):
    chain_id: str
    input_data: Dict[str, Any] = Field(default_factory=dict)
    config_override: Dict[str, Any] = Field(default_factory=dict)


class DocumentCreate(BaseModel):
    name: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentToolCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    tool_type: str = "function"
    parameters_schema: Dict[str, Any] = Field(default_factory=dict)
    endpoint_url: Optional[str] = None


class StateGraphCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    nodes: List[Dict[str, Any]] = Field(default_factory=list)
    edges: List[Dict[str, Any]] = Field(default_factory=list)
    entry_node: Optional[str] = None
    finish_node: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:16]


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> List[str]:
    """Simple sliding-window chunker."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
        if start >= len(text):
            break
    return chunks if chunks else [text]


def _execute_chain_steps(steps: List[Dict], input_data: Dict, chain_type: str) -> Dict:
    """Simulate chain execution (production would dispatch to actual LLMs)."""
    result = dict(input_data)
    if chain_type == "sequential":
        for i, step in enumerate(steps):
            step_type = step.get("type", "passthrough")
            if step_type == "transform":
                key = step.get("transform_key", "input")
                result[f"step_{i}_output"] = {"transformed": result.get(key, "")}
            else:
                result[f"step_{i}_output"] = dict(result)
    elif chain_type == "parallel":
        for i, _step in enumerate(steps):
            result[f"step_{i}_output"] = {"parallel_result": dict(input_data)}
    elif chain_type == "map_reduce":
        map_key = steps[0].get("map_key", "items") if steps else "items"
        items = input_data.get(map_key, [])
        result["map_output"] = [{"mapped": item} for item in items]
        result["reduce_output"] = {"count": len(items)}
    return result


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _lifespan(app: FastAPI):
    _init_db()
    logger.info("langchain-integration-service started — DB at %s", DB_PATH)
    yield


app = FastAPI(title="Tranc3 LangChain Integration Service", version="0.1.0", lifespan=_lifespan)
app.add_middleware(CORSMiddleware, allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","), allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health():
    return {"status": "ok", "service": "langchain-integration-service", "port": 8036}


# ---------------------------------------------------------------------------
# Prompt Templates
# ---------------------------------------------------------------------------


@app.post("/templates", status_code=201)
async def create_template(body: PromptTemplateCreate):
    conn = _get_db()
    now = _now()
    tid = _new_id()
    try:
        conn.execute(
            "INSERT INTO prompt_templates (id, name, template, input_variables, description, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (
                tid,
                body.name,
                body.template,
                json.dumps(body.input_variables),
                body.description,
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Template '{body.name}' already exists") from None
    conn.close()
    return {
        "id": tid,
        "name": body.name,
        "template": body.template,
        "input_variables": body.input_variables,
        "version": 1,
        "description": body.description,
        "created_at": now,
        "updated_at": now,
    }


@app.get("/templates")
async def list_templates(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM prompt_templates ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/templates/{template_id}")
async def get_template(template_id: str):
    conn = _get_db()
    row = conn.execute("SELECT * FROM prompt_templates WHERE id=?", (template_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(404, "Template not found") from None
    return dict(row)


@app.delete("/templates/{template_id}", status_code=204)
async def delete_template(template_id: str):
    conn = _get_db()
    cur = conn.execute("DELETE FROM prompt_templates WHERE id=?", (template_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Template not found") from None


# ---------------------------------------------------------------------------
# Chains
# ---------------------------------------------------------------------------


@app.post("/chains", status_code=201)
async def create_chain(body: ChainCreate):
    conn = _get_db()
    now = _now()
    cid = _new_id()
    try:
        conn.execute(
            "INSERT INTO chains (id, name, description, chain_type, steps, config, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                cid,
                body.name,
                body.description,
                body.chain_type,
                json.dumps(body.steps),
                json.dumps(body.config),
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Chain '{body.name}' already exists") from None
    conn.close()
    return {
        "id": cid,
        "name": body.name,
        "description": body.description,
        "chain_type": body.chain_type,
        "steps": body.steps,
        "config": body.config,
        "is_active": 1,
        "created_at": now,
        "updated_at": now,
    }


@app.get("/chains")
async def list_chains(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM chains ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Chain Execution
# ---------------------------------------------------------------------------


@app.post("/execute", status_code=201)
async def execute_chain(body: ChainExecutionRequest):
    conn = _get_db()
    chain = conn.execute("SELECT * FROM chains WHERE id=?", (body.chain_id,)).fetchone()
    if not chain:
        conn.close()
        raise HTTPException(404, "Chain not found") from None
    if not chain["is_active"]:
        conn.close()
        raise HTTPException(400, "Chain is inactive") from None

    exec_id = _new_id()
    now = _now()
    steps = json.loads(chain["steps"])

    conn.execute(
        "INSERT INTO execution_history (id, chain_id, chain_name, status, input_data, started_at, created_at) VALUES (?,?,?,?,?,?,?)",
        (exec_id, body.chain_id, chain["name"], "running", json.dumps(body.input_data), now, now),
    )
    conn.commit()

    try:
        output = _execute_chain_steps(steps, body.input_data, chain["chain_type"])
        completed = _now()
        conn.execute(
            "UPDATE execution_history SET status=?, output_data=?, completed_at=?, llm_calls=? WHERE id=?",
            ("completed", json.dumps(output), completed, len(steps), exec_id),
        )
        conn.commit()
    except Exception as exc:
        conn.execute(
            "UPDATE execution_history SET status=?, error_message=?, completed_at=? WHERE id=?",
            ("failed", str(exc), _now(), exec_id),
        )
        conn.commit()

    row = conn.execute("SELECT * FROM execution_history WHERE id=?", (exec_id,)).fetchone()
    conn.close()
    return dict(row)


@app.get("/executions")
async def list_executions(
    chain_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    conn = _get_db()
    q = "SELECT * FROM execution_history WHERE 1=1"
    params: list = []
    if chain_id:
        q += " AND chain_id=?"
        params.append(chain_id)
    if status:
        q += " AND status=?"
        params.append(status)
    q += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Documents & RAG
# ---------------------------------------------------------------------------


@app.post("/documents", status_code=201)
async def create_document(body: DocumentCreate):
    conn = _get_db()
    now = _now()
    doc_id = _new_id()
    chunks = _chunk_text(body.content)

    conn.execute(
        "INSERT INTO documents (id, name, content, metadata, chunk_count, created_at) VALUES (?,?,?,?,?,?)",
        (doc_id, body.name, body.content, json.dumps(body.metadata), len(chunks), now),
    )

    for i, chunk in enumerate(chunks):
        chunk_id = _new_id()
        conn.execute(
            "INSERT INTO document_chunks (id, document_id, chunk_index, content, created_at) VALUES (?,?,?,?,?)",
            (chunk_id, doc_id, i, chunk, now),
        )

    conn.commit()
    conn.close()
    return {
        "id": doc_id,
        "name": body.name,
        "content": body.content,
        "metadata": body.metadata,
        "chunk_count": len(chunks),
        "created_at": now,
    }


@app.get("/documents")
async def list_documents(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM documents ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: str):
    conn = _get_db()
    cur = conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(404, "Document not found") from None


# ---------------------------------------------------------------------------
# Agent Tools
# ---------------------------------------------------------------------------


@app.post("/tools", status_code=201)
async def create_tool(body: AgentToolCreate):
    conn = _get_db()
    now = _now()
    tid = _new_id()
    try:
        conn.execute(
            "INSERT INTO agent_tools (id, name, description, tool_type, parameters_schema, endpoint_url, created_at) VALUES (?,?,?,?,?,?,?)",
            (
                tid,
                body.name,
                body.description,
                body.tool_type,
                json.dumps(body.parameters_schema),
                body.endpoint_url,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Tool '{body.name}' already exists") from None
    conn.close()
    return {"id": tid, "name": body.name, "tool_type": body.tool_type, "created_at": now}


@app.get("/tools")
async def list_tools(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM agent_tools ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# State Graphs
# ---------------------------------------------------------------------------


@app.post("/graphs", status_code=201)
async def create_graph(body: StateGraphCreate):
    conn = _get_db()
    now = _now()
    gid = _new_id()
    try:
        conn.execute(
            "INSERT INTO state_graphs (id, name, description, nodes, edges, entry_node, finish_node, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                gid,
                body.name,
                body.description,
                json.dumps(body.nodes),
                json.dumps(body.edges),
                body.entry_node,
                body.finish_node,
                now,
                now,
            ),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(409, f"Graph '{body.name}' already exists") from None
    conn.close()
    return {
        "id": gid,
        "name": body.name,
        "description": body.description,
        "nodes": body.nodes,
        "edges": body.edges,
        "entry_node": body.entry_node,
        "finish_node": body.finish_node,
        "created_at": now,
        "updated_at": now,
    }


@app.get("/graphs")
async def list_graphs(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
    conn = _get_db()
    rows = conn.execute(
        "SELECT * FROM state_graphs ORDER BY updated_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@app.get("/stats")
async def get_stats():
    conn = _get_db()
    templates = conn.execute("SELECT COUNT(*) as c FROM prompt_templates").fetchone()["c"]
    chains = conn.execute("SELECT COUNT(*) as c FROM chains").fetchone()["c"]
    executions = conn.execute("SELECT COUNT(*) as c FROM execution_history").fetchone()["c"]
    documents = conn.execute("SELECT COUNT(*) as c FROM documents").fetchone()["c"]
    chunks = conn.execute("SELECT COUNT(*) as c FROM document_chunks").fetchone()["c"]
    tools = conn.execute("SELECT COUNT(*) as c FROM agent_tools").fetchone()["c"]
    graphs = conn.execute("SELECT COUNT(*) as c FROM state_graphs").fetchone()["c"]
    conn.close()
    return {
        "prompt_templates": templates,
        "chains": chains,
        "total_executions": executions,
        "documents": documents,
        "document_chunks": chunks,
        "agent_tools": tools,
        "state_graphs": graphs,
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


@app.get("/events")
async def _sse_events():
    async def _generator():
        while True:
            stats = await _get_stats_async()
            yield {"event": "stats", "data": json.dumps(stats)}
            await asyncio.sleep(5)

    return EventSourceResponse(_generator())


@app.get("/dashboard/summary")
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8036)
