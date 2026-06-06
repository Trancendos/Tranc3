"""
Ice Box — Quarantine Store
===========================
SQLite-backed store for quarantined content with full audit trail.
"""

from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import List, Optional

from src.security.ice_box.analyser import AnalysisReport, ThreatVerdict

_DEFAULT_DB = Path("data/ice_box_quarantine.db")


@dataclass
class QuarantineRecord:
    quarantine_id: str
    content_hash: str
    source: str
    verdict: str
    findings_json: str
    entropy: float
    content_length: int
    quarantined_at: float
    released_at: Optional[float] = None
    release_reason: Optional[str] = None
    reviewed_by: Optional[str] = None

    @property
    def is_active(self) -> bool:
        return self.released_at is None


class QuarantineStore:
    """
    Thread-safe SQLite quarantine store.  One database file; safe for
    concurrent reads, serialised writes via the WAL journal.
    """

    def __init__(self, db_path: str | Path = _DEFAULT_DB) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS quarantine (
                    quarantine_id   TEXT PRIMARY KEY,
                    content_hash    TEXT NOT NULL,
                    source          TEXT NOT NULL DEFAULT '',
                    verdict         TEXT NOT NULL,
                    findings_json   TEXT NOT NULL DEFAULT '[]',
                    entropy         REAL NOT NULL DEFAULT 0,
                    content_length  INTEGER NOT NULL DEFAULT 0,
                    quarantined_at  REAL NOT NULL,
                    released_at     REAL,
                    release_reason  TEXT,
                    reviewed_by     TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_q_hash ON quarantine(content_hash)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_q_verdict ON quarantine(verdict)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_q_active ON quarantine(released_at) WHERE released_at IS NULL")

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    def quarantine(self, report: AnalysisReport, *, source: str = "") -> str:
        """Store an analysis report; return the quarantine_id."""
        import uuid
        qid = str(uuid.uuid4())
        findings_json = json.dumps([
            {
                "signature_id": f.signature_id,
                "category": f.category.value,
                "severity": f.severity,
                "description": f.description,
                "matched_text": f.matched_text,
            }
            for f in report.findings
        ])
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO quarantine
                   (quarantine_id, content_hash, source, verdict, findings_json,
                    entropy, content_length, quarantined_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (qid, report.content_hash, source, report.verdict.value,
                 findings_json, report.entropy, report.content_length, time.time()),
            )
        return qid

    def release(self, quarantine_id: str, *, reason: str, reviewed_by: str = "") -> bool:
        with self._connect() as conn:
            cursor = conn.execute(
                """UPDATE quarantine
                   SET released_at=?, release_reason=?, reviewed_by=?
                   WHERE quarantine_id=? AND released_at IS NULL""",
                (time.time(), reason, reviewed_by, quarantine_id),
            )
            return cursor.rowcount == 1

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    def get(self, quarantine_id: str) -> Optional[QuarantineRecord]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM quarantine WHERE quarantine_id=?", (quarantine_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def get_by_hash(self, content_hash: str) -> List[QuarantineRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM quarantine WHERE content_hash=? ORDER BY quarantined_at DESC",
                (content_hash,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_active(self, limit: int = 100) -> List[QuarantineRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM quarantine WHERE released_at IS NULL ORDER BY quarantined_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def stats(self) -> dict:
        with self._connect() as conn:
            total = conn.execute("SELECT COUNT(*) FROM quarantine").fetchone()[0]
            active = conn.execute("SELECT COUNT(*) FROM quarantine WHERE released_at IS NULL").fetchone()[0]
            malicious = conn.execute(
                "SELECT COUNT(*) FROM quarantine WHERE verdict='malicious' AND released_at IS NULL"
            ).fetchone()[0]
        return {"total": total, "active": active, "malicious": malicious, "released": total - active}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> QuarantineRecord:
        return QuarantineRecord(
            quarantine_id=row["quarantine_id"],
            content_hash=row["content_hash"],
            source=row["source"],
            verdict=row["verdict"],
            findings_json=row["findings_json"],
            entropy=row["entropy"],
            content_length=row["content_length"],
            quarantined_at=row["quarantined_at"],
            released_at=row["released_at"],
            release_reason=row["release_reason"],
            reviewed_by=row["reviewed_by"],
        )
