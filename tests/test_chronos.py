# tests/test_chronos.py — Tests for src/chronos/scheduler.py
"""Comprehensive tests for the ChronosSphere scheduler."""

from __future__ import annotations

import time

from src.chronos.scheduler import (
    CalendarEvent,
    ChronosSphere,
    ScheduleStatus,
    ScheduleType,
    ScheduledTask,
)


# ── Enum tests ──────────────────────────────────────────────────────────────


class TestScheduleType:
    def test_values(self):
        assert ScheduleType.CRON == "cron"
        assert ScheduleType.INTERVAL == "interval"
        assert ScheduleType.ONCE == "once"
        assert ScheduleType.WORKFLOW == "workflow"


class TestScheduleStatus:
    def test_values(self):
        assert ScheduleStatus.ACTIVE == "active"
        assert ScheduleStatus.PAUSED == "paused"
        assert ScheduleStatus.EXPIRED == "expired"
        assert ScheduleStatus.FAILED == "failed"


# ── Data class tests ────────────────────────────────────────────────────────


class TestScheduledTask:
    def test_defaults(self):
        task = ScheduledTask()
        assert task.id != ""
        assert task.name == ""
        assert task.schedule_type == ScheduleType.ONCE
        assert task.cron_expression is None
        assert task.interval_seconds is None
        assert task.fire_at is None
        assert task.workflow_id is None
        assert task.status == ScheduleStatus.ACTIVE
        assert task.fire_count == 0
        assert task.last_fired is None
        assert task.metadata == {}

    def test_to_dict(self):
        task = ScheduledTask(
            name="test-task",
            schedule_type=ScheduleType.CRON,
            cron_expression="0 * * * *",
        )
        d = task.to_dict()
        assert d["name"] == "test-task"
        assert d["schedule_type"] == "cron"
        assert d["cron_expression"] == "0 * * * *"
        assert d["status"] == "active"


class TestCalendarEvent:
    def test_defaults(self):
        event = CalendarEvent()
        assert event.id != ""
        assert event.user_id == ""
        assert event.title == ""
        assert event.start_ts == 0.0
        assert event.end_ts == 0.0
        assert event.timezone == "UTC"
        assert event.location is None
        assert event.attendees == []
        assert event.metadata == {}

    def test_to_dict(self):
        event = CalendarEvent(
            user_id="user-1",
            title="Meeting",
            start_ts=1000.0,
            end_ts=2000.0,
        )
        d = event.to_dict()
        assert d["user_id"] == "user-1"
        assert d["title"] == "Meeting"
        assert d["start_ts"] == 1000.0
        assert d["end_ts"] == 2000.0


# ── ChronosSphere tests ────────────────────────────────────────────────────


class TestChronosSphere:
    def setup_method(self):
        self.chronos = ChronosSphere()

    # ── Scheduled tasks ─────────────────────────────────────────────────

    def test_create_cron_task(self):
        task = self.chronos.create_task(
            "hourly-cleanup",
            ScheduleType.CRON,
            cron_expression="0 * * * *",
        )
        assert task.name == "hourly-cleanup"
        assert task.schedule_type == ScheduleType.CRON
        assert task.cron_expression == "0 * * * *"
        assert task.status == ScheduleStatus.ACTIVE

    def test_create_interval_task(self):
        task = self.chronos.create_task(
            "health-check",
            ScheduleType.INTERVAL,
            interval_seconds=30.0,
        )
        assert task.schedule_type == ScheduleType.INTERVAL
        assert task.interval_seconds == 30.0

    def test_create_once_task(self):
        fire_at = time.time() + 3600
        task = self.chronos.create_task(
            "one-shot",
            ScheduleType.ONCE,
            fire_at=fire_at,
        )
        assert task.schedule_type == ScheduleType.ONCE
        assert task.fire_at == fire_at

    def test_create_workflow_task(self):
        task = self.chronos.create_task(
            "trigger-pipeline",
            ScheduleType.WORKFLOW,
            workflow_id="wf-123",
        )
        assert task.schedule_type == ScheduleType.WORKFLOW
        assert task.workflow_id == "wf-123"

    def test_get_task(self):
        task = self.chronos.create_task("test", ScheduleType.ONCE)
        retrieved = self.chronos.get_task(task.id)
        assert retrieved is task

    def test_get_task_not_found(self):
        assert self.chronos.get_task("nonexistent") is None

    def test_list_tasks(self):
        self.chronos.create_task("task1", ScheduleType.ONCE)
        self.chronos.create_task("task2", ScheduleType.CRON, cron_expression="* * * * *")
        tasks = self.chronos.list_tasks()
        assert len(tasks) == 2

    def test_list_tasks_by_status(self):
        t1 = self.chronos.create_task("active", ScheduleType.ONCE)
        t2 = self.chronos.create_task("paused", ScheduleType.ONCE)
        self.chronos.pause_task(t2.id)
        active = self.chronos.list_tasks(status=ScheduleStatus.ACTIVE)
        assert len(active) == 1
        assert active[0].id == t1.id

    def test_pause_task(self):
        task = self.chronos.create_task("test", ScheduleType.ONCE)
        assert self.chronos.pause_task(task.id)
        assert task.status == ScheduleStatus.PAUSED

    def test_pause_nonexistent_task(self):
        assert not self.chronos.pause_task("nonexistent")

    def test_resume_task(self):
        task = self.chronos.create_task("test", ScheduleType.ONCE)
        self.chronos.pause_task(task.id)
        assert self.chronos.resume_task(task.id)
        assert task.status == ScheduleStatus.ACTIVE

    def test_resume_nonexistent_task(self):
        assert not self.chronos.resume_task("nonexistent")

    def test_delete_task(self):
        task = self.chronos.create_task("test", ScheduleType.ONCE)
        assert self.chronos.delete_task(task.id)
        assert self.chronos.get_task(task.id) is None

    def test_delete_nonexistent_task(self):
        assert not self.chronos.delete_task("nonexistent")

    # ── Calendar events ─────────────────────────────────────────────────

    def test_create_event(self):
        event = self.chronos.create_event(
            user_id="user-1",
            title="Team Sync",
            start_ts=1000.0,
            end_ts=2000.0,
        )
        assert event.user_id == "user-1"
        assert event.title == "Team Sync"
        assert event.start_ts == 1000.0
        assert event.end_ts == 2000.0

    def test_create_event_with_kwargs(self):
        event = self.chronos.create_event(
            user_id="user-1",
            title="Team Sync",
            start_ts=1000.0,
            end_ts=2000.0,
            description="Weekly sync",
            location="Zoom",
            attendees=["alice", "bob"],
        )
        assert event.description == "Weekly sync"
        assert event.location == "Zoom"
        assert event.attendees == ["alice", "bob"]

    def test_get_event(self):
        event = self.chronos.create_event("u1", "E1", 1000.0, 2000.0)
        retrieved = self.chronos.get_event(event.id)
        assert retrieved is event

    def test_get_event_not_found(self):
        assert self.chronos.get_event("nonexistent") is None

    def test_list_events_by_user(self):
        self.chronos.create_event("u1", "E1", 1000.0, 2000.0)
        self.chronos.create_event("u2", "E2", 3000.0, 4000.0)
        self.chronos.create_event("u1", "E3", 5000.0, 6000.0)
        u1_events = self.chronos.list_events("u1")
        assert len(u1_events) == 2

    def test_list_events_with_time_filter(self):
        self.chronos.create_event("u1", "E1", 1000.0, 2000.0)
        self.chronos.create_event("u1", "E2", 3000.0, 4000.0)
        self.chronos.create_event("u1", "E3", 5000.0, 6000.0)
        # from_ts=1500 should include events where end_ts >= 1500
        filtered = self.chronos.list_events("u1", from_ts=1500.0, to_ts=5500.0)
        assert len(filtered) >= 2

    def test_delete_event(self):
        event = self.chronos.create_event("u1", "E1", 1000.0, 2000.0)
        assert self.chronos.delete_event(event.id)
        assert self.chronos.get_event(event.id) is None

    def test_delete_nonexistent_event(self):
        assert not self.chronos.delete_event("nonexistent")

    # ── Stats ───────────────────────────────────────────────────────────

    def test_stats_empty(self):
        stats = self.chronos.stats()
        assert stats["total_tasks"] == 0
        assert stats["active_tasks"] == 0
        assert stats["total_events"] == 0
        assert stats["service"] == "chronossphere"

    def test_stats_populated(self):
        self.chronos.create_task("t1", ScheduleType.ONCE)
        self.chronos.create_event("u1", "E1", 1000.0, 2000.0)
        stats = self.chronos.stats()
        assert stats["total_tasks"] == 1
        assert stats["active_tasks"] == 1
        assert stats["total_events"] == 1
