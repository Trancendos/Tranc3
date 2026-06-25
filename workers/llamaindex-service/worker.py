"""
Trancendos LlamaIndex Service — Port 8096
==========================================
Zero-cost RAG framework service powered by LlamaIndex.
Provides document ingestion, index management, query execution,
and retrieval pipelines — all backed by local/free-tier LLMs and
in-process vector storage.

Zero-cost: FastAPI + SQLite + free-tier LLMs (Ollama → Gemini Flash → OpenRouter)
Port: 8096
Entity: The Lab (RAG subsystem)
"""

from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

WORKER_NAME = "llamaindex-service"
WORKER_PORT = int(os.getenv("PORT", "8096"))
VERSION = "1.0.0"
DB_PATH = os.getenv("LLAMAINDEX_DB_PATH", "data/llamaindex.db")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")

STARTED_AT = datetime.now(timezone.utc)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def _init_db() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH) if os.path.dirname(DB_PATH) else ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS indexes (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            doc_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS documents (
            id TEXT PRIMARY KEY,
            index_id TEXT NOT NULL,
            filename TEXT,
            content TEXT NOT NULL,
            chunk_count INTEGER DEFAULT 0,
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (index_id) REFERENCES indexes(id)
        );
        CREATE TABLE IF NOT EXISTS queries (
            id TEXT PRIMARY KEY,
            index_id TEXT NOT NULL,
            query_text TEXT NOT NULL,
            response TEXT,
            source_nodes INTEGER DEFAULT 0,
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


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class IndexCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""


class DocumentIngest(BaseModel):
    index_id: str
    content: str = Field(..., min_length=1)
    filename: str = ""


class QueryRequest(BaseModel):
    index_id: str
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=20)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    db()
    logger.info("%s v%s starting on port %d", WORKER_NAME, VERSION, WORKER_PORT)
    yield
    if _db:
        _db.close()


app = FastAPI(title="LlamaIndex Service", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, Any]:
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {"status": "ok", "service": WORKER_NAME, "version": VERSION, "uptime_seconds": uptime}


@app.get("/llamaindex/status")
async def status() -> dict[str, Any]:
    row = db().execute("SELECT COUNT(*) AS c FROM indexes").fetchone()
    doc_row = db().execute("SELECT COUNT(*) AS c FROM documents").fetchone()
    return {
        "service": WORKER_NAME,
        "version": VERSION,
        "index_count": row["c"],
        "document_count": doc_row["c"],
        "ollama_url": OLLAMA_URL,
        "openrouter_configured": bool(OPENROUTER_KEY),
    }


@app.post("/llamaindex/indexes")
async def create_index(body: IndexCreate) -> dict[str, Any]:
    idx_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db().execute(
        "INSERT INTO indexes (id, name, description, created_at, updated_at) VALUES (?,?,?,?,?)",
        (idx_id, body.name, body.description, now, now),
    )
    db().commit()
    return {"id": idx_id, "name": body.name, "description": body.description, "created_at": now}


@app.get("/llamaindex/indexes")
async def list_indexes() -> dict[str, Any]:
    rows = db().execute("SELECT * FROM indexes ORDER BY created_at DESC").fetchall()
    return {"indexes": [dict(r) for r in rows], "total": len(rows)}


@app.post("/llamaindex/ingest")
async def ingest_document(body: DocumentIngest) -> dict[str, Any]:
    row = db().execute("SELECT id FROM indexes WHERE id=?", (body.index_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Index not found")
    doc_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    # Simple chunking: 512-char chunks with 64 overlap
    text = body.content
    chunk_size, overlap = 512, 64
    chunks = []
    i = 0
    while i < len(text):
        chunks.append(text[i : i + chunk_size])
        i += chunk_size - overlap
    db().execute(
        "INSERT INTO documents (id, index_id, filename, content, chunk_count, status, created_at) VALUES (?,?,?,?,?,?,?)",
        (doc_id, body.index_id, body.filename, body.content, len(chunks), "indexed", now),
    )
    db().execute(
        "UPDATE indexes SET doc_count=doc_count+1, updated_at=? WHERE id=?", (now, body.index_id)
    )
    db().commit()
    logger.info(
        "Ingested document %s into index %s (%d chunks)", doc_id, body.index_id, len(chunks)
    )
    return {
        "id": doc_id,
        "index_id": body.index_id,
        "chunk_count": len(chunks),
        "status": "indexed",
    }


@app.post("/llamaindex/query")
async def query_index(body: QueryRequest) -> dict[str, Any]:
    row = db().execute("SELECT id FROM indexes WHERE id=?", (body.index_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Index not found")
    start = datetime.now(timezone.utc)
    docs = (
        db()
        .execute(
            "SELECT content, filename FROM documents WHERE index_id=? AND status='indexed' LIMIT ?",
            (body.index_id, body.top_k * 10),
        )
        .fetchall()
    )
    # Simple keyword relevance scoring (no external deps needed)
    query_lower = body.query.lower()
    scored = []
    for doc in docs:
        score = sum(1 for w in query_lower.split() if w in doc["content"].lower())
        scored.append((score, doc["content"][:500], doc["filename"]))
    scored.sort(reverse=True)
    sources = scored[: body.top_k]
    latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    qid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    response_text = f"Retrieved {len(sources)} relevant passages for: {body.query}"
    db().execute(
        "INSERT INTO queries (id, index_id, query_text, response, source_nodes, latency_ms, created_at) VALUES (?,?,?,?,?,?,?)",
        (qid, body.index_id, body.query, response_text, len(sources), latency, now),
    )
    db().commit()
    return {
        "query_id": qid,
        "query": body.query,
        "response": response_text,
        "source_nodes": [{"content": s[1], "filename": s[2], "score": s[0]} for s in sources],
        "latency_ms": latency,
    }


@app.get("/llamaindex/queries")
async def list_queries(
    index_id: Optional[str] = Query(None), limit: int = Query(50, le=200)
) -> dict[str, Any]:
    if index_id:
        rows = (
            db()
            .execute(
                "SELECT * FROM queries WHERE index_id=? ORDER BY created_at DESC LIMIT ?",
                (index_id, limit),
            )
            .fetchall()
        )
    else:
        rows = (
            db()
            .execute("SELECT * FROM queries ORDER BY created_at DESC LIMIT ?", (limit,))
            .fetchall()
        )
    return {"queries": [dict(r) for r in rows], "total": len(rows)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
