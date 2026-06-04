"""
Trancendos search-service — Self-Hosted Worker
===============================================
Full-text search engine built on SQLite FTS5. Supports multiple named
indices, document ingestion, full-text queries with ranking (BM25),
prefix search, and snippet highlighting.

Port: 8017
Zero-cost: FastAPI + SQLite FTS5 (built-in), no external deps.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from src.entities.health_metadata import health_entity_block

WORKER_PORT = 8017
WORKER_NAME = "search-service"
DB_PATH = Path(__file__).parent / "data" / "search.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS indices (
                name        TEXT PRIMARY KEY,
                description TEXT,
                doc_count   INTEGER NOT NULL DEFAULT 0,
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS documents (
                id          TEXT NOT NULL,
                index_name  TEXT NOT NULL,
                title       TEXT,
                body        TEXT NOT NULL,
                metadata    TEXT DEFAULT '{}',
                indexed_at  REAL NOT NULL,
                PRIMARY KEY (index_name, id)
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS fts_default USING fts5(
                id UNINDEXED,
                index_name UNINDEXED,
                title,
                body,
                content=documents,
                content_rowid=rowid,
                tokenize='porter unicode61'
            );
        """)
        conn.commit()
        # seed default index
        conn.execute(
            "INSERT OR IGNORE INTO indices (name, description, created_at) VALUES (?,?,?)",
            ("default", "Default search index", time.time()),
        )
        conn.commit()


def _ensure_index(name: str) -> None:
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM indices WHERE name = ?", (name,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Index '{name}' not found")


def _rebuild_fts(conn: sqlite3.Connection, index_name: str) -> None:
    """Rebuild FTS index for an index (called after bulk changes)."""
    conn.execute("INSERT INTO fts_default(fts_default) VALUES('rebuild')")


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class IndexCreate(BaseModel):
    name: str
    description: Optional[str] = None


class DocumentIn(BaseModel):
    id: str
    title: Optional[str] = None
    body: str
    metadata: Dict[str, Any] = {}


class BatchIndexIn(BaseModel):
    documents: List[DocumentIn]


class SearchIn(BaseModel):
    query: str
    index: str = "default"
    limit: int = Field(10, ge=1, le=100)
    offset: int = 0
    highlight: bool = False


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("search-service DB ready with FTS5")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="search-service",
    description="SQLite FTS5 full-text search engine (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
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


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    with get_conn() as conn:
        index_count = conn.execute("SELECT COUNT(*) FROM indices").fetchone()[0]
        doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    return {
        "entity": health_entity_block(8017, "search-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "indices": index_count,
        "documents": doc_count,
    }


# --- Indices ---


@_router.get("/indices")
async def list_indices():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM indices ORDER BY name").fetchall()
    return {"indices": [dict(r) for r in rows]}


@_router.post("/indices", status_code=201)
async def create_index(req: IndexCreate):
    with get_conn() as conn:
        if conn.execute("SELECT name FROM indices WHERE name = ?", (req.name,)).fetchone():
            raise HTTPException(status_code=409, detail="Index already exists")
        conn.execute(
            "INSERT INTO indices (name, description, created_at) VALUES (?,?,?)",
            (req.name, req.description, time.time()),
        )
        conn.commit()
    return {"name": req.name, "description": req.description}


@_router.delete("/indices/{name}")
async def delete_index(name: str):
    if name == "default":
        raise HTTPException(status_code=400, detail="Cannot delete the default index")
    with get_conn() as conn:
        _ensure_index(name)
        conn.execute("DELETE FROM documents WHERE index_name = ?", (name,))
        conn.execute("DELETE FROM indices WHERE name = ?", (name,))
        conn.commit()
        _rebuild_fts(conn, name)
        conn.commit()
    return {"deleted": name}


# --- Documents ---


@_router.put("/indices/{index}/documents/{doc_id}", status_code=200)
async def index_document(index: str, doc_id: str, doc: DocumentIn):
    _ensure_index(index)
    now = time.time()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT rowid FROM documents WHERE index_name=? AND id=?", (index, doc_id),
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE documents SET title=?, body=?, metadata=?, indexed_at=? WHERE index_name=? AND id=?",
                (doc.title, doc.body, json.dumps(doc.metadata), now, index, doc_id),
            )
            conn.execute("DELETE FROM fts_default WHERE rowid=?", (existing["rowid"],))
        else:
            conn.execute(
                "INSERT INTO documents (id, index_name, title, body, metadata, indexed_at) VALUES (?,?,?,?,?,?)",
                (doc_id, index, doc.title, doc.body, json.dumps(doc.metadata), now),
            )
            conn.execute("UPDATE indices SET doc_count=doc_count+1 WHERE name=?", (index,))
        row = conn.execute(
            "SELECT rowid FROM documents WHERE index_name=? AND id=?", (index, doc_id),
        ).fetchone()
        conn.execute(
            "INSERT INTO fts_default(rowid, id, index_name, title, body) VALUES (?,?,?,?,?)",
            (row["rowid"], doc_id, index, doc.title or "", doc.body),
        )
        conn.commit()
    return {"indexed": doc_id, "index": index}


@_router.post("/indices/{index}/documents/batch", status_code=201)
async def batch_index(index: str, req: BatchIndexIn):
    _ensure_index(index)
    now = time.time()
    inserted = 0
    with get_conn() as conn:
        for doc in req.documents:
            existing = conn.execute(
                "SELECT rowid FROM documents WHERE index_name=? AND id=?", (index, doc.id),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE documents SET title=?, body=?, metadata=?, indexed_at=? WHERE index_name=? AND id=?",
                    (doc.title, doc.body, json.dumps(doc.metadata), now, index, doc.id),
                )
                conn.execute("DELETE FROM fts_default WHERE rowid=?", (existing["rowid"],))
            else:
                conn.execute(
                    "INSERT INTO documents (id, index_name, title, body, metadata, indexed_at) VALUES (?,?,?,?,?,?)",
                    (doc.id, index, doc.title, doc.body, json.dumps(doc.metadata), now),
                )
                inserted += 1
            row = conn.execute(
                "SELECT rowid FROM documents WHERE index_name=? AND id=?", (index, doc.id),
            ).fetchone()
            conn.execute(
                "INSERT INTO fts_default(rowid, id, index_name, title, body) VALUES (?,?,?,?,?)",
                (row["rowid"], doc.id, index, doc.title or "", doc.body),
            )
        conn.execute("UPDATE indices SET doc_count=doc_count+? WHERE name=?", (inserted, index))
        conn.commit()
    return {"indexed": len(req.documents), "index": index}


@_router.delete("/indices/{index}/documents/{doc_id}")
async def delete_document(index: str, doc_id: str):
    _ensure_index(index)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT rowid FROM documents WHERE index_name=? AND id=?", (index, doc_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Document not found")
        conn.execute("DELETE FROM fts_default WHERE rowid=?", (row["rowid"],))
        conn.execute("DELETE FROM documents WHERE index_name=? AND id=?", (index, doc_id))
        conn.execute("UPDATE indices SET doc_count=MAX(0, doc_count-1) WHERE name=?", (index,))
        conn.commit()
    return {"deleted": doc_id, "index": index}


# --- Search ---


@_router.get("/search")
async def search(
    q: str,
    index: str = "default",
    limit: int = Query(10, ge=1, le=100),
    offset: int = 0,
    highlight: bool = False,
):
    _ensure_index(index)
    with get_conn() as conn:
        if highlight:
            rows = conn.execute(
                "SELECT d.id, d.title, d.metadata, "
                "highlight(fts_default, 3, '<mark>', '</mark>') as snippet, "
                "bm25(fts_default) as score "
                "FROM fts_default f JOIN documents d ON f.rowid = d.rowid "
                "WHERE fts_default MATCH ? AND f.index_name = ? "
                "ORDER BY score LIMIT ? OFFSET ?",
                (q, index, limit, offset),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT d.id, d.title, d.metadata, "
                "snippet(fts_default, 3, '', '', '...', 20) as snippet, "
                "bm25(fts_default) as score "
                "FROM fts_default f JOIN documents d ON f.rowid = d.rowid "
                "WHERE fts_default MATCH ? AND f.index_name = ? "
                "ORDER BY score LIMIT ? OFFSET ?",
                (q, index, limit, offset),
            ).fetchall()
    results = []
    for r in rows:
        d = dict(r)
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            pass
        results.append(d)
    return {"query": q, "index": index, "results": results, "count": len(results)}


@_router.post("/search")
async def search_post(req: SearchIn):
    return await search(req.query, req.index, req.limit, req.offset, req.highlight)


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
