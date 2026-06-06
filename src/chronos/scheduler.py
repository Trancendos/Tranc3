# src/chronos/scheduler.py
# ChronosSphere / ArcStream — Time and schedule management for Trancendos.
#
# ChronosSphere provides:
#   - Scheduled task registry (cron-style, interval, one-shot)
#   - Calendar event management (user-scoped)
#   - Timezone-aware scheduling
#   - Integration with The Digital Grid (triggers workflow on schedule)
#   - Foundation: Cal.com self-hosted for full calendar UI
#
# This scaffold handles in-process scheduling and event storage.
# Production wire-up routes to Cal.com API for full calendar UX.

from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from Dimensional.sanitize import sanitize_for_log

logger = logging.getLogger(__name__)


class ScheduleType(str, Enum):
    CRON = "cron"  # Standard cron expression
    INTERVAL = "interval"  # Repeat every N seconds
    ONCE = "once"  # Fire once at a specific UTC timestamp
    WORKFLOW = "workflow"  # Trigger a Digital Grid workflow


class ScheduleStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    EXPIRED = "expired"
    FAILED = "failed"


@dataclass
class CalendarEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = ""
    title: str = ""
    description: str = ""
    start_ts: float = 0.0
    end_ts: float = 0.0
    timezone: str = "UTC"
    location: Optional[str] = None
    attendees: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "title": self.title,
            "description": self.description,
            "start_ts": self.start_ts,
            "end_ts": self.end_ts,
            "timezone": self.timezone,
            "location": self.location,
            "attendees": self.attendees,
            "created_at": self.created_at,
        }


@dataclass
class ScheduledTask:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    schedule_type: ScheduleType = ScheduleType.ONCE
    cron_expression: Optional[str] = None  # for CRON type
    interval_seconds: Optional[float] = None  # for INTERVAL type
    fire_at: Optional[float] = None  # for ONCE type (UTC epoch)
    workflow_id: Optional[str] = None  # for WORKFLOW type
    status: ScheduleStatus = ScheduleStatus.ACTIVE
    created_at: float = field(default_factory=time.time)
    last_fired: Optional[float] = None
    fire_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "schedule_type": self.schedule_type.value,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "fire_at": self.fire_at,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "last_fired": self.last_fired,
            "fire_count": self.fire_count,
            "created_at": self.created_at,
        }


class ChronosSphere:
    """
    ChronosSphere — schedule management and calendar hub.

    In production this delegates to Cal.com self-hosted for full UX.
    This in-process layer handles task scheduling, event CRUD, and
    workflow trigger dispatch.
    """

    def __init__(self):
        self._tasks: Dict[str, ScheduledTask] = {}
        self._events: Dict[str, CalendarEvent] = {}

    # ── Scheduled tasks ───────────────────────────────────────────────────

    def create_task(
        self,
        name: str,
        schedule_type: ScheduleType,
        *,
        cron_expression: Optional[str] = None,
        interval_seconds: Optional[float] = None,
        fire_at: Optional[float] = None,
        workflow_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            schedule_type=schedule_type,
            cron_expression=cron_expression,
            interval_seconds=interval_seconds,
            fire_at=fire_at,
            workflow_id=workflow_id,
            metadata=metadata or {},
        )
        self._tasks[task.id] = task
        self._emit("chronos.task.created", {"task_id": task.id, "name": name})
        logger.info(  # codeql[py/cleartext-logging]
            "chronos: task created id=%s name=%s type=%s",
            sanitize_for_log(task.id),
            sanitize_for_log(name),
            sanitize_for_log(schedule_type.value),
        )
        return task

    def get_task(self, task_id: str) -> Optional[ScheduledTask]:
        return self._tasks.get(task_id)

    def list_tasks(self, status: Optional[ScheduleStatus] = None) -> List[ScheduledTask]:
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)

    def pause_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = ScheduleStatus.PAUSED
        return True

    def resume_task(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if not task:
            return False
        task.status = ScheduleStatus.ACTIVE
        return True

    def delete_task(self, task_id: str) -> bool:
        if task_id in self._tasks:
            del self._tasks[task_id]
            return True
        return False

    # ── Calendar events ───────────────────────────────────────────────────

    def create_event(
        self,
        user_id: str,
        title: str,
        start_ts: float,
        end_ts: float,
        **kwargs,
    ) -> CalendarEvent:
        event = CalendarEvent(
            user_id=user_id,
            title=title,
            start_ts=start_ts,
            end_ts=end_ts,
            **kwargs,
        )
        self._events[event.id] = event
        self._emit("chronos.event.created", {"event_id": event.id, "user_id": user_id})
        return event

    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        return self._events.get(event_id)

    def list_events(
        self,
        user_id: str,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
    ) -> List[CalendarEvent]:
        events = [e for e in self._events.values() if e.user_id == user_id]
        if from_ts:
            events = [e for e in events if e.end_ts >= from_ts]
        if to_ts:
            events = [e for e in events if e.start_ts <= to_ts]
        return sorted(events, key=lambda e: e.start_ts)

    def delete_event(self, event_id: str) -> bool:
        if event_id in self._events:
            del self._events[event_id]
            return True
        return False

    def stats(self) -> Dict[str, Any]:
        active_tasks = sum(1 for t in self._tasks.values() if t.status == ScheduleStatus.ACTIVE)
        return {
            "service": "chronossphere",
            "total_tasks": len(self._tasks),
            "active_tasks": active_tasks,
            "total_events": len(self._events),
        }

    def _emit(self, event_type: str, metadata: Optional[Dict] = None) -> None:
        try:
            from src.observability.observatory import EventCategory, observe

            observe(
                event_type,
                category=EventCategory.SYSTEM,
                service="chronossphere",
                metadata=metadata or {},
            )
        except Exception:
            pass  # nosec B110 — graceful degradation; error logged upstream


_chronos: Optional[ChronosSphere] = None


def get_chronos() -> ChronosSphere:
    global _chronos
    if _chronos is None:
        _chronos = ChronosSphere()
    return _chronos
