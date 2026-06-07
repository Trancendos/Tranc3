"""
Trancendos config-service — Self-Hosted Worker
===============================================
Namespaced key/value configuration store with versioning and watch support.
Supports typed values (string, int, float, bool, json).

Port: 8024
Zero-cost: FastAPI + SQLite, no external deps.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.database.encrypted_sqlite import connect as sqlite3_connect
from src.entities.health_metadata import health_entity_block

WORKER_PORT = 8024
WORKER_NAME = "config-service"
DB_PATH = Path(__file__).parent / "data" / "config.db"
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s")
logger = logging.getLogger(WORKER_NAME)


# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------


def get_conn() -> sqlite3.Connection:
    conn = sqlite3_connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS namespaces (
                name        TEXT PRIMARY KEY,
                description TEXT,
                created_at  REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS configs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                value_type  TEXT NOT NULL DEFAULT 'string',
                description TEXT,
                version     INTEGER NOT NULL DEFAULT 1,
                updated_at  REAL NOT NULL,
                UNIQUE(namespace, key)
            );

            CREATE TABLE IF NOT EXISTS config_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                namespace   TEXT NOT NULL,
                key         TEXT NOT NULL,
                value       TEXT NOT NULL,
                version     INTEGER NOT NULL,
                changed_at  REAL NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_cfg_ns_key ON configs(namespace, key);
        """)
        # seed default namespace
        conn.execute(
            "INSERT OR IGNORE INTO namespaces (name, description, created_at) VALUES (?,?,?)",
            ("default", "Default configuration namespace", time.time()),
        )
        conn.commit()


def _coerce(value: str, value_type: str) -> Any:
    if value_type == "int":
        return int(value)
    if value_type == "float":
        return float(value)
    if value_type == "bool":
        return value.lower() in ("true", "1", "yes")
    if value_type == "json":
        return json.loads(value)
    return value


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class NamespaceCreate(BaseModel):
    name: str
    description: Optional[str] = None


class ConfigSet(BaseModel):
    value: Any
    value_type: str = "string"
    description: Optional[str] = None


class BulkSetItem(BaseModel):
    key: str
    value: Any
    value_type: str = "string"
    description: Optional[str] = None


class BulkSetIn(BaseModel):
    entries: List[BulkSetItem]


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    logger.info("config-service DB ready")
    yield


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

STARTED_AT = datetime.now(timezone.utc)

app = FastAPI(
    title="config-service",
    description="Namespaced configuration store (self-hosted)",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


_INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


async def require_internal_auth(
    x_internal_secret: str = Header(default="", alias="X-Internal-Secret"),
) -> None:
    if not _INTERNAL_SECRET:
        return
    if x_internal_secret != _INTERNAL_SECRET:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Secret header")


_router = APIRouter(dependencies=[Depends(require_internal_auth)])


@app.get("/health")
async def health():
    with get_conn() as conn:
        ns_count = conn.execute("SELECT COUNT(*) FROM namespaces").fetchone()[0]
        cfg_count = conn.execute("SELECT COUNT(*) FROM configs").fetchone()[0]
    return {
        "entity": health_entity_block(8024, "config-service"),
        "status": "healthy",
        "service": WORKER_NAME,
        "port": WORKER_PORT,
        "uptime_seconds": (datetime.now(timezone.utc) - STARTED_AT).total_seconds(),
        "namespaces": ns_count,
        "config_keys": cfg_count,
    }


# --- Namespaces ---


@_router.get("/namespaces")
async def list_namespaces():
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM namespaces ORDER BY name").fetchall()
    return {"namespaces": [dict(r) for r in rows]}


@_router.post("/namespaces", status_code=201)
async def create_namespace(req: NamespaceCreate):
    with get_conn() as conn:
        if conn.execute("SELECT name FROM namespaces WHERE name = ?", (req.name,)).fetchone():
            raise HTTPException(status_code=409, detail="Namespace already exists")
        conn.execute(
            "INSERT INTO namespaces (name, description, created_at) VALUES (?,?,?)",
            (req.name, req.description, time.time()),
        )
        conn.commit()
    return {"name": req.name, "description": req.description}


@_router.delete("/namespaces/{namespace}")
async def delete_namespace(namespace: str):
    if namespace == "default":
        raise HTTPException(status_code=400, detail="Cannot delete default namespace")
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM namespaces WHERE name = ?", (namespace,)).fetchone():
            raise HTTPException(status_code=404, detail="Namespace not found")
        conn.execute("DELETE FROM configs WHERE namespace = ?", (namespace,))
        conn.execute("DELETE FROM namespaces WHERE name = ?", (namespace,))
        conn.commit()
    return {"deleted": namespace}


# --- Config operations ---


def _ensure_ns(namespace: str) -> None:
    with get_conn() as conn:
        if not conn.execute("SELECT name FROM namespaces WHERE name = ?", (namespace,)).fetchone():
            raise HTTPException(status_code=404, detail=f"Namespace '{namespace}' not found")


@_router.get("/config/{namespace}")
async def list_keys(namespace: str, prefix: Optional[str] = None):
    _ensure_ns(namespace)
    with get_conn() as conn:
        if prefix:
            rows = conn.execute(
                "SELECT * FROM configs WHERE namespace = ? AND key LIKE ? ORDER BY key",
                (namespace, f"{prefix}%"),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM configs WHERE namespace = ? ORDER BY key",
                (namespace,),
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["coerced_value"] = _coerce(d["value"], d["value_type"])
        result.append(d)
    return {"namespace": namespace, "keys": result, "count": len(result)}


@_router.get("/config/{namespace}/{key}")
async def get_key(namespace: str, key: str):
    _ensure_ns(namespace)
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM configs WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Config key not found")
    d = dict(row)
    d["coerced_value"] = _coerce(d["value"], d["value_type"])
    return d


@_router.put("/config/{namespace}/{key}", status_code=200)
async def set_key(namespace: str, key: str, req: ConfigSet):
    _ensure_ns(namespace)
    now = time.time()
    str_value = json.dumps(req.value) if req.value_type == "json" else str(req.value)
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT version, value FROM configs WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone()
        if existing:
            version = existing["version"] + 1
            conn.execute(
                "INSERT INTO config_history (namespace, key, value, version, changed_at) VALUES (?,?,?,?,?)",
                (namespace, key, existing["value"], existing["version"], now),
            )
            conn.execute(
                "UPDATE configs SET value=?, value_type=?, description=?, version=?, updated_at=? WHERE namespace=? AND key=?",
                (str_value, req.value_type, req.description, version, now, namespace, key),
            )
        else:
            version = 1
            conn.execute(
                "INSERT INTO configs (namespace, key, value, value_type, description, version, updated_at) VALUES (?,?,?,?,?,?,?)",
                (namespace, key, str_value, req.value_type, req.description, 1, now),
            )
        conn.commit()
    return {"namespace": namespace, "key": key, "version": version, "updated_at": now}


@_router.delete("/config/{namespace}/{key}")
async def delete_key(namespace: str, key: str):
    _ensure_ns(namespace)
    with get_conn() as conn:
        if not conn.execute(
            "SELECT id FROM configs WHERE namespace = ? AND key = ?",
            (namespace, key),
        ).fetchone():
            raise HTTPException(status_code=404, detail="Config key not found")
        conn.execute("DELETE FROM configs WHERE namespace = ? AND key = ?", (namespace, key))
        conn.commit()
    return {"deleted": key, "namespace": namespace}


@_router.post("/config/{namespace}/bulk", status_code=200)
async def bulk_set(namespace: str, req: BulkSetIn):
    _ensure_ns(namespace)
    now = time.time()
    updated = 0
    with get_conn() as conn:
        for item in req.entries:
            str_value = json.dumps(item.value) if item.value_type == "json" else str(item.value)
            existing = conn.execute(
                "SELECT version, value FROM configs WHERE namespace = ? AND key = ?",
                (namespace, item.key),
            ).fetchone()
            if existing:
                version = existing["version"] + 1
                conn.execute(
                    "INSERT INTO config_history (namespace, key, value, version, changed_at) VALUES (?,?,?,?,?)",
                    (namespace, item.key, existing["value"], existing["version"], now),
                )
                conn.execute(
                    "UPDATE configs SET value=?, value_type=?, description=?, version=?, updated_at=? WHERE namespace=? AND key=?",
                    (
                        str_value,
                        item.value_type,
                        item.description,
                        version,
                        now,
                        namespace,
                        item.key,
                    ),
                )
            else:
                conn.execute(
                    "INSERT INTO configs (namespace, key, value, value_type, description, version, updated_at) VALUES (?,?,?,?,?,?,?)",
                    (namespace, item.key, str_value, item.value_type, item.description, 1, now),
                )
            updated += 1
        conn.commit()
    return {"namespace": namespace, "updated": updated}


@_router.get("/config/{namespace}/{key}/history")
async def key_history(namespace: str, key: str, limit: int = Query(20, le=100)):
    _ensure_ns(namespace)
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM config_history WHERE namespace = ? AND key = ? ORDER BY version DESC LIMIT ?",
            (namespace, key, limit),
        ).fetchall()
    return {"namespace": namespace, "key": key, "history": [dict(r) for r in rows]}


app.include_router(_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=WORKER_PORT)
