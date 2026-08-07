"""
Infinity Auth — Database
=========================
SQLite database class for auth persistence.
Replaces Cloudflare D1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from config import DATABASE_PATH


class AuthDatabase:
    """SQLite database for auth persistence. Replaces CF D1."""

    def __init__(self, db_path: str = DATABASE_PATH) -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_tables()

    def _init_tables(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                mfa_enabled INTEGER DEFAULT 0,
                totp_secret TEXT,
                backup_codes TEXT,
                created_at TEXT NOT NULL,
                last_login TEXT,
                is_active INTEGER DEFAULT 1,
                role TEXT DEFAULT 'user'
            );

            CREATE TABLE IF NOT EXISTS sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                refresh_token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                is_revoked INTEGER DEFAULT 0,
                mfa_verified INTEGER DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );

            CREATE TABLE IF NOT EXISTS rate_limits (
                key TEXT PRIMARY KEY,
                count INTEGER DEFAULT 0,
                window_start TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
            CREATE INDEX IF NOT EXISTS idx_sessions_refresh ON sessions(refresh_token);
        """)
        self._conn.commit()
        self._ensure_auth_codes_table()
        self._ensure_sessions_mfa_verified_column()

    def _ensure_sessions_mfa_verified_column(self) -> None:
        """Migration: add sessions.mfa_verified for DBs created before this column existed.

        Persisting MFA state on the session (set once at login, carried forward unchanged
        on refresh) rather than re-deriving it from the account's current mfa_enabled flag
        matters: without this, refreshing a session created before a user turned MFA on
        would silently start asserting mfa_verified=true, even though no MFA challenge
        was ever completed in that session.
        """
        columns = {row[1] for row in self._conn.execute("PRAGMA table_info(sessions)").fetchall()}
        if "mfa_verified" not in columns:
            self._conn.execute("ALTER TABLE sessions ADD COLUMN mfa_verified INTEGER DEFAULT 0")
            self._conn.commit()

    def _ensure_auth_codes_table(self) -> None:
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS auth_codes (
                code TEXT PRIMARY KEY,
                client_id TEXT NOT NULL DEFAULT '',
                redirect_uri TEXT NOT NULL DEFAULT '',
                scope TEXT NOT NULL DEFAULT 'openid',
                code_challenge TEXT NOT NULL DEFAULT '',
                code_challenge_method TEXT NOT NULL DEFAULT 'S256',
                expires_at INTEGER NOT NULL
            )
        """)
        self._conn.commit()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        return self._conn.execute(sql, params)

    def commit(self) -> None:
        self._conn.commit()
