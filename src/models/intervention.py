# src/models/intervention.py
"""Governance Board interventions — the Board's failover/repair/override
authority over a malfunctioning Trance-One (Sovereign) AI.

The advancement pipeline in `governance.py` is about *improving* a model.
This module is the inverse: what the Governance Board (every currently-
registered T2ance Prime) can do when a Trance-One AI — Cornelius MacIntyre,
The Queen, or tAImra — is failing to function, appears corrupted, or has
gone offline. It exists specifically to prevent degradation or loss of
service functionality at the platform's highest tier, where no single
higher authority exists to intervene unilaterally.

Three intervention types:

    repair_request      -- Board requests Cornelius (or the affected
                            Orchestrator) undergo review and repair
    system_recovery      -- Board brings a stalled/offline Orchestrator
                            back into service
    corruption_override  -- Board overrides the Orchestrator's current
                            state/output because it's believed corrupted

Like a Trance-One advancement proposal, an intervention requires unanimous
Board consent before it takes effect — the same governance primitive
(unanimous vote, fail-fast on the first rejection) reused for a different
purpose, so the platform has one consistent mental model for "any action
touching Sovereign-tier authority needs the whole Board behind it," not
two different consensus rules for two similar situations.

Reaching unanimous consent marks the intervention EXECUTED — this
registry is the authorization + audit trail, not the mechanism that
actually restarts a process or reverts a corrupted state; that remediation
happens outside this system (e.g. an ops runbook), the same way
`governance.human_decide()` records a decision without itself deploying
anything.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import List, Optional

from src.entities.platform import get_orchestration_tier
from src.models.governance import (
    DuplicateBoardVoteError,
    InvalidStageTransitionError,
    NotAGovernanceBoardMemberError,
    governance_board_members,
)

DEFAULT_DB_PATH = Path("data/models_intervention.db")


class InterventionType(str, Enum):
    REPAIR_REQUEST = "repair_request"
    SYSTEM_RECOVERY = "system_recovery"
    CORRUPTION_OVERRIDE = "corruption_override"


class InterventionStatus(str, Enum):
    OPEN = "open"  # awaiting unanimous Board consent
    EXECUTED = "executed"  # unanimous consent reached
    WITHDRAWN = "withdrawn"  # any Prime rejected


class NotASovereignTierModelError(ValueError):
    """Raised when an intervention targets a model that isn't Trance-One
    tier — a Tranc3 or T2ance AI's malfunction doesn't need Board
    authorization, since Cornelius already holds direct HIL-A authority
    over both of those tiers."""


@dataclass
class Intervention:
    id: int
    target_model: str
    intervention_type: InterventionType
    status: InterventionStatus
    reason: str
    raised_by: str
    raised_at: float
    resolved_at: Optional[float] = None


@dataclass
class InterventionVote:
    intervention_id: int
    prime_name: str
    approved: bool
    notes: str
    voted_at: float


def _emit_intervention_event(event_type: str, intervention: Intervention, **extra) -> None:
    """Best-effort audit trail via The Observatory, mirroring
    governance._emit_governance_event()'s non-fatal-on-failure pattern.
    Interventions are always SECURITY-severity — a Board acting on a
    Sovereign-tier AI is exactly the kind of event that must be
    permanently archived to The Basement, per Observatory.record()'s
    SECURITY/CRITICAL forwarding."""
    try:
        from src.observability.observatory import EventCategory, EventSeverity, observe

        observe(
            event_type,
            actor=extra.pop("actor", "system"),
            target=f"model:{intervention.target_model}",
            category=EventCategory.GOVERNANCE,
            severity=EventSeverity.SECURITY,
            metadata={
                "intervention_id": intervention.id,
                "intervention_type": intervention.intervention_type.value,
                "status": intervention.status.value,
                **extra,
            },
        )
    except Exception:
        pass


class InterventionRegistry:
    """SQLite-backed registry of Governance Board interventions against
    Trance-One (Sovereign) AIs and their unanimous-vote resolution trail."""

    def __init__(self, db_path: "str | Path" = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS interventions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_model TEXT NOT NULL,
                intervention_type TEXT NOT NULL,
                status TEXT NOT NULL,
                reason TEXT NOT NULL DEFAULT '',
                raised_by TEXT NOT NULL,
                raised_at REAL NOT NULL,
                resolved_at REAL
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_interventions_target_status "
            "ON interventions(target_model, status)"
        )
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS intervention_votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                intervention_id INTEGER NOT NULL,
                prime_name TEXT NOT NULL,
                approved INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                voted_at REAL NOT NULL,
                UNIQUE(intervention_id, prime_name)
            )
            """
        )
        self._conn.commit()

    def _row_to_intervention(self, row: sqlite3.Row) -> Intervention:
        return Intervention(
            id=row["id"],
            target_model=row["target_model"],
            intervention_type=InterventionType(row["intervention_type"]),
            status=InterventionStatus(row["status"]),
            reason=row["reason"],
            raised_by=row["raised_by"],
            raised_at=row["raised_at"],
            resolved_at=row["resolved_at"],
        )

    def _row_to_vote(self, row: sqlite3.Row) -> InterventionVote:
        return InterventionVote(
            intervention_id=row["intervention_id"],
            prime_name=row["prime_name"],
            approved=bool(row["approved"]),
            notes=row["notes"],
            voted_at=row["voted_at"],
        )

    def _get(self, intervention_id: int) -> Optional[Intervention]:
        cur = self._conn.execute("SELECT * FROM interventions WHERE id = ?", (intervention_id,))
        row = cur.fetchone()
        return self._row_to_intervention(row) if row else None

    # ------------------------------------------------------------------
    # Raising an intervention
    # ------------------------------------------------------------------

    def raise_intervention(
        self,
        target_model: str,
        intervention_type: InterventionType,
        reason: str,
        raised_by: str,
    ) -> Intervention:
        """Any Governance Board member (T2ance Prime) can raise an
        intervention against a Trance-One AI believed to be malfunctioning,
        offline, or corrupted. It stays OPEN until the Board reaches
        unanimous consent via intervention_vote()."""
        if raised_by not in governance_board_members():
            raise NotAGovernanceBoardMemberError(
                f"{raised_by!r} is not a currently-registered T2ance Prime — "
                f"only Governance Board members may raise an intervention"
            )
        if get_orchestration_tier(target_model) != "Trance-One":
            raise NotASovereignTierModelError(
                f"{target_model!r} is not a Trance-One (Sovereign) AI — Board "
                f"interventions only apply there; Cornelius already holds direct "
                f"HIL-A authority over Tranc3/T2ance-tier AIs"
            )
        with self._lock:
            now = time.time()
            cur = self._conn.execute(
                "INSERT INTO interventions "
                "(target_model, intervention_type, status, reason, raised_by, raised_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    target_model,
                    intervention_type.value,
                    InterventionStatus.OPEN.value,
                    reason,
                    raised_by,
                    now,
                ),
            )
            self._conn.commit()
            intervention = self._get(cur.lastrowid)
        _emit_intervention_event(
            "model.intervention.raised", intervention, actor=raised_by, reason=reason
        )
        return intervention

    # ------------------------------------------------------------------
    # Board resolution — unanimous consent required, fail-fast on any "no"
    # ------------------------------------------------------------------

    def intervention_vote(
        self, intervention_id: int, prime_name: str, approved: bool, notes: str = ""
    ) -> Intervention:
        if prime_name not in governance_board_members():
            raise NotAGovernanceBoardMemberError(
                f"{prime_name!r} is not a currently-registered T2ance Prime — "
                f"only Governance Board members may vote"
            )
        with self._lock:
            intervention = self._get(intervention_id)
            if intervention is None:
                raise KeyError(f"No intervention with id={intervention_id}")
            if intervention.status != InterventionStatus.OPEN:
                raise InvalidStageTransitionError(
                    f"Intervention {intervention_id} is {intervention.status.value!r}, "
                    f"not awaiting Board resolution"
                )
            existing = self._conn.execute(
                "SELECT 1 FROM intervention_votes WHERE intervention_id = ? AND prime_name = ?",
                (intervention_id, prime_name),
            ).fetchone()
            if existing is not None:
                raise DuplicateBoardVoteError(
                    f"{prime_name!r} has already voted on intervention {intervention_id}"
                )
            now = time.time()
            self._conn.execute(
                "INSERT INTO intervention_votes "
                "(intervention_id, prime_name, approved, notes, voted_at) VALUES (?, ?, ?, ?, ?)",
                (intervention_id, prime_name, int(approved), notes, now),
            )

            next_status: Optional[InterventionStatus] = None
            if not approved:
                next_status = InterventionStatus.WITHDRAWN
            else:
                votes = self._conn.execute(
                    "SELECT prime_name FROM intervention_votes "
                    "WHERE intervention_id = ? AND approved = 1",
                    (intervention_id,),
                ).fetchall()
                approved_names = {row["prime_name"] for row in votes}
                if approved_names >= set(governance_board_members()):
                    next_status = InterventionStatus.EXECUTED

            if next_status is not None:
                self._conn.execute(
                    "UPDATE interventions SET status = ?, resolved_at = ? WHERE id = ?",
                    (next_status.value, now, intervention_id),
                )
            self._conn.commit()
            intervention = self._get(intervention_id)
        _emit_intervention_event(
            "model.intervention.voted",
            intervention,
            actor=prime_name,
            approved=approved,
            resolved=next_status is not None,
        )
        return intervention

    def get_intervention_votes(self, intervention_id: int) -> List[InterventionVote]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM intervention_votes WHERE intervention_id = ? ORDER BY voted_at",
                (intervention_id,),
            )
            return [self._row_to_vote(row) for row in cur.fetchall()]

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, intervention_id: int) -> Optional[Intervention]:
        with self._lock:
            return self._get(intervention_id)

    def list_interventions(
        self,
        status: Optional[InterventionStatus] = None,
        target_model: Optional[str] = None,
    ) -> List[Intervention]:
        with self._lock:
            query = "SELECT * FROM interventions WHERE 1=1"
            params: list = []
            if status is not None:
                query += " AND status = ?"
                params.append(status.value)
            if target_model is not None:
                query += " AND target_model = ?"
                params.append(target_model)
            query += " ORDER BY raised_at DESC"
            cur = self._conn.execute(query, params)
            return [self._row_to_intervention(row) for row in cur.fetchall()]

    def close(self) -> None:
        self._conn.close()


_registry: Optional[InterventionRegistry] = None
_registry_lock = threading.Lock()


def get_intervention_registry() -> InterventionRegistry:
    """Module-level singleton, matching the `get_<x>()` pattern used
    across this codebase."""
    global _registry
    if _registry is None:
        with _registry_lock:
            if _registry is None:
                _registry = InterventionRegistry()
    return _registry
