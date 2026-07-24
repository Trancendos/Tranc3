"""VRAR3D — SQLite persistence"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import config


class VRARDatabase:
    _local = threading.local()

    def __init__(self, db_path: str = config.DB_PATH):
        self._db_path = db_path
        with self._cursor() as cur:
            cur.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS scenes (
                    scene_id        TEXT PRIMARY KEY,
                    name            TEXT NOT NULL,
                    scene_type      TEXT NOT NULL DEFAULT '3d',
                    description     TEXT,
                    objects         TEXT DEFAULT '[]',
                    environment     TEXT,
                    physics_enabled INTEGER DEFAULT 0,
                    xr_enabled      INTEGER DEFAULT 0,
                    preferred_engine TEXT,
                    metadata        TEXT DEFAULT '{}',
                    created_at      TEXT DEFAULT (datetime('now')),
                    updated_at      TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS assets (
                    asset_id        TEXT PRIMARY KEY,
                    scene_id        TEXT,
                    source_format   TEXT NOT NULL,
                    target_format   TEXT NOT NULL,
                    backend         TEXT NOT NULL,
                    status          TEXT DEFAULT 'pending',
                    output_path     TEXT,
                    metadata        TEXT DEFAULT '{}',
                    created_at      TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS backend_events (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    backend         TEXT NOT NULL,
                    success         INTEGER NOT NULL,
                    ts              REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_scenes_type ON scenes(scene_type);
                CREATE INDEX IF NOT EXISTS idx_assets_scene ON assets(scene_id);
                CREATE INDEX IF NOT EXISTS idx_events_backend ON backend_events(backend, ts);
            """)

    @contextmanager
    def _cursor(self):
        if not getattr(self._local, "conn", None):
            self._local.conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
        conn = self._local.conn
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def save_scene(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO scenes
                  (scene_id, name, scene_type, description, objects, environment,
                   physics_enabled, xr_enabled, preferred_engine, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scene_id) DO UPDATE SET
                  name=excluded.name,
                  scene_type=excluded.scene_type,
                  description=excluded.description,
                  objects=excluded.objects,
                  environment=excluded.environment,
                  physics_enabled=excluded.physics_enabled,
                  xr_enabled=excluded.xr_enabled,
                  preferred_engine=excluded.preferred_engine,
                  metadata=excluded.metadata,
                  updated_at=datetime('now')
                """,
                (
                    data["scene_id"],
                    data["name"],
                    data.get("scene_type", "3d"),
                    data.get("description"),
                    json.dumps(data.get("objects", [])),
                    json.dumps(data["environment"]) if data.get("environment") else None,
                    1 if data.get("physics_enabled") else 0,
                    1 if data.get("xr_enabled") else 0,
                    data.get("preferred_engine"),
                    json.dumps(data.get("metadata", {})),
                ),
            )
        return self.get_scene(data["scene_id"])

    def get_scene(self, scene_id: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM scenes WHERE scene_id=?", (scene_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self._deserialize_scene(dict(row))

    def list_scenes(
        self, scene_type: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            if scene_type:
                cur.execute(
                    "SELECT * FROM scenes WHERE scene_type=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (scene_type, limit, offset),
                )
            else:
                cur.execute(
                    "SELECT * FROM scenes ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            rows = cur.fetchall()
        return [self._deserialize_scene(dict(r)) for r in rows]

    def delete_scene(self, scene_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM scenes WHERE scene_id=?", (scene_id,))
            return cur.rowcount > 0

    def count_scenes(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM scenes")
            row = cur.fetchone()
        return row[0] if row else 0

    def save_asset_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO assets
                  (asset_id, scene_id, source_format, target_format, backend, status, output_path, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                  status=excluded.status,
                  output_path=excluded.output_path
                """,
                (
                    data["asset_id"],
                    data.get("scene_id"),
                    data["source_format"],
                    data["target_format"],
                    data["backend"],
                    data.get("status", "pending"),
                    data.get("output_path"),
                    json.dumps(data.get("metadata", {})),
                ),
            )
        return data

    def get_asset_job(self, asset_id: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM assets WHERE asset_id=?", (asset_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self._deserialize_asset(dict(row))

    def _deserialize_asset(self, d: Dict[str, Any]) -> Dict[str, Any]:
        d["metadata"] = json.loads(d["metadata"])
        return d

    def record_event(self, backend: str, success: bool) -> None:
        import time

        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO backend_events (backend, success, ts) VALUES (?, ?, ?)",
                (backend, 1 if success else 0, time.time()),
            )

    def _deserialize_scene(self, d: Dict[str, Any]) -> Dict[str, Any]:
        d["objects"] = json.loads(d["objects"])
        d["environment"] = json.loads(d["environment"]) if d.get("environment") else None
        d["metadata"] = json.loads(d["metadata"])
        d["physics_enabled"] = bool(d["physics_enabled"])
        d["xr_enabled"] = bool(d["xr_enabled"])
        return d
