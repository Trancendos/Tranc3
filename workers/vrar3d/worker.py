"""
Trancendos vrar3d — Standalone 3D / VR Immersion Platform
==========================================================
Scene management for Three.js / A-Frame VR experiences.
Zero-cost: JSON scene descriptors, no external VR platform required.

Port: 8068  Entity: VRAR3D  Lead AI: Entari
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

WORKER_PORT = 8068
WORKER_NAME = "vrar3d"
DB_PATH = Path(__file__).parent / "data" / "vrar3d.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

SCENE_TYPES = ["vr", "ar", "3d", "360_video", "interactive"]
OBJECT_TYPES = [
    "mesh",
    "light",
    "camera",
    "audio",
    "particle",
    "text",
    "image",
    "video",
    "sky",
    "floor",
]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS experiences (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                experience_type TEXT DEFAULT 'vr',
                renderer    TEXT DEFAULT 'three.js',
                public      INTEGER DEFAULT 0,
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                updated_at  REAL,
                scene_data  TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS scene_objects (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id INTEGER NOT NULL,
                name        TEXT NOT NULL,
                object_type TEXT NOT NULL,
                position    TEXT DEFAULT '{"x":0,"y":0,"z":0}',
                rotation    TEXT DEFAULT '{"x":0,"y":0,"z":0}',
                scale       TEXT DEFAULT '{"x":1,"y":1,"z":1}',
                color       TEXT DEFAULT '#ffffff',
                src         TEXT,
                properties  TEXT DEFAULT '{}',
                created_at  REAL NOT NULL,
                FOREIGN KEY(experience_id) REFERENCES experiences(id)
            );
            CREATE TABLE IF NOT EXISTS vr_sessions (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                experience_id INTEGER NOT NULL,
                user_id     TEXT DEFAULT 'anonymous',
                device      TEXT,
                duration_s  INTEGER,
                started_at  REAL NOT NULL,
                ended_at    REAL,
                FOREIGN KEY(experience_id) REFERENCES experiences(id)
            );
            CREATE INDEX IF NOT EXISTS idx_objects_exp ON scene_objects(experience_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_exp ON vr_sessions(experience_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="VRAR3D — Immersion Platform", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class ExperienceIn(BaseModel):
    title: str
    description: Optional[str] = None
    experience_type: str = "vr"
    renderer: str = "three.js"
    public: bool = False
    created_by: str = "system"
    scene_data: dict = {}


class SceneObjectIn(BaseModel):
    experience_id: int
    name: str
    object_type: str
    position: dict = {"x": 0, "y": 0, "z": 0}
    rotation: dict = {"x": 0, "y": 0, "z": 0}
    scale: dict = {"x": 1, "y": 1, "z": 1}
    color: str = "#ffffff"
    src: Optional[str] = None
    properties: dict = {}


class SessionIn(BaseModel):
    experience_id: int
    user_id: str = "anonymous"
    device: Optional[str] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        exps = conn.execute("SELECT COUNT(*) FROM experiences").fetchone()[0]
        sessions = conn.execute("SELECT COUNT(*) FROM vr_sessions").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "VRAR3D", "lead_ai": "Entari"},
        "experiences": exps,
        "total_sessions": sessions,
        "supported_types": SCENE_TYPES,
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


@_router.post("/experiences", status_code=201)
async def create_experience(body: ExperienceIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.experience_type not in SCENE_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Invalid experience_type. Must be: {SCENE_TYPES}"
        )
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO experiences (title, description, experience_type, renderer, public, created_by, created_at, updated_at, scene_data) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                body.title,
                body.description,
                body.experience_type,
                body.renderer,
                int(body.public),
                body.created_by,
                now,
                now,
                json.dumps(body.scene_data),
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM experiences WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/experiences")
async def list_experiences(
    experience_type: Optional[str] = None,
    public: Optional[bool] = None,
    limit: int = Query(50, le=500),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if experience_type:
        clauses.append("experience_type=?")
        params.append(experience_type)
    if public is not None:
        clauses.append("public=?")
        params.append(int(public))
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM experiences {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/experiences/{exp_id}")
async def get_experience(exp_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM experiences WHERE id=?", (exp_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Experience not found")
        objects = conn.execute(
            "SELECT * FROM scene_objects WHERE experience_id=?", (exp_id,)
        ).fetchall()
    return {**dict(row), "objects": [dict(o) for o in objects]}


@_router.post("/objects", status_code=201)
async def add_object(body: SceneObjectIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.object_type not in OBJECT_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid object_type. Must be: {OBJECT_TYPES}")
    now = time.time()
    with get_conn() as conn:
        if not conn.execute(
            "SELECT id FROM experiences WHERE id=?", (body.experience_id,)
        ).fetchone():
            raise HTTPException(status_code=404, detail="Experience not found")
        cur = conn.execute(
            "INSERT INTO scene_objects (experience_id, name, object_type, position, rotation, scale, color, src, properties, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                body.experience_id,
                body.name,
                body.object_type,
                json.dumps(body.position),
                json.dumps(body.rotation),
                json.dumps(body.scale),
                body.color,
                body.src,
                json.dumps(body.properties),
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM scene_objects WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.delete("/objects/{object_id}", status_code=204)
async def delete_object(object_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        deleted = conn.execute("DELETE FROM scene_objects WHERE id=?", (object_id,)).rowcount
        conn.commit()
    if not deleted:
        raise HTTPException(status_code=404, detail="Object not found")


@_router.post("/sessions", status_code=201)
async def start_session(body: SessionIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO vr_sessions (experience_id, user_id, device, started_at) VALUES (?,?,?,?)",
            (body.experience_id, body.user_id, body.device, now),
        )
        conn.commit()
    return {"session_id": cur.lastrowid, "experience_id": body.experience_id, "started_at": now}


@_router.patch("/sessions/{session_id}/end")
async def end_session(session_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        session = conn.execute("SELECT * FROM vr_sessions WHERE id=?", (session_id,)).fetchone()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        duration_s = int(now - session["started_at"])
        conn.execute(
            "UPDATE vr_sessions SET ended_at=?, duration_s=? WHERE id=?",
            (now, duration_s, session_id),
        )
        conn.commit()
    return {"session_id": session_id, "duration_s": duration_s, "ended_at": now}


@_router.get("/experiences/{exp_id}/aframe")
async def export_aframe(exp_id: int, x_internal_secret: str = Header(default="")):
    """Export experience as A-Frame HTML snippet."""
    _auth(x_internal_secret)
    with get_conn() as conn:
        exp = conn.execute("SELECT * FROM experiences WHERE id=?", (exp_id,)).fetchone()
        if not exp:
            raise HTTPException(status_code=404, detail="Experience not found")
        objects = conn.execute(
            "SELECT * FROM scene_objects WHERE experience_id=?", (exp_id,)
        ).fetchall()

    entities = []
    for obj in objects:
        pos = json.loads(obj["position"])
        rot = json.loads(obj["rotation"])
        scale = json.loads(obj["scale"])
        pos_str = f"{pos.get('x', 0)} {pos.get('y', 0)} {pos.get('z', 0)}"
        rot_str = f"{rot.get('x', 0)} {rot.get('y', 0)} {rot.get('z', 0)}"
        scale_str = f"{scale.get('x', 1)} {scale.get('y', 1)} {scale.get('z', 1)}"
        color = obj["color"] or "#ffffff"
        if obj["object_type"] == "mesh":
            entities.append(
                f'<a-box position="{pos_str}" rotation="{rot_str}" scale="{scale_str}" color="{color}"></a-box>'
            )
        elif obj["object_type"] == "light":
            entities.append(
                f'<a-light type="point" color="{color}" position="{pos_str}"></a-light>'
            )
        elif obj["object_type"] == "sky":
            entities.append(f'<a-sky color="{color}"></a-sky>')
        elif obj["object_type"] == "text":
            text_val = json.loads(obj["properties"] or "{}").get("text", obj["name"])
            entities.append(
                f'<a-text value="{text_val}" position="{pos_str}" color="{color}"></a-text>'
            )

    separator = "\n  "
    html = f"""<a-scene>
  {separator.join(entities)}
  <a-camera position="0 1.6 0"></a-camera>
</a-scene>"""
    return {"experience_id": exp_id, "title": exp["title"], "aframe_html": html}


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
