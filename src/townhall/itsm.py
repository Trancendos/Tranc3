"""The Town Hall — ITSM / ITIL incident and change records."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


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
        }


@dataclass
class ChangeRecord:
    id: str
    title: str
    change_type: str  # standard | normal | emergency
    status: str = "draft"
    risk: str = "low"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "change_type": self.change_type,
            "status": self.status,
            "risk": self.risk,
            "created_at": self.created_at,
        }


class ItsmService:
    def __init__(self) -> None:
        self._incidents: dict[str, ItsmIncident] = {}
        self._changes: dict[str, ChangeRecord] = {}

    def create_incident(
        self,
        title: str,
        description: str,
        *,
        priority: IncidentPriority = IncidentPriority.P3,
        service: str = "tranc3-backend",
    ) -> ItsmIncident:
        inc = ItsmIncident(
            id=str(uuid.uuid4()),
            title=title,
            description=description,
            priority=priority,
            service=service,
        )
        self._incidents[inc.id] = inc
        return inc

    def update_incident_status(
        self, incident_id: str, status: IncidentStatus
    ) -> ItsmIncident | None:
        inc = self._incidents.get(incident_id)
        if not inc:
            return None
        inc.status = status
        if status in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED):
            inc.resolved_at = time.time()
        return inc

    def list_incidents(self, *, open_only: bool = False) -> list[ItsmIncident]:
        items = list(self._incidents.values())
        if open_only:
            items = [
                i for i in items if i.status not in (IncidentStatus.RESOLVED, IncidentStatus.CLOSED)
            ]
        return sorted(items, key=lambda i: i.created_at, reverse=True)

    def create_change(self, title: str, change_type: str = "normal") -> ChangeRecord:
        ch = ChangeRecord(id=str(uuid.uuid4()), title=title, change_type=change_type)
        self._changes[ch.id] = ch
        return ch

    def list_changes(self) -> list[ChangeRecord]:
        return sorted(self._changes.values(), key=lambda c: c.created_at, reverse=True)


_itsm: ItsmService | None = None


def get_itsm_service() -> ItsmService:
    global _itsm
    if _itsm is None:
        _itsm = ItsmService()
    return _itsm
