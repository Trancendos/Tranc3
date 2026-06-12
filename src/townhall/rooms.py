"""The Town Hall — BoardRoom, WarRoom, MeetingRooms session management."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class RoomKind(str, Enum):
    BOARD_ROOM = "board-room"
    WAR_ROOM = "war-room"
    MEETING_ROOM = "meeting-room"


@dataclass
class RoomSession:
    id: str
    room: RoomKind
    title: str
    chair: str | None = None
    attendees: list[str] = field(default_factory=list)
    agenda: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    ended_at: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def active(self) -> bool:
        return self.ended_at is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "room": self.room.value,
            "title": self.title,
            "chair": self.chair,
            "attendees": self.attendees,
            "agenda": self.agenda,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "active": self.active,
            "metadata": self.metadata,
        }


class RoomManager:
    def __init__(self) -> None:
        self._sessions: dict[str, RoomSession] = {}

    def open_session(
        self,
        room: RoomKind,
        title: str,
        *,
        chair: str | None = None,
        agenda: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RoomSession:
        session = RoomSession(
            id=str(uuid.uuid4()),
            room=room,
            title=title,
            chair=chair,
            agenda=agenda or [],
            metadata=metadata or {},
        )
        self._sessions[session.id] = session
        return session

    def end_session(self, session_id: str) -> RoomSession | None:
        session = self._sessions.get(session_id)
        if not session or session.ended_at is not None:
            return None
        session.ended_at = time.time()
        return session

    def list_sessions(
        self,
        room: RoomKind | None = None,
        *,
        active_only: bool = False,
    ) -> list[RoomSession]:
        out = list(self._sessions.values())
        if room is not None:
            out = [s for s in out if s.room == room]
        if active_only:
            out = [s for s in out if s.active]
        return sorted(out, key=lambda s: s.started_at, reverse=True)

    def get(self, session_id: str) -> RoomSession | None:
        return self._sessions.get(session_id)


_rooms: RoomManager | None = None


def get_room_manager() -> RoomManager:
    global _rooms
    if _rooms is None:
        _rooms = RoomManager()
    return _rooms
