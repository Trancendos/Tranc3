"""The Library — SQLite persistence"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import config


class LibraryDatabase:
    _local = threading.local()

    def __init__(self, db_path: str = config.DB_PATH):
        self._db_path = db_path
        with self._cursor() as cur:
            cur.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS documents (
                    doc_id      TEXT PRIMARY KEY,
                    title       TEXT NOT NULL,
                    content     TEXT NOT NULL,
                    format      TEXT DEFAULT 'markdown',
                    collection  TEXT,
                    tags        TEXT DEFAULT '[]',
                    metadata    TEXT DEFAULT '{}',
                    backend     TEXT NOT NULL,
                    url         TEXT,
                    created_at  TEXT DEFAULT (datetime('now')),
                    updated_at  TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS backend_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    backend     TEXT NOT NULL,
                    success     INTEGER NOT NULL,
                    ts          REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_docs_collection ON documents(collection);
                CREATE INDEX IF NOT EXISTS idx_docs_title ON documents(title);
                CREATE INDEX IF NOT EXISTS idx_events_backend_ts ON backend_events(backend, ts);
            """)
        self._migrate()

    def _migrate(self) -> None:
        with self._cursor() as cur:
            for col, defval in [("url", "NULL"), ("updated_at", "datetime('now')")]:
                try:
                    cur.execute(f"ALTER TABLE documents ADD COLUMN {col} TEXT DEFAULT ({defval})")
                except sqlite3.OperationalError:
                    pass

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

    def save_document(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO documents
                  (doc_id, title, content, format, collection, tags, metadata, backend, url)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(doc_id) DO UPDATE SET
                  title=excluded.title,
                  content=excluded.content,
                  format=excluded.format,
                  collection=excluded.collection,
                  tags=excluded.tags,
                  metadata=excluded.metadata,
                  backend=excluded.backend,
                  url=excluded.url,
                  updated_at=datetime('now')
            """,
                (
                    doc["doc_id"],
                    doc["title"],
                    doc["content"],
                    doc["format"],
                    doc.get("collection"),
                    json.dumps(doc.get("tags", [])),
                    json.dumps(doc.get("metadata", {})),
                    doc["backend"],
                    doc.get("url"),
                ),
            )
        return self.get_document(doc["doc_id"])

    def get_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM documents WHERE doc_id=?", (doc_id,))
            row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        d["metadata"] = json.loads(d["metadata"])
        return d

    def search_documents(
        self, query: str, collection: Optional[str] = None, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            like = f"%{query}%"
            if collection:
                cur.execute(
                    "SELECT * FROM documents WHERE (title LIKE ? OR content LIKE ?) AND collection=? LIMIT ?",
                    (like, like, collection, limit),
                )
            else:
                cur.execute(
                    "SELECT * FROM documents WHERE title LIKE ? OR content LIKE ? LIMIT ?",
                    (like, like, limit),
                )
            rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["tags"] = json.loads(d["tags"])
            d["metadata"] = json.loads(d["metadata"])
            results.append(d)
        return results

    def list_documents(
        self, collection: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            if collection:
                cur.execute(
                    "SELECT * FROM documents WHERE collection=? ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (collection, limit, offset),
                )
            else:
                cur.execute(
                    "SELECT * FROM documents ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["tags"] = json.loads(d["tags"])
            d["metadata"] = json.loads(d["metadata"])
            results.append(d)
        return results

    def delete_document(self, doc_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM documents WHERE doc_id=?", (doc_id,))
            return cur.rowcount > 0

    def record_event(self, backend: str, success: bool) -> None:
        import time

        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO backend_events (backend, success, ts) VALUES (?, ?, ?)",
                (backend, 1 if success else 0, time.time()),
            )

    def count_calls_in_window(self, backend: str, window_seconds: int) -> int:
        import time

        cutoff = time.time() - window_seconds
        with self._cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM backend_events WHERE backend=? AND ts > ?",
                (backend, cutoff),
            )
            row = cur.fetchone()
        return row[0] if row else 0
