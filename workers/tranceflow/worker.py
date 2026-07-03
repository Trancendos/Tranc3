"""
Trancendos tranceflow — 3D Modeling & Games Creation Studio
============================================================
Project management for 3D assets, scenes, game entities.
Integrates with Godot Engine export pipelines (local, zero-cost).

Port: 8067  Entity: TranceFlow  Lead AI: Junior Cesar
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

WORKER_PORT = int(os.getenv("PORT", "8067"))
WORKER_NAME = "tranceflow"
DB_PATH = Path(__file__).parent / "data" / "tranceflow.db"
ASSETS_DIR = Path(__file__).parent / "data" / "assets"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

INTERNAL_SECRET = os.getenv("INTERNAL_SECRET", "dev-secret")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)

_start_time = time.time()
_req_count = 0
_err_count = 0

ASSET_TYPES = ["mesh", "texture", "material", "scene", "animation", "audio", "script", "prefab"]
GAME_ENGINES = ["godot", "unity", "unreal", "custom"]


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS games (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT,
                engine      TEXT DEFAULT 'godot',
                genre       TEXT DEFAULT 'unknown',
                status      TEXT DEFAULT 'development',
                version     TEXT DEFAULT '0.1.0',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                updated_at  REAL
            );
            CREATE TABLE IF NOT EXISTS assets (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER,
                name        TEXT NOT NULL,
                asset_type  TEXT NOT NULL,
                file_path   TEXT,
                file_size   INTEGER DEFAULT 0,
                format      TEXT,
                tags        TEXT DEFAULT '[]',
                metadata    TEXT DEFAULT '{}',
                created_by  TEXT DEFAULT 'system',
                created_at  REAL NOT NULL,
                FOREIGN KEY(game_id) REFERENCES games(id)
            );
            CREATE TABLE IF NOT EXISTS scenes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER NOT NULL,
                name        TEXT NOT NULL,
                scene_type  TEXT DEFAULT 'level',
                entities    TEXT DEFAULT '[]',
                properties  TEXT DEFAULT '{}',
                created_at  REAL NOT NULL,
                FOREIGN KEY(game_id) REFERENCES games(id)
            );
            CREATE TABLE IF NOT EXISTS entities (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                scene_id    INTEGER NOT NULL,
                name        TEXT NOT NULL,
                entity_type TEXT DEFAULT 'object',
                position    TEXT DEFAULT '[0,0,0]',
                rotation    TEXT DEFAULT '[0,0,0]',
                scale       TEXT DEFAULT '[1,1,1]',
                properties  TEXT DEFAULT '{}',
                asset_id    INTEGER,
                FOREIGN KEY(scene_id) REFERENCES scenes(id)
            );
            CREATE TABLE IF NOT EXISTS build_events (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id     INTEGER NOT NULL,
                platform    TEXT NOT NULL,
                status      TEXT NOT NULL,
                build_log   TEXT,
                output_path TEXT,
                built_at    REAL NOT NULL,
                duration_s  INTEGER,
                FOREIGN KEY(game_id) REFERENCES games(id)
            );
            CREATE INDEX IF NOT EXISTS idx_assets_game ON assets(game_id);
            CREATE INDEX IF NOT EXISTS idx_scenes_game ON scenes(game_id);
            CREATE INDEX IF NOT EXISTS idx_entities_scene ON entities(scene_id);
        """)
        conn.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("%s starting on port %d", WORKER_NAME, WORKER_PORT)
    yield


app = FastAPI(title="TranceFlow — 3D & Game Studio", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
_router = APIRouter()


def _auth(x_internal_secret: str = Header(default="")) -> None:
    global _req_count, _err_count
    _req_count += 1
    if x_internal_secret != INTERNAL_SECRET:
        _err_count += 1
        raise HTTPException(status_code=401, detail="Unauthorized")


class GameIn(BaseModel):
    title: str
    description: Optional[str] = None
    engine: str = "godot"
    genre: str = "unknown"
    created_by: str = "system"


class AssetIn(BaseModel):
    game_id: Optional[int] = None
    name: str
    asset_type: str
    file_path: Optional[str] = None
    format: Optional[str] = None
    tags: list[str] = []
    metadata: dict = {}
    created_by: str = "system"


class SceneIn(BaseModel):
    game_id: int
    name: str
    scene_type: str = "level"
    properties: dict = {}


class EntityIn(BaseModel):
    scene_id: int
    name: str
    entity_type: str = "object"
    position: list[float] = [0, 0, 0]
    rotation: list[float] = [0, 0, 0]
    scale: list[float] = [1, 1, 1]
    properties: dict = {}
    asset_id: Optional[int] = None


class BuildIn(BaseModel):
    game_id: int
    platform: str
    output_path: Optional[str] = None


@_router.get("/health")
async def health():
    with get_conn() as conn:
        games = conn.execute("SELECT COUNT(*) FROM games").fetchone()[0]
        assets = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    return {
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "entity": {"name": "TranceFlow", "lead_ai": "Junior Cesar"},
        "games": games,
        "assets": assets,
        "supported_engines": GAME_ENGINES,
        "asset_types": ASSET_TYPES,
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


@_router.post("/games", status_code=201)
async def create_game(body: GameIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.engine not in GAME_ENGINES:
        raise HTTPException(
            status_code=400, detail=f"Unsupported engine. Supported: {GAME_ENGINES}"
        )
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO games (title, description, engine, genre, created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?)",
            (body.title, body.description, body.engine, body.genre, body.created_by, now, now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM games WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/games")
async def list_games(
    engine: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=500),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if engine:
        clauses.append("engine=?")
        params.append(engine)
    if status:
        clauses.append("status=?")
        params.append(status)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM games {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.get("/games/{game_id}")
async def get_game(game_id: int, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM games WHERE id=?", (game_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Game not found")
        scenes = conn.execute("SELECT * FROM scenes WHERE game_id=?", (game_id,)).fetchall()
        assets = conn.execute(
            "SELECT id, name, asset_type, format FROM assets WHERE game_id=?", (game_id,)
        ).fetchall()
    return {**dict(row), "scenes": [dict(s) for s in scenes], "assets": [dict(a) for a in assets]}


@_router.post("/assets", status_code=201)
async def add_asset(body: AssetIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    if body.asset_type not in ASSET_TYPES:
        raise HTTPException(
            status_code=400, detail=f"Invalid asset_type. Must be one of: {ASSET_TYPES}"
        )
    now = time.time()
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO assets (game_id, name, asset_type, file_path, format, tags, metadata, created_by, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (
                body.game_id,
                body.name,
                body.asset_type,
                body.file_path,
                body.format,
                json.dumps(body.tags),
                json.dumps(body.metadata),
                body.created_by,
                now,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM assets WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.get("/assets")
async def list_assets(
    game_id: Optional[int] = None,
    asset_type: Optional[str] = None,
    limit: int = Query(100, le=1000),
    x_internal_secret: str = Header(default=""),
):
    _auth(x_internal_secret)
    clauses, params = [], []
    if game_id:
        clauses.append("game_id=?")
        params.append(game_id)
    if asset_type:
        clauses.append("asset_type=?")
        params.append(asset_type)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT * FROM assets {where} ORDER BY id DESC LIMIT ?", params + [limit]
        ).fetchall()
    return [dict(r) for r in rows]


@_router.post("/scenes", status_code=201)
async def create_scene(body: SceneIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM games WHERE id=?", (body.game_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Game not found")
        cur = conn.execute(
            "INSERT INTO scenes (game_id, name, scene_type, properties, created_at) VALUES (?,?,?,?,?)",
            (body.game_id, body.name, body.scene_type, json.dumps(body.properties), now),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM scenes WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.post("/entities", status_code=201)
async def add_entity(body: EntityIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM scenes WHERE id=?", (body.scene_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Scene not found")
        cur = conn.execute(
            "INSERT INTO entities (scene_id, name, entity_type, position, rotation, scale, properties, asset_id) VALUES (?,?,?,?,?,?,?,?)",
            (
                body.scene_id,
                body.name,
                body.entity_type,
                json.dumps(body.position),
                json.dumps(body.rotation),
                json.dumps(body.scale),
                json.dumps(body.properties),
                body.asset_id,
            ),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM entities WHERE id=?", (cur.lastrowid,)).fetchone()
    return dict(row)


@_router.post("/builds", status_code=202)
async def record_build(body: BuildIn, x_internal_secret: str = Header(default="")):
    _auth(x_internal_secret)
    now = time.time()
    with get_conn() as conn:
        if not conn.execute("SELECT id FROM games WHERE id=?", (body.game_id,)).fetchone():
            raise HTTPException(status_code=404, detail="Game not found")
        cur = conn.execute(
            "INSERT INTO build_events (game_id, platform, status, output_path, built_at) VALUES (?,?,?,?,?)",
            (body.game_id, body.platform, "queued", body.output_path, now),
        )
        conn.commit()
    return {
        "id": cur.lastrowid,
        "game_id": body.game_id,
        "platform": body.platform,
        "status": "queued",
        "note": "Build queued. Use Godot CLI or CI pipeline to execute.",
    }


app.include_router(_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)  # nosec B104 — containerised service
