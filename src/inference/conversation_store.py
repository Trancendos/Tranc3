"""
Conversation Store — persistent multi-turn conversation history.

SQLite-backed, per-session. Survives restarts. Supports:
  - Append messages (user/assistant/system)
  - Retrieve full history for a session
  - Sliding window (trim to last N messages)
  - Session TTL expiry
  - Export as OpenAI-compatible message list

Zero-cost: SQLite stdlib only.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional


@dataclass
class Message:
    role: str  # system | user | assistant
    content: str
    timestamp: float
    session_id: str
    message_id: Optional[int] = None


class ConversationStore:
    """
    Persistent conversation history store.

    Each conversation is identified by a session_id (UUID or similar).
    Messages are stored in order and can be retrieved as an OpenAI-
    compatible message list ready to pass to any LLM.
    """

    def __init__(
        self,
        db_path: str = "data/conversations.db",
        max_messages_per_session: int = 100,
        session_ttl_hours: int = 24,
    ) -> None:
        self._db_path = db_path
        self._max_messages = max_messages_per_session
        self._session_ttl = session_ttl_hours * 3600
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ── Init ─────────────────────────────────────────────────────────────────

    def _init_db(self) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp REAL NOT NULL
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_session_ts ON messages(session_id, timestamp)"
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    last_active REAL NOT NULL,
                    user_id TEXT,
                    metadata TEXT
                )"""
            )
            conn.commit()

    # ── Write ─────────────────────────────────────────────────────────────────

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
    ) -> int:
        """Append a message and return its ID."""
        now = time.time()
        with sqlite3.connect(self._db_path) as conn:
            # Upsert session
            conn.execute(
                """INSERT INTO sessions (session_id, created_at, last_active, user_id)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(session_id) DO UPDATE SET last_active=excluded.last_active""",
                (session_id, now, now, user_id),
            )
            cursor = conn.execute(
                "INSERT INTO messages (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, role, content, now),
            )
            msg_id = cursor.lastrowid
            conn.commit()

        # Trim if over limit
        self._trim_session(session_id)
        return msg_id  # type: ignore[return-value]

    def set_system_prompt(self, session_id: str, system_prompt: str) -> None:
        """Set or replace the system message for a session."""
        with sqlite3.connect(self._db_path) as conn:
            # Remove existing system message
            conn.execute(
                "DELETE FROM messages WHERE session_id=? AND role='system'",
                (session_id,),
            )
            conn.commit()
        self.add_message(session_id, "system", system_prompt)

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_messages(
        self,
        session_id: str,
        limit: Optional[int] = None,
        include_system: bool = True,
    ) -> List[Dict]:
        """Return messages as OpenAI-compatible list."""
        with sqlite3.connect(self._db_path) as conn:
            if include_system:
                # System first, then chronological
                rows = conn.execute(
                    """SELECT role, content FROM messages
                       WHERE session_id=?
                       ORDER BY CASE WHEN role='system' THEN 0 ELSE 1 END, timestamp ASC
                       LIMIT ?""",
                    (session_id, limit or self._max_messages),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT role, content FROM messages
                       WHERE session_id=? AND role != 'system'
                       ORDER BY timestamp ASC
                       LIMIT ?""",
                    (session_id, limit or self._max_messages),
                ).fetchall()

        return [{"role": role, "content": content} for role, content in rows]

    def get_session_ids(self, user_id: Optional[str] = None) -> List[str]:
        """List active session IDs, optionally filtered by user."""
        cutoff = time.time() - self._session_ttl
        with sqlite3.connect(self._db_path) as conn:
            if user_id:
                rows = conn.execute(
                    "SELECT session_id FROM sessions WHERE last_active > ? AND user_id = ? ORDER BY last_active DESC",
                    (cutoff, user_id),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT session_id FROM sessions WHERE last_active > ? ORDER BY last_active DESC",
                    (cutoff,),
                ).fetchall()
        return [r[0] for r in rows]

    def session_exists(self, session_id: str) -> bool:
        with sqlite3.connect(self._db_path) as conn:
            row = conn.execute(
                "SELECT 1 FROM sessions WHERE session_id=?", (session_id,)
            ).fetchone()
        return row is not None

    # ── Maintenance ───────────────────────────────────────────────────────────

    def _trim_session(self, session_id: str) -> None:
        """Keep only the last max_messages for a session."""
        with sqlite3.connect(self._db_path) as conn:
            count = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE session_id=? AND role != 'system'",
                (session_id,),
            ).fetchone()[0]
            if count > self._max_messages:
                excess = count - self._max_messages
                conn.execute(
                    """DELETE FROM messages WHERE id IN (
                        SELECT id FROM messages
                        WHERE session_id=? AND role != 'system'
                        ORDER BY timestamp ASC
                        LIMIT ?
                    )""",
                    (session_id, excess),
                )
                conn.commit()

    def delete_session(self, session_id: str) -> None:
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("DELETE FROM messages WHERE session_id=?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE session_id=?", (session_id,))
            conn.commit()

    def expire_old_sessions(self) -> int:
        """Delete sessions older than TTL. Returns count deleted."""
        cutoff = time.time() - self._session_ttl
        with sqlite3.connect(self._db_path) as conn:
            old_sessions = conn.execute(
                "SELECT session_id FROM sessions WHERE last_active < ?", (cutoff,)
            ).fetchall()
            session_ids = [r[0] for r in old_sessions]
            if session_ids:
                # Delete row-by-row to avoid any dynamic SQL construction (Sourcery S608).
                for sid in session_ids:
                    conn.execute("DELETE FROM messages WHERE session_id = ?", (sid,))
                    conn.execute("DELETE FROM sessions WHERE session_id = ?", (sid,))
                conn.commit()
        return len(session_ids)


# Module-level singleton
_store: Optional[ConversationStore] = None


def get_conversation_store() -> ConversationStore:
    global _store
    if _store is None:
        _store = ConversationStore()
    return _store
