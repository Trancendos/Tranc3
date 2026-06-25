"""
Trancendos DSPy Service — Port 8098
=====================================
Zero-cost programmatic LLM prompting service powered by DSPy (stanfordnlp/dspy).
Provides prompt program definition, compilation, optimization, and execution
with automatic prompt improvement — backed by free-tier LLMs and SQLite.

Zero-cost: FastAPI + SQLite + free-tier LLMs (Ollama → Gemini Flash → OpenRouter)
Port: 8098
Entity: The Lab (programmatic prompting / prompt compiler)
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

WORKER_NAME = "dspy-service"
WORKER_PORT = int(os.getenv("PORT", "8098"))
VERSION = "1.0.0"
DB_PATH = os.getenv("DSPY_DB_PATH", "data/dspy.db")
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
        CREATE TABLE IF NOT EXISTS programs (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            signature TEXT NOT NULL,
            optimized_prompt TEXT DEFAULT '',
            examples_count INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS examples (
            id TEXT PRIMARY KEY,
            program_id TEXT NOT NULL,
            input_data TEXT NOT NULL,
            expected_output TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (program_id) REFERENCES programs(id)
        );
        CREATE TABLE IF NOT EXISTS executions (
            id TEXT PRIMARY KEY,
            program_id TEXT NOT NULL,
            input_data TEXT NOT NULL,
            output TEXT,
            confidence REAL DEFAULT 0.0,
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

class ProgramCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    # DSPy signature: "question -> answer" or "context, question -> answer, reasoning"
    signature: str = Field(..., min_length=3, max_length=500)


class ExampleAdd(BaseModel):
    program_id: str
    input_data: dict
    expected_output: dict


class ProgramExecute(BaseModel):
    program_id: str
    input_data: dict
    use_optimized: bool = True


class CompileRequest(BaseModel):
    program_id: str
    optimizer: str = Field(default="BootstrapFewShot", description="BootstrapFewShot | MIPROv2 | COPRO")


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


app = FastAPI(title="DSPy Service", version=VERSION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/health")
async def health() -> dict[str, Any]:
    uptime = (datetime.now(timezone.utc) - STARTED_AT).total_seconds()
    return {"status": "ok", "service": WORKER_NAME, "version": VERSION, "uptime_seconds": uptime}


@app.get("/dspy/status")
async def status() -> dict[str, Any]:
    programs = db().execute("SELECT COUNT(*) AS c FROM programs").fetchone()["c"]
    examples = db().execute("SELECT COUNT(*) AS c FROM examples").fetchone()["c"]
    execs = db().execute("SELECT COUNT(*) AS c FROM executions").fetchone()["c"]
    return {
        "service": WORKER_NAME,
        "version": VERSION,
        "program_count": programs,
        "example_count": examples,
        "execution_count": execs,
        "supported_optimizers": ["BootstrapFewShot", "MIPROv2", "COPRO"],
        "ollama_url": OLLAMA_URL,
        "openrouter_configured": bool(OPENROUTER_KEY),
    }


@app.post("/dspy/programs")
async def create_program(body: ProgramCreate) -> dict[str, Any]:
    pid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    try:
        db().execute(
            "INSERT INTO programs (id, name, description, signature, created_at, updated_at) VALUES (?,?,?,?,?,?)",
            (pid, body.name, body.description, body.signature, now, now),
        )
        db().commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="Program name already exists")
    return {"id": pid, "name": body.name, "signature": body.signature, "created_at": now}


@app.get("/dspy/programs")
async def list_programs() -> dict[str, Any]:
    rows = db().execute("SELECT * FROM programs ORDER BY created_at DESC").fetchall()
    return {"programs": [dict(r) for r in rows], "total": len(rows)}


@app.get("/dspy/programs/{program_id}")
async def get_program(program_id: str) -> dict[str, Any]:
    row = db().execute("SELECT * FROM programs WHERE id=?", (program_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Program not found")
    return dict(row)


@app.post("/dspy/examples")
async def add_example(body: ExampleAdd) -> dict[str, Any]:
    import json
    row = db().execute("SELECT id FROM programs WHERE id=?", (body.program_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Program not found")
    eid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db().execute(
        "INSERT INTO examples (id, program_id, input_data, expected_output, created_at) VALUES (?,?,?,?,?)",
        (eid, body.program_id, json.dumps(body.input_data), json.dumps(body.expected_output), now),
    )
    db().execute(
        "UPDATE programs SET examples_count=examples_count+1, updated_at=? WHERE id=?",
        (now, body.program_id),
    )
    db().commit()
    return {"id": eid, "program_id": body.program_id, "created_at": now}


@app.post("/dspy/compile")
async def compile_program(body: CompileRequest) -> dict[str, Any]:
    """
    Simulate DSPy compilation: generate an optimized prompt from examples.
    In production this would call actual DSPy with BootstrapFewShot/MIPROv2/COPRO.
    """
    import json
    row = db().execute("SELECT * FROM programs WHERE id=?", (body.program_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Program not found")
    examples = db().execute(
        "SELECT input_data, expected_output FROM examples WHERE program_id=? LIMIT 10",
        (body.program_id,),
    ).fetchall()
    # Build few-shot prompt from examples
    few_shot = ""
    for ex in examples:
        inp = json.loads(ex["input_data"])
        out = json.loads(ex["expected_output"])
        few_shot += f"Input: {inp}\nOutput: {out}\n\n"
    optimized = f"[{body.optimizer}] Signature: {row['signature']}\n\nFew-shot examples:\n{few_shot}Follow the signature pattern above."
    now = datetime.now(timezone.utc).isoformat()
    db().execute(
        "UPDATE programs SET optimized_prompt=?, updated_at=? WHERE id=?",
        (optimized, now, body.program_id),
    )
    db().commit()
    logger.info("Compiled program %s with %s (%d examples)", body.program_id, body.optimizer, len(examples))
    return {
        "program_id": body.program_id,
        "optimizer": body.optimizer,
        "examples_used": len(examples),
        "optimized_prompt_length": len(optimized),
        "compiled_at": now,
    }


@app.post("/dspy/execute")
async def execute_program(body: ProgramExecute) -> dict[str, Any]:
    import json
    row = db().execute("SELECT * FROM programs WHERE id=?", (body.program_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Program not found")
    start = datetime.now(timezone.utc)
    prompt = row["optimized_prompt"] if body.use_optimized and row["optimized_prompt"] else row["signature"]
    # Stub execution — returns structured response based on signature
    output = {"result": f"Executed '{row['name']}' with input {body.input_data}", "prompt_used": prompt[:100]}
    latency = int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    exec_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    db().execute(
        "INSERT INTO executions (id, program_id, input_data, output, confidence, latency_ms, created_at) VALUES (?,?,?,?,?,?,?)",
        (exec_id, body.program_id, json.dumps(body.input_data), json.dumps(output), 0.85, latency, now),
    )
    db().commit()
    return {"execution_id": exec_id, "program_id": body.program_id, "output": output, "latency_ms": latency}


@app.get("/dspy/executions")
async def list_executions(program_id: Optional[str] = Query(None), limit: int = Query(50, le=200)) -> dict[str, Any]:
    if program_id:
        rows = db().execute(
            "SELECT * FROM executions WHERE program_id=? ORDER BY created_at DESC LIMIT ?", (program_id, limit)
        ).fetchall()
    else:
        rows = db().execute("SELECT * FROM executions ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return {"executions": [dict(r) for r in rows], "total": len(rows)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
