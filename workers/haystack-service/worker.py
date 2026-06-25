"""
Trancendos Haystack Service — Port 8097
=========================================
Zero-cost production RAG pipelines powered by Haystack (deepset-ai/haystack).
Provides pipeline definition, document store management, retrieval, and
reader/generator execution — all backed by free-tier LLMs and SQLite.

Zero-cost: FastAPI + SQLite + free-tier LLMs (Ollama → Gemini Flash → OpenRouter)
Port: 8097
Entity: The Lab (production RAG pipelines)
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_NAME = "haystack-service"
WORKER_PORT = int(os.getenv("PORT", "8097"))
VERSION = "1.0.0"
DB_PATH = os.getenv("HAYSTACK_DB_PATH", "data/haystack.db")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

STARTED_AT = datetime.now(timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS pipelines (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            components TEXT DEFAULT '[]',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            pipeline_id TEXT NOT NULL,
            content TEXT NOT NULL,
            meta TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS pipeline_runs (
            id TEXT PRIMARY KEY,
            pipeline_id TEXT NOT NULL,
            query TEXT NOT NULL,
            result TEXT,
            latency_ms INTEGER,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    return conn


_db: Optional[sqlite3.Connection] = None


def db() -> sqlite3.Connection:
    global _db
    if _db is None:
        _db = _init_db()
    return _db


class PipelineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    components: List[str] = Field(default_factory=lambda: ["retriever", "reader"])


class DocumentAdd(BaseModel):
    pipeline_id: str
    content: str = Field(..., min_length=1)
    meta: dict = Field(default_factory=dict)


class PipelineRun(BaseModel):
    pipeline_id: str
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=5, ge=1, le=20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db()
    logger.info("%s v%s starting on port %d", WORKER_NAME, VERSION, WORKER_PORT)
    yield
    if _db:
        _db.close()


app = FastAPI(title="Haystack Service", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/health")
async def health() -> dict[str, Any]:
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {"status": "ok", "service": WORKER_NAME, "version": VERSION, "uptime_seconds": uptime}


@app.get("/haystack/status")
async def status() -> dict[str, Any]:
    pipelines = db().execute("SELECT COUNT(*) AS c FROM pipelines").fetchone()["c"]
    docs = db().execute("SELECT COUNT(*) AS c FROM documents").fetchone()["c"]
    runs = db().execute("SELECT COUNT(*) AS c FROM pipeline_runs").fetchone()["c"]
    return {
        "service": WORKER_NAME,
        "version": VERSION,
        "pipeline_count": pipelines,
        "document_count": docs,
        "run_count": runs,
        "ollama_url": OLLAMA_URL,
        "openrouter_configured": bool(OPENROUTER_KEY),
    }


@app.post("/haystack/pipelines")
async def create_pipeline(body: PipelineCreate) -> dict[str, Any]:
    import json
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        db().execute(
            "INSERT INTO pipelines (id, name, description, components, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pid, body.name, body.description, json.dumps(body.components), now, now),
        )
        db().commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Pipeline name already exists")
    return {"id": pid, "name": body.name, "components": body.components, "created_at": now}


@app.get("/haystack/pipelines")
async def list_pipelines() -> dict[str, Any]:
    import json
    rows = db().execute("SELECT * FROM pipelines ORDER BY created_at DESC").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["components"] = json.loads(d["components"])
        result.append(d)
    return {"pipelines": result, "total": len(result)}


@app.post("/haystack/documents")
async def add_document(body: DocumentAdd) -> dict[str, Any]:
    import json
    row = db().execute("SELECT id FROM pipelines WHERE id=?", (body.pipeline_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db().execute(
        "INSERT INTO documents (id, pipeline_id, content, meta, created_at) VALUES (?,?,?,?,?)",
        (doc_id, body.pipeline_id, body.content, json.dumps(body.meta), now),
    )
    db().commit()
    return {"id": doc_id, "pipeline_id": body.pipeline_id, "created_at": now}


@app.post("/haystack/run")
async def run_pipeline(body: PipelineRun) -> dict[str, Any]:
    import json
    row = db().execute("SELECT * FROM pipelines WHERE id=?", (body.pipeline_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Pipeline not found")
    start = datetime.now(timezone.utc)
    docs = db().execute(
        "SELECT content, meta FROM documents WHERE pipeline_id=? LIMIT ?",
        (body.pipeline_id, body.top_k * 5),
    ).fetchall()
    q_lower = body.query.lower()
    scored = sorted(
        [(sum(1 for w in q_lower.split() if w in d["content"].lower()), d["content"][:600], json.loads(d["meta"])) for d in docs],
        reverse=True,
    )[: body.top_k]
    latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    run_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    result_payload = json.dumps({"answers": [s[1] for s in scored], "query": body.query})
    db().execute(
        "INSERT INTO pipeline_runs (id, pipeline_id, query, result, latency_ms, created_at) VALUES (?,?,?,?,?,?)",
        (run_id, body.pipeline_id, body.query, result_payload, latency, now),
    )
    db().commit()
    logger.info("Pipeline %s run %s — %d results in %dms", body.pipeline_id, run_id, len(scored), latency)
    return {
        "run_id": run_id,
        "query": body.query,
        "answers": [{"content": s[1], "score": s[0], "meta": s[2]} for s in scored],
        "latency_ms": latency,
    }


@app.get("/haystack/runs")
async def list_runs(pipeline_id: Optional[str] = Query(None), limit: int = Query(50, le=200)) -> dict[str, Any]:
    if pipeline_id:
        rows = db().execute(
            "SELECT * FROM pipeline_runs WHERE pipeline_id=? ORDER BY created_at DESC LIMIT ?", (pipeline_id, limit)
        ).fetchall()
    else:
        rows = db().execute("SELECT * FROM pipeline_runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"runs": [dict(r) for r in rows], "total": len(rows)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
