"""
Trancendos the-lab — Code Creation Platform
============================================
Code snippet store with sandboxed subprocess execution.
Supports python3, node, bash (with strict allowlist).

Port: 8055  Entity: The Lab  Lead AI: The Dr. & Slime
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8055
WORKER_NAME = "the-lab"
DB_PATH = Path(__file__).parent / "data" / "lab.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")
EXEC_TIMEOUT = int(os.getenv("EXEC_TIMEOUT", "10"))

ALLOWED_LANGS = {
    "python3": ["python3", "-c"],
    "python": ["python3", "-c"],
    "node": ["node", "-e"],
    "bash": ["bash", "-c"],
}

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snippets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                language    TEXT NOT NULL,
                code        TEXT NOT NULL,
                description TEXT,
                tags        TEXT DEFAULT '[]',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                runs        INTEGER DEFAULT 0,
                last_run_at REAL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS executions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                snippet_id  INTEGER NOT NULL,
                stdout      TEXT,
                stderr      TEXT,
                exit_code   INTEGER,
                duration_ms INTEGER,
                ran_at      REAL NOT NULL,
                FOREIGN KEY(snippet_id) REFERENCES snippets(id)
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_snip_lang ON snippets(language)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_exec_snip ON executions(snippet_id)")
        conn.commit()


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield
    logger.info("%s shutdown", WORKER_NAME)


app = FastAPI(title="The Lab — Code Platform", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class SnippetIn(BaseModel):
    title: str
    language: str
    code: str
    description: Optional[str] = None
    tags: list[str] = []
    created_by: str = "system"


class SnippetUpdate(BaseModel):
    title: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None


class ExecIn(BaseModel):
    snippet_id: int


class InlineExecIn(BaseModel):
    language: str
    code: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@_router.get("/health")
async def health():
    with get_conn() as conn:
        snippets = conn.execute("SELECT COUNT(*) FROM snippets").fetchone()[0]
        runs = conn.execute("SELECT COUNT(*) FROM executions").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Lab", "lead_ai": "The Dr. & Slime"},
        "snippets": snippets,
        "total_runs": runs,
    }


@_router.get("/metrics")
async def metrics():
    uptime = time.time() - _start_time
    return (
        f"# HELP requests_total Total requests\n"
        f"# TYPE requests_total counter\n"
        f"requests_total {_req_count}\n"
        f"# HELP errors_total Total errors\n"
        f"# TYPE errors_total counter\n"
        f"errors_total {_err_count}\n"
        f"# HELP uptime_seconds Uptime\n"
        f"# TYPE uptime_seconds gauge\n"
        f"uptime_seconds {uptime:.2f}\n"
    )


@_router.post("/snippets", status_code=201)
async def create_snippet(body: SnippetIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.language not in ALLOWED_LANGS:
        raise HTTPException(status_code=400, detail=f"Language not supported. Allowed: {list(ALLOWED_LANGS)}")
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO snippets (title, language, code, description, tags, created_by, created_at) VALUES (?,?,?,?,?,?,?)",
            (body.title, body.language, body.code, body.description, json.dumps(body.tags), body.created_by, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM snippets WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/snippets")
async def list_snippets(
    language: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if language:
        clauses.append("language = ?"); params.append(language)
    if q:
        clauses.append("(title LIKE ? OR description LIKE ? OR code LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM snippets {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM snippets {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "snippets": [dict(r) for r in rows]}


@_router.get("/snippets/{snippet_id}")
async def get_snippet(snippet_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM snippets WHERE id=?", (snippet_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return dict(row)


@_router.put("/snippets/{snippet_id}")
async def update_snippet(snippet_id: int, body: SnippetUpdate, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM snippets WHERE id=?", (snippet_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Snippet not found")
        updates = {}
        if body.title is not None: updates["title"] = body.title
        if body.code is not None: updates["code"] = body.code
        if body.description is not None: updates["description"] = body.description
        if body.tags is not None: updates["tags"] = json.dumps(body.tags)
        if updates:
            set_clause = ", ".join(f"{k}=?" for k in updates)
            conn.execute(f"UPDATE snippets SET {set_clause} WHERE id=?", list(updates.values()) + [snippet_id])
            conn.commit()
        row = conn.execute("SELECT * FROM snippets WHERE id=?", (snippet_id,)).fetchone()
    return dict(row)


@_router.delete("/snippets/{snippet_id}", status_code=204)
async def delete_snippet(snippet_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        deleted = conn.execute("DELETE FROM snippets WHERE id=?", (snippet_id,)).rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Snippet not found")


@_router.post("/execute")
async def execute_snippet(body: ExecIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM snippets WHERE id=?", (body.snippet_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Snippet not found")
    return await _run_code(row["language"], row["code"], row["id"])


@_router.post("/execute/inline")
async def execute_inline(body: InlineExecIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.language not in ALLOWED_LANGS:
        raise HTTPException(status_code=400, detail=f"Language not supported. Allowed: {list(ALLOWED_LANGS)}")
    return await _run_code(body.language, body.code, None)


async def _run_code(language: str, code: str, snippet_id: Optional[int]) -> dict:
    cmd = ALLOWED_LANGS[language] + [code]
    start = time.time()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=EXEC_TIMEOUT, shell=False
        )
        duration_ms = int((time.time() - start) * 1000)
        stdout, stderr, exit_code = result.stdout[:8192], result.stderr[:4096], result.returncode
    except subprocess.TimeoutExpired:
        duration_ms = EXEC_TIMEOUT * 1000
        stdout, stderr, exit_code = "", f"Execution timed out after {EXEC_TIMEOUT}s", 124
    except Exception as exc:
        duration_ms = 0
        stdout, stderr, exit_code = "", str(exc), 1

    now = time.time()
    if snippet_id:
        with get_conn() as conn:
            conn.execute(
                "INSERT INTO executions (snippet_id, stdout, stderr, exit_code, duration_ms, ran_at) VALUES (?,?,?,?,?,?)",
                (snippet_id, stdout, stderr, exit_code, duration_ms, now),
            )
            conn.execute("UPDATE snippets SET runs=runs+1, last_run_at=? WHERE id=?", (now, snippet_id))
            conn.commit()

    return {
        "snippet_id": snippet_id,
        "language": language,
        "stdout": stdout,
        "stderr": stderr,
        "exit_code": exit_code,
        "duration_ms": duration_ms,
        "ran_at": now,
    }


@_router.get("/executions/{snippet_id}")
async def list_executions(snippet_id: int, limit: int = 20, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM executions WHERE snippet_id=? ORDER BY id DESC LIMIT ?",
            (snippet_id, limit),
        ).fetchall()
    return [dict(r) for r in rows]


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
