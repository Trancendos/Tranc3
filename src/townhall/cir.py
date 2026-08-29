"""The Continual Improvement Register — and the gate that makes it real.

ITIL's continual improvement practice is the one every ITSM implementation
claims and almost none run, because a register nobody is obliged to write to
stays empty and nobody notices. The improvement verbs already existed on the
platform bus (`improvement.raised`, `improvement.realised`,
`improvement.accepted_as_risk`) with nothing emitting them. A register that
merely sits alongside incident closure would be the same defect one layer up:
present, correct, and connected to nothing.

So this register **blocks**. An incident cannot reach CLOSED until it carries
a CIR entry.

Resolution is not closure
-------------------------
The gate is on CLOSED, never on RESOLVED. Resolution restores service, and
blocking it would hold a customer's outage open while paperwork is filed —
the exact perverse incentive that gets improvement gates switched off. By the
time an incident is closed the service is already back; the only thing being
held is the administrative act, which is precisely where the learning
requirement belongs.

The escape hatch is the point, not a hole
-----------------------------------------
A gate with no way through gets routed around: incidents are left open
forever, or someone disables the check. `accept_as_risk` is the way through,
and it is deliberately not free — it demands a named decider and a rationale,
and it emits `improvement.accepted_as_risk` like any other entry. You can
always close an incident. You cannot close one anonymously while claiming
there was nothing to learn.

Every entry, including an acceptance, is durable and attributable. That is
what makes the register worth reading later.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/townhall_cir.db")


class ImprovementKind(str, Enum):
    """What kind of change the entry proposes.

    Deliberately coarse. A taxonomy fine enough to argue about is a taxonomy
    people skip; these are the categories the estate's own remediation work
    has actually fallen into.
    """

    PROCESS = "process"
    TOOLING = "tooling"
    MONITORING = "monitoring"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"


class ImprovementStatus(str, Enum):
    RAISED = "raised"
    REALISED = "realised"
    ACCEPTED_AS_RISK = "accepted_as_risk"


#: Which event each status announces. Every status has one — unlike the
#: incident lifecycle, no CIR state is recorded silently, because the whole
#: purpose of the register is that the decision is visible.
_STATUS_EVENTS: dict[ImprovementStatus, str] = {
    ImprovementStatus.RAISED: "improvement.raised",
    ImprovementStatus.REALISED: "improvement.realised",
    ImprovementStatus.ACCEPTED_AS_RISK: "improvement.accepted_as_risk",
}


class UnknownImprovementError(KeyError):
    """Raised when an improvement id does not exist."""


class ClosureBlocked(PermissionError):
    """Raised when an incident is closed with nothing recorded in the CIR.

    A distinct type rather than a bare ValueError so a caller can answer 409
    for it specifically. It is not a validation failure — the request is
    well-formed and the incident is real; what is missing is the learning.
    """


@dataclass
class ImprovementEntry:
    id: str
    title: str
    kind: ImprovementKind
    status: ImprovementStatus
    rationale: str
    raised_by: str
    #: The incident this came out of, when it came out of one. Improvements
    #: can be raised from a problem, a change post-implementation review, or
    #: nothing at all, so this is optional.
    incident_id: Optional[str] = None
    created_at: float = 0.0
    realised_at: Optional[float] = None
    accepted_by: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "kind": self.kind.value,
            "status": self.status.value,
            "rationale": self.rationale,
            "raised_by": self.raised_by,
            "incident_id": self.incident_id,
            "created_at": self.created_at,
            "realised_at": self.realised_at,
            "accepted_by": self.accepted_by,
        }


def _emit(event_type: str, data: dict[str, Any]) -> None:
    """Announce an entry that has already been committed.

    Best-effort, matching `src.townhall.itsm._emit`: the row is the record and
    the event is the notification, so it is emitted after the commit and never
    allowed to fail the write.
    """
    try:
        from src.event_bus import get_event_bus  # noqa: PLC0415

        get_event_bus().emit_async(event_type=event_type, data=data, source="townhall.cir")
    except Exception as exc:  # noqa: BLE001 - a notification must not fail the write
        logger.debug("cir: emit %s: %s", event_type, exc)


class CirService:
    """Durable improvement entries, and the closure gate that reads them."""

    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_schema()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _create_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS improvements (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    status TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    raised_by TEXT NOT NULL,
                    incident_id TEXT,
                    created_at REAL NOT NULL,
                    realised_at REAL,
                    accepted_by TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_improvement_incident ON improvements (incident_id)"
            )
            self._conn.commit()

    # ── entries ─────────────────────────────────────────────────────────────

    def raise_improvement(
        self,
        title: str,
        *,
        kind: ImprovementKind = ImprovementKind.PROCESS,
        rationale: str = "",
        raised_by: str,
        incident_id: Optional[str] = None,
    ) -> ImprovementEntry:
        """Record something the estate should do differently."""
        if not title.strip():
            raise ValueError("an improvement needs a title")
        if not raised_by.strip():
            raise ValueError("an improvement needs somebody who raised it")
        entry = ImprovementEntry(
            id=f"CIR-{uuid.uuid4().hex[:10]}",
            title=title,
            kind=kind,
            status=ImprovementStatus.RAISED,
            rationale=rationale,
            raised_by=raised_by,
            incident_id=incident_id,
            created_at=time.time(),
        )
        self._insert(entry)
        _emit(_STATUS_EVENTS[ImprovementStatus.RAISED], entry.to_dict())
        return entry

    def accept_as_risk(
        self, title: str, *, accepted_by: str, rationale: str, incident_id: str
    ) -> ImprovementEntry:
        """Record a decision that there is nothing to change here.

        The way past the closure gate, and the reason the gate does not need
        an off switch. Both `accepted_by` and `rationale` are required: an
        unattributed acceptance with no reasoning is indistinguishable from
        the gate not existing.
        """
        if not accepted_by.strip():
            raise ValueError("accepting a risk requires a named decider")
        if not rationale.strip():
            raise ValueError("accepting a risk requires a stated rationale")
        entry = ImprovementEntry(
            id=f"CIR-{uuid.uuid4().hex[:10]}",
            title=title or f"No improvement identified for {incident_id}",
            kind=ImprovementKind.PROCESS,
            status=ImprovementStatus.ACCEPTED_AS_RISK,
            rationale=rationale,
            raised_by=accepted_by,
            incident_id=incident_id,
            created_at=time.time(),
            accepted_by=accepted_by,
        )
        self._insert(entry)
        _emit(_STATUS_EVENTS[ImprovementStatus.ACCEPTED_AS_RISK], entry.to_dict())
        return entry

    def realise(self, improvement_id: str) -> ImprovementEntry:
        """Mark a raised improvement as actually delivered."""
        realised_at = time.time()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE improvements SET status = ?, realised_at = ? WHERE id = ?",
                (ImprovementStatus.REALISED.value, realised_at, improvement_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise UnknownImprovementError(f"no improvement {improvement_id!r}")
        entry = self.get(improvement_id)
        _emit(_STATUS_EVENTS[ImprovementStatus.REALISED], entry.to_dict())
        return entry

    def _insert(self, entry: ImprovementEntry) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO improvements (
                    id, title, kind, status, rationale, raised_by,
                    incident_id, created_at, realised_at, accepted_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.id,
                    entry.title,
                    entry.kind.value,
                    entry.status.value,
                    entry.rationale,
                    entry.raised_by,
                    entry.incident_id,
                    entry.created_at,
                    entry.realised_at,
                    entry.accepted_by,
                ),
            )
            self._conn.commit()

    # ── reads ───────────────────────────────────────────────────────────────

    def get(self, improvement_id: str) -> ImprovementEntry:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM improvements WHERE id = ?", (improvement_id,)
            ).fetchone()
        if row is None:
            raise UnknownImprovementError(f"no improvement {improvement_id!r}")
        return _row_to_entry(row)

    def list_entries(self, *, open_only: bool = False) -> list[ImprovementEntry]:
        query = "SELECT * FROM improvements"
        params: tuple[Any, ...] = ()
        if open_only:
            query += " WHERE status = ?"
            params = (ImprovementStatus.RAISED.value,)
        query += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [_row_to_entry(r) for r in rows]

    def entries_for_incident(self, incident_id: str) -> list[ImprovementEntry]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM improvements WHERE incident_id = ? ORDER BY created_at DESC",
                (incident_id,),
            ).fetchall()
        return [_row_to_entry(r) for r in rows]

    # ── the gate ────────────────────────────────────────────────────────────

    def may_close(self, incident_id: str) -> tuple[bool, str]:
        """Whether this incident carries the learning its closure requires.

        Returns the reason as well as the verdict so a refusal can tell the
        caller what to do about it rather than only that it was refused.
        """
        if self.entries_for_incident(incident_id):
            return True, ""
        return False, (
            f"incident {incident_id} has no Continual Improvement Register entry. "
            "Raise an improvement, or record an explicit accept-as-risk with a "
            "named decider and a rationale, before closing it."
        )

    def require_closable(self, incident_id: str) -> None:
        """`may_close`, as a refusal. Called before the close is written."""
        allowed, reason = self.may_close(incident_id)
        if not allowed:
            raise ClosureBlocked(reason)


def _row_to_entry(row: sqlite3.Row) -> ImprovementEntry:
    return ImprovementEntry(
        id=row["id"],
        title=row["title"],
        kind=ImprovementKind(row["kind"]),
        status=ImprovementStatus(row["status"]),
        rationale=row["rationale"],
        raised_by=row["raised_by"],
        incident_id=row["incident_id"],
        created_at=row["created_at"],
        realised_at=row["realised_at"],
        accepted_by=row["accepted_by"],
    )


_cir: Optional[CirService] = None


def get_cir_service() -> CirService:
    global _cir
    if _cir is None:
        _cir = CirService()
    return _cir
