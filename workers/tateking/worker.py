"""
Trancendos tateking — Video Creation & Editing Platform
========================================================
Video project management, FFmpeg job scheduling, clip metadata store.
Zero-cost: FFmpeg integration (must be installed), no paid video APIs.

Port: 8066  Entity: TateKing  Lead AI: Benji Tate & Sam King
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

WORKER_PORT = 8066
WORKER_NAME = "tateking"
DB_PATH = Path(__file__).parent / "data" / "tateking.db"
MEDIA_DIR = Path(__file__).parent / "data" / "media"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

ALLOWED_FFMPEG_OPS = {
    "convert": "Convert video format",
    "trim": "Trim video to start/end timestamps",
    "compress": "Compress video (reduce file size)",
    "extract_audio": "Extract audio track",
    "thumbnail": "Extract thumbnail at timestamp",
    "concat": "Concatenate video files",
    "resize": "Resize video resolution",
}


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                status      TEXT DEFAULT 'draft',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS clips (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER,
                title       TEXT NOT NULL,
                file_path   TEXT,
                source_url  TEXT,
                duration_s  REAL,
                resolution  TEXT,
                format      TEXT,
                file_size   INTEGER DEFAULT 0,
                tags        TEXT DEFAULT '[]',
                added_at    REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS jobs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                clip_id     INTEGER,
                project_id  INTEGER,
                operation   TEXT NOT NULL,
                params      TEXT DEFAULT '{}',
                status      TEXT DEFAULT 'pending',
                output_path TEXT,
                error       TEXT,
                duration_ms INTEGER,
                created_at  REAL NOT NULL,
                completed_at REAL,
                FOREIGN KEY(clip_id) REFERENCES clips(id)
            );
            CREATE INDEX IF NOT EXISTS idx_clips_project ON clips(project_id);
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    ffmpeg_ok = _ffmpeg_available()
    logger.info(
        "%s starting on port %d — FFmpeg: %s",
        WORKER_NAME,
        WORKER_PORT,
        "available" if ffmpeg_ok else "NOT FOUND",
    )
    yield


app = FastAPI(title="TateKing — Video Platform", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class ProjectIn(BaseModel):
    title: str
    description: Optional[str] = None
    created_by: str = "system"


class ClipIn(BaseModel):
    title: str
    project_id: Optional[int] = None
    source_url: Optional[str] = None
    file_path: Optional[str] = None
    duration_s: Optional[float] = None
    resolution: Optional[str] = None
    format: Optional[str] = None
    tags: list[str] = []


class FFmpegJobIn(BaseModel):
    clip_id: int
    operation: str
    params: dict = {}


@_router.get("/health")
async def health():
    with get_conn() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        clips = conn.execute("SELECT COUNT(*) FROM clips").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "TateKing", "lead_ai": "Benji Tate & Sam King"},
        "ffmpeg_available": _ffmpeg_available(),
        "projects": projects,
        "clips": clips,
    }


@_router.get("/metrics")
async def metrics():
    uptime = time.time() - _start_time
    return (
        f"# HELP requests_total Total requests\n# TYPE requests_total counter\n"
        f"requests_total {_req_count}\n"
        f"# HELP errors_total Total errors\n# TYPE errors_total counter\n"
        f"errors_total {_err_count}\n"
        f"# HELP uptime_seconds Uptime\n# TYPE uptime_seconds gauge\n"
        f"uptime_seconds {uptime:.2f}\n"
    )


@_router.post("/projects", status_code=201)
async def create_project(body: ProjectIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (title, description, created_by, created_at, updated_at) VALUES (?,?,?,?,?)",
            (body.title, body.description, body.created_by, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/projects")
async def list_projects(
    limit: int = Query(50, le=500), x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM projects ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


@_router.post("/clips", status_code=201)
async def add_clip(body: ClipIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO clips (project_id, title, source_url, file_path, duration_s, resolution, format, tags, added_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                body.project_id,
                body.title,
                body.source_url,
                body.file_path,
                body.duration_s,
                body.resolution,
                body.format,
                json.dumps(body.tags),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM clips WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/clips")
async def list_clips(
    project_id: Optional[int] = None,
    limit: int = Query(100, le=1000),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if project_id:
        clauses.append("project_id=?")
        params.append(project_id)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM clips {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.post("/jobs", status_code=201)
async def create_ffmpeg_job(body: FFmpegJobIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.operation not in ALLOWED_FFMPEG_OPS:
        raise HTTPException(
            status_code=400, detail=f"Unknown operation. Allowed: {list(ALLOWED_FFMPEG_OPS)}"
        )
    now = time.time()
    with get_conn() as conn:
        clip = conn.execute("SELECT * FROM clips WHERE id=?", (body.clip_id,)).fetchone()
        if not clip:
            raise HTTPException(status_code=404, detail="Clip not found")
        cur = conn.execute(
            "INSERT INTO jobs (clip_id, project_id, operation, params, status, created_at) VALUES (?,?,?,?,?,?)",
            (
                body.clip_id,
                clip["project_id"],
                body.operation,
                json.dumps(body.params),
                "queued",
                now,
            ),
        )
        conn.commit()
        job_id = cur.lastrowid
    return {
        "id": job_id,
        "clip_id": body.clip_id,
        "operation": body.operation,
        "status": "queued",
        "created_at": now,
        "note": "FFmpeg job queued. Execute via POST /jobs/{id}/run",
    }


@_router.post("/jobs/{job_id}/run")
async def run_ffmpeg_job(job_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if not _ffmpeg_available():
        raise HTTPException(status_code=503, detail="FFmpeg not available — install ffmpeg")
    with get_conn() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        clip = conn.execute("SELECT * FROM clips WHERE id=?", (job["clip_id"],)).fetchone()

    op = job["operation"]
    params = json.loads(job["params"])
    input_path = clip["file_path"] if clip["file_path"] else None

    if not input_path or not Path(input_path).exists():
        with get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', error=? WHERE id=?",
                ("Input file not found", job_id),
            )
            conn.commit()
        raise HTTPException(status_code=400, detail="Clip file_path not found on disk")

    output_path = str(MEDIA_DIR / f"job_{job_id}_output")
    start = time.time()
    cmd = None

    if op == "thumbnail":
        ts = params.get("timestamp", "00:00:01")
        output_path += ".jpg"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-ss", ts, "-vframes", "1", output_path]
    elif op == "extract_audio":
        output_path += ".mp3"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vn",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-b:a",
            "192k",
            output_path,
        ]
    elif op == "compress":
        output_path += ".mp4"
        crf = params.get("crf", "28")
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-vcodec",
            "libx264",
            "-crf",
            str(crf),
            output_path,
        ]
    elif op == "trim":
        start_t = params.get("start", "0")
        end_t = params.get("end", "10")
        output_path += ".mp4"
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            input_path,
            "-ss",
            start_t,
            "-to",
            end_t,
            "-c",
            "copy",
            output_path,
        ]
    elif op == "resize":
        w, h = params.get("width", 1280), params.get("height", 720)
        output_path += ".mp4"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", f"scale={w}:{h}", output_path]
    else:
        raise HTTPException(status_code=400, detail=f"FFmpeg command not implemented for: {op}")

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, shell=False)
        duration_ms = int((time.time() - start) * 1000)
        if result.returncode == 0:
            with get_conn() as conn:
                conn.execute(
                    "UPDATE jobs SET status='completed', output_path=?, duration_ms=?, completed_at=? WHERE id=?",
                    (output_path, duration_ms, time.time(), job_id),
                )
                conn.commit()
            return {
                "job_id": job_id,
                "status": "completed",
                "output_path": output_path,
                "duration_ms": duration_ms,
            }
        else:
            err = result.stderr[-1000:]
            with get_conn() as conn:
                conn.execute("UPDATE jobs SET status='failed', error=? WHERE id=?", (err, job_id))
                conn.commit()
            raise HTTPException(status_code=500, detail=f"FFmpeg failed: {err}")
    except subprocess.TimeoutExpired as exc:
        with get_conn() as conn:
            conn.execute("UPDATE jobs SET status='failed', error='Timeout' WHERE id=?", (job_id,))
            conn.commit()
        raise HTTPException(status_code=408, detail="FFmpeg job timed out") from exc


@_router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/operations")
async def list_operations(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return {"operations": [{"name": k, "description": v} for k, v in ALLOWED_FFMPEG_OPS.items()]}


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
