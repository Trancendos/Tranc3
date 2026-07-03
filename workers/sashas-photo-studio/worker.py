"""
Trancendos sashas-photo-studio — Photo & Image Generation Centre
================================================================
Image generation via Pollinations.ai (zero-cost, no API key required).
Stores job metadata in SQLite
downloads and caches images locally.

Port: 8051  Entity: Sashas Photo Studio  Lead AI: Madam Krystal
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT") or "8051")
WORKER_NAME = "sashas-photo-studio"
DB_PATH = Path(__file__).parent / "data" / "studio.db"
IMAGE_DIR = Path(__file__).parent / "data" / "images"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
IMAGE_DIR.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")
POLLINATIONS_BASE = "https://image.pollinations.ai/prompt"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt       TEXT NOT NULL,
                width        INTEGER DEFAULT 512,
                height       INTEGER DEFAULT 512,
                model        TEXT DEFAULT 'flux',
                status       TEXT DEFAULT 'pending',
                created_at   REAL NOT NULL,
                completed_at REAL,
                image_id     INTEGER,
                error        TEXT
            );
            CREATE TABLE IF NOT EXISTS images (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                prompt       TEXT NOT NULL,
                width        INTEGER NOT NULL,
                height       INTEGER NOT NULL,
                model        TEXT NOT NULL,
                url          TEXT NOT NULL,
                local_path   TEXT,
                generated_at REAL NOT NULL,
                generated_by TEXT DEFAULT 'system',
                status       TEXT DEFAULT 'ready',
                file_size    INTEGER DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
            CREATE INDEX IF NOT EXISTS idx_images_ts ON images(generated_at);
        """)
        conn.commit()


async def _generate_image(job_id: int, prompt: str, width: int, height: int, model: str) -> None:
    """Background task: call Pollinations, download and store image."""
    encoded = urllib.parse.quote(prompt)
    url = f"{POLLINATIONS_BASE}/{encoded}?width={width}&height={height}&model={model}&nologo=true"
    now = time.time()
    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            content = resp.content
    except Exception as exc:
        with get_conn() as conn:
            conn.execute(
                "UPDATE jobs SET status='failed', completed_at=?, error=? WHERE id=?",
                (now, str(exc)[:500], job_id),
            )
            conn.commit()
        logger.error("Job %d failed: %s", job_id, exc)
        return

    local_path = IMAGE_DIR / f"job_{job_id}.png"
    local_path.write_bytes(content)

    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO images (prompt, width, height, model, url, local_path, generated_at, file_size) VALUES (?,?,?,?,?,?,?,?)",
            (prompt, width, height, model, url, str(local_path), now, len(content)),
        )
        img_id = cur.lastrowid
        conn.execute(
            "UPDATE jobs SET status='completed', completed_at=?, image_id=? WHERE id=?",
            (now, img_id, job_id),
        )
        conn.commit()
    logger.info("Job %d completed: image %d (%d bytes)", job_id, img_id, len(content))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="Sashas Photo Studio — Image Generation", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class GenerateIn(BaseModel):
    prompt: str
    width: int = 512
    height: int = 512
    model: str = "flux"
    generated_by: str = "system"


@_router.get("/health")
async def health():
    with get_conn() as conn:
        jobs = conn.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
        images = conn.execute("SELECT COUNT(*) FROM images").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "Sashas Photo Studio", "lead_ai": "Madam Krystal"},
        "total_jobs": jobs,
        "total_images": images,
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


@_router.post("/generate", status_code=202)
async def generate_image(
    body: GenerateIn, background_tasks: BackgroundTasks, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="prompt required")
    if body.width < 64 or body.width > 2048 or body.height < 64 or body.height > 2048:
        raise HTTPException(status_code=400, detail="width/height must be 64–2048")
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO jobs (prompt, width, height, model, status, created_at) VALUES (?,?,?,?,?,?)",
            (body.prompt, body.width, body.height, body.model, "pending", now),
        )
        conn.commit()
        job_id = cur.lastrowid
    background_tasks.add_task(
        _generate_image, job_id, body.prompt, body.width, body.height, body.model
    )
    return {"job_id": job_id, "status": "pending", "created_at": now}


@_router.get("/jobs/{job_id}")
async def get_job(job_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Job not found")
    return dict(row)


@_router.get("/jobs")
async def list_jobs(
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM jobs {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM jobs {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "jobs": [dict(r) for r in rows]}


@_router.get("/images")
async def list_images(
    model: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if model:
        clauses.append("model=?")
        params.append(model)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM images {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM images {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "images": [dict(r) for r in rows]}


@_router.get("/images/{image_id}/download")
async def download_image(image_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM images WHERE id=?", (image_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Image not found")
    local = Path(row["local_path"]) if row["local_path"] else None
    if local and local.exists():
        return FileResponse(str(local), media_type="image/png")
    return {"url": row["url"]}


@_router.get("/models")
async def list_models(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    return {
        "models": [
            {"id": "flux", "description": "FLUX — high quality default"},
            {"id": "turbo", "description": "Turbo — fast generation"},
            {"id": "flux-realism", "description": "FLUX Realism"},
            {"id": "flux-anime", "description": "FLUX Anime"},
            {"id": "flux-3d", "description": "FLUX 3D"},
        ]
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
