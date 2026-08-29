"""The Town Hall — ITSM / ITIL incident and change records.

What changed and why
--------------------
This module used to hold incidents and changes in two in-memory dictionaries.
It emitted nothing and referenced no other subsystem, so a record here was
invisible to the rest of the platform and gone on restart. The ITIL4-AILP
architecture draws arrows from Incident Management to Problem Management, to
Change Enablement and to the improvement register; none of them existed.

Three things are now true:

**Records survive a restart.** SQLite, same convention as the roles registry
and the Exchange registries. A ticket that disappears when a worker recycles
is not a record of anything.

**Transitions are announced.** Every lifecycle change emits the matching verb
from `PlatformEventType`, so Problem Management can see a recurrence and the
CIR can see a resolution without polling this module.

**An incident knows who answers for it.** `service` resolves through
`src.cmdb.identity`, so an incident against `SRV-SPARK-001` carries The Spark,
its Tier-3 AI and its Tier-2 Prime. Before the identity spine existed there was
no programmatic way to get from a service to an owner.

The database is the guarantee; the event is the notification
------------------------------------------------------------
`emit_async` is fire-and-forget and does nothing but warn when no event loop is
running. So emission is *not* a delivery guarantee, and this module does not
pretend otherwise: the transition is committed to SQLite first and emitted
afterwards. A consumer that missed an event can still read the record. Writing
it the other way round — emit, then persist — would produce events for
transitions that never landed.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger("tranc3.townhall.itsm")

DEFAULT_DB_PATH = Path("data/townhall_itsm.db")


class IncidentPriority(str, Enum):
    P1 = "p1"
    P2 = "p2"
    P3 = "p3"
    P4 = "p4"


class IncidentStatus(str, Enum):
    NEW = "new"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"


#: Which event each status transition announces.
#:
#: MITIGATED has no verb of its own. Service is restored but the incident is
#: not resolved, and inventing `incident.mitigated` would give consumers a
#: transition the architecture does not define. It is recorded, not announced.
_STATUS_EVENTS: dict[IncidentStatus, Optional[str]] = {
    IncidentStatus.NEW: "incident.raised",
    IncidentStatus.INVESTIGATING: "incident.triaged",
    IncidentStatus.MITIGATED: None,
    IncidentStatus.RESOLVED: "incident.resolved",
    IncidentStatus.CLOSED: "incident.closed",
}

_TERMINAL = (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)


class UnknownIncidentError(KeyError):
    """Raised when an incident id does not exist.

    Raised rather than returning None: a caller holding an id that resolves to
    nothing is looking at a typo or a deleted record, and a silent None turns
    that into a status update nobody notices was dropped.
    """


@dataclass
class ServiceOwnership:
    """Who answers for the service an incident is about.

    `resolved` is False when the service string is not a known ServiceID, PID,
    Location name or port. That is recorded rather than guessed — putting a
    plausible-looking owner on an incident is worse than admitting there is
    none, because it routes the page to somebody who is not on the hook.
    """

    service: str
    resolved: bool = False
    location: Optional[str] = None
    service_id: Optional[str] = None
    tier3_ai: Optional[str] = None
    tier2_prime: Optional[str] = None
    location_is_ambiguous: bool = False
    unresolved_reason: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "resolved": self.resolved,
            "location": self.location,
            "service_id": self.service_id,
            "tier3_ai": self.tier3_ai,
            "tier2_prime": self.tier2_prime,
            "location_is_ambiguous": self.location_is_ambiguous,
            "unresolved_reason": self.unresolved_reason,
        }


def resolve_ownership(service: str) -> ServiceOwnership:
    """Resolve a service string to the Location and AIs accountable for it."""
    try:
        from src.cmdb.identity import (  # noqa: PLC0415
            IdentityResolutionError,
            resolve,
        )
    except Exception as exc:  # pragma: no cover - cmdb package always present
        return ServiceOwnership(
            service=service, unresolved_reason=f"identity spine unavailable: {exc}"
        )

    try:
        identity = resolve(service)
    except IdentityResolutionError as exc:
        return ServiceOwnership(service=service, unresolved_reason=str(exc))

    return ServiceOwnership(
        service=service,
        resolved=True,
        location=identity.location,
        service_id=identity.service_id,
        tier3_ai=identity.tier3_ai or None,
        tier2_prime=identity.tier2_prime or None,
        location_is_ambiguous=identity.location_is_ambiguous,
        unresolved_reason=identity.unmapped_reason,
    )


@dataclass
class ItsmIncident:
    id: str
    title: str
    description: str
    priority: IncidentPriority
    status: IncidentStatus = IncidentStatus.NEW
    service: str = "tranc3-backend"
    assignee: str | None = None
    created_at: float = field(default_factory=time.time)
    resolved_at: float | None = None
    itil_practice: str = "incident-management"
    ownership: Optional[ServiceOwnership] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority.value,
            "status": self.status.value,
            "service": self.service,
            "assignee": self.assignee,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
            "itil_practice": self.itil_practice,
            "ownership": self.ownership.to_dict() if self.ownership else None,
        }


@dataclass
class ChangeRecord:
    id: str
    title: str
    change_type: str  # standard | normal | emergency
    status: str = "draft"
    risk: str = "low"
    created_at: float = field(default_factory=time.time)
    service: Optional[str] = None
    ownership: Optional[ServiceOwnership] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "change_type": self.change_type,
            "status": self.status,
            "risk": self.risk,
            "created_at": self.created_at,
            "service": self.service,
            "ownership": self.ownership.to_dict() if self.ownership else None,
        }


def _emit(event_type: str, data: dict[str, Any]) -> None:
    """Announce a transition that has already been committed.

    Best-effort by design. `emit_async` warns and drops when no event loop is
    running, so this is a notification and never the record itself.
    """
    try:
        from src.event_bus import get_event_bus  # noqa: PLC0415

        get_event_bus().emit_async(event_type=event_type, data=data, source="townhall.itsm")
    except Exception as exc:  # nosec B110 - notification must not fail the write
        logger.debug("itsm: emit %s: %s", event_type, exc)


class ItsmService:
    """Durable incident and change records that announce their transitions."""

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
                CREATE TABLE IF NOT EXISTS incidents (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    status TEXT NOT NULL,
                    service TEXT NOT NULL,
                    assignee TEXT,
                    created_at REAL NOT NULL,
                    resolved_at REAL,
                    itil_practice TEXT NOT NULL,
                    location TEXT,
                    service_id TEXT,
                    tier3_ai TEXT,
                    tier2_prime TEXT,
                    ownership_resolved INTEGER NOT NULL DEFAULT 0,
                    ownership_ambiguous INTEGER NOT NULL DEFAULT 0,
                    unresolved_reason TEXT
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incident_status "
                "ON incidents (status, created_at DESC)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_incident_location ON incidents (location)"
            )
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS changes (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    change_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    risk TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    service TEXT,
                    location TEXT,
                    service_id TEXT,
                    tier3_ai TEXT,
                    tier2_prime TEXT,
                    ownership_resolved INTEGER NOT NULL DEFAULT 0,
                    ownership_ambiguous INTEGER NOT NULL DEFAULT 0,
                    unresolved_reason TEXT
                )
                """
            )
            self._conn.commit()

    # ── incidents ───────────────────────────────────────────────────────────

    def create_incident(
        self,
        title: str,
        description: str,
        *,
        priority: IncidentPriority = IncidentPriority.P3,
        service: str = "tranc3-backend",
    ) -> ItsmIncident:
        ownership = resolve_ownership(service)
        inc = ItsmIncident(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            priority=priority,
            service=service,
            ownership=ownership,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO incidents (id, title, description, priority, status, service, "
                "assignee, created_at, resolved_at, itil_practice, location, service_id, "
                "tier3_ai, tier2_prime, ownership_resolved, ownership_ambiguous, "
                "unresolved_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    inc.id,
                    inc.title,
                    inc.description,
                    inc.priority.value,
                    inc.status.value,
                    inc.service,
                    inc.assignee,
                    inc.created_at,
                    inc.resolved_at,
                    inc.itil_practice,
                    ownership.location,
                    ownership.service_id,
                    ownership.tier3_ai,
                    ownership.tier2_prime,
                    int(ownership.resolved),
                    int(ownership.location_is_ambiguous),
                    ownership.unresolved_reason,
                ),
            )
            self._conn.commit()

        _emit("incident.raised", self._incident_event(inc))
        return inc

    def update_incident_status(self, incident_id: str, status: IncidentStatus) -> ItsmIncident:
        """Move an incident to a new status, persist it, then announce it."""
        resolved_at = time.time() if status in _TERMINAL else None
        with self._lock:
            cur = self._conn.execute(
                "UPDATE incidents SET status = ?, resolved_at = ? WHERE id = ?",
                (status.value, resolved_at, incident_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise UnknownIncidentError(f"no incident {incident_id!r}")
        inc = self.get_incident(incident_id)

        event = _STATUS_EVENTS.get(status)
        if event:
            _emit(event, self._incident_event(inc))
        return inc

    def escalate_incident(self, incident_id: str, *, reason: str) -> ItsmIncident:
        """Raise an incident to P1 and announce the escalation.

        Separate from a status change because escalation is a priority fact,
        not a lifecycle one — an incident can be escalated while still
        investigating, and the architecture's MIM flow keys off it.
        """
        if not reason.strip():
            raise ValueError("An escalation needs a stated reason")
        with self._lock:
            cur = self._conn.execute(
                "UPDATE incidents SET priority = ? WHERE id = ?",
                (IncidentPriority.P1.value, incident_id),
            )
            self._conn.commit()
            if cur.rowcount == 0:
                raise UnknownIncidentError(f"no incident {incident_id!r}")
        inc = self.get_incident(incident_id)
        _emit("incident.escalated", {**self._incident_event(inc), "reason": reason})
        return inc

    def get_incident(self, incident_id: str) -> ItsmIncident:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM incidents WHERE id = ?", (incident_id,)
            ).fetchone()
        if row is None:
            raise UnknownIncidentError(f"no incident {incident_id!r}")
        return self._row_to_incident(row)

    def list_incidents(self, *, open_only: bool = False) -> list[ItsmIncident]:
        sql = "SELECT * FROM incidents"
        args: tuple = ()
        if open_only:
            sql += " WHERE status NOT IN (?, ?)"
            args = (IncidentStatus.RESOLVED.value, IncidentStatus.CLOSED.value)
        sql += " ORDER BY created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [self._row_to_incident(r) for r in rows]

    def incidents_for_location(self, location: str) -> list[ItsmIncident]:
        """Every incident against a service the given Location owns.

        The question the architecture asks constantly and could not answer
        before the identity spine: what is currently wrong at The Observatory.
        """
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM incidents WHERE location = ? ORDER BY created_at DESC",
                (location,),
            ).fetchall()
        return [self._row_to_incident(r) for r in rows]

    # ── changes ─────────────────────────────────────────────────────────────

    def create_change(
        self,
        title: str,
        change_type: str = "normal",
        *,
        service: Optional[str] = None,
    ) -> ChangeRecord:
        ownership = resolve_ownership(service) if service else None
        ch = ChangeRecord(
            id=str(uuid.uuid4()),
            title=title,
            change_type=change_type,
            service=service,
            ownership=ownership,
        )
        with self._lock:
            self._conn.execute(
                "INSERT INTO changes (id, title, change_type, status, risk, created_at, "
                "service, location, service_id, tier3_ai, tier2_prime, ownership_resolved, "
                "ownership_ambiguous, unresolved_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    ch.id,
                    ch.title,
                    ch.change_type,
                    ch.status,
                    ch.risk,
                    ch.created_at,
                    ch.service,
                    ownership.location if ownership else None,
                    ownership.service_id if ownership else None,
                    ownership.tier3_ai if ownership else None,
                    ownership.tier2_prime if ownership else None,
                    int(bool(ownership and ownership.resolved)),
                    int(bool(ownership and ownership.location_is_ambiguous)),
                    ownership.unresolved_reason if ownership else None,
                ),
            )
            self._conn.commit()
        _emit("change.requested", self._change_event(ch))
        return ch

    def list_changes(self) -> list[ChangeRecord]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM changes ORDER BY created_at DESC").fetchall()
        return [self._row_to_change(r) for r in rows]

    # ── serialisation ───────────────────────────────────────────────────────

    @staticmethod
    def _incident_event(inc: ItsmIncident) -> dict[str, Any]:
        """The payload a consumer needs to act without calling back.

        Carries the owner so Problem Management and the CIR do not each have to
        re-resolve the service, and so a consumer reading only the event stream
        still knows who is accountable.
        """
        own = inc.ownership
        return {
            "incident_id": inc.id,
            "title": inc.title,
            "priority": inc.priority.value,
            "status": inc.status.value,
            "service": inc.service,
            "location": own.location if own else None,
            "tier3_ai": own.tier3_ai if own else None,
            "tier2_prime": own.tier2_prime if own else None,
            "ownership_resolved": bool(own and own.resolved),
        }

    @staticmethod
    def _change_event(ch: ChangeRecord) -> dict[str, Any]:
        own = ch.ownership
        return {
            "change_id": ch.id,
            "title": ch.title,
            "change_type": ch.change_type,
            "status": ch.status,
            "risk": ch.risk,
            "service": ch.service,
            "location": own.location if own else None,
            "ownership_resolved": bool(own and own.resolved),
        }

    @staticmethod
    def _ownership_from_row(row: sqlite3.Row) -> Optional[ServiceOwnership]:
        if row["service"] is None:
            return None
        return ServiceOwnership(
            service=row["service"],
            resolved=bool(row["ownership_resolved"]),
            location=row["location"],
            service_id=row["service_id"],
            tier3_ai=row["tier3_ai"],
            tier2_prime=row["tier2_prime"],
            location_is_ambiguous=bool(row["ownership_ambiguous"]),
            unresolved_reason=row["unresolved_reason"],
        )

    @classmethod
    def _row_to_incident(cls, row: sqlite3.Row) -> ItsmIncident:
        return ItsmIncident(
            id=row["id"],
            title=row["title"],
            description=row["description"],
            priority=IncidentPriority(row["priority"]),
            status=IncidentStatus(row["status"]),
            service=row["service"],
            assignee=row["assignee"],
            created_at=row["created_at"],
            resolved_at=row["resolved_at"],
            itil_practice=row["itil_practice"],
            ownership=cls._ownership_from_row(row),
        )

    @classmethod
    def _row_to_change(cls, row: sqlite3.Row) -> ChangeRecord:
        return ChangeRecord(
            id=row["id"],
            title=row["title"],
            change_type=row["change_type"],
            status=row["status"],
            risk=row["risk"],
            created_at=row["created_at"],
            service=row["service"],
            ownership=cls._ownership_from_row(row),
        )


_itsm: ItsmService | None = None


def get_itsm_service() -> ItsmService:
    global _itsm
    if _itsm is None:
        _itsm = ItsmService()
    return _itsm
