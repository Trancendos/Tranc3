"""
Trancendos devocity — Development Operations Hub
================================================
Dev portal: project registry, deploy events, service catalogue,
environment tracking, and CI/CD event ingestion.

Port: 8062  Entity: DevOcity  Lead AI: Kitty
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

WORKER_PORT = 8062
WORKER_NAME = "devocity"
DB_PATH = Path(__file__).parent / "data" / "devocity.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

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
                name        TEXT UNIQUE NOT NULL,
                description TEXT,
                repo_url    TEXT,
                language    TEXT DEFAULT 'python',
                status      TEXT DEFAULT 'active',
                owner       TEXT DEFAULT 'system',
                tags        TEXT DEFAULT '[]',
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS environments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER NOT NULL,
                name        TEXT NOT NULL,
                url         TEXT,
                status      TEXT DEFAULT 'healthy',
                deployed_at REAL,
                version     TEXT,
                UNIQUE(project_id, name),
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS deploy_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id  INTEGER,
                environment TEXT NOT NULL,
                version     TEXT,
                status      TEXT NOT NULL,
                triggered_by TEXT DEFAULT 'system',
                duration_s  INTEGER,
                logs        TEXT,
                deployed_at REAL NOT NULL,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            );
            CREATE TABLE IF NOT EXISTS service_catalogue (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT UNIQUE NOT NULL,
                description TEXT,
                owner       TEXT,
                port        INTEGER,
                health_url  TEXT,
                tags        TEXT DEFAULT '[]',
                status      TEXT DEFAULT 'active',
                created_at  REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_deploy_project ON deploy_events(project_id);
            CREATE INDEX IF NOT EXISTS idx_deploy_ts ON deploy_events(deployed_at);
            CREATE INDEX IF NOT EXISTS idx_env_project ON environments(project_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="DevOcity — Dev Operations Hub", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class ProjectIn(BaseModel):
    name: str
    description: Optional[str] = None
    repo_url: Optional[str] = None
    language: str = "python"
    status: str = "active"
    owner: str = "system"
    tags: list[str] = []


class EnvironmentIn(BaseModel):
    name: str
    url: Optional[str] = None
    status: str = "healthy"
    version: Optional[str] = None


class DeployEventIn(BaseModel):
    project_id: Optional[int] = None
    environment: str
    version: Optional[str] = None
    status: str
    triggered_by: str = "system"
    duration_s: Optional[int] = None
    logs: Optional[str] = None


class ServiceIn(BaseModel):
    name: str
    description: Optional[str] = None
    owner: Optional[str] = None
    port: Optional[int] = None
    health_url: Optional[str] = None
    tags: list[str] = []
    status: str = "active"


@_router.get("/health")
async def health():
    with get_conn() as conn:
        projects = conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0]
        deploys = conn.execute("SELECT COUNT(*) FROM deploy_events").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "DevOcity", "lead_ai": "Kitty"},
        "active_projects": projects,
        "total_deploys": deploys,
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


# --- Projects ---

@_router.post("/projects", status_code=201)
async def create_project(body: ProjectIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO projects (name, description, repo_url, language, status, owner, tags, created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (body.name, body.description, body.repo_url, body.language, body.status,
                 body.owner, json.dumps(body.tags), now, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM projects WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Project name already exists")


@_router.get("/projects")
async def list_projects(
    status: Optional[str] = None,
    language: Optional[str] = None,
    owner: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if status: clauses.append("status=?"); params.append(status)
    if language: clauses.append("language=?"); params.append(language)
    if owner: clauses.append("owner=?"); params.append(owner)
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
        if not row: raise HTTPException(status_code=404, detail="Project not found")
        envs = conn.execute("SELECT * FROM environments WHERE project_id=?", (project_id,)).fetchall()
        recent_deploys = conn.execute(
            "SELECT * FROM deploy_events WHERE project_id=? ORDER BY deployed_at DESC LIMIT 10",
            (project_id,),
        ).fetchall()
    return {
        **dict(row),
        "environments": [dict(e) for e in envs],
        "recent_deploys": [dict(d) for d in recent_deploys],
    }


# --- Environments ---

@_router.post("/projects/{project_id}/environments", status_code=201)
async def add_environment(project_id: int, body: EnvironmentIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM projects WHERE id=?", (project_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Project not found")
        try:
            cur = conn.execute(
                "INSERT INTO environments (project_id, name, url, status, deployed_at, version) VALUES (?,?,?,?,?,?)",
                (project_id, body.name, body.url, body.status, now, body.version),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM environments WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Environment name already exists for project")


# --- Deploy Events ---

@_router.post("/deploys", status_code=201)
async def record_deploy(body: DeployEventIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO deploy_events (project_id, environment, version, status, triggered_by, duration_s, logs, deployed_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (body.project_id, body.environment, body.version, body.status,
             body.triggered_by, body.duration_s, body.logs, now),
        )
        conn.commit()
    return {"id": cur.lastrowid, "deployed_at": now, "status": body.status}


@_router.get("/deploys")
async def list_deploys(
    project_id: Optional[int] = None,
    environment: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    offset: int = 0,
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if project_id: clauses.append("project_id=?"); params.append(project_id)
    if environment: clauses.append("environment=?"); params.append(environment)
    if status: clauses.append("status=?"); params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(*) FROM deploy_events {where}", params).fetchone()[0]
        rows = conn.execute(
            f"SELECT * FROM deploy_events {where} ORDER BY deployed_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
    return {"total": total, "deploys": [dict(r) for r in rows]}


# --- Service Catalogue ---

@_router.post("/services", status_code=201)
async def register_service(body: ServiceIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        try:
            cur = conn.execute(
                "INSERT INTO service_catalogue (name, description, owner, port, health_url, tags, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (body.name, body.description, body.owner, body.port, body.health_url,
                 json.dumps(body.tags), body.status, now),
            )
            conn.commit()
            row = conn.execute("SELECT * FROM service_catalogue WHERE id=?", (cur.lastrowid,)).fetchone()
            return dict(row)
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Service name already registered")


@_router.get("/services")
async def list_services(
    status: Optional[str] = None,
    limit: int = Query(100, le=1000),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if status: clauses.append("status=?"); params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM service_catalogue {where} ORDER BY name", params).fetchall()
    return [dict(r) for r in rows]


@_router.get("/stats")
async def stats(x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        total_projects = conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
        active_projects = conn.execute("SELECT COUNT(*) FROM projects WHERE status='active'").fetchone()[0]
        total_deploys = conn.execute("SELECT COUNT(*) FROM deploy_events").fetchone()[0]
        success_deploys = conn.execute(
            "SELECT COUNT(*) FROM deploy_events WHERE status='success'"
        ).fetchone()[0]
        by_env = conn.execute(
            "SELECT environment, COUNT(*) c FROM deploy_events GROUP BY environment ORDER BY c DESC"
        ).fetchall()
    return {
        "total_projects": total_projects,
        "active_projects": active_projects,
        "total_deploys": total_deploys,
        "successful_deploys": success_deploys,
        "deploy_success_rate": round(success_deploys / total_deploys * 100, 1) if total_deploys else 0,
        "by_environment": [dict(r) for r in by_env],
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
