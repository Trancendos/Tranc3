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


# Every leg of the fan-out, as data.
#
# The previous version hardcoded two legs in an if/else and addressed four
# more Locations in SERVICE_URLS that it never called. docker-compose gives
# this worker all six URLs, so the deployment was configured for a fan-out
# the code did not perform: a `game_assets` brief produced an image and an
# empty design file, and no game.
#
# `payload` builds the sub-service's own request body from the brief. The
# bodies differ (TranceFlow wants `title`, Warp Radio wants `name`, The
# Studio wants `title` + `brief`), so each leg carries its own builder
# rather than one shape being bent to fit all six.
FAN_OUT_LEGS: tuple[dict, ...] = (
    {
        "key": "image",
        "service": "photo_studio",
        "path": "/photo/generate",
        "types": ("mixed", "music_visual", "video_image", "brand", "game_assets"),
        "payload": lambda title, brief: {
            "prompt": brief,
            "width": 512,
            "height": 512,
            "generated_by": "imaginarium",
        },
    },
    {
        "key": "design",
        "service": "fabulousa",
        "path": "/fabulousa/projects",
        "types": ("mixed", "brand", "video_image", "game_assets"),
        "payload": lambda title, brief: {"name": title[:200], "description": brief},
    },
    {
        "key": "game",
        "service": "tranceflow",
        "path": "/tranceflow/projects",
        "types": ("mixed", "game_assets"),
        # The deployed TranceFlow is main.py -> router.py, whose ProjectCreate
        # wants `name`. worker.py's GameIn wants `title` and is not in any
        # image, so a body shaped for it would 422 against the running service.
        "payload": lambda title, brief: {
            "name": title[:200],
            "description": brief,
            "project_type": "game_3d",
        },
    },
    {
        "key": "video",
        "service": "tateking",
        "path": "/video/create",
        "types": ("mixed", "video_image"),
        # VideoCreateRequest caps title at 200 characters and requires at
        # least one, so a blank brief would 422 rather than fan out.
        "payload": lambda title, brief: {
            "title": title[:200] or "Untitled",
            "description": brief,
        },
    },
    # Warp Radio has no soundtrack leg, and the omission is deliberate rather
    # than the oversight this table was written to fix. Its deployed image is
    # 54 lines of read-only routes — /now-playing and /stations — and serves
    # no POST at all. The playlist API lives in a worker.py the Dockerfile
    # does not run. A leg pointing at it would fail on every music_visual and
    # mixed brief, marking each one "partial" forever, which is a worse lie
    # than the missing leg: it would look like an outage instead of an
    # unbuilt feature. scripts/check_creative_routes.py enforces that every
    # leg below targets a route the deployed entrypoint actually serves, so
    # this one comes back the day Warp Radio ships its create endpoint.
    {
        # The Studio is the creativity centre's hub, so every brief opens a
        # workspace there regardless of discipline — that is what makes the
        # brief findable from one place afterwards.
        "key": "workspace",
        "service": "the_studio",
        "path": "/projects",
        "types": (),  # empty means every project type
        "payload": lambda title, brief: {
            "title": title[:200],
            "brief": brief,
            "created_by": "imaginarium",
        },
    },
)


def _leg_applies(leg: dict, project_type: str) -> bool:
    """A leg with no declared types runs for every brief."""
    return not leg["types"] or project_type in leg["types"]


async def _call_leg(client, leg: dict, title: str, brief: str, headers: dict) -> tuple[str, dict]:
    """Run one leg and describe what happened, successfully or not.

    Accepts any 2xx. The previous version tested `status_code == 202` against
    Sashas Photo Studio's /generate, which answers **200** — so the image
    result was discarded on every single call, and no error was recorded
    either. The project completed with an empty results block and looked
    fine. Anything outside 2xx is recorded with its status so a caller can
    tell a refusal from an outage.
    """
    url = f"{SERVICE_URLS[leg['service']]}{leg['path']}"
    try:
        resp = await client.post(url, json=leg["payload"](title, brief), headers=headers)
    except Exception as exc:  # noqa: BLE001 - one leg failing must not end the brief
        return leg["key"], {"ok": False, "error": str(exc)}
    if 200 <= resp.status_code < 300:
        try:
            body = resp.json()
        except Exception:  # noqa: BLE001 - a 2xx with no JSON body is still a success
            body = {}
        return leg["key"], {"ok": True, "status": resp.status_code, "result": body}
    return leg["key"], {"ok": False, "status": resp.status_code, "error": resp.text[:500]}


async def _fan_out_creation(
    project_id: int, brief: str, project_type: str, title: str = ""
) -> None:
    """Background: call every applicable sub-service and aggregate results."""
    results: dict = {}
    headers = {"X-Internal-Secret": INTERNAL_SECRET, "Content-Type": "application/json"}
    title = title or brief

    try:
        import httpx

        async with httpx.AsyncClient(timeout=60) as client:
            for leg in FAN_OUT_LEGS:
                if not _leg_applies(leg, project_type):
                    continue
                key, outcome = await _call_leg(client, leg, title, brief, headers)
                results[key] = outcome
    except ImportError:
        results["note"] = "httpx not installed — install for fan-out orchestration"

    # A brief whose every leg failed did not succeed, and saying "completed"
    # for it is the same class of untruth as the 202 check was.
    attempted = [v for v in results.values() if isinstance(v, dict) and "ok" in v]
    if attempted and not any(v["ok"] for v in attempted):
        status = "failed"
    elif attempted and not all(v["ok"] for v in attempted):
        status = "partial"
    else:
        status = "completed"

    now = time.time()
    with get_conn() as conn:
        conn.execute(
            "UPDATE projects SET status=?, completed_at=?, results=? WHERE id=?",
            (status, now, json.dumps(results), project_id),
        )
        conn.commit()
    logger.info("Imaginarium project %d %s: %s", project_id, status, list(results.keys()))


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
    background_tasks.add_task(
        _fan_out_creation, project_id, body.brief, body.project_type, body.title
    )
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
