"""TranceFlow — SQLite persistence"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import config


class TranceFlowDatabase:
    _local = threading.local()

    def __init__(self, db_path: str = config.DB_PATH) -> None:
        self._db_path = db_path
        with self._cursor() as cur:
            cur.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS projects (
                    project_id   TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    project_type TEXT NOT NULL DEFAULT 'game_3d',
                    description  TEXT,
                    engine       TEXT NOT NULL DEFAULT 'godot',
                    assets       TEXT DEFAULT '[]',
                    settings     TEXT DEFAULT '{}',
                    metadata     TEXT DEFAULT '{}',
                    created_at   TEXT DEFAULT (datetime('now')),
                    updated_at   TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS export_jobs (
                    job_id        TEXT PRIMARY KEY,
                    project_id    TEXT,
                    source_format TEXT NOT NULL,
                    target_format TEXT NOT NULL,
                    backend       TEXT NOT NULL,
                    status        TEXT DEFAULT 'pending',
                    output_path   TEXT,
                    metadata      TEXT DEFAULT '{}',
                    created_at    TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS backend_events (
                    id       INTEGER PRIMARY KEY AUTOINCREMENT,
                    backend  TEXT NOT NULL,
                    success  INTEGER NOT NULL,
                    ts       REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_projects_type ON projects(project_type);
                CREATE INDEX IF NOT EXISTS idx_jobs_project ON export_jobs(project_id);
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

    def save_project(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO projects
                  (project_id, name, project_type, description, engine, assets, settings, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                  name=excluded.name,
                  project_type=excluded.project_type,
                  description=excluded.description,
                  engine=excluded.engine,
                  assets=excluded.assets,
                  settings=excluded.settings,
                  metadata=excluded.metadata,
                  updated_at=datetime('now')
                """,
                (
                    data["project_id"],
                    data["name"],
                    data.get("project_type", "game_3d"),
                    data.get("description"),
                    data.get("engine", "godot"),
                    json.dumps(data.get("assets", [])),
                    json.dumps(data.get("settings", {})),
                    json.dumps(data.get("metadata", {})),
                ),
            )
        return self.get_project(data["project_id"])

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM projects WHERE project_id=?", (project_id,))
            row = cur.fetchone()
        if not row:
            return None
        return self._deserialize(dict(row))

    def list_projects(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM projects ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            rows = cur.fetchall()
        return [self._deserialize(dict(r)) for r in rows]

    def delete_project(self, project_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM projects WHERE project_id=?", (project_id,))
            return cur.rowcount > 0

    def count_projects(self) -> int:
        with self._cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM projects")
            row = cur.fetchone()
        return row[0] if row else 0

    def save_export_job(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO export_jobs
                  (job_id, project_id, source_format, target_format, backend, status, output_path, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                  status=excluded.status,
                  output_path=excluded.output_path
                """,
                (
                    data["job_id"],
                    data.get("project_id"),
                    data["source_format"],
                    data["target_format"],
                    data["backend"],
                    data.get("status", "pending"),
                    data.get("output_path"),
                    json.dumps(data.get("metadata", {})),
                ),
            )
        return data

    def record_event(self, backend: str, success: bool) -> None:
        import time

        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO backend_events (backend, success, ts) VALUES (?, ?, ?)",
                (backend, 1 if success else 0, time.time()),
            )

    def _deserialize(self, d: Dict[str, Any]) -> Dict[str, Any]:
        d["assets"] = json.loads(d["assets"])
        d["settings"] = json.loads(d["settings"])
        d["metadata"] = json.loads(d["metadata"])
        return d
