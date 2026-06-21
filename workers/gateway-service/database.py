"""
database.py — Gateway Service SQLite layer
Manages cache, event, and access-audit tables.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Any

from config import DB_PATH

logger = logging.getLogger("gateway-service")


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def get_db() -> sqlite3.Connection:
    """Open a SQLite connection with WAL mode and Row factory."""
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------


def init_db() -> None:
    """Create all required tables if they do not already exist."""
    conn = get_db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS cache (
            key        TEXT PRIMARY KEY,
            value      TEXT NOT NULL,
            fetched_at REAL NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id          TEXT PRIMARY KEY,
            source      TEXT NOT NULL,
            event_type  TEXT NOT NULL,
            payload     TEXT NOT NULL DEFAULT '{}',
            created_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS access_audit (
            id          TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,
            tier        TEXT NOT NULL,
            endpoint    TEXT NOT NULL,
            method      TEXT NOT NULL,
            granted     INTEGER NOT NULL,
            reason      TEXT,
            timestamp   TEXT NOT NULL
        );
        """
    )
    conn.close()


# ---------------------------------------------------------------------------
# Audit helpers
# ---------------------------------------------------------------------------


def log_access_audit(audit: dict[str, Any]) -> None:
    """Persist an access-audit entry (OWASP A09)."""
    try:
        conn = get_db()
        eid = uuid.uuid4().hex[:16]
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            "INSERT INTO access_audit "
            "(id, user_id, role, tier, endpoint, method, granted, reason, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                eid,
                audit.get("user_id", "anonymous"),
                audit.get("role", "unknown"),
                audit.get("tier", "unknown"),
                audit.get("endpoint", "unknown"),
                audit.get("method", "unknown"),
                1 if audit.get("granted") else 0,
                audit.get("reason", ""),
                now,
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        logger.debug("Failed to write access audit", exc_info=True)


def insert_event(source: str, event_type: str, payload_json: str) -> str:
    """Insert a platform event row and return its id."""
    eid = uuid.uuid4().hex[:16]
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO events (id, source, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?)",
            (eid, source, event_type, payload_json, now),
        )
        conn.commit()
    finally:
        conn.close()
    return eid


def fetch_events(limit: int = 50) -> list[dict]:
    """Return the most-recent platform events."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def fetch_access_audit(limit: int = 50) -> list[dict]:
    """Return the most-recent access-audit entries."""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM access_audit ORDER BY timestamp DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
