"""
AI Gateway SQLite database — tracks request logs and token budgets per tenant.
"""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from models import TokenBudget


class AIDatabase:
    """SQLite-backed storage for token budgets, usage, and request logs."""

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
                CREATE TABLE IF NOT EXISTS token_budgets (
                    tenant_id TEXT PRIMARY KEY,
                    daily_limit INTEGER DEFAULT 100000,
                    used_today INTEGER DEFAULT 0,
                    last_reset TEXT NOT NULL
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS request_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    request_id TEXT NOT NULL,
                    tenant_id TEXT,
                    model TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    prompt_tokens INTEGER DEFAULT 0,
                    completion_tokens INTEGER DEFAULT 0,
                    total_tokens INTEGER DEFAULT 0,
                    latency_ms INTEGER,
                    success INTEGER DEFAULT 1,
                    error_message TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reqlog_tenant ON request_log(tenant_id)")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_reqlog_timestamp ON request_log(timestamp)")

    def get_budget(self, tenant_id: str) -> TokenBudget:
        conn = self._get_conn()
        row = conn.execute("SELECT * FROM token_budgets WHERE tenant_id=?", (tenant_id,)).fetchone()
        if row:
            budget = TokenBudget(
                tenant_id=row["tenant_id"],
                daily_limit=row["daily_limit"],
                used_today=row["used_today"],
                last_reset=datetime.fromisoformat(row["last_reset"]),
            )
        else:
            budget = TokenBudget(tenant_id=tenant_id)
        # Auto-reset if day changed
        now = datetime.now(timezone.utc)
        if (now - budget.last_reset) >= timedelta(days=1):
            budget.used_today = 0
            budget.last_reset = now
            self._save_budget(budget)
        return budget

    def _save_budget(self, budget: TokenBudget):
        with self._cursor() as cur:
            cur.execute(
                "INSERT OR REPLACE INTO token_budgets "
                "(tenant_id, daily_limit, used_today, last_reset) VALUES (?,?,?,?)",
                (
                    budget.tenant_id,
                    budget.daily_limit,
                    budget.used_today,
                    budget.last_reset.isoformat(),
                ),
            )

    def record_usage(self, tenant_id: str, tokens_used: int):
        budget = self.get_budget(tenant_id)
        budget.used_today += tokens_used
        self._save_budget(budget)

    def check_budget(self, tenant_id: str, tokens_requested: int) -> bool:
        budget = self.get_budget(tenant_id)
        return (budget.used_today + tokens_requested) <= budget.daily_limit

    def log_request(
        self,
        request_id: str,
        tenant_id: Optional[str],
        model: str,
        provider: str,
        prompt_tokens: int,
        completion_tokens: int,
        latency_ms: Optional[int],
        success: bool,
        error: Optional[str] = None,
    ):
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO request_log "
                "(request_id, tenant_id, model, provider, prompt_tokens, completion_tokens, "
                "total_tokens, latency_ms, success, error_message, timestamp) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    request_id,
                    tenant_id,
                    model,
                    provider,
                    prompt_tokens,
                    completion_tokens,
                    prompt_tokens + completion_tokens,
                    latency_ms,
                    int(success),
                    error or "",
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def get_usage_stats(self, tenant_id: Optional[str] = None, hours: int = 24) -> Dict[str, Any]:
        conn = self._get_conn()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        if tenant_id:
            rows = conn.execute(
                "SELECT provider, COUNT(*) as count, SUM(total_tokens) as tokens, "
                "AVG(latency_ms) as avg_latency, "
                "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors "
                "FROM request_log WHERE tenant_id=? AND timestamp>=? GROUP BY provider",
                (tenant_id, cutoff),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT provider, COUNT(*) as count, SUM(total_tokens) as tokens, "
                "AVG(latency_ms) as avg_latency, "
                "SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors "
                "FROM request_log WHERE timestamp>=? GROUP BY provider",
                (cutoff,),
            ).fetchall()
        return {"stats": [dict(r) for r in rows]}
