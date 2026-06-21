"""
Infinity-Admin Service — Database
===================================
AdminDatabase class: SQLite-backed storage for configuration, feature flags,
audit log, compliance events, and entity overrides.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config import DB_PATH


class AdminDatabase:
    """SQLite database for Infinity-Admin configuration and audit logs."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
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

            -- Migration: normalise legacy NULL slots to '' so ON CONFLICT upsert fires correctly.
            -- SQLite UNIQUE treats each NULL as distinct; '' is the correct sentinel for no-slot rows.
            -- This UPDATE is a no-op when no NULL rows exist (idempotent on every startup).
            UPDATE entity_overrides SET slot = '' WHERE slot IS NULL;
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


db = AdminDatabase()
