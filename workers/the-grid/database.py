"""The Digital Grid — SQLite persistence layer"""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from models import WorkflowDefinition, WorkflowExecution


class GridDatabase:
    """SQLite-backed storage for workflow definitions and executions."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(str(self.db_path), timeout=10)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _cursor(self):
        conn = self._get_conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        with self._cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_definitions (
                    workflow_id   TEXT PRIMARY KEY,
                    name          TEXT NOT NULL,
                    description   TEXT DEFAULT '',
                    steps         TEXT NOT NULL DEFAULT '[]',
                    metadata      TEXT DEFAULT '{}',
                    version       INTEGER DEFAULT 1,
                    created_at    TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS workflow_executions (
                    execution_id  TEXT PRIMARY KEY,
                    workflow_id   TEXT NOT NULL,
                    status        TEXT NOT NULL DEFAULT 'pending',
                    engine_used   TEXT,
                    input_data    TEXT DEFAULT '{}',
                    output_data   TEXT DEFAULT '{}',
                    step_results  TEXT DEFAULT '{}',
                    error_message TEXT,
                    started_at    TEXT,
                    completed_at  TEXT,
                    created_at    TEXT NOT NULL
                )
            """)
            # add engine_used column if migrating from old schema
            try:
                cur.execute("ALTER TABLE workflow_executions ADD COLUMN engine_used TEXT")
            except sqlite3.OperationalError:
                pass  # column already exists
            cur.execute(
                "CREATE INDEX IF NOT EXISTS idx_exec_workflow ON workflow_executions(workflow_id)"
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_exec_status ON workflow_executions(status)")

    # ── Definitions ──────────────────────────────────────────────────────────

    def save_definition(self, wf: WorkflowDefinition) -> WorkflowDefinition:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO workflow_definitions "
                "(workflow_id, name, description, steps, metadata, version, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (
                    wf.workflow_id,
                    wf.name,
                    wf.description,
                    json.dumps([s.model_dump() for s in wf.steps]),
                    json.dumps(wf.metadata),
                    wf.version,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return wf

    def get_definition(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        row = (
            self._get_conn()
            .execute("SELECT * FROM workflow_definitions WHERE workflow_id=?", (workflow_id,))
            .fetchone()
        )
        return dict(row) if row else None

    def list_definitions(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        rows = (
            self._get_conn()
            .execute(
                "SELECT * FROM workflow_definitions ORDER BY name LIMIT ? OFFSET ?",
                (limit, offset),
            )
            .fetchall()
        )
        return [dict(r) for r in rows]

    def delete_definition(self, workflow_id: str) -> bool:
        with self._cursor() as cur:
            cur.execute("DELETE FROM workflow_definitions WHERE workflow_id=?", (workflow_id,))
            return cur.rowcount > 0

    # ── Executions ───────────────────────────────────────────────────────────

    def save_execution(self, ex: WorkflowExecution) -> WorkflowExecution:
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO workflow_executions "
                "(execution_id, workflow_id, status, engine_used, input_data, output_data, "
                " step_results, error_message, started_at, completed_at, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ex.execution_id,
                    ex.workflow_id,
                    ex.status.value,
                    ex.engine_used,
                    json.dumps(ex.input_data),
                    json.dumps(ex.output_data),
                    json.dumps(ex.step_results),
                    ex.error_message,
                    ex.started_at.isoformat() if ex.started_at else None,
                    ex.completed_at.isoformat() if ex.completed_at else None,
                    ex.created_at.isoformat(),
                ),
            )
        return ex

    def get_execution(self, execution_id: str) -> Optional[Dict[str, Any]]:
        row = (
            self._get_conn()
            .execute("SELECT * FROM workflow_executions WHERE execution_id=?", (execution_id,))
            .fetchone()
        )
        return dict(row) if row else None

    def list_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query = "SELECT * FROM workflow_executions WHERE 1=1"
        params: list = []
        if workflow_id:
            query += " AND workflow_id=?"
            params.append(workflow_id)
        if status:
            query += " AND status=?"
            params.append(status)
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self._get_conn().execute(query, params).fetchall()
        return [dict(r) for r in rows]
