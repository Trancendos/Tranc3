"""
Database — Infinity Portal Service
====================================
SQLite persistence layer for portal sessions, gate routing log,
and portal events.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config import DB_PATH


class PortalDatabase:
    """SQLite database for portal session and routing persistence."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS portal_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                tier INTEGER NOT NULL DEFAULT 0,
                infinity_role TEXT DEFAULT 'user',
                routed_to TEXT,
                access_token TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_active INTEGER DEFAULT 1,
                ip_address TEXT,
                user_agent TEXT
            );

            CREATE TABLE IF NOT EXISTS gate_routing_log (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                username TEXT NOT NULL,
                role TEXT NOT NULL,
                from_location TEXT NOT NULL DEFAULT 'infinity_portal',
                to_location TEXT NOT NULL,
                routed_at TEXT NOT NULL,
                transfer_system TEXT DEFAULT 'bridge'
            );

            CREATE TABLE IF NOT EXISTS portal_events (
                id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                user_id TEXT,
                username TEXT,
                ip_address TEXT,
                user_agent TEXT,
                payload TEXT,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON portal_sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_active ON portal_sessions(is_active);
            CREATE INDEX IF NOT EXISTS idx_routing_user ON gate_routing_log(user_id);
            CREATE INDEX IF NOT EXISTS idx_events_type ON portal_events(event_type);
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()


# Module-level singleton — imported by service.py and router.py
db = PortalDatabase()
