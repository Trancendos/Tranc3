"""The Lab — SQLite persistence"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

import config


class LabDatabase:
    _local = threading.local()

    def __init__(self, db_path: str = config.DB_PATH):
        self._db_path = db_path
        with self._cursor() as cur:
            cur.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS code_requests (
                    request_id  TEXT PRIMARY KEY,
                    prompt      TEXT NOT NULL,
                    language    TEXT,
                    task_type   TEXT NOT NULL,
                    backend     TEXT NOT NULL,
                    result      TEXT NOT NULL,
                    tokens_used INTEGER,
                    latency_ms  REAL,
                    metadata    TEXT DEFAULT '{}',
                    created_at  TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS backend_events (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    backend     TEXT NOT NULL,
                    success     INTEGER NOT NULL,
                    ts          REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_req_backend ON code_requests(backend);
                CREATE INDEX IF NOT EXISTS idx_req_task ON code_requests(task_type);
                CREATE INDEX IF NOT EXISTS idx_events_backend_ts ON backend_events(backend, ts);
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

    def save_request(self, data: Dict[str, Any]) -> Dict[str, Any]:
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO code_requests
                  (request_id, prompt, language, task_type, backend, result, tokens_used, latency_ms, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO NOTHING
                """,
                (
                    data["request_id"],
                    data["prompt"],
                    data.get("language"),
                    data["task_type"],
                    data["backend"],
                    data["result"],
                    data.get("tokens_used"),
                    data.get("latency_ms"),
                    json.dumps(data.get("metadata", {})),
                ),
            )
        return self.get_request(data["request_id"])

    def get_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM code_requests WHERE request_id=?", (request_id,))
            row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["metadata"] = json.loads(d["metadata"])
        return d

    def list_requests(
        self, backend: Optional[str] = None, limit: int = 50, offset: int = 0
    ) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            if backend:
                cur.execute(
                    "SELECT * FROM code_requests WHERE backend=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (backend, limit, offset),
                )
            else:
                cur.execute(
                    "SELECT * FROM code_requests ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            rows = cur.fetchall()
        results = []
        for row in rows:
            d = dict(row)
            d["metadata"] = json.loads(d["metadata"])
            results.append(d)
        return results

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
