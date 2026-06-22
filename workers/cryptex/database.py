"""Cryptex / The Ice Box — SQLite persistence"""
from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import config
from models import ScanResult, ThreatIndicator, ScanStatus


class CryptexDatabase:
    _local = threading.local()

    def __init__(self, db_path: str = config.DB_PATH):
        self._db_path = db_path
        with self._cursor() as cur:
            cur.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS scan_results (
                    scan_id     TEXT PRIMARY KEY,
                    scan_type   TEXT,
                    target      TEXT,
                    engine_used TEXT,
                    status      TEXT DEFAULT 'pending',
                    threat_found INTEGER DEFAULT 0,
                    severity    TEXT DEFAULT 'unknown',
                    findings    TEXT DEFAULT '[]',
                    raw_output  TEXT DEFAULT '{}',
                    error_message TEXT,
                    started_at  TEXT,
                    completed_at TEXT,
                    created_at  TEXT DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS threat_indicators (
                    indicator_id TEXT PRIMARY KEY,
                    ioc_type    TEXT,
                    value       TEXT,
                    severity    TEXT DEFAULT 'unknown',
                    source      TEXT DEFAULT '',
                    tags        TEXT DEFAULT '[]',
                    metadata    TEXT DEFAULT '{}',
                    created_at  TEXT DEFAULT (datetime('now'))
                );
                CREATE INDEX IF NOT EXISTS idx_scans_status ON scan_results(status);
                CREATE INDEX IF NOT EXISTS idx_ioc_value ON threat_indicators(value);
                CREATE INDEX IF NOT EXISTS idx_ioc_type ON threat_indicators(ioc_type);
            """)

    @contextmanager
    def _cursor(self):
        if not getattr(self._local, "conn", None):
            self._local.conn = sqlite3.connect(self._db_path)
            self._local.conn.row_factory = sqlite3.Row
        conn = self._local.conn
        try:
            cur = conn.cursor()
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def save_result(self, result: ScanResult) -> ScanResult:
        with self._cursor() as cur:
            cur.execute("""
                INSERT OR REPLACE INTO scan_results
                  (scan_id, engine_used, status, threat_found, severity,
                   findings, raw_output, error_message, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                result.scan_id,
                result.engine_used,
                result.status.value,
                1 if result.threat_found else 0,
                result.severity.value,
                json.dumps(result.findings),
                json.dumps(result.raw_output),
                result.error_message,
                result.started_at.isoformat() if result.started_at else None,
                result.completed_at.isoformat() if result.completed_at else None,
            ))
        return result

    def get_result(self, scan_id: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute("SELECT * FROM scan_results WHERE scan_id=?", (scan_id,))
            row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def list_results(self, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM scan_results ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
            return [dict(r) for r in cur.fetchall()]

    def save_indicator(self, ioc: ThreatIndicator) -> ThreatIndicator:
        with self._cursor() as cur:
            cur.execute("""
                INSERT OR REPLACE INTO threat_indicators
                  (indicator_id, ioc_type, value, severity, source, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                ioc.indicator_id,
                ioc.ioc_type,
                ioc.value,
                ioc.severity.value,
                ioc.source,
                json.dumps(ioc.tags),
                json.dumps(ioc.metadata),
            ))
        return ioc

    def list_indicators(
        self,
        ioc_type: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._cursor() as cur:
            if ioc_type:
                cur.execute(
                    "SELECT * FROM threat_indicators WHERE ioc_type=? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (ioc_type, limit, offset),
                )
            else:
                cur.execute(
                    "SELECT * FROM threat_indicators ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            return [dict(r) for r in cur.fetchall()]

    def lookup_indicator(self, value: str) -> Optional[Dict[str, Any]]:
        with self._cursor() as cur:
            cur.execute(
                "SELECT * FROM threat_indicators WHERE value=? ORDER BY created_at DESC LIMIT 1",
                (value,),
            )
            row = cur.fetchone()
        return dict(row) if row else None
