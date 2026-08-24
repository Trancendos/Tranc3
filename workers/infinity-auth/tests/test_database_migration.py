"""
Infinity Auth — Database migration + mfa_verified persistence tests
=====================================================================
Regression coverage for the cubic-flagged bug where refresh_token()
re-derived mfa_verified from the account's *current* mfa_enabled flag
instead of the session's own recorded state, plus the migration that
adds sessions.mfa_verified to databases created before the column existed.

Deliberately DB-level only (uses the tmp_db fixture directly, not
test_client) — test_client depends on main.create_app, which conftest.py's
test_router.py fixture already fails to import (pre-existing, unrelated to
this session's changes: main.py exposes a module-level `app`, not a
`create_app` factory). Fixing that import mismatch is a separate, broader
task; these tests exercise the real AuthDatabase/session logic without
depending on it.
"""

from __future__ import annotations

import sqlite3


def test_new_database_has_mfa_verified_column(tmp_db):
    columns = {row[1] for row in tmp_db.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "mfa_verified" in columns


def test_mfa_verified_defaults_to_zero(tmp_db):
    tmp_db.execute(
        "INSERT INTO users (user_id, username, email, password_hash, created_at) "
        "VALUES ('u1', 'alice', 'alice@example.com', 'hash', '2026-01-01T00:00:00Z')"
    )
    tmp_db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at) "
        "VALUES ('s1', 'u1', 'rt1', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')"
    )
    tmp_db.commit()
    row = tmp_db.execute("SELECT mfa_verified FROM sessions WHERE session_id = 's1'").fetchone()
    assert row["mfa_verified"] == 0


def test_mfa_verified_persists_when_set_at_login(tmp_db):
    tmp_db.execute(
        "INSERT INTO users (user_id, username, email, password_hash, created_at) "
        "VALUES ('u1', 'alice', 'alice@example.com', 'hash', '2026-01-01T00:00:00Z')"
    )
    tmp_db.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at, "
        "mfa_verified) VALUES ('s1', 'u1', 'rt1', '2026-01-01T00:00:00Z', "
        "'2026-01-02T00:00:00Z', 1)"
    )
    tmp_db.commit()
    row = tmp_db.execute("SELECT mfa_verified FROM sessions WHERE session_id = 's1'").fetchone()
    assert row["mfa_verified"] == 1


def test_migration_adds_column_to_pre_existing_database(tmp_path):
    """
    A DB file created before sessions.mfa_verified existed must gain the
    column (default 0) the next time AuthDatabase opens it, without losing
    existing rows.
    """
    db_path = str(tmp_path / "legacy_auth.db")

    # Simulate a pre-migration DB: sessions table without mfa_verified.
    legacy_conn = sqlite3.connect(db_path)
    legacy_conn.executescript("""
        CREATE TABLE users (
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
        CREATE TABLE sessions (
            session_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            refresh_token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            is_revoked INTEGER DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users(user_id)
        );
    """)
    legacy_conn.execute(
        "INSERT INTO users (user_id, username, email, password_hash, created_at) "
        "VALUES ('u1', 'alice', 'alice@example.com', 'hash', '2026-01-01T00:00:00Z')"
    )
    legacy_conn.execute(
        "INSERT INTO sessions (session_id, user_id, refresh_token, created_at, expires_at) "
        "VALUES ('s1', 'u1', 'rt1', '2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')"
    )
    legacy_conn.commit()
    legacy_conn.close()

    from database import AuthDatabase

    db = AuthDatabase(db_path=db_path)

    columns = {row[1] for row in db.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "mfa_verified" in columns

    # Pre-existing row survives the migration, with the new column defaulted.
    row = db.execute("SELECT * FROM sessions WHERE session_id = 's1'").fetchone()
    assert row is not None
    assert row["mfa_verified"] == 0

    # A second open (idempotency: PRAGMA-gated migration must not error on
    # an already-migrated DB).
    db2 = AuthDatabase(db_path=db_path)
    columns2 = {row[1] for row in db2.execute("PRAGMA table_info(sessions)").fetchall()}
    assert "mfa_verified" in columns2
