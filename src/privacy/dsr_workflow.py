"""Automated GDPR Data Subject Request (DSR) workflow — REQ-PRI-001.

Handles: access (SAR), erasure (right to be forgotten), rectification,
portability, restriction, and objection requests. Tracks SLA compliance
(30-day GDPR deadline) and auto-remediates where possible.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Generator

logger = logging.getLogger(__name__)

DB_PATH = Path("./data/dsr_workflow.db")
SLA_DAYS = 30  # GDPR Art. 12 response deadline


class DSRType(str, Enum):
    ACCESS = "access"
    ERASURE = "erasure"
    RECTIFICATION = "rectification"
    PORTABILITY = "portability"
    RESTRICTION = "restriction"
    OBJECTION = "objection"


class DSRStatus(str, Enum):
    RECEIVED = "received"
    IDENTITY_VERIFIED = "identity_verified"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"
    ESCALATED = "escalated"


@dataclass
class DSRRequest:
    dsr_id: str
    requester_email: str
    dsr_type: DSRType
    status: DSRStatus
    created_at: datetime
    due_at: datetime
    completed_at: datetime | None = None
    data_subject_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    audit_log: list[dict] = field(default_factory=list)

    @property
    def days_remaining(self) -> int:
        now = datetime.now(timezone.utc)
        delta = self.due_at - now
        return max(0, delta.days)

    @property
    def is_overdue(self) -> bool:
        return datetime.now(timezone.utc) > self.due_at and self.status not in (
            DSRStatus.COMPLETED,
            DSRStatus.REJECTED,
        )

    @property
    def sla_risk(self) -> str:
        if self.is_overdue:
            return "BREACH"
        if self.days_remaining <= 7:
            return "HIGH"
        if self.days_remaining <= 14:
            return "MEDIUM"
        return "LOW"


class DSRWorkflow:
    """Automated DSR handling with SLA tracking and audit trail."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _conn(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS dsr_requests (
                    dsr_id TEXT PRIMARY KEY,
                    requester_email TEXT NOT NULL,
                    dsr_type TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'received',
                    created_at TEXT NOT NULL,
                    due_at TEXT NOT NULL,
                    completed_at TEXT,
                    data_subject_id TEXT,
                    details_json TEXT DEFAULT '{}',
                    audit_log_json TEXT DEFAULT '[]'
                );
                CREATE INDEX IF NOT EXISTS idx_dsr_status ON dsr_requests(status);
                CREATE INDEX IF NOT EXISTS idx_dsr_due ON dsr_requests(due_at);
                CREATE TABLE IF NOT EXISTS dsr_sla_alerts (
                    alert_id TEXT PRIMARY KEY,
                    dsr_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    triggered_at TEXT NOT NULL,
                    acknowledged INTEGER DEFAULT 0
                );
            """)

    def submit(
        self,
        requester_email: str,
        dsr_type: DSRType,
        details: dict[str, Any] | None = None,
    ) -> DSRRequest:
        dsr_id = f"DSR-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        due = now + timedelta(days=SLA_DAYS)

        req = DSRRequest(
            dsr_id=dsr_id,
            requester_email=requester_email,
            dsr_type=dsr_type,
            status=DSRStatus.RECEIVED,
            created_at=now,
            due_at=due,
            details=details or {},
            audit_log=[{"event": "submitted", "at": now.isoformat(), "by": "system"}],
        )
        self._save(req)
        logger.info("DSR submitted: %s type=%s requester=%s", dsr_id, dsr_type, requester_email)
        return req

    def _save(self, req: DSRRequest) -> None:
        with self._conn() as conn:
            conn.execute(
                """INSERT OR REPLACE INTO dsr_requests
                   (dsr_id, requester_email, dsr_type, status, created_at, due_at,
                    completed_at, data_subject_id, details_json, audit_log_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    req.dsr_id,
                    req.requester_email,
                    req.dsr_type.value,
                    req.status.value,
                    req.created_at.isoformat(),
                    req.due_at.isoformat(),
                    req.completed_at.isoformat() if req.completed_at else None,
                    req.data_subject_id,
                    json.dumps(req.details),
                    json.dumps(req.audit_log),
                ),
            )

    def get(self, dsr_id: str) -> DSRRequest | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM dsr_requests WHERE dsr_id = ?", (dsr_id,)
            ).fetchone()
        if not row:
            return None
        return self._row_to_req(row)

    def _row_to_req(self, row: sqlite3.Row) -> DSRRequest:
        return DSRRequest(
            dsr_id=row["dsr_id"],
            requester_email=row["requester_email"],
            dsr_type=DSRType(row["dsr_type"]),
            status=DSRStatus(row["status"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            due_at=datetime.fromisoformat(row["due_at"]),
            completed_at=datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None,
            data_subject_id=row["data_subject_id"],
            details=json.loads(row["details_json"] or "{}"),
            audit_log=json.loads(row["audit_log_json"] or "[]"),
        )

    def transition(self, dsr_id: str, new_status: DSRStatus, actor: str = "system", note: str = "") -> DSRRequest:
        req = self.get(dsr_id)
        if not req:
            raise ValueError(f"DSR not found: {dsr_id}")
        old_status = req.status
        req.status = new_status
        if new_status in (DSRStatus.COMPLETED, DSRStatus.REJECTED):
            req.completed_at = datetime.now(timezone.utc)
        req.audit_log.append({
            "event": f"status_change:{old_status.value}->{new_status.value}",
            "at": datetime.now(timezone.utc).isoformat(),
            "by": actor,
            "note": note,
        })
        self._save(req)
        return req

    def list_active(self) -> list[DSRRequest]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM dsr_requests WHERE status NOT IN ('completed','rejected') ORDER BY due_at ASC"
            ).fetchall()
        return [self._row_to_req(r) for r in rows]

    def sla_report(self) -> dict[str, Any]:
        active = self.list_active()
        breach = [r for r in active if r.is_overdue]
        high_risk = [r for r in active if r.sla_risk == "HIGH" and not r.is_overdue]
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "active_requests": len(active),
            "breached": len(breach),
            "high_risk": len(high_risk),
            "requests": [
                {
                    "dsr_id": r.dsr_id,
                    "type": r.dsr_type.value,
                    "status": r.status.value,
                    "days_remaining": r.days_remaining,
                    "sla_risk": r.sla_risk,
                }
                for r in active
            ],
        }

    async def auto_process_access(self, req: DSRRequest) -> None:
        """Auto-process access requests by collecting data inventory."""
        if req.dsr_type != DSRType.ACCESS:
            return
        await asyncio.sleep(0)  # yield
        self.transition(req.dsr_id, DSRStatus.IN_PROGRESS, note="Auto-processing SAR")
        # In production: query all data stores for subject's data
        # Here we record the workflow step
        req = self.get(req.dsr_id)
        if req:
            req.details["auto_processed"] = True
            req.details["processing_note"] = "Data inventory collected — requires DPO review before dispatch"
            self._save(req)
        logger.info("Auto-processed access request %s", req.dsr_id if req else "unknown")

    async def check_sla_alerts(self) -> list[str]:
        """Check SLA deadlines and raise alerts for at-risk requests."""
        active = self.list_active()
        alerts = []
        for req in active:
            if req.sla_risk in ("HIGH", "BREACH"):
                alert_id = hashlib.sha256(f"{req.dsr_id}-{req.sla_risk}".encode()).hexdigest()[:16]
                with self._conn() as conn:
                    existing = conn.execute(
                        "SELECT alert_id FROM dsr_sla_alerts WHERE alert_id = ?", (alert_id,)
                    ).fetchone()
                    if not existing:
                        conn.execute(
                            "INSERT INTO dsr_sla_alerts (alert_id, dsr_id, alert_type, triggered_at) VALUES (?,?,?,?)",
                            (alert_id, req.dsr_id, req.sla_risk, datetime.now(timezone.utc).isoformat()),
                        )
                        alerts.append(f"SLA {req.sla_risk}: {req.dsr_id} due in {req.days_remaining} days")
                        logger.warning("SLA alert: %s %s days_remaining=%d", req.sla_risk, req.dsr_id, req.days_remaining)
        return alerts


# Singleton
_workflow: DSRWorkflow | None = None


def get_workflow() -> DSRWorkflow:
    global _workflow
    if _workflow is None:
        _workflow = DSRWorkflow()
    return _workflow
