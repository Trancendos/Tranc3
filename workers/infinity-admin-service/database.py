"""
Infinity-Admin Service — Database
===================================
SQLite-backed storage for configuration, feature flags, audit log,
compliance events, and entity overrides.

Connection strategy: each execute() opens a fresh connection, runs the
query, commits if needed, and closes before returning — so no single
connection is shared across concurrent async tasks.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from config import DB_PATH

_DDL = """
    CREATE TABLE IF NOT EXISTS system_config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        category TEXT DEFAULT 'general',
        description TEXT,
        updated_at TEXT NOT NULL,
        updated_by TEXT
    );

    CREATE TABLE IF NOT EXISTS feature_flags (
        key TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 0,
        description TEXT,
        pillar TEXT,
        tier_required INTEGER DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT
    );

    CREATE TABLE IF NOT EXISTS admin_actions (
        id TEXT PRIMARY KEY,
        action_type TEXT NOT NULL,
        actor_id TEXT NOT NULL,
        actor_username TEXT,
        target_type TEXT,
        target_id TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS compliance_events (
        id TEXT PRIMARY KEY,
        event_type TEXT NOT NULL,
        severity TEXT DEFAULT 'info',
        pillar TEXT,
        details TEXT,
        created_at TEXT NOT NULL
    );

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

    CREATE INDEX IF NOT EXISTS idx_config_category ON system_config(category);
    CREATE INDEX IF NOT EXISTS idx_actions_actor ON admin_actions(actor_id);
    CREATE INDEX IF NOT EXISTS idx_actions_type ON admin_actions(action_type);
    CREATE INDEX IF NOT EXISTS idx_compliance_type ON compliance_events(event_type);
    CREATE INDEX IF NOT EXISTS idx_overrides_pid ON entity_overrides(location_pid);

    UPDATE entity_overrides SET slot = '' WHERE slot IS NULL;
"""


class _EagerResult:
    """Holds pre-fetched rows so the connection can be closed immediately."""

    def __init__(self, rows: list, lastrowid: int | None = None) -> None:
        self._rows = rows
        self.lastrowid = lastrowid

    def fetchall(self) -> list:
        return self._rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)

    def __getitem__(self, idx):
        return self._rows[idx]


class AdminDatabase:
    """SQLite helper that opens and closes a connection per operation."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _init_schema(self) -> None:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def execute(self, sql: str, params: tuple = ()) -> _EagerResult:
        """Run *sql*, auto-commit writes, and return an eager result."""
        conn = self._open()
        try:
            cursor = conn.execute(sql, params)
            rows = cursor.fetchall()
            lastrowid = cursor.lastrowid
            sql_upper = sql.lstrip().upper()
            if sql_upper.startswith(("INSERT", "UPDATE", "DELETE", "REPLACE")):
                conn.commit()
            return _EagerResult(rows, lastrowid)
        finally:
            conn.close()

    def commit(self) -> None:
        """No-op: execute() auto-commits writes."""


db = AdminDatabase()
