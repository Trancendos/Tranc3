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

from Dimensional.service_auth_fastapi import guard_internal_secret

WORKER_PORT = int(os.getenv("PORT") or "8064")
WORKER_NAME = "imaginarium"
DB_PATH = Path(__file__).parent / "data" / "imaginarium.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

_internal_secret_raw = os.getenv("INTERNAL_SECRET")
if (
    not _internal_secret_raw
    or not _internal_secret_raw.strip()
    or _internal_secret_raw.strip() == "dev-secret"
):
    raise RuntimeError(
        "INTERNAL_SECRET is not set (or still the default). "
        "This worker cannot start without a strong unique internal secret. "
        'Generate one: python -c "import secrets; print(secrets.token_hex(32))"'
    )
INTERNAL_SECRET: str = _internal_secret_raw.strip()

# Sub-service endpoints (all self-hosted, zero-cost).
#
# Defaults use Compose service-name DNS, not localhost. Inside a container
# `localhost` is that container, so a localhost default can never reach a
# sibling service no matter which port it names — it fails closed and silently.
# The estate's own convention is `http://<compose-service>:<port>` (26 such
# vars already in docker-compose.production.yml, e.g. LIBRARY_SERVICE_URL=
# http://library-service:8067); these now match it.
#
# Every port here was previously wrong as well, each pointing at an unrelated
# worker: 8051=hive-service, 8057=the-dutchy, 8065=observatory,
# 8066=lab-service, 8067=library-service. Ports are the compose-published
# values, which are the deployment truth.
SERVICE_URLS = {
    "photo_studio": os.getenv("PHOTO_STUDIO_URL", "http://sashas-photo-studio:8062"),
    "warp_radio": os.getenv("WARP_RADIO_URL", "http://warp-radio:8073"),
    "the_studio": os.getenv("THE_STUDIO_URL", "http://the-studio:8069"),
    "tateking": os.getenv("TATEKING_URL", "http://tateking:8061"),
    "tranceflow": os.getenv("TRANCEFLOW_URL", "http://tranceflow:8059"),
    "fabulousa": os.getenv("FABULOUSA_URL", "http://fabulousa-service:8048"),
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

            # Design is a creative discipline like the rest: a brand or mixed
            # brief opens a Fabulousa design file alongside the imagery, rather
            # than leaving the one design Location out of the fan-out.
            if project_type in ("mixed", "brand", "video_image", "game_assets"):
                try:
                    resp = await client.post(
                        f"{SERVICE_URLS['fabulousa']}/fabulousa/projects",
                        json={"name": brief[:200], "description": brief},
                        headers=headers,
                    )
                    if resp.status_code == 200:
                        results["design_project"] = resp.json()
                    else:
                        results["design_error"] = f"HTTP {resp.status_code}"
                except Exception as exc:
                    # Fabulousa answers 503 when Penpot is down. That degrades
                    # this project's design leg; it does not fail the project.
                    results["design_error"] = str(exc)
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
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", os.getenv("ALLOWED_ORIGINS", "http://localhost:3000")
        ).split(",")
        if o.strip() and o.strip() != "*"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    try:
        guard_internal_secret(
            x_internal_secret, INTERNAL_SECRET, mismatch_status=401, detail="Unauthorized"
        )
    except HTTPException:
        _err_count += 1
        raise


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


# Both filters are optional, which is four possible queries. They are written out
# in full rather than assembled from fragments: SQLite cannot bind a WHERE clause,
# so any "build the clause then interpolate" version puts an f-string in front of
# the database. Here the values are the only variable part and they are bound.
_PROJECT_QUERIES: dict[tuple[bool, bool], tuple[str, str]] = {
    (False, False): (
        "SELECT COUNT(*) FROM projects",
        "SELECT * FROM projects ORDER BY id DESC LIMIT ? OFFSET ?",
    ),
    (True, False): (
        "SELECT COUNT(*) FROM projects WHERE status=?",
        "SELECT * FROM projects WHERE status=? ORDER BY id DESC LIMIT ? OFFSET ?",
    ),
    (False, True): (
        "SELECT COUNT(*) FROM projects WHERE project_type=?",
        "SELECT * FROM projects WHERE project_type=? ORDER BY id DESC LIMIT ? OFFSET ?",
    ),
    (True, True): (
        "SELECT COUNT(*) FROM projects WHERE status=? AND project_type=?",
        "SELECT * FROM projects WHERE status=? AND project_type=? "
        "ORDER BY id DESC LIMIT ? OFFSET ?",
    ),
}


def _project_queries(
    status: Optional[str], project_type: Optional[str]
) -> tuple[str, str, list[str]]:
    """Pick the count/rows query pair and the values to bind into it."""
    count_sql, rows_sql = _PROJECT_QUERIES[(bool(status), bool(project_type))]
    params = [value for value in (status, project_type) if value]
    return count_sql, rows_sql, params


@_router.get("/projects")
async def list_projects(
    status: Optional[str] = None,
    project_type: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    count_sql, rows_sql, params = _project_queries(status, project_type)
    with get_conn() as conn:
        total = conn.execute(count_sql, params).fetchone()[0]
        rows = conn.execute(rows_sql, [*params, limit, offset]).fetchall()
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
