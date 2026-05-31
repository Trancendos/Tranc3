"""Infinity Admin OS — shared SQLite (entity overrides + admin metadata)."""

from __future__ import annotations

import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from src.entities.override_store import invalidate_override_cache

_DB_PATH = Path(
    os.environ.get(
        "ENTITY_OVERRIDES_DB",
        os.environ.get("INFINITY_ADMIN_DB_PATH", "data/infinity_admin.db"),
    )
)


def db_path() -> Path:
    return _DB_PATH


def get_connection() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS entity_overrides (
            id TEXT PRIMARY KEY,
            location_pid TEXT NOT NULL,
            entity_type TEXT NOT NULL,
            slot TEXT NOT NULL DEFAULT '',
            original_name TEXT NOT NULL,
            override_name TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            UNIQUE(location_pid, entity_type, slot)
        );
        CREATE INDEX IF NOT EXISTS idx_overrides_pid ON entity_overrides(location_pid);

        CREATE TABLE IF NOT EXISTS admin_os_backup_log (
            id TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            size_bytes INTEGER DEFAULT 0,
            trigger TEXT DEFAULT 'manual',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_os_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    conn.execute("UPDATE entity_overrides SET slot = '' WHERE slot IS NULL")
    conn.commit()


def upsert_override(
    location_pid: str,
    entity_type: str,
    slot: str | None,
    original_name: str,
    override_name: str,
    updated_by: str = "admin-os",
) -> None:
    slot_val = slot if slot is not None else ""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO entity_overrides
               (id, location_pid, entity_type, slot, original_name, override_name, updated_at, updated_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(location_pid, entity_type, slot)
           DO UPDATE SET override_name=excluded.override_name,
                         updated_at=excluded.updated_at,
                         updated_by=excluded.updated_by""",
        (
            uuid.uuid4().hex[:16],
            location_pid,
            entity_type,
            slot_val,
            original_name,
            override_name,
            now,
            updated_by,
        ),
    )
    conn.commit()
    conn.close()
    invalidate_override_cache()


def log_backup(backup_id: str, path: str, size_bytes: int, trigger: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        "INSERT INTO admin_os_backup_log (id, path, size_bytes, trigger, created_at) VALUES (?,?,?,?,?)",
        (backup_id, path, size_bytes, trigger, now),
    )
    conn.commit()
    conn.close()


def list_backup_log(limit: int = 50) -> list[dict]:
    conn = get_connection()
    rows = conn.execute(
        "SELECT id, path, size_bytes, trigger, created_at FROM admin_os_backup_log ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    row = conn.execute("SELECT value FROM admin_os_settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    conn.execute(
        """INSERT INTO admin_os_settings (key, value, updated_at) VALUES (?, ?, ?)
           ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
        (key, value, now),
    )
    conn.commit()
    conn.close()
