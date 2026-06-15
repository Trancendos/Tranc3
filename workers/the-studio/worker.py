"""
Trancendos the-studio — Central Hub of the Creativity Center
=============================================================
Creative project management, asset coordination, collaboration hub.
Orchestrates between Sashas Photo Studio, TateKing, TranceFlow, Warp Radio.

Port: 8069  Entity: The Studio  Lead AI: Voxx
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

from fastapi import APIRouter, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

WORKER_PORT = 8069
WORKER_NAME = "the-studio"
DB_PATH = Path(__file__).parent / "data" / "studio.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

PROJECT_TYPES = ["music", "visual", "video", "game", "mixed", "branding", "interactive"]
ASSET_STATUSES = ["draft", "in_progress", "review", "approved", "published", "archived"]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS studio_projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                title        TEXT NOT NULL,
                brief        TEXT,
                project_type TEXT DEFAULT 'mixed',
                client       TEXT DEFAULT 'internal',
                status       TEXT DEFAULT 'draft',
                priority     INTEGER DEFAULT 3,
                deadline     REAL,
                budget_hrs   REAL DEFAULT 0,
                spent_hrs    REAL DEFAULT 0,
                created_by   TEXT DEFAULT 'voxx',
                created_at   REAL NOT NULL,
                updated_at   REAL,
                tags         TEXT DEFAULT '[]',
                metadata     TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS creative_assets (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER,
                title        TEXT NOT NULL,
                asset_type   TEXT NOT NULL,
                status       TEXT DEFAULT 'draft',
                source_service TEXT,
                source_id    TEXT,
                file_path    TEXT,
                url          TEXT,
                notes        TEXT,
                created_by   TEXT DEFAULT 'voxx',
                created_at   REAL NOT NULL,
                updated_at   REAL,
                FOREIGN KEY(project_id) REFERENCES studio_projects(id)
            );
            CREATE TABLE IF NOT EXISTS collaborators (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                user_id      TEXT NOT NULL,
                role         TEXT DEFAULT 'contributor',
                added_at     REAL NOT NULL,
                UNIQUE(project_id, user_id),
                FOREIGN KEY(project_id) REFERENCES studio_projects(id)
            );
            CREATE TABLE IF NOT EXISTS time_entries (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                user_id      TEXT NOT NULL,
                description  TEXT,
                hours        REAL NOT NULL,
                logged_at    REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES studio_projects(id)
            );
            CREATE TABLE IF NOT EXISTS feedback (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                asset_id     INTEGER,
                author       TEXT NOT NULL,
                content      TEXT NOT NULL,
                rating       INTEGER CHECK(rating BETWEEN 1 AND 5),
                status       TEXT DEFAULT 'open',
                created_at   REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES studio_projects(id)
            );
            CREATE INDEX IF NOT EXISTS idx_assets_project ON creative_assets(project_id);
            CREATE INDEX IF NOT EXISTS idx_time_project ON time_entries(project_id);
            CREATE INDEX IF NOT EXISTS idx_collab_project ON collaborators(project_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="The Studio — Creativity Hub", version="1.0.0", lifespan=lifespan)
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
    brief: Optional[str] = None
    project_type: str = "mixed"
    client: str = "internal"
    priority: int = 3
    deadline: Optional[float] = None
    budget_hrs: float = 0
    created_by: str = "voxx"
    tags: list[str] = []
    metadata: dict = {}


class AssetIn(BaseModel):
    project_id: Optional[int] = None
    title: str
    asset_type: str
    status: str = "draft"
    source_service: Optional[str] = None
    source_id: Optional[str] = None
    file_path: Optional[str] = None
    url: Optional[str] = None
    notes: Optional[str] = None
    created_by: str = "voxx"


class CollabIn(BaseModel):
    project_id: int
    user_id: str
    role: str = "contributor"


class TimeIn(BaseModel):
    project_id: int
    user_id: str
    description: Optional[str] = None
    hours: float


class FeedbackIn(BaseModel):
    project_id: int
    asset_id: Optional[int] = None
    author: str
    content: str
    rating: Optional[int] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM studio_projects").fetchone()[0]
        assets = conn.execute("SELECT COUNT(*) FROM creative_assets").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "The Studio", "lead_ai": "Voxx"},
        "projects": projects,
        "creative_assets": assets,
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
    if body.project_type not in PROJECT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid project_type. Must be: {PROJECT_TYPES}")
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO studio_projects (title, brief, project_type, client, priority, deadline, budget_hrs, created_by, created_at, updated_at, tags, metadata) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (body.title, body.brief, body.project_type, body.client, body.priority,
             body.deadline, body.budget_hrs, body.created_by, now, now,
             json.dumps(body.tags), json.dumps(body.metadata)),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM studio_projects WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/projects")
async def list_projects(
    project_type: Optional[str] = None,
    status: Optional[str] = None,
    client: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if project_type:
        clauses.append("project_type=?")
        params.append(project_type)
    if status:
        clauses.append("status=?")
        params.append(status)
    if client:
        clauses.append("client=?")
        params.append(client)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM studio_projects {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM studio_projects {where} ORDER BY priority, created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "projects": [dict(r) for r in rows]}


@_router.get("/projects/{project_id}")
async def get_project(project_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM studio_projects WHERE id=?", (project_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Project not found")
        assets = conn.execute("SELECT * FROM creative_assets WHERE project_id=?", (project_id,)).fetchall()
        collabs = conn.execute("SELECT * FROM collaborators WHERE project_id=?", (project_id,)).fetchall()
        total_time = conn.execute(
            "SELECT SUM(hours) FROM time_entries WHERE project_id=?", (project_id,)
        ).fetchone()[0] or 0
    return {
        **dict(row),
        "assets": [dict(a) for a in assets],
        "collaborators": [dict(c) for c in collabs],
        "total_hours_logged": round(total_time, 2),
    }


@_router.patch("/projects/{project_id}/status")
async def update_status(project_id: int, payload: dict, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    new_status = payload.get("status")
    if new_status not in ASSET_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be: {ASSET_STATUSES}")
    with get_conn() as conn:
        conn.execute(
            "UPDATE studio_projects SET status=?, updated_at=? WHERE id=?",
            (new_status, time.time(), project_id),
        )
        conn.commit()
    return {"project_id": project_id, "status": new_status}


@_router.post("/assets", status_code=201)
async def add_asset(body: AssetIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO creative_assets (project_id, title, asset_type, status, source_service, source_id, file_path, url, notes, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (body.project_id, body.title, body.asset_type, body.status, body.source_service,
             body.source_id, body.file_path, body.url, body.notes, body.created_by, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM creative_assets WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.post("/collaborators", status_code=201)
async def add_collaborator(body: CollabIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO collaborators (project_id, user_id, role, added_at) VALUES (?,?,?,?)",
                (body.project_id, body.user_id, body.role, now),
            )
            conn.commit()
            return {"id": cur.lastrowid, "project_id": body.project_id, "user_id": body.user_id, "role": body.role}
        except sqlite3.IntegrityError as exc:
            raise HTTPException(status_code=409, detail="User already a collaborator on this project") from exc


@_router.post("/time", status_code=201)
async def log_time(body: TimeIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.hours <= 0:
        raise HTTPException(status_code=400, detail="hours must be positive")
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO time_entries (project_id, user_id, description, hours, logged_at) VALUES (?,?,?,?,?)",
            (body.project_id, body.user_id, body.description, body.hours, now),
        )
        conn.execute(
            "UPDATE studio_projects SET spent_hrs=spent_hrs+?, updated_at=? WHERE id=?",
            (body.hours, now, body.project_id),
        )
        conn.commit()
    return {"id": cur.lastrowid, "project_id": body.project_id, "hours": body.hours, "logged_at": now}


@_router.post("/feedback", status_code=201)
async def add_feedback(body: FeedbackIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO feedback (project_id, asset_id, author, content, rating, created_at) VALUES (?,?,?,?,?,?)",
            (body.project_id, body.asset_id, body.author, body.content, body.rating, now),
        )
        conn.commit()
    return {"id": cur.lastrowid, "project_id": body.project_id, "author": body.author, "created_at": now}


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM studio_projects").fetchone()[0]
        by_type = conn.execute(
            "SELECT project_type, COUNT(*) c FROM studio_projects GROUP BY project_type ORDER BY c DESC"
        ).fetchall()
        by_status = conn.execute(
            "SELECT status, COUNT(*) c FROM studio_projects GROUP BY status"
        ).fetchall()
        total_hours = conn.execute("SELECT SUM(hours) FROM time_entries").fetchone()[0] or 0
    return {
        "total_projects": total,
        "total_hours_logged": round(total_hours, 2),
        "by_type": [dict(r) for r in by_type],
        "by_status": [dict(r) for r in by_status],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
