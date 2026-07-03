"""
Trancendos imaginarium — Omni-Creative Masterpiece Wizard
=========================================================
Orchestrates Sashas Photo Studio, TateKing, TranceFlow, The Studio, and Warp Radio.
Accepts high-level creative briefs, fans out to sub-services, aggregates results.

Port: 8064  Entity: Imaginarium  Lead AI: Voxx
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = int(os.getenv("PORT", "8064"))
WORKER_NAME = "imaginarium"
DB_PATH = Path(__file__).parent / "data" / "imaginarium.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

# Sub-service endpoints (all self-hosted, zero-cost)
SERVICE_URLS = {
    "photo_studio": os.getenv("PHOTO_STUDIO_URL", "http://localhost:8051"),
    "warp_radio": os.getenv("WARP_RADIO_URL", "http://localhost:8057"),
    "the_studio": os.getenv("THE_STUDIO_URL", "http://localhost:8065"),
    "tateking": os.getenv("TATEKING_URL", "http://localhost:8066"),
    "tranceflow": os.getenv("TRANCEFLOW_URL", "http://localhost:8067"),
}

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
            CREATE TABLE IF NOT EXISTS projects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                brief       TEXT NOT NULL,
                project_type TEXT DEFAULT 'mixed',
                status      TEXT DEFAULT 'pending',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                completed_at REAL,
                sub_tasks   TEXT DEFAULT '[]',
                results     TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS templates (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                description TEXT,
                project_type TEXT NOT NULL,
                config      TEXT DEFAULT '{}',
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
        """)
        # Seed default templates
        default_templates = [
            (
                "Album Cover",
                "Music album artwork + playlist creation",
                "music_visual",
                json.dumps(
                    {"image": {"width": 1000, "height": 1000, "model": "flux"}, "playlist": True}
                ),
            ),
            (
                "Video Thumbnail",
                "Video thumbnail + metadata",
                "video_image",
                json.dumps(
                    {"image": {"width": 1280, "height": 720, "model": "flux"}, "video": True}
                ),
            ),
            (
                "Game Asset Pack",
                "3D models + textures + sound effects",
                "game_assets",
                json.dumps({"tranceflow": True, "image": {"width": 512, "height": 512}}),
            ),
            (
                "Brand Kit",
                "Logo + hero image + brand soundtrack",
                "brand",
                json.dumps({"image": {"width": 800, "height": 800}, "playlist": True}),
            ),
        ]
        for tmpl in default_templates:
            try:
                conn.execute(
                    "INSERT OR IGNORE INTO templates (name, description, project_type, config, created_at) VALUES (?,?,?,?,?)",
                    (*tmpl, time.time()),
                )
            except Exception:
                pass
        conn.commit()


async def _fan_out_creation(project_id: int, brief: str, project_type: str) -> None:
    """Background: call sub-services and aggregate results."""
    results = {}
    headers = {"X-Internal-Secret": INTERNAL_SECRET, "Content-Type": "application/json"}

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            # Always try image generation for visual projects
            if project_type in ("mixed", "music_visual", "video_image", "brand", "game_assets"):
                try:
                    resp = await client.post(
                        f"{SERVICE_URLS['photo_studio']}/generate",
                        json={
                            "prompt": brief,
                            "width": 512,
                            "height": 512,
                            "generated_by": "imaginarium",
                        },
                        headers=headers,
                    )
                    if resp.status_code == 202:
                        results["image_job"] = resp.json()
                except Exception as exc:
                    results["image_error"] = str(exc)
    except ImportError:
        results["note"] = "httpx not installed — install for fan-out orchestration"

    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET status='completed', completed_at=?, results=? WHERE id=?",
            (now, json.dumps(results), project_id),
        )
        conn.commit()
    logger.info("Imaginarium project %d completed: %s", project_id, list(results.keys()))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="Imaginarium — Creative Orchestrator", version="1.0.0", lifespan=lifespan)
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
    brief: str
    project_type: str = "mixed"
    created_by: str = "system"
    sub_tasks: list[str] = []


class TemplateIn(BaseModel):
    name: str
    description: Optional[str] = None
    project_type: str
    config: dict = {}


@_router.get("/health")
async def health():
    with get_conn() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        completed = conn.execute(
            "SELECT COUNT(*) FROM projects WHERE status='completed'"
        ).fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "Imaginarium", "lead_ai": "Voxx"},
        "total_projects": projects,
        "completed_projects": completed,
        "sub_services": list(SERVICE_URLS.keys()),
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


@_router.post("/create", status_code=202)
async def create_project(
    body: ProjectIn, background_tasks: BackgroundTasks, x_internal_secret: str = Header(default="")
):
    _auth(x_internal_secret)
    if not body.brief.strip():
        raise HTTPException(status_code=400, detail="brief required")
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO projects (title, brief, project_type, status, created_by, created_at, sub_tasks) VALUES (?,?,?,?,?,?,?)",
            (
                body.title,
                body.brief,
                body.project_type,
                "pending",
                body.created_by,
                now,
                json.dumps(body.sub_tasks),
            ),
        )
        conn.commit()
        project_id = cur.lastrowid
    background_tasks.add_task(_fan_out_creation, project_id, body.brief, body.project_type)
    return {"project_id": project_id, "status": "pending", "created_at": now}


@_router.get("/projects")
async def list_projects(
    status: Optional[str] = None,
    project_type: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if status:
        clauses.append("status=?")
        params.append(status)
    if project_type:
        clauses.append("project_type=?")
        params.append(project_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM projects {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM projects {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "projects": [dict(r) for r in rows]}


@_router.get("/projects/{project_id}")
async def get_project(project_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Project not found")
    return dict(row)


@_router.get("/templates")
async def list_templates(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM templates ORDER BY name").fetchall()
    return [dict(r) for r in rows]


@_router.post("/templates", status_code=201)
async def create_template(body: TemplateIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO templates (name, description, project_type, config, created_at) VALUES (?,?,?,?,?)",
                (body.name, body.description, body.project_type, json.dumps(body.config), now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM templates WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="Template name already exists") from exc


@_router.get("/services/status")
async def services_status(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    statuses = {}
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5) as client:
            for name, url in SERVICE_URLS.items():
                try:
                    resp = await client.get(f"{url}/health")
                    statuses[name] = {"status": "up", "code": resp.status_code}
                except Exception as exc:
                    statuses[name] = {"status": "down", "error": str(exc)[:100]}
    except ImportError:
        statuses = {
            name: {"status": "unknown", "note": "httpx not installed"} for name in SERVICE_URLS
        }
    return {"services": statuses}


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
